"""Host-only Tabletop8 -> shared Unix socket bridge; exposes no TCP listener."""
import http.client
import os
import socketserver
from http.server import BaseHTTPRequestHandler


class Relay(BaseHTTPRequestHandler):
    def forward(self):
        if not self.path.startswith('/') or self.path.startswith('//'):
            self.send_error(400);return
        conn=http.client.HTTPConnection('127.0.0.1',18664,timeout=360)
        try:
            body=self.rfile.read(int(self.headers.get('Content-Length',0)))
            headers={k:v for k,v in self.headers.items() if k.lower() in ('authorization','content-type','range','if-range')}
            conn.request(self.command,self.path,body,headers)
            r=conn.getresponse();self.send_response(r.status)
            for k,v in r.getheaders():
                if k.lower() in ('content-type','content-length','content-range','accept-ranges','etag','last-modified'):self.send_header(k,v)
            self.end_headers()
            while chunk:=r.read(65536):self.wfile.write(chunk)
        except (OSError,http.client.HTTPException):
            # Do not log request URLs: actor paths contain capability credentials.
            pass
        finally:conn.close()
    do_GET=forward
    do_POST=forward
    def log_message(self,*args):pass


if __name__=='__main__':
    path=os.getenv('VIC_EMBODIED_SOCKET','/bridge/tabletop8.sock')
    os.makedirs(os.path.dirname(path),exist_ok=True)
    if os.path.exists(path):os.unlink(path)
    with socketserver.ThreadingUnixStreamServer(path,Relay) as server:
        os.chmod(path,0o666)
        server.serve_forever()
