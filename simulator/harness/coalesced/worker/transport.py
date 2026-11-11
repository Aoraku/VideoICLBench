"""One authenticated local transport per independent room."""
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
if __package__:
    from .wire_images import image_layout
    from .stream_metadata import record_stop_metadata
else:
    from wire_images import image_layout
    from stream_metadata import record_stop_metadata
import uuid

TOOLS = {'observe','action_batch','depth_points','demo_frames','history','done','giveup'}
CA = os.environ.get('VIC_PROVIDER_CA_BUNDLE')


class MissingUpstreamHTTPStatus(RuntimeError):
    pass


def response_observer(status, content_type, encoding, route, record):
    """Reuse native Responses completion validation without changing wire bytes."""
    from vic_sdk.tls_relay import ResponseOutcomeObserver

    class Observer(ResponseOutcomeObserver):
        def _value(self, value):
            super()._value(value)
            if not isinstance(value, dict):
                return
            response = value.get('response', value)
            if not isinstance(response, dict):
                return
            if isinstance(response.get('model'), str):
                record['returned_model'] = response['model']
            # Native compaction returns response.compaction without a terminal
            # status. The SDK validates completion, but its usage hook handles
            # only regular Responses terminal statuses.
            if (self.route.endswith('/compact')
                    and response.get('object') == 'response.compaction'
                    and isinstance(response.get('usage'), dict)
                    and response.get('status') not in ('completed', 'failed', 'incomplete')
                    and value.get('type') not in ('response.completed', 'response.failed', 'response.incomplete')):
                try:
                    self._usage(response)
                except Exception:
                    self.provider_usage_conflict = True

    return Observer(status, content_type, encoding, route, usage_metadata=True)


def make_relay(engine, model, token, key, out, timing):
    from vic_sdk.episode_api_admission import register_api_request_start, EpisodeApiClosed
    from vic_sdk.api_timing import append_timing_event
    curl = shutil.which('curl')
    if not curl: raise FileNotFoundError('curl')
    from aihubmix_provider import route_for, upstream_url
    origin,provider,direct_route=route_for(engine)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            route = urlsplit(self.path)
            allowed = {'/v1/messages', '/v1/messages/count_tokens'}
            if engine=='codex': allowed={'/v1/responses', '/v1/responses/compact'}
            if engine=='kimi': allowed={'/v1/chat/completions'}
            if engine=='gemini':
                allowed={f'/v1beta/models/{model}:{s}' for s in ('generateContent','streamGenerateContent','countTokens')}
            auth = [self.headers.get(k,'') for k in ('Authorization','x-api-key','x-goog-api-key')]
            if route.path not in allowed or route.query not in ('','beta=true','alt=sse') or not any(hmac.compare_digest(v,token) or hmac.compare_digest(v,'Bearer '+token) for v in auth):
                self.send_error(403); return
            body=self.rfile.read(int(self.headers['Content-Length']))
            data=json.loads(body)
            if engine!='gemini' and data.get('model')!=model:
                self.send_error(403); return
            names=set()
            for tool in data.get('tools',[]):
                for item in tool.get('functionDeclarations',tool.get('function_declarations',[tool.get('function',tool)])):
                    names.add(item.get('name','').removeprefix('mcp__vic__').removeprefix('mcp_vic_').removeprefix('vic_'))
            counting=route.path.endswith(('count_tokens','countTokens'))
            compact=not names and (out/'decision-admitted').is_file() and (
                (engine=='codex' and route.path.endswith('/compact'))
                or any(s in body.lower() for s in (b'compact',b'summariz',b'compress')))
            if not counting and not compact and names!=TOOLS:
                self.send_error(400,'missing or unexpected GUI tools');return
            rid=uuid.uuid4().hex
            try:register_api_request_start(timing,rid)
            except EpisodeApiClosed:
                self.send_error(410,'episode closed');return
            rec={'request_body_sha256':hashlib.sha256(body).hexdigest(),'id':rid,'route':route.path,'started':time.time(),'tools':sorted(names),'bytes':len(body),'count_only':counting,'compact_candidate':compact}
            phase=None
            status=502
            outcome='failure'
            failure_kind='provider_error'
            try:
                if engine=='gemini':
                    rec['upstream_image_layout']=image_layout(data)
                    from gemini_route import query, relay_stream, request_images
                    rec['submitted_images']=request_images(data)
                    if route.path.endswith(':streamGenerateContent'):
                        status, delivered = relay_stream(self, lambda live: query(
                            curl, CA, self.path, body, key, out, rec, client_alive=live), rec)
                        if delivered:
                            outcome = 'success'
                            if names == TOOLS:
                                (out/'decision-admitted').touch()
                        return
                    status,payload,rc=query(curl,CA,self.path,body,key,out,rec)
                    rec['upstream_completed']=bool(rc==0 and status==200 and not rec.get('error'))
                    rec['downstream_complete_write']=False
                    self.send_response(status)
                    self.send_header('Content-Type','text/event-stream' if status==200 and 'streamGenerateContent' in route.path else 'application/json')
                    self.send_header('Content-Length',str(len(payload)));self.end_headers()
                    self.wfile.write(payload)
                    self.wfile.flush()
                    rec['downstream_complete_write']=rec['upstream_completed']
                    if rec['downstream_complete_write']:
                        outcome='success'
                        if names==TOOLS:(out/'decision-admitted').touch()
                    return
                if engine=='zcode':
                    from zcode_vision import promote
                    try:
                        moved=promote(data,out/'image-ledger.jsonl')
                    except (ValueError,KeyError,OSError) as exc:
                        rec['failure_class']='zcode_image_ownership_'+type(exc).__name__
                        status=422
                        self.send_error(status,'Cannot bind a GUI image to its public tool result')
                        return
                    if moved:
                        body=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
                    if not counting:
                        from zcode_effort import enforce
                        rec.update(enforce(data))
                        body=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
                    rec['zcode_public_images']=moved
                    rec['upstream_body_bytes']=len(body)
                layout_data=data
                if engine=='codex' and isinstance(data.get('input'),list):
                    layout_data={'messages':data['input']}
                rec['upstream_image_layout']=image_layout(layout_data)
                rec['provider']=provider;rec['upstream_origin']=origin
                try:
                    from upstream_budget_metadata import metadata as upstream_budget_metadata
                    rec.update(upstream_budget_metadata(body,model))
                except Exception:
                    rec['actual_upstream_budget_metadata']={'schema':'videoicl-actual-upstream-budget-metadata-v1','status':'unknown'}
                if engine=='dsh':
                    try:
                        from transport_phases import begin
                        phase=begin(rec,body)
                    except Exception:
                        rec['transport_phase_metadata']={'unknown':True}
                from newapi_gate import upstream_admission
                with upstream_admission(out,rec):
                    if phase is not None:phase.mark('api_admission_granted')
                    with tempfile.NamedTemporaryFile() as raw:
                        raw.write(body);raw.flush()
                        if phase is not None:phase.mark('body_file_flushed')
                        cfg=['url = '+json.dumps(upstream_url(origin,self.path)),'header = "Content-Type: application/json"','header = '+json.dumps('Authorization: Bearer '+key),'connect-timeout = 15','data-binary = '+json.dumps('@'+raw.name)]
                        if CA:cfg+=['proxy-cacert = '+json.dumps(CA)]
                        if engine=='zcode':cfg+=['http1.1']
                        if direct_route:cfg+=['noproxy = "*"']
                        if engine not in ('kimi','codex'):cfg+=['header = '+json.dumps('x-api-key: '+key),'header = "anthropic-version: 2023-06-01"']
                        with subprocess.Popen([curl,'-q','--silent','--no-buffer','--suppress-connect-headers','--dump-header','-','--config','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as p:
                            if phase is not None:phase.mark('curl_spawned')
                            p.stdin.write(('\n'.join(cfg)+'\n').encode());p.stdin.close()
                            if phase is not None:phase.mark('curl_config_stdin_closed')
                            while True:
                                statusline=p.stdout.readline()
                                if not statusline.startswith(b'HTTP/'):
                                    # EOF without an HTTP response is a transport error.
                                    # The 502 sent to the CLI is synthesized locally.
                                    p.stdout.read()
                                    rec.update(curl_exit=p.wait(), upstream_http=None,
                                               local_http_synthesized=True,
                                               upstream_completed=False,
                                               downstream_complete_write=False)
                                    raise MissingUpstreamHTTPStatus('No upstream HTTP status')
                                status=int(statusline.split()[1]); headers={}
                                for line in p.stdout:
                                    if not line.strip():break
                                    name,_,value=line.partition(b':');headers[name.lower()]=value.strip().decode('latin1')
                                if status!=100:break
                            rec['upstream_http']=status
                            if phase is not None:phase.headers(status,headers)
                            mime=headers.get(b'content-type','application/json')
                            observer=(response_observer(status,mime,headers.get(b'content-encoding',''),route.path,rec)
                                      if engine=='codex' else None)
                            rec.update(upstream_completed=False, downstream_complete_write=False)
                            connected=True
                            try:
                                self.send_response(status)
                                self.send_header('Content-Type',mime)
                                if engine=='codex' and headers.get(b'content-encoding'):
                                    self.send_header('Content-Encoding',headers[b'content-encoding'])
                                self.end_headers()
                            except OSError:
                                connected=False
                                rec['downstream_write_failed']=True
                            complete=False
                            kimi_done=False
                            kimi_finished=False
                            for line in p.stdout:
                                if observer is not None:observer.feed(line)
                                if phase is not None:phase.line(line)
                                if connected:
                                    try:self.wfile.write(line);self.wfile.flush()
                                    except OSError:
                                        connected=False
                                        rec['downstream_write_failed']=True
                                if line.strip()==b'data: [DONE]' and engine=='kimi':
                                    kimi_done=True
                                try:event=json.loads(line.removeprefix(b'data:').strip())
                                except ValueError:continue
                                if not isinstance(event,dict):continue
                                if phase is not None:phase.event(event,is_sse=line.lstrip().startswith(b'data:'))
                                record_stop_metadata(rec,event)
                                from newapi_usage import record_provider_usage
                                record_provider_usage(rec,event)
                                if counting:
                                    complete |= type(event.get('input_tokens')) is int
                                elif engine=='kimi':
                                    kimi_finished |= any(c.get('finish_reason') is not None for c in event.get('choices',[]) if isinstance(c,dict))
                                else:
                                    complete |= event.get('type')=='message_stop' or (event.get('type')=='message' and bool(event.get('stop_reason')))
                                msg=event.get('message')
                                if not isinstance(msg,dict):msg={}
                                for usage in (msg.get('usage'),event.get('usage'),event.get('usageMetadata')):
                                    if isinstance(usage,dict):rec.setdefault('usage',{}).update(usage)
                                if event.get('error'):rec['error']=True
                                returned=msg.get('model') or event.get('model') or event.get('modelVersion')
                                if returned:rec['returned_model']=returned
                            if phase is not None:phase.eof()
                            if engine=='kimi':
                                complete=kimi_done and kimi_finished
                                rec.update(sse_done_observed=kimi_done,finish_reason_observed=kimi_finished)
                            rec['curl_exit']=p.wait()
                            if phase is not None:phase.mark('curl_wait_returned')
                            if observer is not None:
                                observed,observed_failure=observer.finish()
                                complete=observed=='success'
                                rec.update(response_outcome=observed,response_failure_kind=observed_failure,
                                           response_incomplete_reason=observer.incomplete_reason,
                                           provider_usage_records=observer.provider_usage_records,
                                           provider_usage_duplicate_events=observer.provider_usage_duplicate_events,
                                           provider_usage_conflict=observer.provider_usage_conflict)
                                if len(observer.provider_usage_records)==1 and not observer.provider_usage_conflict:
                                    usage=observer.provider_usage_records[0]
                                    rec['provider_usage']={'source':'native_responses_terminal_usage',
                                        'input_tokens_including_cached':usage['input_tokens'],
                                        'cached_input_tokens':usage['cached_input_tokens'],
                                        'output_tokens_including_reasoning':usage['output_tokens'],
                                        'reasoning_output_tokens':usage['reasoning_output_tokens'],
                                        'total_tokens':usage['total_tokens'],
                                        'cache_creation_input_tokens':usage['cache_write_tokens']}
                                if rec['curl_exit']==0:
                                    outcome=observed
                                    failure_kind=observed_failure
                                else:
                                    outcome='failure';failure_kind='upstream_transport_error'
                                if observed_failure:rec['failure_class']=observed_failure
                            rec['upstream_completed']=(rec['curl_exit']==0 and complete and status==200 and not rec.get('error'))
                            rec['downstream_complete_write']=bool(rec['upstream_completed'] and connected)
                            if rec['downstream_complete_write']:
                                outcome='success'
                                if names==TOOLS:(out/'decision-admitted').touch()
                            elif not connected:
                                rec['failure_class']='downstream_disconnected'
                                outcome='failure';failure_kind='downstream_disconnected'
                            elif status==200 and observer is None:
                                rec['failure_class']='incomplete_upstream_response'
            except Exception as exc:
                outcome='failure'
                rec['failure_class']=type(exc).__name__
                if not self.wfile.closed and status==502:
                    try:self.send_error(502)
                    except OSError:pass
            finally:
                if engine=='zcode' and 'provider_usage' not in rec and 'output_tokens' in rec.get('usage',{}):
                    u=rec['usage'];inp=u.get('input_tokens');outp=u.get('output_tokens');cr=u.get('cache_read_input_tokens');cw=u.get('cache_creation_input_tokens')
                    if type(inp) is int and type(outp) is int:
                        rec['provider_usage']={'source':'glm_newapi_verified_anthropic_semantics','input_tokens_including_cached':inp+(cr or 0)+(cw or 0),'output_tokens_including_reasoning':outp,'cached_input_tokens':cr,'cache_creation_input_tokens':cw,'uncached_input_tokens':inp,'missing_cache_fields':cr is None or cw is None}
                rec.update(http=status,outcome=outcome,ended=time.time())
                if phase is not None:phase.finish()
                with (out/'transport.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
                append_timing_event(timing,'request_end',request_id=rid,outcome=outcome,failure_kind=None if outcome=='success' else failure_kind)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=False
    return server
