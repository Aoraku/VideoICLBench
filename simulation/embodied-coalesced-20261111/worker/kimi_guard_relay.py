"""Optional Kimi-only front relay; existing billing/admission relay stays authoritative.

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
from kimi_stream_guard import StreamGuard
from transport import make_relay as make_billing_relay


def make_relay(engine, model, token, key, out, timing):
    if engine != 'kimi':
        raise ValueError('This relay is exclusively for Kimi')
    inner = make_billing_relay(engine, model, token, key, out, timing)
    thread = threading.Thread(target=inner.serve_forever, name='kimi-billing-relay', daemon=False)
    thread.start()
    guard = StreamGuard()
    ledger_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            route = urlsplit(self.path)
            auth = self.headers.get('Authorization', '')
            if route.path != '/v1/chat/completions' or route.query or not hmac.compare_digest(auth, 'Bearer ' + token):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 256 * 1024 * 1024:
                    raise ValueError('invalid request size')
                body = self.rfile.read(size)
                data = json.loads(body)
                if data.get('stream') is not True:
                    raise ValueError('requires native streaming')
            except (ValueError, AttributeError):
                self.send_error(400)
                return
            receipt = {'started': time.time(), 'layer': 'kimi_downstream_guard',
                       'billing_scope': 'nonbillable_delivery_receipt'}

            def query(upstream_receipt):
                # Fixed loopback target created above, no new provider routing.
                conn = http.client.HTTPConnection('127.0.0.1', inner.server_address[1], timeout=None)
                try:
                    conn.request('POST', self.path, body, {'Content-Type': 'application/json',
                                                        'Authorization': 'Bearer ' + token})
                    reply = conn.getresponse()
                    raw = reply.read()
                    return reply.status, raw, 0
                except (OSError, http.client.HTTPException):
                    upstream_receipt['local_delivery_failure'] = True
                    return None, b'', 1
                finally:
                    conn.close()
            try:
                status, delivered = guard.serve(self, self.path, body, query, receipt)
                receipt.pop('upstream_http', None)
                receipt.update(delivered=delivered, inner_http=status)
            finally:
                receipt['ended'] = time.time()
                with ledger_lock:
                    with (out/'kimi-stream-guard.jsonl').open('a') as f:
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
