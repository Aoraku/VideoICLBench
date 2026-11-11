"""Anthropic Messages SSE liveness and same-body in-flight coalescing.

No model/history edits. Instantiate one guard per room relay. The query callback
must perform exactly one upstream attempt and return (status, raw_sse, curl_exit).
Its receipt is the single billing record; joined HTTP consumers are not new API
attempts. Never stop query when a downstream client disconnects.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import hashlib
import json
import re
import threading
import time
import uuid


def completed_messages(payload):
    """Validate completion, then retain every original upstream SSE byte."""
    stopped = False
    reason = False
    for block in payload.replace(b'\r\n', b'\n').split(b'\n\n'):
        raw = b'\n'.join(line[5:].lstrip() for line in block.splitlines() if line.startswith(b'data:'))
        if not raw:
            continue
        event = json.loads(raw)
        if not isinstance(event, dict) or event.get('error') or event.get('type') == 'error':
            raise ValueError('provider_error_or_invalid_frame')
        stopped |= event.get('type') == 'message_stop'
        delta = event.get('delta', {})
        msg = event.get('message', {})
        reason |= any(isinstance(x, dict) and isinstance(x.get('stop_reason'), str) and bool(x['stop_reason']) for x in (event, delta, msg))
    if not stopped or not reason:
        raise ValueError('incomplete_upstream_sse')
    return payload


class StreamGuard:
    """A guard belongs to one authenticated room, never to unrelated sessions."""
    def __init__(self, heartbeat=5.0, orphan_ttl=600.0):
        self.heartbeat = heartbeat
        self.orphan_ttl = orphan_ttl
        self.lock = threading.Lock()
        self.entries = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='qwen-upstream')

    def close(self):
        # No cancellation: accepted upstream requests must fully drain.
        self.executor.shutdown(wait=True, cancel_futures=False)

    def serve(self, handler, path, body, query, receipt):
        """query(upstream_receipt) returns raw provider bytes; no internal retries."""
        request = json.loads(body)
        if request.get('stream') is not True:
            raise ValueError('Qwen stream guard only accepts stream=true')
        digest = hashlib.sha256(path.encode() + b'\0' + body).hexdigest()
        now = time.monotonic()
        with self.lock:
            for key, old in list(self.entries.items()):
                if old['future'].done() and not old['users'] and now - old.get('completed_at', now) > self.orphan_ttl:
                    del self.entries[key]
            entry = self.entries.get(digest)
            joined = entry is not None
            if entry is None:
                upstream = {'upstream_request_id': uuid.uuid4().hex,
                            'request_body_sha256': hashlib.sha256(body).hexdigest()}
                entry = {'upstream': upstream, 'created': now, 'users': 0, 'delivered': False}
                def run_query():
                    try:
                        return query(upstream)
                    finally:
                        entry['completed_at'] = time.monotonic()
                entry['future'] = self.executor.submit(run_query)
                self.entries[digest] = entry
            entry['users'] += 1
        receipt.update(upstream_request_id=entry['upstream']['upstream_request_id'],
                       request_body_sha256=hashlib.sha256(body).hexdigest(),
                       joined_existing_upstream=joined, billable_upstream_owner=not joined,
                       heartbeat_count=0, downstream_complete_write=False)
        handler.protocol_version = 'HTTP/1.1'
        handler.close_connection = True
        live = True
        delivered = False
        status = None

        def chunk(data):
            handler.wfile.write(('%x\r\n' % len(data)).encode() + data + b'\r\n')
            handler.wfile.flush()

        try:
            try:
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                handler.send_header('Transfer-Encoding', 'chunked')
                handler.send_header('Cache-Control', 'no-cache, no-transform')
                handler.send_header('Connection', 'close')
                handler.end_headers()
                chunk(b'event: ping\ndata: {"type":"ping"}\n\n')
            except OSError:
                live = False
            while True:
                try:
                    status, payload, rc = entry['future'].result(timeout=self.heartbeat)
                    break
                except TimeoutError:
                    if entry['future'].done():
                        raise
                    if live:
                        try:
                            chunk(b'event: ping\ndata: {"type":"ping"}\n\n')
                            receipt['heartbeat_count'] += 1
                        except OSError:
                            live = False
            receipt.update(upstream_http=status, curl_exit=rc)
            # Joined consumers have no duplicated billable usage in their receipt.
            if not joined:
                receipt.update(entry['upstream'])
            complete = rc == 0 and status == 200
            decision = None
            if complete:
                try:
                    decision = completed_messages(payload)
                except (ValueError, TypeError):
                    complete = False
                    receipt['failure_class'] = 'incomplete_or_invalid_upstream_sse'
            receipt['upstream_completed'] = complete
            entry['completed_valid'] = complete
            if live:
                if complete:
                    chunk(decision)
                    delivered = True
                    receipt['downstream_complete_write'] = True
                else:
                    # Anthropic streams raise APIError on event:error.
                    # Do not send [DONE] or fabricate a model/tool response on errors.
                    try:
                        error = json.loads(payload).get('error')
                    except (ValueError, AttributeError):
                        error = None
                    if not isinstance(error, dict):
                        error = {'type': 'api_error',
                                 'code': 'upstream_generation_incomplete',
                                 'message': 'Upstream generation did not complete.'}
                    # Keep the provider's own error fields; the actual HTTP
                    # status is retained in the authoritative billing receipt.
                    provider_error_frame = None
                    blocks = re.split(br'(\r?\n\r?\n)', payload)
                    for offset in range(0, len(blocks), 2):
                        block = blocks[offset]
                        raw_error = b'\n'.join(line[5:].lstrip() for line in block.splitlines() if line.startswith(b'data:'))
                        try:
                            event = json.loads(raw_error)
                        except ValueError:
                            continue
                        if isinstance(event, dict) and event.get('type') == 'error' and isinstance(event.get('error'), dict):
                            error = event['error']
                            provider_error_frame = block + (blocks[offset+1] if offset+1 < len(blocks) else b'\n\n')
                            break
                    chunk(provider_error_frame if provider_error_frame is not None else b'event: error\ndata: ' + json.dumps({'type':'error', 'error':error}).encode() + b'\n\n')
                handler.wfile.write(b'0\r\n\r\n')
                handler.wfile.flush()
            else:
                receipt['failure_class'] = 'downstream_disconnected'
            return status, delivered
        except OSError:
            receipt['failure_class'] = 'downstream_disconnected'
            return status, False
        finally:
            with self.lock:
                entry['users'] -= 1
                # A flush is not proof that the native consumer persisted it.
                # Retain exact-body completed results until completion-based TTL.
                # Normal new decisions change native history and therefore SHA.
                entry['delivered'] |= delivered
                failed = entry['future'].done() and (entry.get('completed_valid') is False or entry['future'].exception() is not None)
                if not entry['users'] and failed and self.entries.get(digest) is entry:
                    del self.entries[digest]
