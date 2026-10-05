"""Release checks against a running controller/worker; no video or private writes.

Uses private test plans to issue ordinary authenticated application commands.
Only workspaces created by this check are destroyed. Credentials are never saved.
"""
import argparse
import base64
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from vic import v2, games, business
from vic_apps import reversi_training, stopping_training

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_applications import reference


def commands(state, variant):
    task = state['task_id']
    if task in v2.ATOMIC_TASKS:
        from test_v2_atomic_batch import batch_reference
        yield from batch_reference(state, variant)
        return
    if task in v2.WORKSET_TASKS:
        from vic.v2_worksets import reference_commands
        yield from reference_commands(state, variant)
        return
    if task == 69:
        for direction in stopping_training.reference_paths(state['seed'])[variant]:
            yield 'move', '', direction, []
        yield 'stop', '', '', []
        from vic.v2_worksets import document_commands
        yield from document_commands(state,['practice-result'])
        return
    if task == 74:
        for _ in range(6):
            target = ','.join(map(str, games.expected(74, variant, state)))
            yield 'choose', target, '', []
            state = reversi_training.apply(state, 'choose', target)
        from vic.v2_worksets import document_commands
        yield from document_commands(state,['practice-result'])
        return
    if task == 45:
        from test_v2 import purchase_lines
        quantities = purchase_lines(state)
        for index, dep in enumerate(state['world']['departments'], 1):
            key = f'PO-{index:03d}'
            yield 'order.create', '', json.dumps({'department': dep['id']}), []
            yield 'order.address', key, json.dumps({'address': dep['address']}), []
            for (department, sku), quantity in quantities.items():
                if department != dep['id']:
                    continue
                name = next(p['name'] for p in state['world']['products'] if p['id'] == sku)
                note = {'A': f'{quantity}{name}', 'B': f'{name}{quantity}', 'C': '零一二三四五六七八九'[quantity] + name}[variant]
                yield 'order.line', key, json.dumps(dict(sku=sku, quantity=quantity, note=note)), []
            yield 'order.save', key, '{}', []
        return
    groups = [
        ({11, 13, 15}, 'communications', 'commands'),
        ({18, 28, 32}, 'music_projects', 'plan'),
        ({29, 30}, 'editorial_projects', 'plan'),
        ({35}, 'screening', 'operations'),
        ({40, 42}, 'publishing', 'plan'),
        ({41, 43}, 'studio_projects', 'plan'),
        ({44, 51, 54}, 'travel_projects', 'plan'),
        ({46, 56}, 'payment_projects', 'plan'),
        ({52, 55}, 'shop_projects', 'plan'),
        ({58, 60, 64, 65}, 'code_projects', 'commands'),
    ]
    for tasks, module, function in groups:
        if task not in tasks:
            continue
        plan = getattr(importlib.import_module('test_v2_' + module), function)
        for row in plan(state, variant):
            op, target, value = row[:3]
            yield op, target, value if isinstance(value, str) else json.dumps(value), row[3] if len(row) == 4 else []
        return
    raise AssertionError(f'Missing task plan: {task}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:18765')
    parser.add_argument('--token-file', default='.local/agentlab-admin-token')
    parser.add_argument('--tasks', default=','.join(map(str, range(1, 76))))
    parser.add_argument('--variants', default='ABC')
    parser.add_argument('--mode', choices=['eval', 'demo'], default='eval')
    parser.add_argument('--output', default='.local/v2-deployed-api.json')
    args = parser.parse_args()
    secret = Path(args.token_file).read_text().strip()
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(verified_at=datetime.now(timezone.utc).isoformat(), mode=args.mode, video_recorded=False, cases=[])

    def require(response):
        # Do not include URLs or credentials in exception messages.
        if not response.is_success:
            raise AssertionError(f'HTTP {response.status_code}: {response.text[:500]}')
        return response.json()

    with httpx.Client(base_url=args.base, headers={'Authorization': 'Bearer ' + secret}, trust_env=False, timeout=120, limits=httpx.Limits(keepalive_expiry=1)) as control, httpx.Client(trust_env=False, timeout=120, limits=httpx.Limits(keepalive_expiry=1)) as worker:
        catalog = require(control.get('/v2/tasks'))['tasks']
        assert len(catalog) == 75 and all(t['status'] == 'application-ready' for t in catalog)
        for task in map(int, args.tasks.split(',')):
            contract = require(control.get(f'/v2/tasks/{task}/contract'))
            assert contract
            for variant in args.variants:
                run = require(control.post('/v1/runs', json=dict(suite='v2', task_id=task, variant=variant, seed=0 if args.mode == 'demo' else 10001, mode=args.mode, interaction='human', runtime='browser', teaching=args.mode == 'demo')))
                path = '/v1/runs/' + run['id']
                record = dict(task=task, variant=variant, status='failed', mode=args.mode, suite='v2')
                try:
                    address = urlsplit(run['application_url'])
                    endpoint = address.scheme + '://' + address.netloc + '/api/runs/' + run['id']
                    headers = {'Authorization': 'Bearer ' + address.fragment}
                    initial = require(worker.get(endpoint, headers=headers))['state']
                    if args.mode == 'eval':
                        empty = require(control.post(f'/v2/tasks/{task}/eval', json={'run_id': run['id']}))
                        assert not empty['success'], 'Untouched environment passed'
                        run = require(control.post(path + '/reset'))
                        headers = {'Authorization': 'Bearer ' + urlsplit(run['application_url']).fragment}
                        assert require(worker.get(endpoint, headers=headers))['state'] == initial
                    count = 0
                    for episode in range(run['lesson']['total'] if args.mode == 'demo' else 1):
                        state = require(worker.get(endpoint, headers=headers))['state']
                        plan = reference(state, variant) if args.mode == 'demo' else commands(state, variant)
                        for index, (op, target, value, ids) in enumerate(plan):
                            require(worker.post(endpoint + '/commands', headers=headers, json=dict(epoch=run['epoch'], action_id=f'{episode}-{index}', op=op, target=target, value=value, ids=ids)))
                            count += 1
                        if args.mode == 'demo':
                            body = dict(epoch=run['epoch'], index=episode)
                            if task == 43 and variant == 'B':
                                done = require(worker.get(endpoint, headers=headers))['state']
                                body['clipboard'] = done['domain']['clipboard_history'][-1]['text']
                            run.update(require(control.post(path + '/lesson/next', headers=headers, json=body)))
                            headers = {'Authorization': 'Bearer ' + urlsplit(run['application_url']).fragment}
                    final = require(worker.get(endpoint, headers=headers))['state']
                    downloads = 0
                    for key, file in final.get('domain', {}).get('files', {}).items():
                        response = worker.get(endpoint + '/files/' + key, headers=headers)
                        assert response.status_code == 200 and response.content == base64.b64decode(file['content'])
                        downloads += 1
                    result = require(control.post(f'/v2/tasks/{task}/eval', json={'run_id': run['id']}))
                    assert result['success'], result.get('violations', [])
                    old_headers = headers
                    run = require(control.post(path + '/reset'))
                    headers = {'Authorization': 'Bearer ' + urlsplit(run['application_url']).fragment}
                    assert worker.get(endpoint, headers=old_headers).status_code == 403
                    assert require(worker.get(endpoint, headers=headers))['state'] == initial
                    record.update(status='passed', commands=count, downloads=downloads, reset=True, stale_credentials_rejected=True, episodes=episode+1)
                    print(f'{task:03d}{variant} {args.mode} PASS', flush=True)
                except Exception as exc:
                    record['error'] = str(exc).replace(secret, '[redacted]')
                    print(f'{task:03d}{variant} {args.mode} FAIL {type(exc).__name__}', flush=True)
                    raise
                finally:
                    require(control.delete(path))
                    report['cases'].append(record)
                    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
