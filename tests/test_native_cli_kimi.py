import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/sdk'))
from vic_sdk.native_cli_engines import kimi

class KimiAdapterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve();self.profile=self.root/'profile';self.workspace=self.root/'work';self.workspace.mkdir()
  self.provider={'base_url':'http://127.0.0.1:9999/v1','api_key':'dummy-private-key','wire_api':'chat'}
  self.options={'context_window':1050000,'compact_tokens':945000,'effort':'high'}
 def configure(self):return kimi.configure(self.profile,self.workspace,'test-model',{'command':'python','args':['mcp.py']},self.provider,self.options)
 def wire(self,events,sid='session_test-id'):
  p=self.profile/'sessions/wd_test'/sid/'agents/main';p.mkdir(parents=True,exist_ok=True)
  (p/'wire.jsonl').write_text('\n'.join(json.dumps(dict(type=kind,time=i,**payload))for i,(kind,payload)in enumerate(events))+'\n')
  return sid
 def output(self,events):
  p=self.root/'stdout.jsonl';p.write_text('\n'.join(json.dumps(x)for x in events)+'\n');return p
 def response(self,sid='session_test-id'):
  return [{'role':'meta','type':'session.resume_hint','session_id':sid},{'role':'assistant','content':'done'}]
 def test_private_toml_gui_only_native_compact(self):
  receipt=self.configure();text=(self.profile/'config.toml').read_text()
  self.assertNotIn('dummy-private-key',json.dumps(receipt));self.assertIn('reserved_context_size = 103576',text);self.assertIn('max_context_size = 1048576',text)
  self.assertEqual(receipt['context_window'],1048576);self.assertEqual(receipt['requested_context_window'],1050000)
  self.assertIn('enabled = ["mcp__vic__*"]',text);self.assertIn('type = "openai"',text)
  self.assertNotIn('${base_prompt}',(self.profile/'agent.md').read_text());self.assertIn('subagents: []',(self.profile/'agent.md').read_text())
  self.assertEqual(stat.S_IMODE((self.profile/'config.toml').stat().st_mode),0o600)
 def test_responses_and_unknown_context_refused(self):
  self.provider['wire_api']='responses'
  with self.assertRaisesRegex(ValueError,'Responses'):self.configure()
  self.provider['wire_api']='chat';self.options['context_window']=None
  with self.assertRaises(ValueError):self.configure()
 def test_model_context_cannot_change_on_existing_profile(self):
  self.configure();self.options['context_window']=2000000
  with self.assertRaises(ValueError):self.configure()
 def test_explicit_smaller_window_is_preserved(self):
  self.options.update(context_window=262144,compact_tokens=200000)
  receipt=self.configure();self.assertEqual(receipt['context_window'],262144);self.assertEqual(receipt['requested_context_window'],262144)
 def test_stub_and_unknown_native_version_refused(self):
  self.configure()
  for v in ('1.52.0\nkimi-cli is no longer maintained.\n','9.0.0'):
   with patch.object(kimi.subprocess,'check_output',return_value=v):
    with self.assertRaisesRegex(ValueError,'stub'):kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi')
 def test_initial_command_and_resume_are_distinct(self):
  self.configure()
  with patch.object(kimi.subprocess,'check_output',return_value='2.5.0\n'):
   cmd,env=kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi')
   self.assertIn('--agent-file',cmd);self.assertNotIn('--session',cmd);self.assertNotIn('--print',cmd)
   self.assertEqual(env['KIMI_CODE_HOME'],str(self.profile))
   with self.assertRaises(ValueError):kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi',resume='missing')
   sid=self.wire([]);kimi.summarize(self.output(self.response(sid)),self.profile)
   cmd,_=kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi',resume=sid)
   self.assertIn('--session',cmd);self.assertNotIn('--agent-file',cmd)
 def test_native_stdout_tools_and_session_are_preserved(self):
  self.configure();sid=self.wire([]);events=self.response(sid)
  events[1]={'role':'assistant','content':'answer','tool_calls':[{'id':'t','function':{'name':'mcp__vic__execute','arguments':'{}'}}]}
  r=kimi.summarize(self.output(events),self.profile)
  self.assertEqual(r['final_text'],'answer');self.assertEqual(r['tool_calls'][0]['name'],'mcp__vic__execute');self.assertEqual(r['session_id'],sid);self.assertIsNone(r['usage']);self.assertFalse(r['is_error'])
 def test_native_usage_and_compaction_records(self):
  self.configure();usage={'inputOther':10,'inputCacheRead':20,'inputCacheCreation':3,'output':4}
  sid=self.wire([('usage.record',{'usage':usage}),('full_compaction.begin',{}),('full_compaction.complete',{})])
  r=kimi.summarize(self.output(self.response(sid)),self.profile)
  self.assertEqual(r['usage']['input_tokens'],33);self.assertEqual(r['usage']['cached_input_tokens'],20);self.assertEqual(r['usage']['output_tokens'],4);self.assertEqual(len(r['compaction_events']),2)
 def test_missing_cache_is_not_zero_filled(self):
  self.configure();sid=self.wire([('usage.record',{'usage':{'inputOther':10,'output':4,'inputCacheCreation':0}})])
  r=kimi.summarize(self.output(self.response(sid)),self.profile)
  self.assertIsNone(r['usage']['input_tokens']);self.assertIsNone(r['usage']['cached_input_tokens'])
 def test_zero_exit_deprecation_notice_not_success(self):
  self.configure();p=self.root/'stub';p.write_text('kimi-cli is no longer maintained.\n')
  r=kimi.summarize(p,self.profile);self.assertTrue(r['is_error']);self.assertFalse(r['model_response_observed'])
 def test_session_mismatch_is_error(self):
  self.configure();sid=self.wire([]);r=kimi.summarize(self.output(self.response(sid)),self.profile,'different-session')
  self.assertTrue(r['is_error'])
 def test_failed_provider_keeps_native_session_for_resume(self):
  self.configure();sid=self.wire([('turn.started',{}),('turn.ended',{'status':'failed'})])
  r=kimi.summarize(self.output([self.response(sid)[0],{'type':'error','message':'quota'}]),self.profile)
  self.assertTrue(r['is_error']);self.assertEqual(json.loads((self.profile/'kimi-adapter.json').read_text())['session_id'],sid)
  with patch.object(kimi.subprocess,'check_output',return_value='2.5.0\n'):
   cmd,_=kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi',resume=sid)
   self.assertEqual(cmd[-1],sid)
 def test_resume_history_does_not_poison_final_turn(self):
  self.configure();sid=self.wire([('turn.prompt',{}),('full_compaction.begin',{}),('turn.ended',{'reason':'failed'}),('turn.prompt',{}),('turn.ended',{'reason':'completed'})])
  r=kimi.summarize(self.output(self.response(sid)),self.profile);self.assertFalse(r['is_error'])
 def test_native_blocked_turn_not_success(self):
  self.configure();sid=self.wire([('turn.prompt',{}),('turn.ended',{'reason':'blocked'})])
  r=kimi.summarize(self.output(self.response(sid)),self.profile);self.assertTrue(r['is_error']);self.assertEqual(r['native_turn_end_reason'],'blocked')
 def test_current_incomplete_compact_is_error(self):
  self.configure();sid=self.wire([('turn.started',{}),('full_compaction.begin',{})])
  self.assertTrue(kimi.summarize(self.output(self.response(sid)),self.profile)['is_error'])
 def prepared_resume(self):
  self.configure();first={'inputOther':80,'inputCacheRead':20,'inputCacheCreation':0,'output':4}
  sid=self.wire([('usage.record',{'usage':first}),('full_compaction.begin',{}),('full_compaction.complete',{})])
  out=self.root/'attempt1.jsonl';out.write_text('\n'.join(map(json.dumps,self.response(sid)))+'\n')
  previous=kimi.summarize(out,self.profile)
  with patch.object(kimi.subprocess,'check_output',return_value='2.5.0\n'):
   kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi',resume=sid)
  return sid,out,previous,kimi._session_file(self.profile,sid)
 def test_resume_usage_is_only_new_attempt(self):
  sid,out,previous,wire=self.prepared_resume()
  usage={'inputOther':40,'inputCacheRead':10,'inputCacheCreation':0,'output':4}
  with wire.open('a')as f:f.write(json.dumps({'type':'usage.record','usage':usage})+'\n')
  current=kimi.summarize(self.output(self.response(sid)),self.profile,sid)
  self.assertEqual(previous['usage']['input_tokens'],100);self.assertEqual(current['usage']['input_tokens'],50)
  self.assertEqual(current['usage']['cached_input_tokens'],10);self.assertEqual(current['usage']['output_tokens'],4)
  self.assertEqual(current['session_usage']['input_tokens'],150);self.assertEqual(current['usage_scope'],'attempt')
  self.assertEqual(current['compaction_events'],[])
  # A later resume must not change the meaning of an archived old output.
  old=kimi.summarize(out,self.profile,sid);self.assertEqual(old['usage']['input_tokens'],100)
  self.assertEqual(old['session_usage']['input_tokens'],100)
 def test_attempt_includes_only_its_new_compaction_usage(self):
  sid,out,previous,wire=self.prepared_resume()
  rows=[{'type':'full_compaction.begin'},
        {'type':'usage.record','usageScope':'session','usage':{'inputOther':8,'inputCacheRead':2,'inputCacheCreation':0,'output':1}},
        {'type':'full_compaction.complete'},
        {'type':'usage.record','usageScope':'turn','usage':{'inputOther':40,'inputCacheRead':10,'inputCacheCreation':0,'output':4}}]
  with wire.open('a')as f:f.write('\n'.join(map(json.dumps,rows))+'\n')
  r=kimi.summarize(self.output(self.response(sid)),self.profile,sid)
  self.assertEqual(r['usage']['input_tokens'],60);self.assertEqual(r['usage']['output_tokens'],5)
  self.assertEqual(r['session_usage']['input_tokens'],160);self.assertEqual(len(r['compaction_events']),2)
 def test_rewritten_wire_prefix_refuses_usage(self):
  sid,out,previous,wire=self.prepared_resume();raw=wire.read_bytes()
  wire.write_bytes(raw.replace(b'80',b'81',1)+json.dumps({'type':'usage.record','usage':{'inputOther':1,'inputCacheRead':0,'inputCacheCreation':0,'output':1}}).encode()+b'\n')
  r=kimi.summarize(self.output(self.response(sid)),self.profile,sid)
  self.assertTrue(r['is_error']);self.assertIsNone(r['usage']);self.assertIsNone(r['session_usage'])
  self.assertTrue(any('prefix'in e.get('message','')for e in r['errors']))
 def test_truncated_wire_prefix_refuses_usage(self):
  sid,out,previous,wire=self.prepared_resume();wire.write_text('{}\n')
  r=kimi.summarize(self.output(self.response(sid)),self.profile,sid)
  self.assertTrue(r['is_error']);self.assertIsNone(r['usage'])
 def test_resume_cursor_refuses_partial_record(self):
  sid,out,previous,wire=self.prepared_resume()
  with wire.open('ab')as f:f.write(b'{"in_flight":')
  with patch.object(kimi.subprocess,'check_output',return_value='2.5.0\n'):
   with self.assertRaisesRegex(ValueError,'in-flight'):kimi.command(self.profile,self.workspace,'test-model',binary='/tmp/kimi',resume=sid)
 def test_transparent_bridge_preserves_prompt_and_workspace(self):
  binary=self.root/'kimi-fake'
  binary.write_text('#!'+sys.executable+'\nimport sys,json,os\nif "--version" in sys.argv: print("2.5.0")\nelse: print(json.dumps({"argv":sys.argv[1:],"cwd":os.getcwd()}))\n');binary.chmod(0o700)
  self.configure();cmd,extra=kimi.command(self.profile,self.workspace,'test-model',binary=binary)
  prompt='GUI task\n中文 with $HOME `literal`'
  r=subprocess.run(cmd,input=prompt,text=True,capture_output=True,check=True,env=dict(os.environ,**extra));payload=json.loads(r.stdout)
  self.assertEqual(payload['argv'][-2:],['--prompt',prompt]);self.assertEqual(payload['cwd'],str(self.workspace))

if __name__=='__main__':unittest.main()
