"""Shared native CLI supervisor; GUI/control-plane identity owns every terminal."""
import argparse
import importlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

from transport import make_relay, TOOLS

SDK=Path(__file__).resolve().parents[1]/'VideoICLBench/packages/sdk'
GUI_PY=Path(os.environ.get('VIC_GUI_PYTHON', sys.executable))
MODELS={'qwen':'qwen3.8-max','gemini':'gemini-4-argon','dsh':'deepseek-v4.1-flash-1017','zcode':'glm-5.3-flash','kimi':'kimi-k3','codex':'gpt-6-astra','claude':'claude-opus-5-5'}
CLAUDE_ENGINES = ('qwen', 'claude')
BATCH_INSTRUCTIONS = (
    'Each action_batch commits its own sequence once and returns the updated GUI. '
    'You may then submit further action_batch calls using new operation IDs, '
    'up to the episode budget of 500 physical actions in total.'
)
sys.path.insert(0,str(SDK))

def read(path):
    return json.loads(path.read_text())

def save(path,obj):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2)+'\n')
    tmp.replace(path)

def hold(out,reason):
    save(out/'hold.json',{'reason':reason,'preserve_world':True,'time':time.time()})
    threading.Event().wait()

def run(args):
    import httpx
    from vic_sdk.embodied_recovery import checked_barrier
    engine=args.engine
    settings=worker_settings(args)
    model=settings['model']
    room=args.room.resolve();out=args.out.resolve()
    os.umask(0o077);out.mkdir(mode=0o700,exist_ok=False)
    save(out/'effective-config.json', settings)
    cfg=read(room/'computer-private.json')
    if cfg['condition']=='none':
        import transport
        transport.TOOLS = transport.TOOLS - {'demo_frames'}
    info=room/'worker-owner.json'
    connection_path=Path(read(info)['connection']) if info.exists() else room.parent/'gui/connection.private.json'
    connection=read(connection_path)
    identity=connection['identity']
    if cfg['program_episode_identity']!=identity or cfg['control_url']!=connection['control_url']:raise ValueError('wrong room owner')
    timing=Path(connection['api_timing_log']).resolve()
    owner=httpx.Client(base_url=connection['control_url'],trust_env=False,headers={'Authorization':'Bearer '+(connection_path.parent/connection['admin_token_file']).read_text().strip()},timeout=30)
    state=owner.get('/api/private/state');state.raise_for_status()
    barrier=checked_barrier(state.json(),identity)
    if barrier.get('status')!='running' or barrier['action_count'] or Path(barrier['api_timing_log']).resolve()!=timing:raise ValueError('not a fresh running owner at step zero')
    secret=sys.stdin.readline().strip()
    if engine=='gemini':secret=json.loads(secret)
    token=secrets.token_urlsafe(32)
    if engine in ('qwen','claude','dsh','zcode'):
        from anthropic_guard_relay import make_relay as make_anthropic_relay
        relay = make_anthropic_relay(engine, model, token, secret, out, timing)
    elif engine == 'kimi':
        from kimi_guard_relay import make_relay as make_kimi_relay
        relay = make_kimi_relay(engine, model, token, secret, out, timing)
    else:
        relay=make_relay(engine,model,token,secret,out,timing)
    threading.Thread(target=relay.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{relay.server_port}'
    workspace=out/'workspace';profile=out/'profile';workspace.mkdir();profile.mkdir()
    mcp={'command':str(GUI_PY),'args':[str(Path(__file__).resolve().with_name('lazy_mcp_gui.py')),'--sdk',str(SDK),'--config',str(room/'computer-private.json')],'tool_timeout_sec':86400}
    if engine=='zcode':mcp['args']+=['--image-ledger',str(out/'image-ledger.jsonl')]
    if engine in ('qwen','claude','zcode'):mcp['args']+=['--compact-depth']
    if engine in CLAUDE_ENGINES:
        binary=Path(settings['binary'])
        save(profile/'settings.json',{'autoCompactEnabled':True})
        save(profile/'mcp.json',{'mcpServers':{'vic':{k:mcp[k] for k in ('command','args')}}})
        save(profile/'claude-runtime.private.json',{'mcp':mcp,'base_url':base,'token':token})
        if engine=='claude':
            from vic_sdk.claude_structured import configure
            configure(profile,binary,model)
    else:
        module,binary=adapter_runtime(engine, settings['binary'])
        options=dict(settings)
        provider={'base_url':base,'api_key':token}
        if engine=='gemini':provider['api_version']='v1beta';mcp['includeTools']=sorted(TOOLS)
        elif engine=='kimi':provider['base_url']+='/v1'
        elif engine=='codex':
            provider['base_url']+='/v1'
            provider['wire_api']='responses'
        else:provider['wire_api']='messages'
        module.configure(profile,workspace,model,mcp,provider,options)
    if engine=='codex':
        record=read(profile/'codex-adapter.private.json')
        settings.update(native_cli_version=record['cli_version'],
                        derived_model_catalog_sha256=record['catalog_sha256'])
    settings['native_profile_configured']=True
    save(out/'effective-config.json', settings)
    prompt=(room/'prompt-1.txt').read_text()+'\n'+BATCH_INSTRUCTIONS
    if engine not in CLAUDE_ENGINES and engine!='codex':prompt+='\nFirst call observe for the current GUI. Use the public tools to complete the task. Use done or giveup for the terminal decision.'
    attempt_loop(engine=engine,room=room,out=out,owner=owner,identity=identity,binary=binary,module=None if engine in CLAUDE_ENGINES else module,
                 prompt=prompt,qwen_config=(mcp,base,token),relay=relay)



def worker_settings(args):
    engine = args.engine
    window = (262144 if engine == 'kimi' else 184000 if engine == 'zcode'
              else 1000000 if engine in (*CLAUDE_ENGINES, 'codex') else 1048576)
    compact = 150000
    if getattr(args, 'context_window', None) is not None:
        window = args.context_window
    if getattr(args, 'compact_tokens', None) is not None:
        compact = args.compact_tokens
    if type(window) is not int or window<=0:
        raise ValueError('Context window must be a positive integer')
    if engine!='zcode' and (type(compact) is not int or not 0 < compact < window):
        raise ValueError('Compaction must be positive and below the context window')
    if engine in ('dsh','kimi','gemini') and window>1048576:
        raise ValueError('Selected native CLI model supports at most 1048576 context tokens')
    if engine=='kimi' and not .5<=compact/window<=.99:
        raise ValueError('Kimi native compaction ratio must be .5..99')
    model=getattr(args,'model',None) or MODELS[engine]
    effort=getattr(args,'effort',None) or 'high'
    expected_compact=None
    if engine=='zcode':
        if effort!='high' or model!=MODELS[engine]:
            raise ValueError('The GLM provider adapter supports glm-5.3-flash with high effort')
        if getattr(args,'compact_tokens',None) is not None:
            raise ValueError('ZCode derives compaction from context/output budgets; --compact-tokens is unsupported')
        expected_compact=window-34000
        if expected_compact<=0:
            raise ValueError('ZCode context must leave its native output and compaction reserve')
        compact=None
    policy = ('native_context_output_budget' if engine=='zcode' else
              'claude_native_autocompact_80_percent_window' if engine in CLAUDE_ENGINES else
              'native_token_threshold')
    return dict(compaction_policy=policy, native_compact_expected_tokens=expected_compact,
                engine=engine, model=model, effort=effort, context_window=window,
                compact_tokens=compact, binary=str(cli_binary(engine, getattr(args, 'binary', None))),
                model_catalog=str(args.codex_model_catalog.resolve()) if getattr(args, 'codex_model_catalog', None) else None,
                model_catalog_sha256=getattr(args, 'codex_model_catalog_sha256', None),
                native_history=True, native_compaction=True)


def cli_binary(engine, override=None):
    name = 'VIC_CLI_' + engine.upper()
    path = override or os.environ.get(name)
    if not path:
        raise ValueError(name + ' must point to the installed native CLI')
    binary=Path(path).expanduser().resolve(strict=True)
    if not binary.is_file():
        raise ValueError(name + ' must point to a native CLI file')
    return binary


def adapter_runtime(engine, binary=None):
    return importlib.import_module('adapters.' + engine), cli_binary(engine, binary)


def wait_for_provider(owner, identity, timing_path):
    """After natural CLI exit wait for the original relay's still-live requests."""
    from vic_sdk.embodied_recovery import checked_barrier
    from vic_sdk.native_structured_supervisor import provider_drained
    while True:
        response = owner.get('/api/private/state')
        response.raise_for_status()
        state = response.json()
        barrier = checked_barrier(state, identity)
        if Path(barrier['api_timing_log']).resolve() != timing_path:
            raise ValueError('Owner API journal identity changed')
        timing = barrier.get('api_timing') or {}
        if provider_drained(timing):
            return state
        if timing.get('ledger_integrity_failed') or not (timing.get('active') or timing.get('pending_log_write')):
            raise ValueError('Owner API journal cannot establish quiescence')
        time.sleep(2)


def continue_existing(*,engine,room,owner,session,previous_attempt):
    """Called only by the owner-checked, exclusive companion. Reuses the original relay."""
    from vic_sdk.embodied_recovery import checked_barrier
    if engine not in (*CLAUDE_ENGINES,'gemini','kimi','dsh','zcode','codex') or not session or previous_attempt < 1:
        raise ValueError('Unsupported existing CLI session')
    room=Path(room).resolve()
    out=room/'cli'
    connection=read(Path(read(room/'worker-owner.json')['connection']))
    cfg=read(room/'computer-private.json')
    if cfg['program_episode_identity'] != connection['identity'] or cfg['control_url'] != connection['control_url']:
        raise ValueError('Companion room identity mismatch')
    if str(owner.base_url).rstrip('/') != connection['control_url'].rstrip('/'):
        raise ValueError('Companion controller endpoint mismatch')
    receipt=read(out/f'attempt-{previous_attempt}-receipt.json')
    if receipt['session_id'] != session or (out/f'attempt-{previous_attempt + 1}.jsonl').exists() or (out/'result.json').exists():
        raise ValueError('Existing native session receipt changed')
    state=wait_for_provider(owner,connection['identity'],Path(connection['api_timing_log']).resolve())
    if checked_barrier(state,connection['identity']).get('recovery_id'):
        raise ValueError('Owner recovery is already locked')
    selected=read(out/'effective-config.json') if (out/'effective-config.json').exists() else {}
    if engine in CLAUDE_ENGINES:
        module,binary=None,cli_binary(engine,selected.get('binary'))
        config=read(out/'profile/claude-runtime.private.json')
        qwen_config=(config['mcp'],config['base_url'],config['token'])
    else:
        module,binary=adapter_runtime(engine,selected.get('binary'))
        qwen_config=None
    return attempt_loop(engine=engine,room=room,out=out,owner=owner,identity=connection['identity'],
                        binary=binary,module=module,prompt='',session=session,review_attempt=previous_attempt,qwen_config=qwen_config)


def attempt_loop(*,engine,room,out,owner,identity,binary,module,prompt,session=None,review_attempt=None,qwen_config=None,relay=None,start_attempt=1,session_recovery_record=None):
    from vic_sdk.native_structured_supervisor import native_terminal_proven,unresolved_tool_input
    from vic_sdk.embodied_recovery import checked_barrier,recover_control,failure_class
    from vic_sdk.embodied_agent import checked_evaluation
    from vic_sdk import claude_structured as claude
    from vic_sdk.native_agent import summarize as cc_summary
    if type(start_attempt) is not int or start_attempt < 1:
        raise ValueError('Invalid starting CLI attempt')
    if start_attempt != 1:
        if not session or review_attempt is not None:
            raise ValueError('A continuation requires one original session and no review replay')
        previous=read(out/f'attempt-{start_attempt-1}-receipt.json')
        if previous.get('session_id') != session:
            if engine != 'kimi' or start_attempt != 2 or previous.get('session_id') is not None or previous.get('exit_code') != 1 or session_recovery_record is None:
                raise ValueError('Original session receipt mismatch')
            import hashlib
            proof_path = Path(session_recovery_record).resolve(strict=True)
            if proof_path != (out/'kimi-stream-recovery-claim/session-correction.private.json').resolve(strict=True):
                raise ValueError('Unrecognized session correction evidence')
            proof = read(proof_path)
            wire = module._session_file(out/'profile', session)
            if (proof.get('reason') != 'missing_session_hint_on_failed_first_attempt' or proof.get('session_id') != session
                    or proof.get('original_receipt_sha256') != hashlib.sha256((out/'attempt-1-receipt.json').read_bytes()).hexdigest()
                    or proof.get('wire_sha256') != hashlib.sha256(wire.read_bytes()).hexdigest()
                    or proof.get('native_identity') != identity):
                raise ValueError('Session correction proof changed')
        if (out/'result.json').exists():
            raise ValueError('Already terminal')
    workspace=out/'workspace'
    profile=out/'profile'
    settings=read(out/'effective-config.json') if (out/'effective-config.json').exists() else {}
    model=settings.get('model',MODELS[engine])
    connection_path=Path(read(room/'worker-owner.json')['connection']) if (room/'worker-owner.json').is_file() else room.parent/'gui/connection.private.json'
    timing=Path(read(connection_path)['api_timing_log']).resolve()
    if qwen_config:
        mcp,base,token=qwen_config
    for attempt in range(review_attempt or start_attempt,sys.maxsize):
        stream=out/f'attempt-{attempt}.jsonl'
        if attempt == review_attempt:
            exit_code=read(out/f'attempt-{attempt}-receipt.json')['exit_code']
        else:
            if engine in CLAUDE_ENGINES:
                cmd,env=claude.command(profile,workspace,model,mcp,binary=binary,budget=0,base_url=base,key=token,effort=settings.get('effort','high'),resume=session)
                window=settings.get('context_window',1000000)
                compact=settings.get('compact_tokens',150000)
                env.update(CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(window),CLAUDE_CODE_AUTO_COMPACT_WINDOW=str(compact))
                cmd[cmd.index('--autocompact')+1]=str(compact)
                from qwen_runtime import configure_tool_wait, configure_provider_wait
                save(out/f'attempt-{attempt}-tool-wait-policy.json',configure_tool_wait(env))
                save(out/f'attempt-{attempt}-provider-wait-policy.json',configure_provider_wait(env))
                if '--max-budget-usd' in cmd:
                    idx=cmd.index('--max-budget-usd');del cmd[idx:idx+2]
                content=claude.user_message(prompt,room/'native-structured/initial-gui.png' if attempt==1 else None)
            else:
                cmd,env=module.command(profile,workspace,model,binary=binary,resume=session)
                env.update(PATH=os.environ['PATH'],LD_LIBRARY_PATH=os.environ.get('LD_LIBRARY_PATH',''),NO_PROXY='localhost,127.0.0.1')
                if engine in ('kimi','dsh'):env.setdefault('HOME',str(profile))
                if engine=='codex' and attempt==1:
                    cmd=cmd[:-1]+['--image',str(room/'native-structured/initial-gui.png'),cmd[-1]]
                content=prompt
            with stream.open('xb') as stdout,(out/f'attempt-{attempt}.stderr').open('xb') as stderr:
                proc=subprocess.run(cmd,cwd=workspace,env=env,input=content.encode(),stdout=stdout,stderr=stderr)
            exit_code=proc.returncode
        owner_state=wait_for_provider(owner,identity,timing)
        summary=cc_summary('claude',stream,profile) if engine in CLAUDE_ENGINES else module.summarize(stream,profile,session_id=session)
        if native_terminal_proven(owner_state,identity):
            score=owner.post('/api/private/evaluate',json={'identity':identity});score.raise_for_status()
            evaluation=checked_evaluation(score.json(),identity)
            save(out/'authoritative-evaluation.json',evaluation)
            owner.post('/api/private/close',json={'identity':identity}).raise_for_status()
            save(out/'result.json',dict(identity=identity,engine=engine,model=model,evaluation=evaluation,attempts=attempt,terminal=True,scored=True,benchmark_completed=True,session_id=summary.get('session_id'),last_attempt_usage=summary.get('usage'),physical_actions_confirmed=checked_barrier(owner_state,identity)['action_count'],outcome='success' if evaluation['success'] else 'fail'))
            if relay is not None:
                relay.shutdown();relay.server_close()
            return
        sid=summary.get('session_id')
        if attempt != review_attempt:
            save(out/f'attempt-{attempt}-receipt.json',{'session_id':sid,'usage':summary.get('usage'),'exit_code':exit_code})
        errors=json.dumps(summary.get('errors',[])).lower()
        if ('mismatch' in errors and 'session' in errors) or 'multiple gemini native session' in errors:
            hold(out,'native_session_identity_conflict')
        if engine in CLAUDE_ENGINES:sid=claude.resolve_session(profile,summary,session)
        if not sid or (session and sid!=session):hold(out,'missing_or_changed_native_session')
        if engine=='gemini':
            persisted={read(path).get('sessionId') for path in profile.rglob('session-*.json')}
            if persisted!={sid}:hold(out,'native_session_identity_conflict')
        if engine=='zcode' and (room/'program/owner').exists():
            # The native CLI can exit before its MCP has released the lifetime
            # ProgramGuiSession lease. First allow normal shutdown; only a proven
            # dead original lease can be archived under the native recovery lock.
            from migrate_zcode_session import session_proven
            from zcode_dead_lease import proof as dead_lease_proof, reconcile as reconcile_dead_lease
            try:
                session_proven(out,sid)
                deadline=time.monotonic()+5.
                while (room/'program/owner').exists() and time.monotonic()<deadline:
                    time.sleep(.2)
                if (room/'program/owner').exists():
                    evidence=dead_lease_proof(room,identity)
                    reconcile_dead_lease(owner,identity,room,expected=evidence)
                    owner_state=wait_for_provider(owner,identity,timing)
            except (RuntimeError,ValueError,OSError,KeyError) as exc:
                save(out/'dead-lease-check.private.json',dict(time=time.time(),
                    rejected=True,error_class=type(exc).__name__,reason=str(exc),preserve_world=True))
                hold(out,'unresolved_native_input_or_owner')
        if unresolved_tool_input(room) or (room/'gui-input-pending.private.json').exists() or (room/'program/owner').exists():hold(out,'unresolved_native_input_or_owner')
        barrier=checked_barrier(owner_state,identity)
        if barrier['status']!='running' or barrier.get('recovery_id'):hold(out,'owner_or_transport_unresolved')
        env_error=read(room/'environment-error.json') if (room/'environment-error.json').exists() else None
        stderr=(out/f'attempt-{attempt}.stderr').read_text(errors='replace')
        if engine=='gemini' and 'fetch failed' in errors:
            stderr+='\nnetwork error'  # Gemini's native fetch failure, after original request drain.
        failure=failure_class(summary,stderr,env_error)
        if not failure and engine in ('dsh','zcode'):
            from owned_provider_transport_recovery import recoverable_exit
            failure=recoverable_exit(engine,out,summary,stderr,env_error,sid)
        if not failure and engine=='gemini' and not env_error:
            failure=module.recoverable_exit(summary,exit_code)
        if not failure and engine=='dsh' and not env_error:
            failure=module.recoverable_exit(summary)
        if not failure and exit_code==0 and not env_error and not summary.get('is_error'):
            failure='native_exit_without_terminal'
        if not failure:
            hold(out,'unclassified_cli_exit')
        from dsh_output_recovery_policy import consecutive_for_recovery
        try:
            recovery_consecutive=consecutive_for_recovery(engine=engine,failure=failure,attempt=attempt,room=room,identity=identity,barrier=barrier)
        except (ValueError,OSError):
            hold(out,'invalid_native_output_recovery_history')
        if not recover_control(owner,identity,room,attempt=attempt,failure=failure,consecutive=recovery_consecutive):
            hold(out,'recovery_requires_owner_review')
        session=sid
        prompt=('Continue the same task and existing world. Observe the current GUI before acting. '
                'Never replay accepted or uncertain input. '+BATCH_INSTRUCTIONS)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--room',type=Path);p.add_argument('--out',type=Path);p.add_argument('--engine',choices=MODELS,required=True)
    p.add_argument('--check-config',action='store_true')
    p.add_argument('--model')
    p.add_argument('--effort')
    p.add_argument('--context-window',type=int)
    p.add_argument('--compact-tokens',type=int)
    p.add_argument('--binary',type=Path)
    p.add_argument('--codex-model-catalog',type=Path)
    p.add_argument('--codex-model-catalog-sha256')
    args=p.parse_args()
    if args.check_config:
        settings=worker_settings(args)
        if args.engine=='codex':
            from vic_sdk.direct_tools import validate_context_window
            if not settings['model_catalog'] or not settings['model_catalog_sha256']:
                p.error('Codex requires --codex-model-catalog and --codex-model-catalog-sha256')
            validate_context_window(settings['model_catalog'],settings['model_catalog_sha256'],
                settings['model'],settings['context_window'],settings['compact_tokens'])
        print(json.dumps(settings))
        raise SystemExit(0)
    if args.room is None or args.out is None:
        p.error('--room and --out are required for model execution')
    try:run(args)
    except FileExistsError:
        raise
    except Exception as exc:
        if args.out.is_dir():hold(args.out,'worker_error: '+type(exc).__name__)
        raise
