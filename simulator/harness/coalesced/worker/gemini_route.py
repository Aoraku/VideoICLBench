"""Deliver Gemini SSE heartbeats and release model decisions after upstream completion."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import socket
import threading
import time
import json
import base64
import hashlib
import os
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from contextlib import nullcontext
if __package__:
    from .gemini_gate import primary_admission, record_result
else:
    from gemini_gate import primary_admission, record_result


def configured_routes():
    from aihubmix_provider import https_origin
    return [('primary', https_origin('VIC_GEMINI_PRIMARY')),
            ('fallback', https_origin('VIC_GEMINI_FALLBACK'))]



def request_images(body):
    """Audit exactly the image parts forwarded in the Gemini request; retain no payload."""
    images=[]
    for turn, content in enumerate(body.get('contents', [])):
        if not isinstance(content,dict):
            continue
        for index, part in enumerate(content.get('parts', [])):
            if not isinstance(part,dict):
                continue
            blob=part.get('inlineData') or part.get('inline_data')
            if not isinstance(blob,dict):
                continue
            mime=blob.get('mimeType',blob.get('mime_type',''))
            if not isinstance(mime,str) or not mime.startswith('image/'):
                continue
            record={'turn':turn,'part':index,'mime':mime}
            try:
                raw=base64.b64decode(blob['data'],validate=True)
                record.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            except (TypeError,ValueError,KeyError):
                record['malformed_base64']=True
            images.append(record)
    return images


def exhausted(status, data):
    if status not in (400, 402, 403, 429):
        return False
    try:
        value = json.loads(data)
    except ValueError:
        return False
    error = value.get('error') if isinstance(value, dict) else None
    if not isinstance(error, dict):
        return False
    codes = {str(error.get(k, '')).lower() for k in ('code', 'type', 'reason')}
    for detail in error.get('details') or []:
        if isinstance(detail, dict):
            codes.add(str(detail.get('reason', '')).lower())
    if codes & {'insufficient_quota', 'insufficient_balance', 'budget_exhausted',
                'balance_exhausted', 'insufficient_funds', 'credit_balance_too_low'}:
        return True
    message = str(error.get('message', '')).lower()
    return any(s in message for s in (
        'insufficient account balance', 'insufficient balance', 'insufficient funds',
        'account balance depleted', 'budget exhausted', 'credit balance is too low',
        '余额不足', '账户余额已用尽', '额度已用尽', '额度耗尽'))


def cache_evidence(usage):
    """Retain contradictory wire counters; count converted cache only after parity."""
    native = {key: usage.get(key) for key in (
        'promptTokenCount', 'candidatesTokenCount', 'thoughtsTokenCount',
        'totalTokenCount', 'cachedContentTokenCount')}
    result = {'native': native}
    bill = usage.get('billing_usage') or {}
    if not isinstance(bill, dict):
        return result
    upstream = bill.get('openai_usage') or {}
    if bill.get('source') != 'oai_chat' or not isinstance(upstream, dict):
        return result
    details = upstream.get('prompt_tokens_details') or {}
    count = details.get('cached_tokens') if isinstance(details, dict) else None
    mapped = {'input_tokens': upstream.get('prompt_tokens'),
              'output_tokens': upstream.get('completion_tokens'),
              'total_tokens': upstream.get('total_tokens'), 'cached_input_tokens': count}
    result['converted_provider'] = mapped
    integer = lambda n: type(n) is int and n >= 0
    valid = all(integer(v) for v in mapped.values()) and all(integer(native[k]) for k in (
        'promptTokenCount', 'candidatesTokenCount', 'thoughtsTokenCount', 'totalTokenCount'))
    compatible = bool(valid and mapped['input_tokens'] == native['promptTokenCount'] and
                      mapped['output_tokens'] == native['candidatesTokenCount'] + native['thoughtsTokenCount'] and
                      mapped['total_tokens'] == native['totalTokenCount'] == mapped['input_tokens'] + mapped['output_tokens'] and
                      count <= mapped['input_tokens'])
    result['converted_counts_compatible'] = compatible
    result['provider_reported_cache_for_accounting'] = count if compatible else None
    result['provider_cache_source'] = ('billing_usage.openai_usage.prompt_tokens_details.cached_tokens'
                                       if compatible else None)
    result['cache_fields_disagree'] = (native['cachedContentTokenCount'] != count
                                       if integer(native['cachedContentTokenCount']) and integer(count) else None)
    return result


def completed(path, data, rec):
    try:
        if any(line.startswith(b'data:') for line in data.splitlines()):
            events = [json.loads(line[5:].strip()) for line in data.splitlines()
                      if line.startswith(b'data:') and line[5:].strip() != b'[DONE]']
        else:
            value = json.loads(data)
            events = value if isinstance(value, list) else [value]
    except (TypeError, ValueError):
        return False
    if not events or any(not isinstance(e, dict) or e.get('error') for e in events):
        return False
    if urlsplit(path).path.endswith(':countTokens'):
        total = events[-1].get('totalTokens')
        return type(total) is int and total >= 0
    finished = False
    # Keep protocol shape, never model text or image contents. This distinguishes
    # a completed provider stream from a CLI-invalid empty candidate/tool frame.
    rec['response_shape'] = []
    for event in events:
        if isinstance(event.get('usageMetadata'), dict):
            rec['usage'] = event['usageMetadata']
            rec['cache_evidence'] = cache_evidence(rec['usage'])
        if isinstance(event.get('modelVersion'), str):
            rec['returned_model'] = event['modelVersion']
        candidates = event.get('candidates', [])
        if not isinstance(candidates, list):
            return False
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get('content') or {}
            parts = content.get('parts') or [] if isinstance(content, dict) else []
            rec['response_shape'].append({
                'finish': candidate.get('finishReason'),
                'parts': [{'keys': sorted(part),
                           'empty_text': part.get('text') == '',
                           'thought': bool(part.get('thought'))}
                          for part in parts if isinstance(part, dict)]})
        finished |= any(isinstance(c, dict) and c.get('finishReason') not in
                        (None, '', 'FINISH_REASON_UNSPECIFIED') for c in candidates)
        # Safety filtering is a complete native response, without a decision.
        finished |= bool((event.get('promptFeedback') or {}).get('blockReason'))
    return finished


def query(curl, ca, path, body, keys, out, rec, *, client_alive=lambda: True):
    marker = out / 'primary-quota-exhausted.json'
    routes = configured_routes()
    if marker.exists():
        routes = routes[1:]
    rec['provider_attempts'] = []
    with tempfile.NamedTemporaryFile() as f, tempfile.NamedTemporaryFile() as headers:
        f.write(body)
        f.flush()
        for name, base in routes:
            if not client_alive():
                rec['failure_class']='downstream_disconnected'
                return 499,b'',1
            key = keys[name]
            cfg = ['url = ' + json.dumps(base + path), 'header = "Content-Type: application/json"',
                   'header = ' + json.dumps('x-goog-api-key: ' + key),
                   'header = ' + json.dumps('Authorization: Bearer ' + key),
                   'dump-header = ' + json.dumps(headers.name), 'connect-timeout = 15', 'data-binary = ' + json.dumps('@' + f.name),
                   'write-out = "\\nVIC_TIMING\\t%{http_code}\\t%{time_namelookup}\\t%{time_connect}\\t%{time_appconnect}\\t%{time_pretransfer}\\t%{time_starttransfer}\\t%{time_total}\\t%{size_upload}\\t%{speed_upload}\\t%{size_download}"']
            if name == 'primary':
                cfg += ['noproxy = "*"']
            elif ca:
                cfg += ['proxy-cacert = ' + json.dumps(ca)]
            with primary_admission(out, rec) if name == 'primary' and not path.split('?',1)[0].endswith(':countTokens') else nullcontext(None) as gate_config:
                if not client_alive():
                    rec['failure_class']='downstream_disconnected_while_queued'
                    return 499,b'',1
                headers.seek(0); headers.truncate()
                r = subprocess.run([curl, '-q', '--silent', '--config', '-'],
                                   input=('\n'.join(cfg) + '\n').encode(), capture_output=True)
            data, _, http = r.stdout.rpartition(b'\n')
            timing = None
            if http.startswith(b'VIC_TIMING\t'):
                fields = http.split(b'\t')[1:]
                http = fields[0]
                names = ('dns_seconds', 'connect_seconds', 'tls_seconds',
                         'pretransfer_seconds', 'first_byte_seconds', 'total_seconds',
                         'upload_bytes', 'upload_bytes_per_second', 'download_bytes')
                try:
                    timing = dict(zip(names, map(float, fields[1:])))
                except ValueError:
                    timing = {'parse_error': True}
            status = int(http) if http.isdigit() and int(http) else 502
            quota = r.returncode == 0 and exhausted(status, data)
            rec['provider'] = name
            rec['provider_attempts'].append(dict(provider=name, http=status, quota=quota, curl_exit=r.returncode))
            if timing is not None:
                rec['provider_attempts'][-1]['timing'] = timing
            if status >= 400:
                headers.seek(0)
                rec['provider_attempts'][-1].update(error_evidence(data, headers.read(), keys.values()))
            valid_response = r.returncode == 0 and (not 200 <= status < 300 or completed(path, data, rec))
            if name == 'primary':
                try:
                    rec['primary_adaptive_update'] = record_result(gate_config, status, rec['provider_attempts'][-1], completed=valid_response and status==200, count_only=rec.get('count_only',False))
                except Exception as exc:
                    # Adaptive bookkeeping cannot withhold an already-completed
                    # upstream body. Admission itself remains fail-closed.
                    rec['primary_adaptive_update'] = {'state':'deferred','reason':type(exc).__name__}
            if not valid_response:
                rec['failure_class'] = 'incomplete_upstream_response'
                return 502, b'{"error":{"code":502,"message":"Incomplete upstream response"}}', r.returncode or 65
            if name == 'primary' and quota:
                with tempfile.NamedTemporaryFile('w', dir=out, delete=False) as temp:
                    json.dump({'http': status, 'request_id': rec['id']}, temp)
                os.replace(temp.name, marker)
                continue
            return status, data, 0


def response_shapes(events):
    shapes = []
    for event in events:
        candidates = event.get('candidates', [])
        if not isinstance(candidates, list):
            raise ValueError('invalid candidates')
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError('invalid candidate')
            content = candidate.get('content') or {}
            if not isinstance(content, dict) or not isinstance(content.get('parts', []), list):
                raise ValueError('invalid candidate content')
            parts = content.get('parts', [])
            if any(not isinstance(part, dict) for part in parts):
                raise ValueError('invalid candidate part')
            shapes.append({'finish': candidate.get('finishReason'),
                           'parts': [{'keys': sorted(part), 'empty_text': part.get('text') == '',
                                      'thought': bool(part.get('thought'))} for part in parts]})
    return shapes


def decision_frames(payload, receipt=None):
    """Normalize a validated response into frames the pinned Google client accepts."""
    data=payload.lstrip()
    if data.startswith((b'{',b'[')):
        value=json.loads(data)
        events=value if isinstance(value,list) else [value]
    else:
        data=data.replace(b'\r\n',b'\n')
        if not data.endswith(b'\n\n'):
            raise ValueError('truncated SSE frame')
        events=[]
        for frame in data.split(b'\n\n'):
            parts=[]
            for line in frame.splitlines():
                if line.startswith(b'data:'):
                    parts.append(line[5:].strip())
                elif line and not line.startswith((b':',b'event:',b'id:',b'retry:')):
                    raise ValueError('malformed SSE field')
            if parts and parts!=[b'[DONE]']:
                events.append(json.loads(b'\n'.join(parts)))
    if not events or any(not isinstance(e,dict) or e.get('error') for e in events):
        raise ValueError('invalid Gemini response')
    raw_shape = response_shapes(events)
    removed = 0
    decision = False
    for event in events:
        for candidate in event.get('candidates', []):
            content = candidate.get('content') or {}
            parts = content.get('parts') or []
            # Native 0.32.1 rejects the whole candidate when a pure empty-text
            # placeholder accompanies a real tool call. Remove only that exact
            # placeholder, preserving signatures, calls and their order.
            if any(isinstance(part, dict) and part.get('functionCall') for part in parts):
                kept = [part for part in parts if part != {'text': ''}]
                removed += len(parts) - len(kept)
                content['parts'] = kept
                parts = kept
            decision |= any(isinstance(part, dict) and (part.get('functionCall') or
                            (isinstance(part.get('text'), str) and part['text'].strip() and not part.get('thought')))
                            for part in parts)
    if receipt is not None:
        receipt.update(raw_response_shape=raw_shape, normalized_response_shape=response_shapes(events),
                       empty_tool_text_placeholders_removed=removed, model_decision_present=bool(decision))
    return b''.join(b'data: '+json.dumps(e,ensure_ascii=False,separators=(',',':')).encode()+b'\n\n' for e in events)


def relay_stream(handler, request, receipt, *, heartbeat=5.0):
    """request(client_alive) preserves the original quota routing and naturally drains."""
    handler.protocol_version='HTTP/1.1'
    handler.close_connection=True
    live=threading.Event()
    live.set()
    opened=False
    started=time.monotonic()
    receipt.update(heartbeat_count=0,upstream_completed=False,downstream_complete_write=False)

    def chunk(data):
        handler.wfile.write(('%x\r\n'%len(data)).encode()+data+b'\r\n')
        handler.wfile.flush()

    def open_stream():
        nonlocal opened
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream; charset=utf-8')
        handler.send_header('Cache-Control','no-cache, no-transform')
        handler.send_header('Transfer-Encoding','chunked')
        handler.send_header('Connection','close')
        handler.end_headers()
        opened=True
        receipt['first_headers_seconds']=round(time.monotonic()-started,3)

    def peer_left():
        try:
            return handler.connection.recv(1,socket.MSG_PEEK|socket.MSG_DONTWAIT)==b''
        except BlockingIOError:
            return False
        except OSError:
            return True

    with ThreadPoolExecutor(max_workers=1) as executor:
        work=executor.submit(request,lambda: live.is_set() and not peer_left())
        delay=min(.15,heartbeat)
        while True:
            try:
                status,payload,rc=work.result(timeout=delay)
                break
            except FutureTimeout:
                if work.done():
                    status,payload,rc=work.result()
                    break
                delay=heartbeat
                if not live.is_set():continue
                try:
                    if peer_left():raise ConnectionResetError
                    if not opened:open_stream()
                    chunk(b': keep-alive\n\n')
                    receipt['heartbeat_count']+=1
                except OSError:
                    live.clear()
    complete=rc==0 and status==200
    receipt['upstream_http'] = status
    receipt['provider_completed'] = complete
    decision=None
    if complete:
        try:
            decision=decision_frames(payload,receipt)
            if not receipt['model_decision_present']:
                status=502
                receipt['local_synthesized_http']=502
                receipt['failure_class']='empty_model_response'
                complete=False
        except (TypeError,ValueError):
            status=502
            receipt['local_synthesized_http']=502
            receipt['failure_class']='invalid_or_truncated_sse'
            complete=False
    receipt['upstream_completed']=complete
    if not live.is_set() or peer_left():
        receipt['failure_class']='downstream_disconnected'
        return status,False
    try:
        if complete:
            if not opened:open_stream()
            chunk(decision)
            handler.wfile.write(b'0\r\n\r\n')
            handler.wfile.flush()
            receipt['downstream_complete_write']=True
            return status,True
        code=status if 400<=status<600 else 502
        if not opened:
            handler.send_error(code,'Upstream generation failed')
        else:
            # The pinned SDK recognizes a raw status object. Deliberately omit
            # the HTTP terminator so coalescing can never turn failure into EOF success.
            chunk(json.dumps(native_error(code, receipt)).encode())
        return status,False
    except OSError:
        receipt['failure_class']='downstream_disconnected'
        return status,False


def error_evidence(data, headers, secrets=()):
    """Small diagnostic whitelist; never persist raw response headers or credentials."""
    def clean(value):
        text = str(value)
        for secret in secrets:
            if secret: text = text.replace(secret, '[redacted]')
        text = re.sub(r'(?i)(?:sk-|hf_)[A-Za-z0-9_-]+|Bearer\s+[^\s\"\']+', '[redacted]', text)
        return text[:512]
    result = {'error_body_bytes': len(data)}
    try:
        value = json.loads(data)
        error = value.get('error') if isinstance(value, dict) else None
        if isinstance(error, dict):
            result['upstream_error'] = {key: clean(error[key]) for key in ('code', 'type', 'status', 'reason', 'message') if key in error and isinstance(error[key], (str, int))}
    except (ValueError, TypeError):
        result['error_body_json'] = False
    retry = re.findall(rb'(?im)^retry-after:[ \t]*([^\r\n]+)', headers)
    if retry: result['retry_after'] = clean(retry[-1].decode(errors='replace'))[:128]
    return result


def native_error(http_status, receipt):
    """Forward safe provider errors through heartbeat SSE without inventing retries."""
    attempts = receipt.get('provider_attempts') or []
    last = attempts[-1] if attempts else {}
    upstream = last.get('upstream_error') or {}
    error = {'code': http_status, 'status': 'UPSTREAM_ERROR',
             'message': upstream.get('message') or 'Incomplete upstream generation'}
    status = upstream.get('status')
    if isinstance(status, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', status):
        error['status'] = status
    # Preserve non-numeric provider codes as structured diagnostic evidence,
    # while the Google native API error retains its required HTTP integer code.
    diagnostics = {k: upstream[k] for k in ('code', 'type', 'reason') if k in upstream}
    if diagnostics: error['providerError'] = diagnostics
    retry = last.get('retry_after', '')
    if isinstance(retry, str) and re.fullmatch(r'[0-9]{1,8}', retry):
        error['details'] = [{'@type': 'type.googleapis.com/google.rpc.RetryInfo',
                             'retryDelay': retry + 's'}]
    return {'error': error}
