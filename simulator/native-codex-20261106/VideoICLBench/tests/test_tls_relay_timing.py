"""Loopback TLS fixtures only: per-room routes, immutable bytes and timing logs."""
import http.client
import json
import time
from vic_sdk.api_timing import ApiTimingLedger
from test_tls_relay import upstream,delayed_upstream,relay


def test_private_route_stripped_and_success_interval_is_not_excluded(tmp_path,upstream):
    timing=tmp_path/'room'/'api-timing.jsonl';opaque='a'*32
    with relay(tmp_path,upstream,episode_timing_routes={opaque:str(timing)}) as (details,server):
        assert details['episode_timing_route_count']==1
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        body=b'{"model":"unchanged"}'
        client.request('POST',f'/episodes/{opaque}/v1/responses',body)
        response=client.getresponse();assert response.read()==upstream[3];client.close()
    assert upstream[2][0]['path']=='/v1/responses' and upstream[2][0]['body']==body
    s=ApiTimingLedger(timing).snapshot()
    assert s['request_count']==1 and not s['active'] and not s['uncertain'] and s['excluded_intervals']==[]
    assert opaque not in (tmp_path/'relay/transport.private.jsonl').read_text()


def test_route_transport_failure_records_exactly_one_failed_request(tmp_path,upstream):
    timing=tmp_path/'room'/'timing';opaque='b'*32
    with relay(tmp_path,upstream,episode_timing_routes={opaque:str(timing)}) as (_,server):
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request('POST',f'/episodes/{opaque}/v1/responses/compact',b'{}')
        response=client.getresponse();assert response.status==502;response.read();client.close()
    s=ApiTimingLedger(timing).snapshot()
    assert len(upstream[2])==s['request_count']==1 and len(s['failed_intervals'])==1
    assert s['retry_gap_open'] and not s['active']


def test_active_request_visible_before_upstream_finishes(tmp_path,delayed_upstream):
    upstream,started,release,finished=delayed_upstream
    timing=tmp_path/'room'/'timing';opaque='c'*32
    with relay(tmp_path,upstream,episode_timing_routes={opaque:str(timing)}) as (_,server):
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        client.request('POST',f'/episodes/{opaque}/v1/responses',b'{}')
        response=client.getresponse();assert started.wait(3)
        state=ApiTimingLedger(timing).snapshot()
        assert state['active'] and state['active_request_count']==1 and state['excluded_intervals']==[]
        release.set();assert response.read()==upstream[3];client.close()
    assert not ApiTimingLedger(timing).snapshot()['active']


def test_unmapped_post_cannot_escape_episode_timing(tmp_path,upstream):
    timing=tmp_path/'room'/'timing';opaque='d'*32
    with relay(tmp_path,upstream,episode_timing_routes={opaque:str(timing)}) as (_,server):
        for path in ('/v1/responses','/episodes/wrong/v1/responses'):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port)
            client.request('POST',path,b'{}');response=client.getresponse()
            assert response.status==404;response.read();client.close()
    assert not upstream[2] and not timing.exists()


import gzip
import ssl
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest


@pytest.fixture
def failure_upstream(tmp_path,upstream,request):
    status,logical_error=request.param
    payload=(b'data: {"type":"response.failed","response":{"error":{"code":"server_error"}}}\n\n'
             if logical_error else b'{"error":{"code":"server_error"}}')
    encoded=gzip.compress(payload);calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            calls.append(self.path);self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(status);self.send_header('Content-Type','text/event-stream' if logical_error else 'application/json')
            self.send_header('Content-Encoding','gzip');self.send_header('Content-Length',str(len(encoded)))
            self.end_headers();self.wfile.write(encoded)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(upstream[1],tmp_path/'key.pem')
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield (f'https://127.0.0.1:{server.server_port}/v1',upstream[1],calls,encoded)
    finally:server.shutdown();server.server_close();thread.join(2)


@pytest.mark.parametrize('failure_upstream',[(500,False),(529,False),(200,True)],indirect=True)
def test_http_and_logical_sse_failures_get_private_per_room_intervals(tmp_path,failure_upstream):
    route1,route2='e'*32,'f'*32;log1,log2=tmp_path/'one/timing',tmp_path/'two/timing'
    with relay(tmp_path,failure_upstream,episode_timing_routes={route1:str(log1),route2:str(log2)}) as (_,server):
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request('POST',f'/episodes/{route1}/v1/responses',b'{}')
        response=client.getresponse();assert response.read()==failure_upstream[3];client.close()
    assert len(failure_upstream[2])==1 and not log2.exists()
    state=ApiTimingLedger(log1).snapshot()
    assert len(state['failed_intervals'])==1 and not state['uncertain'] and not state['active']
    record=json.loads((tmp_path/'relay/transport.private.jsonl').read_text())
    assert record['api_outcome']=='failure' and record['request_forward_attempts']==1


def test_stream_timestamps_distinguish_headers_and_generated_delta(monkeypatch):
    from vic_sdk.tls_relay import ResponseOutcomeObserver
    now=[10.0]
    monkeypatch.setattr('vic_sdk.tls_relay.time.monotonic', lambda:now[0])
    observer=ResponseOutcomeObserver(200,'text/event-stream')
    observer.feed(b'data: {"type":"response.created"}\n\n')
    assert observer.first_sse_event_monotonic==10.0
    assert observer.first_output_delta_monotonic is None
    now[0]=25.0
    observer.feed(b'data: {"type":"response.function_call_arguments.delta","delta":"{\\"x\\":1}"}\n\n')
    now[0]=26.0
    observer.feed(b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n')
    assert observer.finish()==('success',None)
    assert observer.first_sse_event_monotonic==10.0
    assert observer.first_output_delta_monotonic==25.0


def test_sealed_episode_rejected_without_upstream_or_new_timing(tmp_path,upstream):
    from vic_sdk.episode_api_admission import EpisodeApiAdmission
    timing=tmp_path/'room'/'timing';opaque='9'*32
    admission=EpisodeApiAdmission(timing)
    with admission.guard():
        admission.close_locked(reason='done')
    with relay(tmp_path,upstream,episode_timing_routes={opaque:str(timing)}) as (_,server):
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request('POST',f'/episodes/{opaque}/v1/responses',b'{}')
        response=client.getresponse()
        assert response.status==410
        assert json.loads(response.read())['error']['code']=='episode_closed'
        client.close()
    assert not upstream[2] and not timing.exists()
    record=json.loads((tmp_path/'relay/transport.private.jsonl').read_text())
    assert record['admission_rejected']=='episode_closed'
    assert record['local_http_status']==410 and record['local_response_complete']
    assert record['upstream_not_attempted_reason']=='episode_closed'
    assert record['request_forward_attempts']==0
