"""Versioned execution contracts. Rule answers never enter application state."""
import hashlib
import json
from .config import ROOT
from .v2_atomic import TASKS as ATOMIC_TASKS
from .v2_worksets import TASKS as WORKSET_TASKS

EXECUTABLE = {45,74} | ATOMIC_TASKS | WORKSET_TASKS


def catalog():
    data = json.loads((ROOT / 'tasks/v2/catalog.json').read_text())
    for item in data['tasks']:
        item['status'] = 'application-ready' if item['id'] in EXECUTABLE else 'implementation-pending'
    return data


def task(task_id):
    return next(t for t in catalog()['tasks'] if t['id'] == task_id)


def digest(task_id):
    return hashlib.sha256(json.dumps(task(task_id), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def generate(task_id, seed, mode):
    if task_id not in EXECUTABLE:
        raise ValueError('此 v2 执行环境尚未完成，不能使用基础任务代替。')
    if mode == 'demo':
        from . import business
        from vic_apps.domain import initialize
        return initialize(business.generate(task_id, seed))
    if task_id in ATOMIC_TASKS:
        from .v2_atomic import generate as generate_atomic
        return generate_atomic(task_id,seed,task(task_id))
    if task_id in WORKSET_TASKS:
        from .v2_worksets import generate as generate_worksets
        return generate_worksets(task_id,seed,task(task_id))
    if task_id == 74:
        from vic_apps.reversi_training import fixture
        return fixture(seed,task(task_id))
    if task_id == 45:
        from vic_apps.procurement import fixture
        return fixture(seed)
    raise ValueError('Unsupported v2 execution')


def evaluate(initial, state, variant, events):
    if initial.get('v2_worksets'):
        from .v2_worksets import evaluate as evaluate_worksets
        return evaluate_worksets(initial,state,variant,events)
    if initial.get('v2_reversi'):
        from vic_apps.reversi_training import evaluate as evaluate_reversi
        return evaluate_reversi(initial,state,variant,events)
    if initial.get('v2_atomic'):
        from .v2_atomic import evaluate as evaluate_atomic
        return evaluate_atomic(initial,state,variant,events)
    if initial.get('workflow') != 'procurement':
        raise ValueError('Missing v2 evaluator')
    from .business import transform
    checks = []

    def check(name, passed):
        checks.append(dict(id=name, passed=bool(passed)))

    w, start = state['world'], initial['world']
    # Input requests are immutable evidence, not editable answers.
    for key in ('requests', 'products', 'departments', 'brief'):
        check(f'input:{key}', w[key] == start[key])
    quantities = {}
    latest = {}
    for req in start['requests']:
        if req['number'] not in latest or req['revision'] > latest[req['number']]['revision']:
            latest[req['number']] = req
    for req in latest.values():
        for line in req['lines']:
            key = (req['department'], line['sku'])
            quantities[key] = quantities.get(key, 0) + line['quantity']
    check('order_count', len(w['orders']) == len(start['departments']))
    for dep in start['departments']:
        orders = [o for o in w['orders'].values() if o['department'] == dep['id']]
        check(f'{dep["id"]}:one_order', len(orders) == 1)
        if len(orders) != 1:
            continue
        order = orders[0]
        expected_skus = {sku for (dept, sku) in quantities if dept == dep['id']}
        check(f'{dep["id"]}:address', order['address'] == dep['address'])
        check(f'{dep["id"]}:saved', order['status'] == 'saved')
        check(f'{dep["id"]}:products', set(order['lines']) == expected_skus)
        for sku in sorted(expected_skus):
            actual = order['lines'].get(sku, {})
            q = quantities[(dep['id'], sku)]
            product = next(p for p in start['products'] if p['id'] == sku)
            expected_note = transform(45, 'ABC'.index(variant), dict(source=dict(text=product['name'], quantity=q)))
            check(f'{dep["id"]}:{sku}:quantity', actual.get('quantity') == q)
            check(f'{dep["id"]}:{sku}:note', actual.get('note') == expected_note)
    return dict(success=all(c['passed'] for c in checks),
                completion=sum(c['passed'] for c in checks)/len(checks), checks=checks,
                violations=[c['id'] for c in checks if not c['passed']])
