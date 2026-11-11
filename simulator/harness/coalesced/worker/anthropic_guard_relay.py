"""Optional Anthropic-engine front relay; existing billing/admission relay stays authoritative.

Use make_relay instead of transport.make_relay for a *new* worker/companion.
Never rebind a running room. No upstream credential is persisted here.
"""
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from urllib.parse import urlsplit
from anthropic_stream_guard import StreamGuard
from transport import make_relay as make_billing_relay


def make_relay(engine, model, token, key, out, timing):
    if engine not in ('qwen','dsh','zcode'):
        raise ValueError('This relay accepts audited Anthropic Messages engines only')
    inner = make_billing_relay(engine, model, token, key, out, timing)
    thread = threading.Thread(target=inner.serve_forever, name=engine+'-billing-relay', daemon=False)
    thread.start()
    guard = StreamGuard()
    ledger_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            route = urlsplit(self.path)
            auth = self.headers.get('Authorization', '')
            auth_key = self.headers.get('x-api-key','')
            if route.path not in ('/v1/messages', '/v1/messages/count_tokens') or route.query not in ('','beta=true') or not (hmac.compare_digest(auth, 'Bearer ' + token) or hmac.compare_digest(auth_key, token)):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 256 * 1024 * 1024:
                    raise ValueError('invalid request size')
                body = self.rfile.read(size)
                data = json.loads(body)
            except (ValueError, AttributeError):
                self.send_error(400)
                return
            receipt = {'started': time.time(), 'layer': engine+'_downstream_guard',
                       'billing_scope': 'nonbillable_delivery_receipt'}

            def query(upstream_receipt):
                # Fixed loopback target created above, no new provider routing.
                conn = http.client.HTTPConnection('127.0.0.1', inner.server_address[1], timeout=None)
                try:
                    conn.request('POST', self.path, body, {'Content-Type': 'application/json',
                                                        'Authorization': 'Bearer ' + token})
                    reply = conn.getresponse()
                    raw = reply.read()
                    if engine == 'dsh':
                        try:
                            from stream_shape_audit import audit
                            audit(out, upstream_receipt, raw)
                        except BaseException as audit_exc:
                            upstream_receipt['shape_audit_error'] = type(audit_exc).__name__
                    if engine == 'dsh' and reply.status == 200:
                        try:
                            from dsh_messages_compat import normalize
                            raw, compat_meta = normalize(raw)
                            compat_meta['request_body_sha256'] = upstream_receipt.get('request_body_sha256')
                            compat_meta['upstream_request_id'] = upstream_receipt.get('upstream_request_id')
                            with ledger_lock:
                                with (out/'dsh-sse-compat.jsonl').open('a') as compat_log:
                                    compat_log.write(json.dumps(compat_meta, separators=(',', ':')) + '\n')
                        except BaseException as compat_exc:
                            upstream_receipt['compat_error'] = type(compat_exc).__name__
                    if engine=='zcode' and reply.status!=200:
                        # The native ZCode CLI otherwise hides the HTTP status
                        # behind PROVIDER_BUSINESS_ERROR. Retain its error and
                        # expose the actual relay HTTP status to same-SID recovery.
                        try: envelope=json.loads(raw)
                        except ValueError: envelope={}
                        error=envelope.get('error') if isinstance(envelope,dict) else None
                        if not isinstance(error,dict):error={'type':'api_error','message':'Relay transport did not complete the request.'}
                        error=dict(error)
                        detail=str(error.get('message','')).replace(key,'[redacted]')
                        kind='rate limit' if reply.status==429 else 'relay transport error'
                        error['message']=f'HTTP {reply.status} {kind}: {detail}'
                        raw=json.dumps({'type':'error','error':error}).encode()
                    return reply.status, raw, 0
                except (OSError, http.client.HTTPException):
                    upstream_receipt['local_delivery_failure'] = True
                    return None, b'', 1
                finally:
                    conn.close()
            try:
                if data.get('stream') is not True:
                    status, payload, rc = query({})
                    self.send_response(status or 502)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    self.wfile.flush()
                    delivered = status == 200 and rc == 0
                else:
                    status, delivered = guard.serve(self, self.path, body, query, receipt)
                receipt.pop('upstream_http', None)
                receipt.update(delivered=delivered, inner_http=status)
            finally:
                receipt['ended'] = time.time()
                with ledger_lock:
                    with (out/(engine+'-stream-guard.jsonl')).open('a') as f:
                        f.write(json.dumps(receipt) + '\n')

    class Relay(ThreadingHTTPServer):
        daemon_threads = False
        def server_close(self):
            # All HTTP consumers and their accepted upstream must first finish.
            super().server_close()
            guard.close()
            inner.shutdown()
            inner.server_close()
            thread.join()
    return Relay(('127.0.0.1', 0), Handler)
