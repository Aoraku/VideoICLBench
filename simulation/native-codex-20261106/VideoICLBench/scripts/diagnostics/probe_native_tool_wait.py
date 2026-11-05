#!/usr/bin/env python3
"""Real Codex + synthetic localhost Responses/MCP wait test. No provider/GPU calls."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def mcp_main(log_path, seconds):
    log_path = pathlib.Path(log_path)
    def log(kind, **kwargs):
        with log_path.open('a') as stream:
            stream.write(json.dumps(dict(event=kind, at=time.time(), **kwargs))+'\n')
    for line in sys.stdin:
        request=json.loads(line);method=request.get('method');rid=request.get('id')
        if rid is None:
            if method and 'cancel' in method:log('cancel_notification', method=method)
            continue
        if method=='initialize':
            result={'protocolVersion':request.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'synthetic-slow','version':'1'}}
        elif method=='tools/list':
            result={'tools':[{'name':'wait_once','description':'Synthetic diagnostic: await completion and return ACK after the configured delay. No robot or model API.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]}
        elif method=='tools/call':
            log('tool_start',request_id=rid);time.sleep(seconds);log('tool_end',request_id=rid)
            result={'content':[{'type':'text','text':'ACK: synthetic wait completed'}],'isError':False}
        elif method=='ping':result={}
        else:
            print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unsupported method'}}),flush=True);continue
        print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)


def flatten_tools(tools, namespace=None):
    found=[]
    for tool in tools:
        found.append({'name':tool.get('name'),'type':tool.get('type'),'namespace':namespace})
        found.extend(flatten_tools(tool.get('tools',[]), tool.get('name') if tool.get('type')=='namespace' else namespace))
    return found


def request_tools(body):
    advertised=list(body.get('tools',[]))
    for message in body.get('input',[]):
        if isinstance(message,dict) and message.get('type') in ('additional_tools','tool_search_output'):
            advertised.extend(message.get('tools',[]))
    return advertised, flatten_tools(advertised)


def run_probe(binary, output_dir, seconds=35., mode='explicit_off', model_catalog=None, exec_yield_ms=None, eager_tools=False):
    root=pathlib.Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=False)
    profile=root/'profile';profile.mkdir();workspace=root/'workspace';workspace.mkdir()
    records=[];mcp_log=root/'mcp-events.jsonl';failures=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            index=len(records)+1;advertised,tools=request_tools(body);records.append({'index':index,'at':time.time(),'path':self.path,'tools':tools,'advertised_tools':advertised,'input':body.get('input'),'model':body.get('model')})
            if index>3:
                self.send_error(500,'Synthetic request cap exceeded');return
            if not any(e.get('slow_call') for e in records):
                names=[t['name']for t in tools if t.get('name')]
                direct=next((name for name in names if 'wait_once' in name),None)
                if direct:
                    records[-1]['slow_call']=True
                    item={'id':'fc_synthetic','type':'function_call','call_id':'call_synthetic_slow','name':direct,'namespace':next(t.get('namespace') for t in tools if t.get('name')==direct),'arguments':'{}','status':'completed'}
                elif 'exec' in names:
                    records[-1]['slow_call']=True
                    item={'id':'ct_synthetic','type':'custom_tool_call','call_id':'call_synthetic_slow','name':'exec','input':'const r=await tools.mcp__slow__wait_once({}); for(const c of r.content??[])if(c.type==="text")text(c.text);','status':'completed'}
                elif any(t['type']=='tool_search'for t in tools) and index==1:
                    item={'id':'ts_synthetic','type':'tool_search_call','call_id':'call_discovery','execution':'client','arguments':{'query':'slow wait_once','limit':1},'status':'completed'}
                else:
                    failures.append('No direct wait_once or exec in request schema')
                    item={'id':'msg_unknown','type':'message','role':'assistant','content':[{'type':'output_text','text':'NO_TOOL_SCHEMA','annotations':[]}],'status':'completed'}
            else:
                item={'id':'msg_synthetic','type':'message','role':'assistant','content':[{'type':'output_text','text':'OK','annotations':[]}],'status':'completed'}
            response={'id':'resp_synthetic_'+str(index),'object':'response','created_at':int(time.time()),'status':'completed','model':body.get('model'),'output':[item],'usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
            added=dict(item,status='in_progress')
            events=[('response.created',{'response':dict(response,status='in_progress',output=[])}),('response.output_item.added',{'output_index':0,'item':added}),('response.output_item.done',{'output_index':0,'item':item}),('response.completed',{'response':response})]
            payload=''.join('event: '+name+'\ndata: '+json.dumps(dict(type=name,sequence_number=i,**data))+'\n\n'for i,(name,data)in enumerate(events))
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(payload.encode())));self.end_headers();self.wfile.write(payload.encode());self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    features={k:False for k in ('shell_tool','unified_exec','apps','plugins','remote_plugin','skill_search','browser_use','computer_use','in_app_browser','multi_agent','memories','image_generation','goals','workspace_dependencies')}
    features['skip_host_skill_discovery']=True
    if eager_tools:features.update(incremental_tools=False,tool_search_always_defer_mcp_tools=False)
    if mode=='explicit_off':features.update(code_mode=False,code_mode_only=False)
    elif mode=='host_off':features.update(code_mode=False,code_mode_only=False,code_mode_host=False)
    elif mode!='omitted':raise ValueError(mode)
    q=json.dumps
    config=['model = "gpt-6-astra"','model_provider = "synthetic"','model_reasoning_effort = "high"','approval_policy = "never"','sandbox_mode = "read-only"','web_search = "disabled"','project_doc_max_bytes = 0','[features]']
    if model_catalog:config.insert(0, 'model_catalog_json = '+q(str(pathlib.Path(model_catalog).resolve())))
    config.extend(k+' = '+str(v).lower()for k,v in features.items())
    if exec_yield_ms is not None:config.extend(['[code_mode]',f'default_exec_yield_time_ms = {int(exec_yield_ms)}'])
    config+=['[model_providers.synthetic]','name = "LOCALHOST SYNTHETIC ONLY"',f'base_url = "http://127.0.0.1:{server.server_port}/v1"','wire_api = "responses"','env_key = "SYNTHETIC_TEST_KEY"','request_max_retries = 0','stream_max_retries = 0','stream_idle_timeout_ms = 120000','[mcp_servers.slow]',f'command = {q(sys.executable)}',f'args = {q([str(pathlib.Path(__file__).resolve()),"--mcp-server",str(mcp_log),"--delay",str(seconds)])}','required = true','startup_timeout_sec = 20','tool_timeout_sec = 90','default_tools_approval_mode = "approve"']
    (profile/'config.toml').write_text('\n'.join(config)+'\n')
    env={k:v for k,v in os.environ.items()if k in ('PATH','HOME','TMPDIR','SystemRoot','LANG','LC_ALL')};env.update(CODEX_HOME=str(profile),SYNTHETIC_TEST_KEY='dummy-localhost-only',NO_PROXY='127.0.0.1,localhost')
    version=subprocess.run([str(binary),'--version'],capture_output=True,text=True,env=env,timeout=10).stdout.strip()
    cmd=[str(binary),'exec','--json','--skip-git-repo-check','--ephemeral','--model','gpt-6-astra','-C',str(workspace),'-']
    started=time.time()
    try:
        result=subprocess.run(cmd,input='Call wait_once once and await its completion, then say OK.',text=True,capture_output=True,env=env,timeout=max(90,seconds+45))
        (root/'stdout.jsonl').write_text(result.stdout);(root/'stderr.log').write_text(result.stderr);exit_code=result.returncode
    finally:
        server.shutdown();server.server_close()
    mcp_events=[json.loads(line)for line in mcp_log.read_text().splitlines()]if mcp_log.exists()else[]
    starts=[e for e in mcp_events if e['event']=='tool_start'];ends=[e for e in mcp_events if e['event']=='tool_end'];names=[t['name']for t in records[0]['tools']]if records else[]
    slow_record=next((r for r in records if r.get('slow_call')),None)
    following=next((r for r in records if slow_record and r['index']>slow_record['index']),None)
    second_at=following['at'] if following else None
    direct=any(t.get('name') and 'wait_once'in t['name'] for t in (slow_record or {}).get('tools',[]))
    completed_before_next=bool(ends and second_at is not None and second_at>=ends[0]['at'])
    passed=exit_code==0 and len(starts)==len(ends)==1 and completed_before_next and not any(e['event']=='cancel_notification'for e in mcp_events)and direct and 'exec'not in names and 'wait'not in names
    report={'schema':'native-localhost-tool-wait-probe-v1','mode':mode,'exec_yield_ms':exec_yield_ms,'eager_tools':eager_tools,'model_catalog_override':str(model_catalog) if model_catalog else None,'binary':str(binary),'cli_version':version,'synthetic_provider':True,'external_api_requests':0,'gpu_processes_started':0,'mock_requests':len(records),'configured_delay_seconds':seconds,'duration_seconds':time.time()-started,'exit_code':exit_code,'first_request_tools':records[0]['tools']if records else[],'mcp_events':mcp_events,'second_request_at':second_at,'second_request_after_mcp_complete':completed_before_next,'slow_call_request_index':slow_record['index'] if slow_record else None,'direct_tool_wait_passed':passed,'failures':failures}
    (root/'requests.private.json').write_text(json.dumps(records,indent=2)+'\n');(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def gui_mcp_main(log_path, seconds):
    """Actual embodied MCP server with a CPU-only fake browser boundary."""
    from vic_sdk.embodied_gui_mcp import make_server
    from mcp.types import CallToolResult, TextContent, ImageContent
    class FakeBrowser:
        condition='sim'
        generation=0
        def log(self,event,**kw):
            with open(log_path,'a') as f:f.write(json.dumps(dict(event=event,at=time.time(),**kw))+'\n')
        def check(self):pass
        def picture(self):
            return CallToolResult(content=[TextContent(type='text',text=json.dumps({'frame_id':f'synthetic-{self.generation}','synthetic_no_robot':True})),ImageContent(type='image',mimeType='image/png',data='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1cAAAAASUVORK5CYII=')])
        def observe(self):self.log('observe',generation=self.generation);return self.picture()
        def act(self,frame_id,inputs):
            if frame_id != f'synthetic-{self.generation}':raise ValueError('stale frame')
            self.log('tool_start',frame_id=frame_id);time.sleep(seconds);self.generation+=1;self.log('tool_end',generation=self.generation);return self.picture()
        def terminal(self,kind,summary,frame_id=None):self.log('terminal',kind=kind);return self.picture()
        def unavailable(self,reason):self.log('unavailable',reason=reason)
        def demo_info(self):return {'synthetic_no_media':True}
        def demo_frame(self,seconds):return self.picture()
    make_server(FakeBrowser()).run(transport='stdio')


def run_harness_probe(binary,output_dir,seconds=65.,inject_503=True,adversarial=False):
    """Unmodified codex_config + official bundled catalog + real GUI MCP schema."""
    from vic_sdk.native_agent import codex_config
    from vic_sdk.direct_tools import freeze_direct_model_catalog
    root=pathlib.Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=False)
    profile=root/'profile';profile.mkdir();workspace=root/'workspace';workspace.mkdir()
    env={k:v for k,v in os.environ.items()if k in ('PATH','HOME','TMPDIR','SystemRoot','LANG','LC_ALL','PYTHONPATH')}
    if env.get('PYTHONPATH'):env['PYTHONPATH']=os.pathsep.join(str(pathlib.Path(p).resolve())for p in env['PYTHONPATH'].split(os.pathsep))
    env.update(CODEX_HOME=str(profile),VIC_MODEL_API_KEY='dummy-localhost-only',NO_PROXY='127.0.0.1,localhost')
    version=subprocess.run([str(binary),'--version'],capture_output=True,text=True,env=env,check=True,timeout=10).stdout.strip()
    catalog=subprocess.run([str(binary),'debug','models','--bundled'],capture_output=True,env=env,check=True,timeout=10).stdout
    source=root/'bundled-model-catalog.private.json';source.write_bytes(catalog)
    receipt=freeze_direct_model_catalog(profile,source,hashlib.sha256(catalog).hexdigest(),'gpt-6-astra',cli_version=version)
    records=[];events=root/'mcp-events.jsonl';phase=0;injected=False
    allowed={'observe','act','done','giveup','demo_info','demo_frame','demo_frames'}
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            nonlocal phase,injected
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));advertised,tools=request_tools(body)
            record={'index':len(records)+1,'at':time.time(),'phase':phase,'body_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),'body':body,'tools':tools,'status':200}
            records.append(record)
            if len(records)>20:self.send_error(500,'Synthetic cap');return
            discovery=any(t['type']=='tool_search' for t in records[0]['tools'])
            retry_phase=3 if discovery else 2
            step=phase if discovery else phase+1
            if phase==retry_phase and inject_503 and not injected and not adversarial:
                injected=True;record['status']=503
                payload=json.dumps({'error':{'message':'Synthetic transient failure','type':'server_error','code':'synthetic_503'}}).encode()
                self.send_response(503);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
            def call(name,args):
                return {'id':'fc_'+str(len(records)),'type':'function_call','call_id':'call_'+str(len(records)),'namespace':'mcp__vic','name':name,'arguments':json.dumps(args),'status':'completed'}
            if adversarial:
                bad_calls=[('functions','apply_patch','*** Begin Patch\n*** Add File: forbidden-probe-marker.txt\n+unexpected\n*** End Patch','custom'),('clock','sleep',{'duration_ms':1},'function'),('collaboration','list_agents',{},'function'),('functions','exec','text(\"unexpected\")','custom'),('functions','wait',{'cell_id':'none','terminate':True},'function'),('functions','view_image',{'path':str(source)},'function'),('functions','exec_command',{'cmd':'pwd'},'function'),('functions','read_mcp_resource',{'server':'vic','uri':'file:///synthetic-no-resource'},'function')]
                bad_calls += [('multi_agent_v1',name,{},'function') for name in ('spawn_agent','send_input','resume_agent','close_agent','wait_agent')]
                if phase<len(bad_calls):
                    namespace,name,arguments,kind=bad_calls[phase]
                    item={'id':'bad_'+str(phase),'type':'custom_tool_call'if kind=='custom'else'function_call','call_id':'badcall_'+str(phase),'namespace':namespace,'name':name,'status':'completed'}
                    item['input'if kind=='custom'else'arguments']=arguments if kind=='custom'else json.dumps(arguments)
                else:item={'id':'msg_ok','type':'message','role':'assistant','content':[{'type':'output_text','text':'OK','annotations':[]}],'status':'completed'}
            elif step==0:
                item={'id':'ts_1','type':'tool_search_call','call_id':'discover_1','execution':'client','arguments':{'query':'vic observe act done giveup demo','limit':7},'status':'completed'}
            elif step==1:item=call('observe',{})
            elif step==2:item=call('act',{'frame_id':'synthetic-0','inputs':[{'kind':'click','x':10,'y':10}]})
            elif step==3:item=call('observe',{})
            elif step==4:item=call('done',{'summary':'Synthetic transport complete','frame_id':'synthetic-1'})
            else:item={'id':'msg_ok','type':'message','role':'assistant','content':[{'type':'output_text','text':'OK','annotations':[]}],'status':'completed'}
            phase+=1
            response={'id':'resp_'+str(len(records)),'object':'response','created_at':int(time.time()),'status':'completed','model':body.get('model'),'output':[item],'usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
            chunks=[('response.created',{'response':dict(response,status='in_progress',output=[])}),('response.output_item.added',{'output_index':0,'item':dict(item,status='in_progress')}),('response.output_item.done',{'output_index':0,'item':item}),('response.completed',{'response':response})]
            payload=''.join('event: '+name+'\ndata: '+json.dumps(dict(type=name,sequence_number=i,**data))+'\n\n'for i,(name,data)in enumerate(chunks)).encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    mcp={'command':sys.executable,'args':[str(pathlib.Path(__file__).resolve()),'--gui-mcp-server',str(events),'--delay',str(seconds)],'startup_timeout_sec':30,'tool_timeout_sec':86400,'env':{'PYTHONPATH':env.get('PYTHONPATH','')}}
    config=codex_config('gpt-6-astra',f'http://127.0.0.1:{server.server_port}/v1',mcp,compact_tokens=32768,effort='high',isolated_tools=True,tool_output_tokens=4096,stream_idle_timeout_ms=86400000)
    config=config.replace('tools.view_image = false','tools.experimental_request_user_input.enabled = false\ntools.update_plan.enabled = false')
    config='model_catalog_json = '+json.dumps(receipt['catalog_path'])+'\n'+config
    (profile/'config.toml').write_text(config)
    started=time.time()
    try:
        result=subprocess.run([str(binary),'exec','--json','--skip-git-repo-check','--ephemeral','-C',str(workspace),'-'],input='Observe, perform one visible GUI action, wait for its completed observation, then observe and finish.',text=True,capture_output=True,env=env,timeout=seconds+90)
    finally:server.shutdown();server.server_close()
    (root/'stdout.jsonl').write_text(result.stdout);(root/'stderr.log').write_text(result.stderr)
    mcp_events=[json.loads(x)for x in events.read_text().splitlines()]if events.exists()else[]
    start=next((x['at']for x in mcp_events if x['event']=='tool_start'),None);end=next((x['at']for x in mcp_events if x['event']=='tool_end'),None)
    during=[r['index']for r in records if start is not None and start<r['at']<(end or float('inf'))]
    forbidden=sorted({(str(t.get('namespace')),str(t.get('name')))for r in records for t in r['tools']if t.get('type')not in ('namespace','tool_search')and not(t.get('namespace')=='mcp__vic'and t.get('name')in allowed)})
    discovery=bool(records) and any(t['type']=='tool_search' for t in records[0]['tools'])
    first_gui={t['name'] for t in records[0]['tools'] if t.get('namespace')=='mcp__vic'} if records else set()
    eager=not discovery and first_gui==allowed
    retry=[r for r in records if r['phase']==(3 if discovery else 2)]
    stdout=[json.loads(x)for x in result.stdout.splitlines()if x.startswith('{')]
    thread_ids=[x.get('thread_id')for x in stdout if x.get('type')=='thread.started']
    outputs={x.get('call_id'):x.get('output') for r in records for x in r['body'].get('input',[]) if x.get('type') in ('function_call_output','custom_tool_call_output')}
    rejected={k:v for k,v in outputs.items() if k and k.startswith('badcall_')}
    safe_discovery={('functions','list_mcp_resources'),('functions','list_mcp_resource_templates'),('functions','read_mcp_resource')}
    scope_ok=bool(records)and all(tuple(pair) in safe_discovery for pair in forbidden)
    adversarial_ok=adversarial and all('unsupported' in str(rejected.get('badcall_'+str(i),'')) for i in [*range(7),*range(8,13)]) and 'Unknown resource' in str(rejected.get('badcall_7','')) and not mcp_events
    report={'schema':'native-harness-direct-eager-wait-v3','first_request_gui_tools':sorted(first_gui),'eager_gui_schema_passed':eager,'tool_search_advertised':discovery,'cli_version':version,'external_api_requests':0,'gpu_processes_started':0,'elapsed':time.time()-started,'configured_delay_seconds':seconds,'exit_code':result.returncode,'catalog_receipt':receipt,'requests':len(records),'request_statuses':[r['status']for r in records],'requests_during_action':during,'mcp_events':mcp_events,'only_gui_tools_exposed':bool(records)and not forbidden,'only_gui_and_discovery_tools_exposed':scope_ok,'adversarial_rejections':rejected,'adversarial_rejection_passed':adversarial_ok,'forbidden_exposed_tools':forbidden,'action_await_passed':bool(end and not during and end-start>=seconds),'single_native_session':len(thread_ids)==1,'adversarial':adversarial,'marker_created':(workspace/'forbidden-probe-marker.txt').exists(),'thread_ids':thread_ids,'retry_503_same_body':bool(len(retry)==2 and retry[0]['status']==503 and retry[0]['body_sha256']==retry[1]['body_sha256']),'retry_mode_preserved':bool(retry)and all(not any(t.get('name')in ('exec','wait')for t in r['tools'])for r in retry),'formal_readiness':False}
    (root/'requests.private.json').write_text(json.dumps(records,indent=2)+'\n');(root/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mcp-server');parser.add_argument('--gui-mcp-server');parser.add_argument('--harness',action='store_true');parser.add_argument('--adversarial',action='store_true');parser.add_argument('--delay',type=float,default=35.);parser.add_argument('--exec-yield-ms',type=int);parser.add_argument('--eager-tools',action='store_true');parser.add_argument('--model-catalog');parser.add_argument('--binary');parser.add_argument('--out');parser.add_argument('--mode',choices=['omitted','explicit_off','host_off'],default='explicit_off');args=parser.parse_args()
    if args.gui_mcp_server:gui_mcp_main(args.gui_mcp_server,args.delay);return
    if args.harness:print(json.dumps(run_harness_probe(args.binary,args.out,args.delay,adversarial=args.adversarial),indent=2));return
    if args.mcp_server:mcp_main(args.mcp_server,args.delay);return
    print(json.dumps(run_probe(args.binary,args.out,args.delay,args.mode,args.model_catalog,args.exec_yield_ms,args.eager_tools),indent=2))
if __name__=='__main__':main()
