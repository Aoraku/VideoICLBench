"""Expose one native-pool room through the same GUI as a single-room trial."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/sdk'))
if __name__ == '__main__':
    for name in list(sys.modules):
        if name == 'vic_sdk' or name.startswith('vic_sdk.'):
            del sys.modules[name]
from serve_embodied import load_assignment
from vic_sdk.embodied_environment.episode import Episode, Identity, private_write
from vic_sdk.embodied_environment.pool import NativePoolProxy
from vic_sdk.embodied_environment.server import serve


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task-dir', type=Path, required=True)
    p.add_argument('--rpc-root', type=Path, required=True)
    p.add_argument('--room-id', required=True)
    p.add_argument('--condition', choices=['real', 'sim', 'text_rule', 'none'], required=True)
    p.add_argument('--max-actions', type=int, required=True)
    p.add_argument('--timeout', type=int, required=True)
    p.add_argument('--unknown-api-policy', choices=['retire_unscored','preserve_world','resume_closed_unknown'], default='retire_unscored')
    p.add_argument('--embodied-auto-recover', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--defer-budget-start', action='store_true')
    p.add_argument('--native-response-timeout', type=float)
    p.add_argument('--api-timing-log', type=Path,
                   help='Private per-episode API failure timing journal from the verified relay')
    p.add_argument('--allow-unvalidated-environment', action='store_true')
    args = p.parse_args()
    if args.unknown_api_policy == 'resume_closed_unknown' and (args.timeout != 0 or not args.embodied_auto_recover or args.api_timing_log is None):
        p.error('Closed unknown recovery requires timeout 0, auto-recovery and a private API journal')
    native, instruction, demo, rule = load_assignment(args.task_dir, args.condition)
    ready = json.loads((args.rpc_root / 'ready.json').read_text())
    record = ready['rooms'][args.room_id]
    identity = Identity(**record['identity'])
    if (identity.task_id, identity.variant, identity.seed) != (native['task_id'], native['variant'], native['seed']):
        raise ValueError('Assigned Harbor task differs from the native pool room')
    if record.get('fingerprints', {}).get('provenance', {}).get('dataset_revision') != native.get('dataset_revision'):
        raise ValueError('Harbor and native dataset revisions differ')
    validated = (native.get('readiness') in ('available', 'ready')
        and native.get('native_interaction_validated') is True and native.get('budget', {}).get('status') == 'frozen')
    if not args.allow_unvalidated_environment:
        if not validated:
            raise ValueError('Pool native interaction requires explicit diagnostic validation')
        if native['budget']['max_actions'] != args.max_actions or native['budget']['timeout_sec'] != args.timeout:
            raise ValueError('Formal budgets must match the frozen task package')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    proxy = NativePoolProxy(args.rpc_root, args.room_id, asdict(identity), timeout_seconds=args.native_response_timeout)
    episode = Episode(proxy, identity, title=record['public']['title'], instruction=instruction,
        condition=args.condition, max_actions=args.max_actions, timeout_seconds=args.timeout,
        output=out / 'environment', action_schema=record['action_schema'], demo=demo,
        text_rule=rule, require_rule_report=False, defer_budget_start=args.defer_budget_start,
        api_timing_log=args.api_timing_log,unknown_api_policy=args.unknown_api_policy,
        validation_only=bool(args.allow_unvalidated_environment or not validated))
    episode.observe()
    actor, admin = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    for name, value in [('actor-token', actor), ('admin-token', admin)]:
        fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)

    def connected(port):
        private_write(out / 'connection.private.json', dict(control_url=f'http://127.0.0.1:{port}',
            identity=asdict(identity), actor_token_file=str(out / 'actor-token'),
            admin_token_file=str(out / 'admin-token'), condition=args.condition,
            max_actions=args.max_actions, timeout_seconds=args.timeout, demo=demo,
            unknown_api_policy=args.unknown_api_policy,
            validation_only=episode.validation_only, runtime_fingerprints=record['fingerprints'],
            barrier_timeout_seconds=proxy.barrier_timeout_seconds,
            barrier_policy=proxy.barrier_policy, budget_policy=episode.budget_policy,
            api_timing_log=str(args.api_timing_log.resolve()) if args.api_timing_log else None,
            api_failure_budget_policy='per_episode_failed_request_and_retry_wait_v1' if args.api_timing_log else None,
            native_response_timeout_seconds=proxy.timeout, budget_start_deferred=args.defer_budget_start,
            native_pool_hostname=proxy.native_hostname,
            execution_topology='same_pod_kit_gui_cli_file_rpc',
            agent_protocol='roboprobe_gui_v1', agent_interaction='gui_only',
            pool_room_id=args.room_id))
        print(json.dumps(dict(event='environment_ready', run_id=identity.run_id,
            connection=str(out / 'connection.private.json'))), flush=True)

    try:
        serve(episode, port=args.port, agent_token=actor, admin_token=admin,
              frontend=ROOT / 'apps/portal/public/embodied', ready=connected)
    finally:
        proxy.close()


if __name__ == '__main__':
    main()
