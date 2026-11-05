"""Private loopback HTTP to verified-HTTPS transport, without request changes.

Native CLI inference, tools, history, and retry policy remain native. This
adapter forwards each received request exactly once and never logs credentials
or model content. Response bytes, including SSE/gzip, are forwarded unchanged.
"""
import argparse
import codecs
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import os
import re
from pathlib import Path
import signal
import ssl
import threading
import time
from urllib.parse import urlsplit
import uuid
import zlib

from .api_timing import append_timing_event
from .api_concurrency import FileConcurrencyGate
from .episode_api_admission import register_api_request_start, EpisodeApiClosed

import httpx

HOP_HEADERS = {'connection','keep-alive','proxy-authenticate','proxy-authorization',
               'te','trailer','transfer-encoding','upgrade','host'}


def safe_request_metadata(body, headers):
    """Opt-in hashes/counts only. Never modify the forwarded body or headers.

    This observes the native client's existing cache identity; it does not add a
    cache key or assert a cache hit. No prompt, URL, image or credential is logged.
    """
    digest = lambda value: hashlib.sha256(value).hexdigest()
    result = {'schema': 'native-request-metadata-v1', 'body_sha256': digest(body),
              'body_bytes': len(body), 'parse_valid': False}
    lowered = {str(k).lower(): v for k, v in headers.items()}
    result['cache_header_sha256'] = {
        k: digest(lowered[k].encode()) for k in ('session-id', 'session_id')
        if isinstance(lowered.get(k), str)}
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        return result
    if not isinstance(value, dict): return result
    result['parse_valid'] = True
    key = value.get('prompt_cache_key')
    result['prompt_cache_key_present'] = isinstance(key, str)
    result['prompt_cache_key_sha256'] = digest(key.encode()) if isinstance(key, str) else None
    instructions = value.get('instructions')
    result['instructions_utf8_bytes'] = len(instructions.encode()) if isinstance(instructions, str) else None
    result['instructions_sha256'] = digest(instructions.encode()) if isinstance(instructions, str) else None
    tools = value.get('tools')
    result['tool_count'] = len(tools) if isinstance(tools, list) else None
    result['tools_sha256'] = digest(json.dumps(tools, sort_keys=True, separators=(',', ':')).encode()) if isinstance(tools, list) else None
    inputs = value.get('input')
    result['input_is_string'] = isinstance(inputs, str)
    result['input_string_utf8_bytes'] = len(inputs.encode()) if isinstance(inputs, str) else None
    result['input_count'] = len(inputs) if isinstance(inputs, list) else None
    result['stream'] = value.get('stream') if type(value.get('stream')) is bool else None
    result['max_output_tokens'] = value.get('max_output_tokens') if type(value.get('max_output_tokens')) is int else None
    result['items'] = []
    result['image_count'] = 0
    result['text_utf8_bytes'] = 0
    result['item_metadata_truncated'] = isinstance(inputs, list) and len(inputs) > 4096
    if not isinstance(inputs, list): return result
    roles = {'system', 'developer', 'user', 'assistant', 'tool'}
    types = {'message', 'function_call', 'function_call_output', 'reasoning', 'compaction',
             'custom_tool_call', 'custom_tool_call_output'}
    for index, item in enumerate(inputs[:4096]):
        if not isinstance(item, dict):
            result['items'].append({'index': index, 'type': 'non_object'}); continue
        row = {'index': index, 'type': item.get('type') if isinstance(item.get('type'), str) and item['type'] in types else 'other',
               'role': item.get('role') if isinstance(item.get('role'), str) and item['role'] in roles else None,
               'sha256': digest(json.dumps(item, sort_keys=True, separators=(',', ':')).encode()),
               'text_utf8_bytes': [], 'image_count': 0}
        if isinstance(item.get('arguments'), str): row['arguments_utf8_bytes'] = len(item['arguments'].encode())
        content = item.get('content')
        if isinstance(content, str): row['text_utf8_bytes'].append(len(content.encode()))
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict): continue
                if block.get('type') in ('input_text', 'output_text', 'text') and isinstance(block.get('text'), str):
                    row['text_utf8_bytes'].append(len(block['text'].encode()))
                if block.get('type') == 'input_image': row['image_count'] += 1
        # Tool outputs may use Responses' typed output blocks, not content.
        output = item.get('output')
        if isinstance(output, str): row['text_utf8_bytes'].append(len(output.encode()))
        elif isinstance(output, list):
            for block in output:
                if not isinstance(block, dict): continue
                if block.get('type') in ('input_text', 'output_text', 'text') and isinstance(block.get('text'), str):
                    row['text_utf8_bytes'].append(len(block['text'].encode()))
                if block.get('type') == 'input_image': row['image_count'] += 1
        result['image_count'] += row['image_count']
        result['text_utf8_bytes'] += sum(row['text_utf8_bytes'])
        result['items'].append(row)
    return result




def safe_error_token(value):
    if type(value) is int:value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}',value):return None
    if value.lower().startswith(('sk-','sk_','bearer','rbp1.')):return None
    return value


def safe_response_headers(headers):
    result={}
    for header,field in (('request-id','response_request_id'),('x-request-id','response_x_request_id')):
        value=safe_error_token(headers.get(header))
        if value is not None:result[field]=value
    value=headers.get('retry-after')
    if isinstance(value,str) and value.isascii() and len(value)<=96 and '\r' not in value and '\n' not in value:
        valid=bool(re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,3})?',value))
        if not valid:
            try:valid=parsedate_to_datetime(value) is not None
            except (TypeError,ValueError,OverflowError):pass
        if valid:result['response_retry_after']=value
    return result


class ResponseOutcomeObserver:
    """Bounded side-channel inspection; forwarded bytes are never changed."""
    def __init__(self,status,content_type,encoding='',route='/v1/responses',*,usage_metadata=False):
        self.status=status;self.route=route;self.failed=None;self.completed=False;self.invalid=False
        self.incomplete_reason=None;self.unclassified_incomplete=False
        self.error_code=None;self.error_type=None
        self.first_sse_event_monotonic=None
        self.first_output_delta_monotonic=None
        self.usage_metadata=usage_metadata
        self.provider_usage_records=[]
        self.provider_usage_duplicate_events=0
        self.provider_usage_conflict=False
        self.sse='text/event-stream' in content_type.lower();self.json='json' in content_type.lower()
        self.buffer='';self.data=[];self.event_name='';self.decoder=codecs.getincrementaldecoder('utf-8')()
        self.unzip=None
        if encoding.lower() in ('gzip','x-gzip'):self.unzip=zlib.decompressobj(16+zlib.MAX_WBITS)
        elif encoding.lower() not in ('','identity'):self.invalid=True

    def _event(self):
        if self.event_name in ('error','response.failed'):self.failed='sse_'+self.event_name
        data='\n'.join(self.data);self.data=[];self.event_name=''
        if not data or data=='[DONE]':return
        try:value=json.loads(data)
        except ValueError:self.invalid=True;return
        self._value(value)

    def _value(self,value):
        if not isinstance(value,dict):self.invalid=True;return
        kind=value.get('type');response=value.get('response',value)
        if self.usage_metadata and isinstance(response,dict) and isinstance(response.get('usage'),dict):
            if kind in ('response.completed','response.failed','response.incomplete') or response.get('status') in ('completed','failed','incomplete'):
                try:self._usage(response)
                except Exception:self.provider_usage_conflict=True
        if self.sse and isinstance(kind, str):
            if self.first_sse_event_monotonic is None:
                self.first_sse_event_monotonic=time.monotonic()
            if (kind in {'response.output_text.delta', 'response.function_call_arguments.delta',
                         'response.reasoning_summary_text.delta'}
                    and value.get('delta') and self.first_output_delta_monotonic is None):
                self.first_output_delta_monotonic=time.monotonic()
        error=value.get('error') or (response.get('error') if isinstance(response,dict) else None)
        if not isinstance(error,dict) and kind=='error':error=value
        if isinstance(error,dict):
            self.error_code=safe_error_token(error.get('code'))
            self.error_type=safe_error_token(error.get('type'))
        if kind in ('error','response.failed') or (isinstance(response,dict) and response.get('status')=='failed'):
            self.failed='sse_response_failed' if self.sse else 'json_response_failed'
        elif kind=='response.incomplete' or (isinstance(response,dict) and response.get('status')=='incomplete'):
            details=response.get('incomplete_details',{}) if isinstance(response,dict) else {}
            reason=details.get('reason') if isinstance(details,dict) else None
            self.incomplete_reason=reason if isinstance(reason,str) and re.fullmatch(r'[a-z_]{1,64}',reason) else None
            if reason in {'max_output_tokens','content_filter'}:
                # A normal per-request generation/policy boundary consumed real
                # model time. It is not free infrastructure retry credit.
                self.completed=True
            elif reason in {'server_error','rate_limit_exceeded','timeout','overloaded','insufficient_quota'}:
                self.failed='response_incomplete_provider_error'
            else:self.unclassified_incomplete=True
        elif value.get('error'):
            self.failed='response_error'
        elif kind=='response.completed' or (isinstance(response,dict) and response.get('status')=='completed'):
            self.completed=True
        elif self.route.endswith('/compact') and value.get('object')=='response.compaction':
            self.completed=True

    def _usage(self,response):
        """Request-anchored numeric usage only; never double count completed events."""
        raw=response['usage']
        numeric=lambda v:v if type(v)is int and v>=0 else None
        details=raw.get('input_tokens_details')
        details=details if isinstance(details,dict) else {}
        out=raw.get('output_tokens_details')
        out=out if isinstance(out,dict) else {}
        record={'input_tokens':numeric(raw.get('input_tokens')),
                'cached_input_tokens':numeric(details.get('cached_tokens',raw.get('cached_input_tokens'))),
                'output_tokens':numeric(raw.get('output_tokens')),
                'reasoning_output_tokens':numeric(out.get('reasoning_tokens',raw.get('reasoning_output_tokens'))),
                'total_tokens':numeric(raw.get('total_tokens'))}
        writes=details.get('cache_write_tokens_details')
        writes=writes if isinstance(writes,dict) else {}
        record['cache_write_tokens']=numeric(details.get('cache_write_tokens',raw.get('cache_write_tokens')))
        record['cache_write_ttl_30m_tokens']=numeric(writes.get('ttl_30m_tokens'))
        record['cache_write_ttl_12h_tokens']=numeric(writes.get('ttl_12h_tokens'))
        response_id=response.get('id')
        record['response_id_sha256']=hashlib.sha256(response_id.encode()).hexdigest() if isinstance(response_id,str) else None
        if record in self.provider_usage_records:
            self.provider_usage_duplicate_events+=1
        elif self.provider_usage_records:
            self.provider_usage_conflict=True
            if len(self.provider_usage_records)<4:self.provider_usage_records.append(record)
        else:self.provider_usage_records.append(record)

    def feed(self,chunk):
        if self.invalid:return
        try:
            if self.unzip is not None:
                chunk=self.unzip.decompress(chunk,8*1024*1024)
                if self.unzip.unconsumed_tail:raise ValueError('Bounded decoder limit')
            self._text(self.decoder.decode(chunk))
        except (ValueError,UnicodeError,zlib.error):self.invalid=True

    def _text(self,text):
        self.buffer+=text
        if len(self.buffer)>8*1024*1024:self.invalid=True;self.buffer='';return
        if not self.sse:return
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1);line=line.rstrip('\r')
            if not line:self._event()
            elif line.startswith('data:'):self.data.append(line[5:].lstrip(' '))
            elif line.startswith('event:'):self.event_name=line[6:].strip()
            if sum(map(len,self.data))>8*1024*1024:self.invalid=True;self.data=[];return

    def finish(self):
        try:
            if self.unzip is not None:
                self._text(self.decoder.decode(self.unzip.flush()))
                if not self.unzip.eof:self.invalid=True
            self._text(self.decoder.decode(b'',final=True))
            if self.sse:
                if self.buffer.strip():self._text('\n')
                if self.data or self.event_name:self._event()
            elif self.json:self._value(json.loads(self.buffer))
            else:self.invalid=True
        except (ValueError,UnicodeError,zlib.error):self.invalid=True
        if self.status>=400:return 'failure','http_'+str(self.status)
        if not 200<=self.status<300:return 'unknown','unexpected_http_status'
        if self.failed:return 'failure',self.failed
        if self.unclassified_incomplete:return 'unknown','unclassified_response_incomplete'
        if self.invalid or not self.completed:return 'unknown','unverified_response_completion'
        return 'success',None


def validated_timing_routes(routes):
    if routes is None:return None
    if not isinstance(routes,dict) or not routes:raise ValueError('Nonempty episode timing route map required')
    result={}
    for opaque,path in routes.items():
        if not isinstance(opaque,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',opaque):
            raise ValueError('Opaque episode route required')
        if not isinstance(path,str) or not Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('Absolute private timing log required')
        result[opaque]=Path(path)
    if len(set(result.values()))!=len(result):raise ValueError('Each episode needs a distinct timing ledger')
    return result


def serve(upstream, ca_bundle, output, *, port=0, timeout=300, ready=None, proxy=None,
          episode_timing_routes=None, concurrency_config=None, request_metadata=False):
    if type(request_metadata) is not bool: raise ValueError('request_metadata must be an explicit boolean')
    timing_routes=validated_timing_routes(episode_timing_routes)
    concurrency_gate=FileConcurrencyGate(concurrency_config) if concurrency_config is not None else None
    url = urlsplit(upstream)
    if url.scheme != 'https' or url.username or url.password or url.query or url.fragment:
        raise ValueError('Relay requires a private configured HTTPS upstream')
    context = ssl.create_default_context(cafile=str(ca_bundle))
    proxy_authority=None
    if proxy is not None:
        parsed_proxy=urlsplit(proxy)
        if (parsed_proxy.scheme not in ('http','https') or not parsed_proxy.hostname
                or parsed_proxy.query
                or parsed_proxy.fragment or parsed_proxy.path not in ('','/')):
            raise ValueError('Explicit proxy must be an HTTP(S) authority')
        proxy_authority=parsed_proxy.scheme+'://'+parsed_proxy.netloc.rsplit('@',1)[-1]
        # The proxy's own TLS and the provider's TLS use the same verified CA
        # context; no environment-dependent implicit proxy or TLS bypass.
        proxy=httpx.Proxy(proxy,ssl_context=context)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    log_fd = os.open(output/'transport.private.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    log = os.fdopen(log_fd,'a')
    lock = threading.Lock()
    # Episode budgets close admission elsewhere. They must never cancel a
    # request that has already reached this transport. Only establishment and
    # connection-pool acquisition retain a finite timeout.
    client = httpx.Client(verify=context,trust_env=False,
                         timeout=httpx.Timeout(timeout,read=None,write=None),
                         follow_redirects=False,http2=False,proxy=proxy)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self,*_):
            pass

        def dispatch(self):
            started = time.monotonic()
            record = dict(request_id=uuid.uuid4().hex,method=self.command,
                request_forward_attempts=0,response_complete=False,
                upstream_response_complete=False,downstream_disconnected=False)
            headers_started = False
            timing_path=None;timing_started=False;observer=None
            outcome,failure_kind='unknown','request_not_classified'
            request_secret=''
            lease=None

            def downstream(write):
                # Closing the CLI/browser side is not permission to cancel an
                # already submitted model request. Continue consuming upstream
                # bytes, but never replay or fabricate a response.
                if record['downstream_disconnected']:
                    return
                try:
                    write()
                except OSError as exc:
                    record['downstream_disconnected'] = True
                    record['downstream_error_class'] = type(exc).__name__

            try:
                path = urlsplit(self.path)
                route = path.path
                matched=re.fullmatch(r'/episodes/([A-Za-z0-9_-]+)/v1(/.*)',route)
                if matched:
                    if timing_routes is None or matched.group(1) not in timing_routes:
                        self.send_error(404);return
                    timing_path=timing_routes[matched.group(1)]
                    route='/v1'+matched.group(2)
                elif timing_routes is not None and self.command=='POST':
                    self.send_error(404);return
                if (path.scheme or path.netloc or path.fragment or path.query
                        or route not in ('/v1/models','/v1/responses','/v1/responses/compact')
                        or self.command not in ('GET','POST')):
                    self.send_error(404);return
                record['path'] = route
                if timing_path is not None and self.command=='POST' and route.startswith('/v1/responses'):
                    try:
                        register_api_request_start(timing_path, record['request_id'], monotonic=started)
                    except EpisodeApiClosed:
                        record['admission_rejected']='episode_closed'
                        record['local_http_status']=410
                        record['upstream_not_attempted_reason']='episode_closed'
                        payload=json.dumps({'error': {'code': 'episode_closed',
                            'message': 'The episode has ended; no new model request was sent.'}}).encode()
                        self.send_response(410)
                        self.send_header('Content-Type','application/json')
                        self.send_header('Content-Length',str(len(payload)))
                        self.send_header('Connection','close')
                        self.end_headers();self.wfile.write(payload)
                        record['local_response_complete']=True
                        return
                    timing_started=True
                limit = 128*1024*1024
                encoding = self.headers.get('Transfer-Encoding','').lower()
                if encoding == 'chunked':
                    chunks,total = [],0
                    while True:
                        line = self.rfile.readline(1024)
                        size = int(line.strip().split(b';',1)[0],16)
                        if size==0:
                            while self.rfile.readline(8192).strip():
                                pass
                            break
                        total += size
                        if total>limit or size<0:
                            raise ValueError('Request size limit')
                        chunk = self.rfile.read(size)
                        if len(chunk)!=size or self.rfile.read(2)!=b'\r\n':
                            raise ConnectionError('Incomplete request')
                        chunks.append(chunk)
                    body = b''.join(chunks)
                elif not encoding:
                    length = int(self.headers.get('Content-Length','0'))
                    if not 0<=length<=limit:
                        self.send_error(400);return
                    body = self.rfile.read(length)
                    if len(body)!=length:
                        raise ConnectionError('Incomplete request')
                else:
                    self.send_error(400);return
                headers = {k:v for k,v in self.headers.items() if k.lower() not in HOP_HEADERS}
                headers.pop('Content-Length',None)
                suffix = route[len('/v1'):]
                record['request_bytes'] = len(body)
                if request_metadata and self.command == 'POST':
                    # Side-channel only: forwarding below uses the original objects.
                    try: record['request_metadata'] = safe_request_metadata(body, headers)
                    except Exception:
                        # Inspection failure must not cancel or replay a request.
                        record['request_metadata'] = {'schema': 'native-request-metadata-v1',
                                                      'inspection_failed': True}
                if concurrency_gate is not None:
                    queued_at=time.monotonic()
                    if timing_started:
                        append_timing_event(timing_path,'queue_start',monotonic=queued_at,
                                            request_id=record['request_id'])
                    try:
                        # The request has already been marked active. Waiting
                        # for capacity cannot look quiescent to its owner or
                        # consume the episode's effective execution budget.
                        lease=concurrency_gate.acquire()
                    finally:
                        admitted_at=time.monotonic()
                        record['concurrency_queue_seconds']=admitted_at-queued_at
                        if timing_started:
                            append_timing_event(timing_path,'queue_end',monotonic=admitted_at,
                                                request_id=record['request_id'])
                    record['concurrency_slot']=lease.slot
                record['request_forward_attempts'] = 1
                record['upstream_started_monotonic'] = time.monotonic()
                with client.stream(self.command,upstream.rstrip('/')+suffix,
                                   headers=headers,content=body) as response:
                    record['response_headers_monotonic'] = time.monotonic()
                    def send_headers():
                        self.send_response(response.status_code)
                        for key,value in response.headers.multi_items():
                            if key.lower() not in HOP_HEADERS:
                                self.send_header(key,value)
                        self.send_header('Connection','close')
                        self.end_headers()
                    downstream(send_headers)
                    headers_started = True
                    record['http_status'] = response.status_code
                    audit_headers=safe_response_headers(response.headers)
                    authorization=self.headers.get('Authorization','')
                    request_secret=authorization.split(' ',1)[-1] if authorization else ''
                    record.update({k:v for k,v in audit_headers.items() if not request_secret or request_secret not in v})
                    if timing_started or request_metadata:
                        observer=ResponseOutcomeObserver(response.status_code,response.headers.get('content-type',''),
                            response.headers.get('content-encoding',''),route,usage_metadata=request_metadata)
                    record['upstream_response_bytes'] = 0
                    for chunk in response.iter_raw():
                        if chunk and 'first_body_chunk_monotonic' not in record:
                            record['first_body_chunk_monotonic'] = time.monotonic()
                        record['upstream_response_bytes'] += len(chunk)
                        if observer is not None:observer.feed(chunk)
                        def send_chunk():
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        downstream(send_chunk)
                record['upstream_response_complete'] = True
                record['response_complete'] = not record['downstream_disconnected']
                if observer is not None:outcome,failure_kind=observer.finish()
                if record['downstream_disconnected']:outcome,failure_kind='failure','downstream_disconnected'
            except Exception as exc:
                record['error_class'] = type(exc).__name__
                outcome,failure_kind='failure','transport_'+type(exc).__name__
                if not headers_started:
                    try:
                        self.send_error(502,'Verified upstream transport failed')
                    except (BrokenPipeError,ConnectionResetError):
                        pass
                # A partial POST/response is never retried by this relay.
            finally:
                if lease is not None:
                    # Even a disconnected downstream client must hold its
                    # capacity until the upstream stream has been consumed.
                    try:lease.release()
                    except Exception as exc:record['concurrency_release_error_class']=type(exc).__name__
                self.close_connection = True
                ended=time.monotonic()
                record['duration_seconds'] = round(ended-started,3)
                record['started_monotonic']=started;record['ended_monotonic']=ended
                if request_metadata and observer is not None:
                    record['provider_usage_records']=observer.provider_usage_records
                    record['provider_usage_duplicate_events']=observer.provider_usage_duplicate_events
                    record['provider_usage_conflict']=observer.provider_usage_conflict
                if timing_started:
                    if observer is not None:
                        record['first_sse_event_monotonic']=observer.first_sse_event_monotonic
                        record['first_output_delta_monotonic']=observer.first_output_delta_monotonic
                    record.update(api_outcome=outcome,api_failure_kind=failure_kind,
                        api_incomplete_reason=observer.incomplete_reason if observer is not None else None,
                        response_error_code=observer.error_code if observer is not None else None,
                        response_error_type=observer.error_type if observer is not None else None)
                    for field in ('response_error_code','response_error_type'):
                        if request_secret and request_secret in (record.get(field) or ''):record[field]=None
                    append_timing_event(timing_path,'request_end',monotonic=ended,request_id=record['request_id'],
                        outcome=outcome,failure_kind=failure_kind,
                        incomplete_reason=observer.incomplete_reason if observer is not None else None,
                        error_code=record.get('response_error_code'),error_type=record.get('response_error_type'),
                        **{k:v for k,v in record.items() if k in {'response_request_id','response_x_request_id','response_retry_after'}})
                with lock:
                    log.write(json.dumps(record)+'\n');log.flush()

        do_POST = dispatch
        do_GET = dispatch

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    # server_close waits for accepted handlers after shutdown stops accepting
    # new connections. Close the shared client/log only after this drain.
    server.daemon_threads = False
    server.block_on_close = True
    details = dict(base_url=f'http://127.0.0.1:{server.server_port}/v1',
        pid=os.getpid(),upstream=upstream,strict_upstream_tls=True,
        proxy_environment_ignored=True,automatic_request_replay=False,
        explicit_proxy=proxy_authority,
        upstream_read_timeout_seconds=None,upstream_write_timeout_seconds=None,
        connection_timeout_seconds=timeout,graceful_shutdown_drains_requests=True,
        model_request_and_response_bytes_unchanged=True,
        episode_timing_enabled=timing_routes is not None,episode_timing_route_count=len(timing_routes or {}),
        concurrency_gate_enabled=concurrency_gate is not None,
        request_metadata_enabled=request_metadata,
        concurrency_config=str(concurrency_config) if concurrency_config is not None else None,
        timing_timebase='same_host_monotonic')
    fd = os.open(output/'ready.private.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(details,f,indent=2)
    if ready:
        ready(details,server)
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close();client.close();log.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream',required=True)
    p.add_argument('--ca-bundle',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--port',type=int,default=0)
    p.add_argument('--episode-timing-routes',type=Path,help='Private JSON map: opaque route to absolute per-room timing ledger')
    p.add_argument('--concurrency-config',type=Path,
                   help='Shared API concurrency admission policy; queued time is excluded from episode budgets')
    p.add_argument('--request-metadata',action='store_true',
                   help='Opt-in content-free request structure/cache identity hashes; forwarding remains byte-identical')
    p.add_argument('--timeout',type=int,default=300,
                   help='Connection/pool acquisition timeout only; accepted request reads/writes have no local deadline')
    group=p.add_mutually_exclusive_group()
    group.add_argument('--proxy',help='Explicit trusted HTTP(S) egress proxy; use --proxy-env for authenticated proxies')
    group.add_argument('--proxy-env',help='Read the explicit trusted proxy URL from this environment variable without putting credentials in argv')
    args = p.parse_args()

    def ready(details,server):
        for sig in [signal.SIGTERM,signal.SIGINT]:
            signal.signal(sig,lambda *_: threading.Thread(target=server.shutdown,daemon=True).start())
        print(json.dumps(details),flush=True)
    proxy=os.environ.get(args.proxy_env) if args.proxy_env else args.proxy
    if args.proxy_env and not proxy:
        p.error('Configured proxy environment variable is absent')
    serve(args.upstream,args.ca_bundle,args.out,port=args.port,timeout=args.timeout,ready=ready,proxy=proxy,
          request_metadata=args.request_metadata,
          concurrency_config=args.concurrency_config,
          episode_timing_routes=json.loads(args.episode_timing_routes.read_text()) if args.episode_timing_routes else None)


if __name__=='__main__':
    main()
