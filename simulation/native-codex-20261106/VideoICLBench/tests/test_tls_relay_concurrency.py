"""Real loopback TLS streams verify shared admission without cancelling requests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
import socket
import ssl
import struct
import threading
import time

from vic_sdk.api_timing import ApiTimingLedger,interval_seconds
from test_tls_relay import upstream,relay


def policy(tmp_path,limit=1,reserved=0):
    path=tmp_path/'concurrency.json'
    path.write_text(json.dumps(dict(schema='videoicl-api-concurrency-v1',scope='unit-test-provider',
        limit=limit,legacy_reserved=reserved,lock_directory=str(tmp_path/'locks'),
        filesystem_atomic_mkdir_verified=True)))
    return path


def update_policy(path,**changes):
    value=json.loads(path.read_text());value.update(changes)
    temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value));temporary.replace(path)


def wait_for(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>=deadline:raise AssertionError('Expected test state did not arrive')
        time.sleep(.01)


@contextmanager
def controlled_upstream(tmp_path,certificate):
    calls=[];started={name:threading.Event() for name in ('one','two','three')}
    release={name:threading.Event() for name in started};finished={name:threading.Event() for name in started}
    first=b'data: {"type":"response.created"}\n\n'
    tail=b':'+b'x'*(1024*1024)+b'\n\ndata: {"type":"response.completed"}\n\n'
    expected=first+tail
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']));name=body.decode();calls.append(name)
            self.send_response(200);self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(expected)));self.end_headers()
            self.wfile.write(first);self.wfile.flush();started[name].set()
            if not release[name].wait(10):return
            self.wfile.write(tail);self.wfile.flush();finished[name].set()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate,tmp_path/'key.pem')
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield (f'https://127.0.0.1:{server.server_port}/v1',certificate,calls,expected),started,release,finished
    finally:
        for event in release.values():event.set()
        server.shutdown();server.server_close();thread.join(3)


def post(server,name,route='/v1/responses'):
    client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=8)
    try:
        client.request('POST',route,name.encode());response=client.getresponse()
        return response.status,response.read()
    finally:client.close()


def test_two_relays_share_capacity_and_queued_time_is_excluded(tmp_path,upstream):
    config=policy(tmp_path);timing=tmp_path/'two-timing.jsonl';opaque='a'*32
    with controlled_upstream(tmp_path,upstream[1]) as (remote,started,release,_):
        with relay(tmp_path/'first',remote,concurrency_config=config) as (details,first), \
             relay(tmp_path/'second',remote,concurrency_config=config,
                   episode_timing_routes={opaque:str(timing)}) as (_,second), \
             ThreadPoolExecutor(2) as executor:
            assert details['concurrency_gate_enabled']
            one=executor.submit(post,first,'one');assert started['one'].wait(3)
            two=executor.submit(post,second,'two',f'/episodes/{opaque}/v1/responses')
            try:
                wait_for(lambda: bool(ApiTimingLedger(timing).snapshot()['queue_wait_intervals']))
                time.sleep(.15)
                state=ApiTimingLedger(timing).snapshot()
                assert state['active'] and not state['transport_quiescent_confirmed']
                assert interval_seconds(state['excluded_intervals'])>=.1
                assert remote[2]==['one'] and not two.done()
                release['one'].set();assert one.result(5)==(200,remote[3])
                assert started['two'].wait(3)
                queue_seconds=interval_seconds(ApiTimingLedger(timing).snapshot()['excluded_intervals'])
                time.sleep(.1)
                assert interval_seconds(ApiTimingLedger(timing).snapshot()['excluded_intervals'])==queue_seconds
                release['two'].set();assert two.result(5)==(200,remote[3])
            finally:
                release['one'].set();release['two'].set()
    state=ApiTimingLedger(timing).snapshot()
    assert not state['active'] and not state['uncertain'] and len(remote[2])==2


def test_lowering_limit_waits_for_existing_streams_without_cancelling(tmp_path,upstream):
    config=policy(tmp_path,limit=2);timing=tmp_path/'third-timing';opaque='b'*32
    with controlled_upstream(tmp_path,upstream[1]) as (remote,started,release,finished):
        with relay(tmp_path/'first',remote,concurrency_config=config) as (_,first), \
             relay(tmp_path/'second',remote,concurrency_config=config,
                   episode_timing_routes={opaque:str(timing)}) as (_,second),ThreadPoolExecutor(3) as executor:
            one=executor.submit(post,first,'one');two=executor.submit(post,first,'two')
            assert started['one'].wait(3) and started['two'].wait(3)
            update_policy(config,limit=1)
            three=executor.submit(post,second,'three',f'/episodes/{opaque}/v1/responses')
            try:
                wait_for(lambda: bool(ApiTimingLedger(timing).snapshot()['queue_wait_intervals']))
                assert not one.done() and not two.done() and not started['three'].is_set()
                release['one'].set();assert one.result(5)==(200,remote[3])
                time.sleep(.15)
                assert not started['three'].is_set() and not two.done()
                release['two'].set();assert two.result(5)==(200,remote[3])
                assert started['three'].wait(3)
                release['three'].set();assert three.result(5)==(200,remote[3])
                assert all(event.is_set()for event in finished.values())
            finally:
                for event in release.values():event.set()


def test_disconnected_downstream_keeps_capacity_until_upstream_finishes(tmp_path,upstream):
    config=policy(tmp_path);timing=tmp_path/'second-timing';opaque='c'*32
    with controlled_upstream(tmp_path,upstream[1]) as (remote,started,release,finished):
        with relay(tmp_path/'first',remote,concurrency_config=config) as (_,first), \
             relay(tmp_path/'second',remote,concurrency_config=config,
                   episode_timing_routes={opaque:str(timing)}) as (_,second),ThreadPoolExecutor(1) as executor:
            client=socket.create_connection(('127.0.0.1',first.server_port),timeout=3)
            client.sendall(b'POST /v1/responses HTTP/1.1\r\nHost: localhost\r\nContent-Length: 3\r\n\r\none')
            assert started['one'].wait(3) and client.recv(4096)
            client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0));client.close()
            two=executor.submit(post,second,'two',f'/episodes/{opaque}/v1/responses')
            try:
                wait_for(lambda: bool(ApiTimingLedger(timing).snapshot()['queue_wait_intervals']))
                time.sleep(.15)
                assert remote[2]==['one'] and not finished['one'].is_set()
                release['one'].set();assert finished['one'].wait(3)
                assert started['two'].wait(3)
                release['two'].set();assert two.result(5)==(200,remote[3])
            finally:
                release['one'].set();release['two'].set()
    record=json.loads((tmp_path/'first/relay/transport.private.jsonl').read_text())
    assert record['downstream_disconnected'] and record['upstream_response_complete']
    assert record['request_forward_attempts']==1


def test_invalid_updated_policy_never_forwards_and_closes_queue_timing(tmp_path,upstream):
    config=policy(tmp_path);timing=tmp_path/'timing';opaque='d'*32
    with relay(tmp_path/'first',upstream,concurrency_config=config,
               episode_timing_routes={opaque:str(timing)}) as (_,server):
        update_policy(config,limit=0)
        status,_=post(server,'one',f'/episodes/{opaque}/v1/responses')
        assert status==502
    assert upstream[2]==[]
    state=ApiTimingLedger(timing).snapshot()
    assert not state['active'] and not state['uncertain']
    assert state['queue_wait_intervals'] and state['failed_intervals']
    record=json.loads((tmp_path/'first/relay/transport.private.jsonl').read_text())
    assert record['request_forward_attempts']==0
