"""Native Codex / Claude Code Stop hook: require an explicit finish, within a bounded native loop.

Reads only the public tool lifecycle log. Does not call a model or summarize history.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
from urllib.parse import urlsplit
try:
    from .embodied_protocol import STOP_PENDING_INSTRUCTIONS, STOP_CONTINUE_INSTRUCTIONS
except ImportError:  # The native CLI executes this sibling file as a hook script.
    from embodied_protocol import STOP_PENDING_INSTRUCTIONS, STOP_CONTINUE_INSTRUCTIONS


def controller_has_stopped(config, root):
    """Release the next natural CLI stop after controller drain, even without GUI tools.

    This is a bounded local public-state read, never a model request or success
    oracle. Unavailable/mismatched controllers cannot authorize termination.
    """
    url = config.get('control_url', '')
    token = config.get('actor_token')
    run_id = config.get('run_id')
    try:
        route = urlsplit(url)
        if (route.scheme != 'http' or route.hostname not in {'127.0.0.1','localhost','::1'}
                or route.username or route.password or not token or not run_id):
            return False
        request = urllib.request.Request(url.rstrip('/') + '/api/state',
            headers={'Authorization': 'Bearer ' + token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=1) as response:
            state = json.loads(response.read(65537))
        if state.get('run_id') != run_id or state.get('status') not in {
                'done','give_up','finished','budget_exhausted','budget_paused','faulted'}:
            return False
    except (OSError, ValueError, TypeError):
        return False
    # Preserve provenance: the harness checked public lifecycle state; the model
    # did not necessarily receive a GUI frame and did not declare completion.
    receipt = dict(run_id=run_id, status=state['status'], steps=state.get('steps'),
                   observed_unix=time.time(), source='stop_hook_controller_public_state',
                   model_declared_terminal=False, inflight_model_request_cancelled=False)
    (root/'stop-hook-controller-terminal.private.json').write_text(json.dumps(receipt)+'\n')
    return True


def decision(config, now=None):
    now = time.time() if now is None else now
    root = Path(config['output_dir'])
    graceful = config.get('budget_policy') == 'effective_time_graceful_v1'
    if ((root / 'environment-error.json').exists()
            or (not graceful and config.get('deadline_unix', 0) - now < 20)):
        return {}
    log = root / 'computer.jsonl'
    if log.exists() and any(json.loads(line).get('type') in {'finish','environment_terminal'} for line in log.read_text().splitlines()):
        return {}
    if graceful and config.get('agent_protocol') == 'roboprobe_gui_v1':
        if controller_has_stopped(config, root):
            return {}
        pending = (root / 'gui-input-pending.private.json').exists()
        return {'decision':'block', 'reason':STOP_PENDING_INSTRUCTIONS if pending else STOP_CONTINUE_INSTRUCTIONS}
    count_file = root / 'stop-guard-count.json'
    count = json.loads(count_file.read_text()) if count_file.exists() else 0
    if count >= 3:
        return {}
    count_file.write_text(json.dumps(count + 1))
    if config.get('agent_protocol') == 'roboprobe_gui_v1':
        pending = (root / 'gui-input-pending.private.json').exists()
        return {'decision':'block', 'reason':STOP_PENDING_INSTRUCTIONS if pending else STOP_CONTINUE_INSTRUCTIONS}
    return {'decision': 'block', 'reason': 'The environment task has not been explicitly finished. Continue the original task using its vic tools and current native session. If complete or unable to proceed, call the vic finish tool with an honest summary. Do not claim success without completing the actions. Do not restart the task or repeat deliveries.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    sys.stdin.read()
    print(json.dumps(decision(json.loads(args.config.read_text()))))


if __name__ == '__main__':
    main()
