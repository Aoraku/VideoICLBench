"""Verified HTTPS, unchanged compressed bytes, and no automatic POST replay."""
from contextlib import contextmanager
import gzip
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import ipaddress
import json
from pathlib import Path
import queue
import select
import socket
import ssl
import subprocess
import struct
import sys
import threading
import time

import pytest

from vic_sdk.tls_relay import serve


@pytest.fixture
def upstream(tmp_path):
    cert,key = tmp_path/'cert.pem',tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1',
        '-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
    calls = []
    response = gzip.compress(b'data: {"type":"response.completed"}\n\n')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            calls.append(dict(path=self.path,body=body,authorization=self.headers.get('Authorization'),
                              encoding=self.headers.get('Content-Encoding')))
            if self.path=='/v1/responses/compact':
                self.connection.close();return
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Encoding','gzip')
            self.send_header('Content-Length',str(len(response)))
            self.end_headers();self.wfile.write(response)
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert,key)
    server.socket = context.wrap_socket(server.socket,server_side=True)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        yield f'https://127.0.0.1:{server.server_port}/v1',cert,calls,response
    finally:
        server.shutdown();server.server_close();thread.join(2.)


@contextmanager
def relay(tmp_path,upstream,proxy=None,**options):
    url,cert,_,_ = upstream
    ready = queue.Queue()
    thread = threading.Thread(target=serve,args=(url,cert,tmp_path/'relay'),
        kwargs=dict(ready=lambda details,server:ready.put((details,server)),proxy=proxy,**options),daemon=True)
    thread.start();details,server = ready.get(timeout=5.)
    try:yield details,server
    finally:server.shutdown();thread.join(3.)


@pytest.mark.parametrize('chunked',[False,True])
def test_request_response_gzip_bytes_and_authorization_preserved(tmp_path,upstream,chunked):
    _,_,calls,expected = upstream
    body = gzip.compress(b'{"model":"fixed-model","input":"unchanged test"}')
    with relay(tmp_path,upstream) as (_,server):
        client = http.client.HTTPConnection('127.0.0.1',server.server_port)
        headers = {'Authorization':'Bearer test-secret-not-a-credential','Content-Encoding':'gzip'}
        if chunked:
            client.request('POST','/v1/responses',iter([body[:10],body[10:]]),headers,encode_chunked=True)
        else:client.request('POST','/v1/responses',body,headers)
        result = client.getresponse()
        assert result.status==200 and result.getheader('Content-Encoding')=='gzip'
        assert result.read()==expected
        client.close()
    assert len(calls)==1 and calls[0]['body']==body
    assert calls[0]['authorization']=='Bearer test-secret-not-a-credential'
    log = (tmp_path/'relay/transport.private.jsonl').read_text()
    assert 'test-secret' not in log and 'unchanged test' not in log
    assert json.loads(log)['request_forward_attempts']==1


def test_upstream_connection_loss_never_replays_post(tmp_path,upstream):
    with relay(tmp_path,upstream) as (_,server):
        client = http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request('POST','/v1/responses/compact',b'{}')
        response = client.getresponse();assert response.status==502
        response.read();client.close()
    assert len(upstream[2])==1
    record = json.loads((tmp_path/'relay/transport.private.jsonl').read_text())
    assert record['request_forward_attempts']==1 and record['response_complete'] is False


def test_explicit_verified_https_proxy_preserves_single_request(tmp_path,upstream,monkeypatch):
    from urllib.parse import urlsplit
    url,cert,calls,expected=upstream;parsed=urlsplit(url);connects=[]
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_CONNECT(self):
            assert self.path==f'127.0.0.1:{parsed.port}'
            assert self.headers['Proxy-Authorization']=='Basic '+base64.b64encode(b'proxy-user:proxy-test-secret').decode()
            connects.append(self.path)
            with socket.create_connection(('127.0.0.1',parsed.port),timeout=3) as remote:
                self.send_response(200);self.end_headers()
                self.connection.settimeout(3);remote.settimeout(3)
                while True:
                    readable,_,_=select.select([self.connection,remote],[],[],3)
                    if not readable:return
                    for source in readable:
                        data=source.recv(65536)
                        if not data:return
                        (remote if source is self.connection else self.connection).sendall(data)
    proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy);proxy.daemon_threads=True
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert,tmp_path/'key.pem')
    proxy.socket=context.wrap_socket(proxy.socket,server_side=True)
    thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start()
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
    authority=f'https://127.0.0.1:{proxy.server_port}'
    explicit=f'https://proxy-user:proxy-test-secret@127.0.0.1:{proxy.server_port}'
    try:
        with relay(tmp_path,upstream,explicit) as (details,server):
            assert details['strict_upstream_tls'] and details['explicit_proxy']==authority
            assert 'proxy-test-secret' not in json.dumps(details)
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('POST','/v1/responses',b'{"test":"single"}')
            response=client.getresponse();assert response.status==200
            assert response.read()==expected;client.close()
        assert len(calls)==1 and len(connects)==1
        assert 'proxy-test-secret' not in (tmp_path/'relay/transport.private.jsonl').read_text()
    finally:
        proxy.shutdown();proxy.server_close();thread.join(3)


@pytest.mark.parametrize('proxy',['socks5://127.0.0.1:1','https://localhost:1?secret=bad','https://localhost/path'])
def test_invalid_explicit_proxy_is_rejected_before_serving(tmp_path,upstream,proxy):
    with pytest.raises(ValueError,match='Explicit proxy'):
        serve(upstream[0],upstream[1],tmp_path/'must-not-start',proxy=proxy)
    assert not (tmp_path/'must-not-start').exists()


@pytest.fixture
def delayed_upstream(tmp_path,upstream):
    """A real TLS response paused after its first bytes, not a mocked client."""
    started,release,finished=threading.Event(),threading.Event(),threading.Event()
    calls=[]
    first=b'data: {"type":"response.created"}\n\n'
    tail=b':'+b'x'*(1024*1024)+b'\n\ndata: {"type":"response.completed"}\n\n'
    expected=first+tail
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(expected)))
            self.end_headers();self.wfile.write(first);self.wfile.flush();started.set()
            if not release.wait(10):return
            self.wfile.write(tail);self.wfile.flush();finished.set()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(upstream[1],tmp_path/'key.pem')
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        yield (f'https://127.0.0.1:{server.server_port}/v1',upstream[1],calls,expected),started,release,finished
    finally:
        release.set();server.shutdown();server.server_close();thread.join(2)


def test_disconnected_downstream_still_drains_submitted_upstream(tmp_path,delayed_upstream):
    upstream,started,release,finished=delayed_upstream
    with relay(tmp_path,upstream) as (_,server):
        client=socket.create_connection(('127.0.0.1',server.server_port),timeout=3)
        client.sendall(b'POST /v1/responses HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}')
        assert started.wait(3)
        assert client.recv(4096)
        client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
        client.close()
        release.set()
        assert finished.wait(3)
    records=[json.loads(x) for x in (tmp_path/'relay/transport.private.jsonl').read_text().splitlines()]
    assert len(records)==len(upstream[2])==1
    record=records[0]
    assert record['downstream_disconnected'] is True
    assert record['response_complete'] is False  # Client did not receive it.
    assert record['upstream_response_complete'] is True
    assert record['upstream_response_bytes']==len(upstream[3])
    assert record['request_forward_attempts']==1


def test_connection_timeout_does_not_truncate_idle_model_stream(tmp_path,delayed_upstream):
    upstream,started,release,finished=delayed_upstream
    with relay(tmp_path,upstream,timeout=.2) as (details,server):
        assert details['upstream_read_timeout_seconds'] is None
        assert details['upstream_write_timeout_seconds'] is None
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        client.request('POST','/v1/responses',b'{}')
        response=client.getresponse();assert started.wait(3)
        # Longer than the configured connect timeout, without upstream bytes.
        time.sleep(.5)
        release.set();assert response.read()==upstream[3];client.close()
    record=json.loads((tmp_path/'relay/transport.private.jsonl').read_text())
    assert record['upstream_response_complete'] and record['response_complete']
    assert 'error_class' not in record


def test_sigterm_closes_listener_but_waits_for_inflight_response(tmp_path,delayed_upstream):
    upstream,started,release,finished=delayed_upstream
    output=tmp_path/'process-relay'
    process=subprocess.Popen([sys.executable,'-m','vic_sdk.tls_relay','--upstream',upstream[0],
        '--ca-bundle',str(upstream[1]),'--out',str(output),'--timeout','1'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    client=None
    try:
        deadline=time.monotonic()+5
        while not (output/'ready.private.json').exists() and time.monotonic()<deadline:
            assert process.poll() is None
            time.sleep(.02)
        details=json.loads((output/'ready.private.json').read_text())
        port=int(details['base_url'].split(':')[-1].split('/')[0])
        client=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        client.request('POST','/v1/responses',b'{}')
        response=client.getresponse();assert started.wait(3)
        process.terminate()
        closed=False
        for _ in range(30):
            try:
                connection=socket.create_connection(('127.0.0.1',port),timeout=.1)
            except OSError:
                closed=True;break
            else:connection.close();time.sleep(.02)
        assert closed and process.poll() is None
        assert not finished.is_set()
        release.set();assert response.read()==upstream[3]
        client.close();client=None
        assert process.wait(timeout=5)==0
        record=json.loads((output/'transport.private.jsonl').read_text())
        assert record['upstream_response_complete'] and record['response_complete']
        assert record['request_forward_attempts']==1 and len(upstream[2])==1
    finally:
        release.set()
        if client:client.close()
        if process.poll() is None:
            process.kill();process.wait(timeout=3)
        process.communicate(timeout=3)
