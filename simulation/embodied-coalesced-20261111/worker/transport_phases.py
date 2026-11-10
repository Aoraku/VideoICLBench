"""Content-safe observation at existing transport read points. Never HTTP I/O."""
import hashlib
import re
import time

HEADER_IDS = (b'x-request-id', b'request-id', b'x-oneapi-request-id', b'x-new-api-request-id')
SAFE_ID = re.compile(r'[A-Za-z0-9_.:/-]{1,160}\Z')


class Phases:
    def __init__(self, receipt, submitted_body, *, wall=time.time, clock=time.monotonic):
        self.wall, self.clock = wall, clock
        self.start = clock()
        self.digest = hashlib.sha256()
        self.state = {
            'schema': 'videoicl-transport-observed-phases-v1',
            'layer': 'upstream_curl_reader',
            'submitted_body_sha256': hashlib.sha256(submitted_body).hexdigest(),
            'submitted_body_bytes': len(submitted_body),
            'clock_origin_unix': wall(), 'events': {}, 'body_bytes_observed': 0,
            'server_request_ids': {}, 'telemetry_errors': 0,
            'upload_started': None, 'upload_complete': None,
            'upload_measurement': 'not_instrumented',
            'timestamps_are_application_read_observations': True,
        }
        receipt['transport_phase_metadata'] = self.state

    def _unknown(self):
        self.state['telemetry_errors'] += 1

    def mark(self, name, *, last=False, observed=None):
        try:
            if name not in ('api_admission_granted', 'body_file_flushed', 'curl_spawned', 'curl_config_stdin_closed',
                            'final_HTTP_headers_observed', 'first_body_line_observed',
                            'last_body_line_observed', 'first_SSE_JSON_observed',
                            'first_generated_SSE_content_observed', 'protocol_terminal_observed',
                            'body_EOF_observed', 'curl_wait_returned', 'receipt_finalized'):
                raise ValueError('unknown_phase')
            events = self.state['events']
            if last or name not in events:
                events[name] = (dict(observed) if observed is not None else
                                {'unix': self.wall(), 'elapsed_monotonic_seconds': self.clock()-self.start})
        except Exception:
            self._unknown()

    def headers(self, status, headers):
        try:
            self.mark('final_HTTP_headers_observed')
            self.state['header_HTTP_status'] = status if type(status) is int else None
            for name in HEADER_IDS:
                value = headers.get(name)
                if type(value) is str and SAFE_ID.fullmatch(value):
                    self.state['server_request_ids'][name.decode()] = value
        except Exception:
            self._unknown()

    def line(self, raw):
        try:
            # Called immediately after the unchanged existing line read and
            # before any downstream write; raw is not retained or modified.
            self.digest.update(raw)
            self.state['body_bytes_observed'] += len(raw)
            self.mark('first_body_line_observed')
            self.mark('last_body_line_observed', last=True)
        except Exception:
            self._unknown()

    def event(self, event, *, is_sse):
        try:
            if not is_sse or type(event) is not dict:
                return
            # Parsing occurs after the unchanged existing downstream write.
            # Use this line's pre-write timestamp, not the later parse time.
            observed = self.state['events'].get('last_body_line_observed')
            self.mark('first_SSE_JSON_observed', observed=observed)
            delta = event.get('delta')
            generated = type(delta) is dict and any(type(delta.get(k)) is str and bool(delta[k])
                                                    for k in ('text', 'thinking', 'partial_json'))
            block = event.get('content_block')
            if type(block) is dict:
                generated |= any(type(block.get(k)) is str and bool(block[k]) for k in ('text', 'thinking'))
                generated |= block.get('type') == 'tool_use' and type(block.get('name')) is str and bool(block['name'])
            if generated:
                self.mark('first_generated_SSE_content_observed', observed=observed)
            if event.get('type') == 'message_stop':
                self.mark('protocol_terminal_observed', observed=observed)
        except Exception:
            self._unknown()

    def eof(self):
        try:
            self.mark('body_EOF_observed')
            self.state['observed_response_body_sha256'] = self.digest.hexdigest()
            self.state['response_body_observation_complete'] = True
        except Exception:
            self._unknown()

    def finish(self):
        try:
            self.mark('receipt_finalized')
            self.state.setdefault('observed_response_body_sha256', self.digest.hexdigest())
            self.state.setdefault('response_body_observation_complete', False)
        except Exception:
            self._unknown()


def begin(receipt, submitted_body):
    """A telemetry failure must not refuse, duplicate or modify an API request."""
    try:
        return Phases(receipt, submitted_body)
    except Exception:
        receipt['transport_phase_metadata'] = {'schema': 'videoicl-transport-observed-phases-v1', 'unknown': True}
        return None
