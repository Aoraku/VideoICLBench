"""Process supervisor for native Codex; never creates model requests or history.

Only the real Codex exec/resume process owns its model loop and compaction.
No CLI exit, error, prose or budget pause can manufacture a native terminal.
"""
import json
from pathlib import Path
import subprocess
import threading
import time

import httpx

from .embodied_codex_mcp import NativeStructuredTools
from .native_agent import cli_command, summarize, private_json
from .embodied_recovery import failure_class, resolve_session, recover_control, retire_exited_cli_tools, checked_barrier


def native_terminal_proven(value, identity):
    if not isinstance(value, dict) or value.get('identity') != identity:
        return False
    try:
        barrier = checked_barrier(value, identity)
    except (ValueError, KeyError, TypeError):
        return False
    timing = barrier.get('api_timing') or {}
    if (barrier.get('terminal_snapshot_ready') is not True or not provider_drained(timing)):
        return False
    return (barrier.get('model_stop') in {'done', 'give_up'}
        or barrier.get('status') == 'budget_exhausted')


def provider_drained(timing):
    return (timing.get('transport_quiescent_confirmed') is True
        and timing.get('ledger_integrity_valid') is True and timing.get('active') is False
        and timing.get('active_request_count') == 0 and timing.get('pending_log_write') is False)


def unresolved_tool_input(out):
    path = Path(out)/'native-structured/state.private.json'
    if not path.exists():
        return False
    state = json.loads(path.read_text())
    return any(row.get('state') != 'completed' for row in state.get('operations', {}).values())


def hold_world(out, reason):
    private_json(Path(out)/'native-structured-world-preserved.private.json', dict(
        reason=reason, world_preserved=True, terminal_manufactured=False, api_cancelled=False))
    print(json.dumps(dict(phase='diagnostic_hold', reason=reason, world_preserved=True)), flush=True)
    threading.Event().wait()


def run(args, *, out, profile, workspace, identity, connection, computer, instruction,
        server, command, env, model_key, admin_key, ready, metadata, result, hold=hold_world):
    """One isolated native CLI session, infrastructure resumes only after CLI exit."""
    proven = False
    session = None
    with httpx.Client(base_url=connection['control_url'], timeout=None, trust_env=False,
            headers={'Authorization':'Bearer '+admin_key}) as control:
        try:
            state = control.get('/api/private/state'); state.raise_for_status(); value = state.json()
            if value.get('identity') != identity or value.get('state', {}).get('condition') != args.condition:
                raise ValueError('Native structured owner/condition mismatch')
            if args.embodied_auto_recover and value.get('owner_barrier', {}).get('api_timing_log') != connection.get('api_timing_log'):
                raise ValueError('Native owner/provider timing path mismatch')
            if native_terminal_proven(value, identity):
                raise ValueError('A new native structured episode cannot reuse a terminal world')
            bootstrap = NativeStructuredTools(computer)
            try:
                image_path, public = bootstrap.bootstrap_files()
            finally:
                bootstrap.close()
            prompt = instruction
            if args.condition == 'text_rule':
                rule = value.get('state', {}).get('text_rule')
                if not isinstance(rule, str) or not rule.strip():
                    raise ValueError('Public text rule is missing')
                prompt += '\n\n'+rule
            prompt += '\n\nInitial public observation and assigned demonstration metadata:\n'+json.dumps(public, ensure_ascii=False, separators=(',', ':'))
            (out/'prompt-1.txt').write_text(prompt)
            metadata['initial_gui_image'] = str(image_path)
            metadata['native_conversation'] = dict(initial_user_material_once=True,
                subsequent_observations='native MCP tool outputs', host_history_reconstruction=False,
                automatic_compaction='native Codex CLI', model_context_window=args.codex_context_window,
                auto_compact_token_limit=args.codex_compact_tokens)
            private_json(out/'manifest.json', metadata)
            started = control.post('/api/private/start', json={'identity':identity}); started.raise_for_status()
            attempt = 0
            while True:
                attempt += 1
                if attempt > 1:
                    command, env = cli_command('codex', profile, workspace, args.model, server,
                        resume=session, binary=args.binary, serial_tools=True)
                    env['VIC_MODEL_API_KEY'] = model_key
                else:
                    # Native exec attaches the first GUI directly to the first user request.
                    command = list(command[:-1])+['--image', str(image_path), command[-1]]
                text = prompt if attempt == 1 else (
                    'Continue the same episode and native session after an infrastructure interruption. '
                    'Call observe before further actions. Do not replay an accepted or uncertain operation. '
                    'Do not give up because of the infrastructure wait.')
                stdout_path, stderr_path = out/f'stdout-{attempt}.jsonl', out/f'stderr-{attempt}.log'
                with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
                    process = subprocess.Popen(command, env=env, cwd=workspace, stdin=subprocess.PIPE,
                        stdout=stdout, stderr=stderr, text=True, start_new_session=True)
                    process.communicate(text)  # Unlimited; never kill an in-flight API request.
                summary = summarize('codex', stdout_path, profile)
                session = resolve_session(profile, summary, session)
                result.update(summary, session_id=session, exit_code=process.returncode)
                result['native_attempts'].append(dict(attempt=attempt, session_id=session,
                    stdout=stdout_path.name, stderr=stderr_path.name, exit_code=process.returncode))
                result['recovery']['attempt_count'] = attempt
                response = control.get('/api/private/state'); response.raise_for_status(); owner = response.json()
                proven = native_terminal_proven(owner, identity)
                if proven:
                    break
                if unresolved_tool_input(out) or (out/'gui-input-pending.private.json').exists():
                    hold(out, 'accepted_tool_input_unresolved_no_replay')
                    return 1
                timing = checked_barrier(owner, identity).get('api_timing') or {}
                if not provider_drained(timing):
                    hold(out, 'provider_not_fully_drained_no_recovery_or_cleanup')
                    return 1
                failure = failure_class(summary, stderr_path.read_text(), None)
                if (failure is None and process.returncode == 0
                        and not summary.get('errors') and not summary.get('is_error')):
                    failure = 'native_exit_without_terminal'
                if not args.embodied_auto_recover or failure is None:
                    hold(out, failure or 'nonrecoverable_native_cli_error')
                    return 1
                retire_exited_cli_tools(process)
                if not recover_control(control, identity, out, attempt=attempt, failure=failure, consecutive=attempt):
                    hold(out, 'native_recovery_requires_owner_review')
                    return 1
                result['recovery']['resume_count'] += 1
            # GUI Done/giveup or native physical budget already created the terminal.
            # Do not call /seal here: it would turn an ordinary exit into finish().
            from .embodied_agent import checked_evaluation
            evaluated = control.post('/api/private/evaluate', json={'identity':identity}); evaluated.raise_for_status()
            result['evaluation'] = checked_evaluation(evaluated.json(), identity)
            result.update(scored=True, benchmark_completed=True,
                scientific_evaluation=bool(ready), outcome='success' if result['evaluation']['success'] else 'fail')
            private_json(out/'authoritative-evaluation.json', result['evaluation'])
            private_json(out/'result.json', result)
            print(json.dumps(dict(artifacts=str(out), **result), ensure_ascii=False), flush=True)
            return 0
        except Exception as exc:
            result['outcome'] = 'preserved_unscored'
            result['error'] = dict(type=type(exc).__name__, message='Native integration needs review; original world preserved')
            private_json(out/'result.private.json', result)
            hold(out, 'native_structured_infrastructure_failure')
            return 1
        finally:
            if proven:
                # Positive native terminal proof is the sole authority for releasing this world.
                try:
                    control.post('/api/private/close', json={'identity':identity}).raise_for_status()
                    result['cleanup_confirmed'] = True
                    private_json(out/'result.json', result)
                except httpx.HTTPError:
                    result.setdefault('cleanup_errors', []).append(dict(operation='close', error='native_terminal_close_failed'))
                    private_json(out/'result.json', result)
