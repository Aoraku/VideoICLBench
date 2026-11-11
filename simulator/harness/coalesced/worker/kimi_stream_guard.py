"""Kimi-only SSE liveness and same-body in-flight coalescing.

No model/history edits. Instantiate one guard per room relay. The query callback
must perform exactly one upstream attempt and return (status, raw_sse, curl_exit).
Its receipt is the single billing record; joined HTTP consumers are not new API
attempts. Never stop query when a downstream client disconnects.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import hashlib
import json
import threading
import time
import uuid


def completed_chat(payload):
    """Reject a truncated response even if it contains a partial tool invocation."""
    done = False
    finished = False
    frames = []
    for block in payload.replace(b'\r\n', b'\n').split(b'\n\n'):
        data = b'\n'.join(line[5:].lstrip() for line in block.splitlines()
                          if line.startswith(b'data:'))
        if not data:
            continue
        if data == b'[DONE]':
            done = True
            continue
        event = json.loads(data)
        if not isinstance(event, dict) or event.get('error'):
            raise ValueError('provider_error_or_invalid_frame')
        finished |= any(c.get('finish_reason') is not None for c in event.get('choices', [])
                        if isinstance(c, dict))
        frames.append(b'data: ' + data + b'\n\n')
    if not done or not finished:
        raise ValueError('incomplete_upstream_sse')
    return b''.join(frames) + b'data: [DONE]\n\n'


class StreamGuard:
    """A guard belongs to one authenticated room, never to unrelated sessions."""
    def __init__(self, heartbeat=5.0, orphan_ttl=600.0):
        self.heartbeat = heartbeat
        self.orphan_ttl = orphan_ttl
        self.lock = threading.Lock()
        self.entries = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='kimi-upstream')

    def close(self):
        # No cancellation: accepted upstream requests must fully drain.
        self.executor.shutdown(wait=True, cancel_futures=False)

    def serve(self, handler, path, body, query, receipt):
        """query(upstream_receipt) returns raw provider bytes; no internal retries."""
        request = json.loads(body)
        if request.get('stream') is not True:
            raise ValueError('Kimi stream guard only accepts stream=true')
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
                chunk(b': waiting for upstream\n\n')
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
                            chunk(b': keep-alive\n\n')
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
                    decision = completed_chat(payload)
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
                    # OpenAI Stream.fromSSEResponse raises APIError on event.error.
                    # Do not send [DONE] or fabricate a model/tool response on errors.
                    try:
                        error = json.loads(payload).get('error')
                    except (ValueError, AttributeError):
                        error = None
                    if not isinstance(error, dict):
                        error = {'type': 'upstream_transport_error',
                                 'code': 'upstream_generation_incomplete',
                                 'message': 'Upstream generation did not complete.'}
                    error = dict(error, status=status)
                    chunk(b'data: ' + json.dumps({'error': error}).encode() + b'\n\n')
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
                # Keep a completed orphan for the client's retry. A delivered
                # decision must not be reused after the native conversation advances.
                entry['delivered'] |= delivered
                failed = entry['future'].done() and (entry.get('completed_valid') is False or entry['future'].exception() is not None)
                if not entry['users'] and (entry['delivered'] or failed) and self.entries.get(digest) is entry:
                    del self.entries[digest]
