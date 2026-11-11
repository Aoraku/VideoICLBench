"""Official @moonshot-ai/kimi-code2.5.0 adapter; inference stays native."""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION='2.5.0'
SUPPORTED_CLI_VERSION=VERSION
SUPPORTED_VERSIONS=(VERSION,)
def _get(options,key,default=None):
    return options.get(key,default)if isinstance(options,dict)else getattr(options,key,default)
def _private(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise ValueError('Refusing symlink in private Kimi profile')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.chmod(path,0o600)
    with os.fdopen(fd,'w')as stream:stream.write(value if isinstance(value,str)else json.dumps(value,indent=2))

def configure(profile,workspace,model,server,provider,options):
    profile,workspace=Path(profile).resolve(),Path(workspace).resolve()
    profile.mkdir(parents=True,exist_ok=True,mode=0o700);(profile/'empty-skills').mkdir(exist_ok=True,mode=0o700)
    requested_window,compact=_get(options,'context_window'),_get(options,'compact_tokens')
    window=1048576 if type(requested_window)is int and requested_window==1050000 else requested_window
    if type(window)is not int or type(compact)is not int or not 0<compact<window:
        raise ValueError('Kimi requires explicit provider-supported window and lower compact threshold')
    if window>1048576:raise ValueError('Kimi Code model window exceeds the admitted1048576 limit')
    ratio=compact/window
    if not .5<=ratio<=.99:raise ValueError('Kimi native compaction ratio must be .5..99')
    if provider.get('wire_api','chat')not in ('chat','chat_completions','openai_chat_completions'):
        raise ValueError('Kimi adapter admits Chat Completions only; Responses is not admitted')
    if not provider.get('base_url')or not provider.get('api_key'):raise ValueError('Kimi requires explicit base_url/api_key')
    old=json.loads((profile/'kimi-adapter.json').read_text())if(profile/'kimi-adapter.json').exists()else{}
    identity=dict(engine='kimi',version=VERSION,model=model,workspace=str(workspace),context_window=window,compact_tokens=compact)
    if old and any(old.get(k)!=v for k,v in identity.items()):raise ValueError('Refusing different Kimi session profile')
    q=json.dumps
    config='\n'.join([
        'default_model = "evaluation-model"','telemetry = false','merge_all_available_skills = false',
        '[providers.evaluation-provider]','type = "openai"','base_url = '+q(provider['base_url']),'api_key = '+q(provider['api_key']),
        '[models.evaluation-model]','provider = "evaluation-provider"','model = '+q(model),'max_context_size = '+str(window),
        'capabilities = ["image_in", "thinking", "tool_use"]','[thinking]',
        'enabled = '+('false'if _get(options,'effort','high')=='off'else'true'),'effort = '+q(_get(options,'effort','high')),'keep = "all"',
        '[tools]','enabled = ["mcp__vic__*"]','[loop_control]','max_steps_per_turn = 1000','max_attempts_per_step = 3',
        'reserved_context_size = '+str(window-compact),'compaction_trigger_ratio = '+repr(ratio),
        '[mcp]','startup_timeout_ms = 60000','tool_timeout_ms = '+str(int(server.get('tool_timeout_sec',3600)*1000)),
        '[database]','global_search = false','[experimental]','micro_compaction = false','[image]','max_edge_px = 2000',
    ])+'\n'
    _private(profile/'config.toml',config);_private(profile/'tui.toml','[upgrade]\nauto_install = false\n')
    mcp=dict(command=str(server['command']),args=list(map(str,server.get('args',[]))),deferred=False)
    if server.get('env'):mcp['env']=server['env']
    _private(profile/'mcp.json',{'mcpServers':{'vic':mcp}})
    _private(profile/'agent.md','---\nname: videoicl-gui-only\ndescription: GUI-only evaluation agent\ntools:\n  - mcp__vic__*\nsubagents: []\n---\nUse only the supplied GUI MCP tools. Follow the user task and public controls.\n')
    receipt=dict(identity,requested_context_window=requested_window,session_id=old.get('session_id'),native_compaction=True,native_tools=[],mcp_servers=['vic'],credentials_included=False,package='@moonshot-ai/kimi-code',media_patch_required=False)
    if not old:_private(profile/'kimi-attempt.json',_cursor(None,None,b''))
    _private(profile/'kimi-adapter.json',receipt);return receipt

def _session_file(profile,session_id):
    if not isinstance(session_id,str)or not re.fullmatch(r'[A-Za-z0-9_-]+',session_id):raise ValueError('Invalid Kimi session ID')
    files=list((profile/'sessions').glob('*/'+session_id+'/agents/main/wire.jsonl'))
    if len(files)!=1 or not files[0].stat().st_size:raise ValueError('Kimi session absent/ambiguous; refusing implicit new session')
    return files[0]

def _cursor(session_id,wire,raw):
    return {'attempt_id':str(uuid.uuid4()),'session_id':session_id,'wire_file':str(wire.resolve())if wire else None,
            'byte_offset':len(raw),'prefix_sha256':hashlib.sha256(raw).hexdigest(),
            'prefix_lines':len(raw.splitlines()),'usage_scope':'attempt'}

def command(profile,workspace,model,*,binary=None,resume=None):
    profile,workspace=Path(profile).resolve(),Path(workspace).resolve();meta=json.loads((profile/'kimi-adapter.json').read_text())
    if meta['workspace']!=str(workspace)or meta['model']!=model:raise ValueError('Kimi model/workspace identity changed')
    executable=str(Path(shutil.which(str(binary or'kimi'))or str(binary or'kimi')).resolve())
    env={'KIMI_CODE_HOME':str(profile)}
    probe_env={k:v for k,v in os.environ.items()if k in ('PATH','HOME','TMPDIR','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR')};probe_env.update(env)
    version=subprocess.check_output([executable,'--version'],text=True,env=probe_env,timeout=15).strip()
    if version!=VERSION:raise ValueError('Require official Kimi Code2.5.0; legacy Python/stub or unknown version refused')
    args=['--model','evaluation-model','--output-format','stream-json','--skills-dir',str(profile/'empty-skills')]
    if resume:
        if meta.get('session_id')!=resume:raise ValueError('Kimi exact original session ID required')
        wire=_session_file(profile,resume);raw=wire.read_bytes()
        if not raw.endswith(b'\n'):raise ValueError('Kimi wire has an incomplete last record; do not resume in-flight session')
        cursor=_cursor(resume,wire,raw);args+=['--session',resume]
    else:
        if meta.get('session_id'):raise ValueError('Existing Kimi session requires explicit resume')
        cursor=_cursor(None,None,b'')
        args+=['--agent-file',str(profile/'agent.md')]
    _private(profile/'kimi-attempt.json',cursor)
    return [sys.executable,str(Path(__file__).resolve()),'--invoke-native',executable,str(workspace),*args],env

def _text(content):
    if isinstance(content,str):return content
    return ''.join(x.get('text','')for x in content or[]if isinstance(x,dict)and x.get('type')=='text')

def _usage(usages):
    if not usages:return None
    totals={k:sum(u[k]for u in usages)if all(type(u.get(k))is int for u in usages)else None for k in ('inputOther','inputCacheRead','inputCacheCreation','output')}
    ins=[totals[k]for k in ('inputOther','inputCacheRead','inputCacheCreation')]
    return {'input_tokens':sum(ins)if all(x is not None for x in ins)else None,'cached_input_tokens':totals['inputCacheRead'],'cache_creation_input_tokens':totals['inputCacheCreation'],'output_tokens':totals['output'],'native_usage_records':len(usages),**totals}

def _bound_cursor(output,profile,session_id):
    """Bind repeated summaries to their attempt even after a later resume."""
    raw=output.read_bytes();stat=output.stat();key=str(output.resolve())
    fingerprint=hashlib.sha256(raw).hexdigest()+':'+str(stat.st_mtime_ns)+':'+str(len(raw))
    path=profile/'kimi-output-attempts.json';bindings=json.loads(path.read_text())if path.exists()else{}
    bound=bindings.get(key,{})
    if bound.get('fingerprint')==fingerprint:return bound['cursor']
    cursor=json.loads((profile/'kimi-attempt.json').read_text())
    if session_id:
        try:
            wire=_session_file(profile,session_id);native=wire.read_bytes()
            cursor.update(end_byte_offset=len(native),end_prefix_sha256=hashlib.sha256(native).hexdigest())
        except ValueError:pass
    bindings[key]={'fingerprint':fingerprint,'cursor':cursor};_private(path,bindings)
    return cursor

def recover_persisted_session(profile, meta):
    """Recover an interrupted first attempt only from one strictly bound wire."""
    profile = Path(profile)
    cursor = json.loads((profile/'kimi-attempt.json').read_text())
    if meta.get('session_id') or cursor.get('session_id') or cursor.get('wire_file') or cursor.get('byte_offset') != 0:
        raise ValueError('Not an unbound first attempt')
    files = list((profile/'sessions').glob('*/session_*/agents/main/wire.jsonl'))
    if len(files) != 1:
        raise ValueError('Missing or ambiguous persisted Kimi session')
    wire = files[0]
    sid = wire.parents[2].name
    if wire.resolve() != _session_file(profile, sid).resolve() or not wire.resolve().is_relative_to(profile.resolve()):
        raise ValueError('Kimi session path escaped profile')
    raw = wire.read_bytes()
    if not raw.endswith(b'\n'):
        raise ValueError('Incomplete native session wire')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    workspace = meta['workspace']
    binds = [x for x in rows if x.get('type') == 'profile.bind' and x.get('agentId') == 'main']
    if not binds or any(x.get('environmentDisclosure', {}).get('cwd') != workspace or x.get('modelAlias') != 'evaluation-model' for x in binds):
        raise ValueError('Persisted session workspace/model binding mismatch')
    mappings = [x.get('workspacePrimaryByWorkspace', {}) for x in rows if x.get('type') == 'changeNotifier.snapshot']
    if not mappings or any(x.get(wire.parents[3].name) != workspace for x in mappings):
        raise ValueError('Persisted workspace identity mismatch')
    models = {x.get('model') for x in rows if x.get('type') == 'llm.request' and x.get('agentId') == 'main'}
    if models != {meta['model']}:
        raise ValueError('Persisted request model mismatch')
    return sid


def summarize(output:Path,profile:Path,session_id=None):
    profile=Path(profile);meta_path=profile/'kimi-adapter.json';meta=json.loads(meta_path.read_text())if meta_path.exists()else{}
    result=dict(engine='kimi',session_id=session_id or meta.get('session_id'),final_text='',usage=None,errors=[],compaction_events=[],tool_calls=[],model_response_observed=False,is_error=False)
    for line in Path(output).read_text(errors='replace').splitlines():
        try:event=json.loads(line)
        except ValueError:
            if line.strip():result['errors'].append({'source':'native_stdout','message':line[:2000]})
            continue
        if not isinstance(event,dict):continue
        if event.get('type')=='session.resume_hint':
            sid=event.get('session_id')
            if result['session_id']and sid!=result['session_id']:result['errors'].append({'message':'Native Kimi session ID mismatch'})
            else:result['session_id']=sid
        if event.get('role')=='assistant':
            result['model_response_observed']=True;text=_text(event.get('content'))
            if text:result['final_text']=text
            for tool in event.get('tool_calls')or[]:
                fn=tool.get('function',{});result['tool_calls'].append({'id':tool.get('id'),'name':fn.get('name'),'arguments':fn.get('arguments')})
        if event.get('type')=='error'or event.get('is_error'):result['errors'].append(event)
    if not result['session_id'] and meta:
        try:
            result['session_id'] = recover_persisted_session(profile, meta)
            result['session_identity_source'] = 'unique_persisted_workspace_and_model_binding'
        except (ValueError, KeyError, OSError) as exc:
            result['errors'].append({'message': 'Cannot recover persisted session: '+str(exc)})
    sid=result['session_id'];cursor=_bound_cursor(Path(output),profile,sid)
    result.update(usage_scope='attempt',usage_cursor=cursor,session_usage=None)
    usages=[];session_usages=[];seen=set();compact=False;last_turn_error=False
    if sid:
        try:wire=_session_file(profile,sid)
        except ValueError as e:result['errors'].append({'message':str(e)});wire=None
        if wire:
            raw=wire.read_bytes();offset=cursor['byte_offset'];end=cursor.get('end_byte_offset',len(raw))
            valid_cursor=(type(offset)is int and 0<=offset<=len(raw)
                          and hashlib.sha256(raw[:offset]).hexdigest()==cursor['prefix_sha256']
                          and type(end)is int and offset<=end<=len(raw)
                          and ('end_prefix_sha256'not in cursor or hashlib.sha256(raw[:end]).hexdigest()==cursor['end_prefix_sha256'])
                          and cursor.get('session_id')in(None,sid)
                          and cursor.get('wire_file')in(None,str(wire.resolve())))
            if not valid_cursor:
                result['errors'].append({'message':'Kimi wire prefix changed/truncated or cursor identity mismatch; usage refused'})
                raw=b''
            else:raw=raw[:end]
            position=0;session_usage_valid=True
            for number,line in enumerate(raw.splitlines(keepends=True),1):
                in_attempt=position>=offset;position+=len(line)
                if not line.strip():continue
                try:event=json.loads(line)
                except ValueError:
                    session_usage_valid=False
                    if in_attempt:result['errors'].append({'message':'Malformed native Kimi wire JSON','line':number})
                    continue
                kind=event.get('type');payload=event.get('payload',event)
                if kind=='usage.record'and isinstance(payload.get('usage'),dict):
                    ident=event.get('id')or(str(wire),number)
                    if ident not in seen:
                        seen.add(ident);session_usages.append(payload['usage'])
                        if in_attempt:usages.append(payload['usage'])
                if not in_attempt:continue
                if kind in('turn.prompt','turn.started'):compact=False;last_turn_error=False
                if kind in ('full_compaction.begin','full_compaction.complete','full_compaction.cancel'):
                    compact=kind=='full_compaction.begin';result['compaction_events'].append({'source':'native_wire','type':kind,'line':number,'timestamp':event.get('time')})
                if kind=='turn.ended':
                    reason=payload.get('reason',payload.get('status'))
                    result['native_turn_end_reason']=reason
                    last_turn_error=reason in('failed','error','cancelled','interrupted','blocked')
            # Provider failure still owns a real native session. Preserve its
            # ID so recovery cannot accidentally create a replacement session.
            if meta and meta.get('session_id')in(None,sid):meta['session_id']=sid;_private(meta_path,meta)
            if session_usage_valid:result['session_usage']=_usage(session_usages)
    result['usage']=_usage(usages)
    result['native_compaction_incomplete']=compact
    if not result['model_response_observed']:result['errors'].append({'message':'No native Kimi assistant response; exit0/stub is not success'})
    result['is_error']=bool(result['errors']or compact or last_turn_error);return result

if __name__=='__main__':
    if len(sys.argv)<5 or sys.argv[1]!='--invoke-native':raise SystemExit('Internal CLI bridge only')
    prompt=sys.stdin.read()
    if not prompt.strip():raise SystemExit('Empty native Kimi prompt')
    os.chdir(sys.argv[3]);os.execv(sys.argv[2],[sys.argv[2],*sys.argv[4:],'--prompt',prompt])
