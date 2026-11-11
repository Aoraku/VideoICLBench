import io,json,os,sys,tempfile,unittest,gzip
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT/'VideoICLBench/packages/sdk')]
import transport,aihubmix_provider
import vic_sdk.episode_api_admission as admission
import vic_sdk.api_timing as timing

class DummyServer:
 def __init__(self,addr,handler):self.RequestHandlerClass=handler
class Writable(io.BytesIO):
 def close(self):pass
class Proc:
 wire=b'';cfg=b'';drained=False;rc=0
 def __init__(self,*a,**kw):self.stdout=io.BytesIO(self.wire);self.stdin=Writable()
 def __enter__(self):return self
 def __exit__(self,*a):type(self).cfg=self.stdin.getvalue();type(self).drained=self.stdout.tell()==len(self.wire)
 def wait(self):return self.rc
class BrokenWriter:
 closed=False
 def write(self,v):raise BrokenPipeError()
 def flush(self):pass

class TransportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name);self.events=[]
  self.env=patch.dict(os.environ,{'VIC_UPSTREAM_ORIGIN':'https://provider.invalid/v1','VIC_PROVIDER_DIRECT':'1'})
  self.env.start();self.addCleanup(self.env.stop);self.addCleanup(self.tmp.cleanup)
 def req(self,engine='codex',route='/v1/responses',payload=None,raw=None,status=200,mime='text/event-stream',headers=b'',broken=False,closed=False):
  if payload is None:payload={'model':'model-test','tools':[{'type':'function','name':'mcp__vic__'+n} for n in transport.TOOLS],'input':[{'role':'user','content':[{'type':'input_image','image_url':'data:fake'}]}]}
  if raw is None:raw=b'data: '+json.dumps({'type':'response.completed','response':{'id':'response-test','model':'model-test','status':'completed','usage':{'input_tokens':120,'input_tokens_details':{'cached_tokens':90},'output_tokens':7,'output_tokens_details':{'reasoning_tokens':2},'total_tokens':127}}}).encode()+b'\n\n'
  Proc.wire=f'HTTP/1.1 {status} TEST\r\nContent-Type: {mime}\r\n'.encode()+headers+b'\r\n'+raw;Proc.drained=False;Proc.rc=0
  def start(*args):
   if closed:raise admission.EpisodeApiClosed()
   self.events.append(('start',args[1]))
  with patch.object(transport,'ThreadingHTTPServer',DummyServer),patch.object(transport.subprocess,'Popen',Proc),patch.object(admission,'register_api_request_start',start),patch.object(timing,'append_timing_event',lambda *a,**k:self.events.append(('end',k))):
   server=transport.make_relay(engine,'model-test','local-test','upstream-test',self.out,self.out/'timing')
   h=server.RequestHandlerClass.__new__(server.RequestHandlerClass)
   body=json.dumps(payload).encode();h.path=route;h.headers={'Authorization':'Bearer local-test','Content-Length':str(len(body))};h.rfile=io.BytesIO(body);h.wfile=BrokenWriter() if broken else io.BytesIO()
   codes=[];h.send_error=lambda code,*a:codes.append(code);h.send_response=lambda code:codes.append(code);h.send_header=lambda *a:None;h.end_headers=lambda:None
   h.do_POST()
   records=[json.loads(x) for x in (self.out/'transport.jsonl').read_text().splitlines()] if (self.out/'transport.jsonl').exists() else []
   return codes,records[-1] if records else None,None if broken else h.wfile.getvalue()
 def test_completed_usage_auth_and_bytes(self):
  code,r,wire=self.req();self.assertEqual(code,[200]);self.assertEqual(r['outcome'],'success');self.assertEqual(r['provider_usage']['cached_input_tokens'],90);self.assertEqual(r['provider_usage']['reasoning_output_tokens'],2);self.assertEqual(r['upstream_image_layout']['all_messages'],{'user':1});self.assertTrue(Proc.drained);self.assertEqual(len(self.events),2);self.assertNotIn(b'anthropic-version',Proc.cfg);self.assertIn(b'https://provider.invalid/v1/responses',Proc.cfg);self.assertNotIn(b'/v1/v1',Proc.cfg);self.assertTrue((self.out/'decision-admitted').exists());self.assertTrue(wire.endswith(b'\n\n'))
 def test_multiline_and_duplicate_usage(self):
  event={'type':'response.completed','response':{'status':'completed','id':'x','usage':{'input_tokens':3,'output_tokens':2}}}
  encoded=json.dumps(event,indent=2).encode();sse=b'event: response.completed\n'+b'\n'.join(b'data: '+line for line in encoded.splitlines())+b'\n\n'
  _,r,wire=self.req(raw=sse+sse);self.assertEqual(r['outcome'],'success');self.assertEqual(r['provider_usage_duplicate_events'],1);self.assertEqual(len(r['provider_usage_records']),1);self.assertEqual(wire,sse+sse)
 def test_failed_and_truncated_never_success(self):
  for raw in (b'data: {"type":"response.failed","response":{"status":"failed","error":{"code":"server_error"}}}\n\n',b'data: [DONE]\n\n',b'data: {"type":"response.created"}\n\n'):
   with self.subTest(raw=raw):
    _,r,_=self.req(raw=raw);self.assertNotEqual(r['outcome'],'success');self.assertFalse(r['upstream_completed']);self.assertFalse((self.out/'decision-admitted').exists());self.assertTrue(Proc.drained)
 def test_provider_incomplete(self):
  _,r,_=self.req(raw=b'data: {"type":"response.incomplete","response":{"status":"incomplete","incomplete_details":{"reason":"timeout"}}}\n\n');self.assertEqual(r['outcome'],'failure');self.assertEqual(r['response_failure_kind'],'response_incomplete_provider_error')
 def test_compact_requires_decision_and_records_usage(self):
  body={'model':'model-test','input':[]}
  code,r,_=self.req(route='/v1/responses/compact',payload=body);self.assertEqual(code,[400]);self.assertIsNone(r);self.assertEqual(self.events,[])
  self.req();_,r,_=self.req(route='/v1/responses/compact',payload=body,mime='application/json',raw=b'{"object":"response.compaction","id":"compact-test","usage":{"input_tokens":12,"output_tokens":3}}')
  self.assertEqual(r['outcome'],'success');self.assertTrue(r['compact_candidate']);self.assertEqual(r['provider_usage']['input_tokens_including_cached'],12)
 def test_gzip_preserved(self):
  raw=gzip.compress(b'{"status":"completed","usage":{"input_tokens":2,"output_tokens":1}}');_,r,wire=self.req(raw=raw,mime='application/json',headers=b'Content-Encoding: gzip\r\n');self.assertEqual(r['outcome'],'success');self.assertEqual(wire,raw)
 def test_disconnect_still_drains(self):
  _,r,_=self.req(broken=True);self.assertTrue(Proc.drained);self.assertTrue(r['upstream_completed']);self.assertFalse(r['downstream_complete_write']);self.assertEqual(r['outcome'],'failure');self.assertEqual(self.events[-1][1]['failure_kind'],'downstream_disconnected')
 def test_invalid_tools_and_closed_admission(self):
  code,r,_=self.req(payload={'model':'model-test','tools':[{'type':'web_search'}]});self.assertEqual(code,[400]);self.assertIsNone(r);self.assertEqual(self.events,[])
  code,r,_=self.req(closed=True);self.assertEqual(code,[410]);self.assertIsNone(r)
 def test_claude_messages_unchanged(self):
  _,r,wire=self.req(engine='claude',route='/v1/messages',raw=b'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}\n\ndata: {"type":"message_stop"}\n\n');self.assertEqual(r['outcome'],'success');self.assertEqual(r['usage']['input_tokens'],5);self.assertIn(b'anthropic-version',Proc.cfg)
 def test_base_routes(self):
  self.assertEqual(aihubmix_provider.upstream_url('https://a.invalid/api/v1','/v1/responses/compact'),'https://a.invalid/api/v1/responses/compact')
  self.assertEqual(aihubmix_provider.upstream_url('https://a.invalid','/v1/messages'),'https://a.invalid/v1/messages')
if __name__=='__main__':unittest.main(verbosity=2)
