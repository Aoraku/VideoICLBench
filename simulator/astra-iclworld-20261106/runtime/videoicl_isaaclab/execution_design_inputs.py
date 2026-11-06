"""Explicit input adapters for opt-in execution v2; unsupported inputs fail closed."""
from copy import deepcopy
from fractions import Fraction
from .execution_design import build_task_contract, WORKFLOW_TASKS, metadata
from .realworld_contracts import _bell_counts

IMPLEMENTED_IE = frozenset(('E04', 'E05', 'E26'))


def condition_capability(task, condition, *, revision=None):
    from .execution_design import REVISION
    revision = revision or REVISION
    if revision == 'embodied50-execution-v3-20261102':
        from .execution_design_inputs_v3 import condition_capability_v3
        return condition_capability_v3(task, condition)
    if condition not in metadata(task, revision=revision)['support_mask']:
        return dict(implemented=False, reason='unsupported_by_source_design')
    if task in WORKFLOW_TASKS:
        return dict(implemented=True, adapter='execution_workflow_scenes', physics_validated=False)
    if condition == 'R':
        return dict(implemented=True, adapter='canonical_demo_layout', physics_validated=False)
    if task in IMPLEMENTED_IE:
        return dict(implemented=True, adapter='explicit_inputs_v2', physics_validated=False)
    return dict(implemented=False, reason='task_specific_input_and_target_recomputation_not_implemented')


def apply_execution_inputs(base_spec, *, condition, seed, revision=None):
    from .execution_design import REVISION
    revision = revision or REVISION
    if revision == 'embodied50-execution-v3-20261102':
        from .execution_design_inputs_v3 import apply_execution_inputs_v3
        return apply_execution_inputs_v3(base_spec, condition=condition, seed=seed)
    task = base_spec['id']; variant = base_spec['variant']
    contract = build_task_contract(task, variant, seed, condition, revision=revision)
    if task in WORKFLOW_TASKS:
        raise ValueError('Use the dedicated workflow scene builder')
    if base_spec.get('inference_generalization'):
        raise ValueError('Execution R/I/E requires canonical source bindings, not old G1/G2 assets')
    cap = condition_capability(task, condition, revision=revision)
    if not cap['implemented']:
        raise NotImplementedError(f'{task}/{condition}: {cap["reason"]}')
    spec = deepcopy(base_spec)
    if condition == 'R':
        if base_spec.get('seed') != 0:
            raise ValueError('R requires canonical demonstration reset at seed 0')
        changes = dict(kind='fixed_demo_input', semantic_seed=None)
    elif task in ('E04', 'E05'):
        # Fixed derangements, not small position jitter; identities and shape/color
        # labels remain attached to their actual objects/regions.
        objects = [o for o in spec['objects'] if o.get('role') != 'fixture']
        zones = [z for z in spec['zones'] if z.get('shape') in ('triangle', 'square', 'circle')]
        if len(objects) != 3 or len(zones) != 3:
            raise ValueError('Expected three source pieces and three visible graph regions')
        offset = 1 + seed % 2
        for group in (objects, zones):
            positions = [deepcopy(v['xy']) for v in group]
            for i, v in enumerate(group):
                v['xy'] = positions[(i + offset) % 3]
        changes = dict(kind='source_object_and_region_derangement', offset=offset,
                       objects=[o['id'] for o in objects], zones=[z['id'] for z in zones])
    else:
        left, right = 1 + seed % 5, 1 + (seed // 5) % 5
        cards = {'left': left, 'right': right}
        for side, number in cards.items():
            matches = [z for z in spec['zones'] if z['id'] == side + '_digit']
            if len(matches) != 1:
                raise ValueError('Native rendered digit region is missing')
            matches[0]['digit'] = number
        spec['semantic']['digit_cards'] = cards
        spec['semantic']['execution_design_bell_rule'] = 'paired-digit-correspondence-v2'
        changes = dict(kind='new_digit_pair', digits=cards)
    if condition == 'E':
        # Same semantic input as paired I, physically translated workstation.
        # For these three adapters all mechanism control points are body-local.
        dx, dy = .035, -.025
        for o in spec.get('objects', []):
            o['xy'] = [o['xy'][0] + dx, o['xy'][1] + dy]
        for z in spec.get('zones', []):
            z['xy'] = [z['xy'][0] + dx, z['xy'][1] + dy]
        for m in spec.get('mechanisms', []):
            m['position'][0] += dx; m['position'][1] += dy
        changes['environment_translation_xy'] = [dx, dy]
    spec.update(seed=seed, title=contract['title'], instruction=contract['instruction'],
                execution_design=contract['execution_design'], release_ready=False)
    spec['execution_design']['applied_input_changes'] = changes
    return spec


def e26_targets(spec):
    if (spec.get('id') != 'E26' or spec.get('execution_design', {}).get('revision') not in ('embodied50-execution-v2-20261102', 'embodied50-execution-v3-20261102')):
        raise ValueError('Explicit E26 execution v2 contract required')
    cards = spec['semantic']['digit_cards']
    left, right = cards['left'], cards['right']
    condition = spec['execution_design']['condition']
    if condition == 'R':
        if (left, right) != (9, 1):raise ValueError('R must preserve demonstration digits')
    elif any(type(v) is not int or not 1 <= v <= 5 for v in (left, right)) or left + right > 10:
        raise ValueError('Invalid I/E digits')
    for side, number in cards.items():
        region = next(z for z in spec['zones'] if z['id'] == side + '_digit')
        if region.get('digit') != number:raise ValueError('Scoring and rendered digits disagree')
    return dict(zip(('left', 'right'), {'A': (left, right), 'B': (right, left), 'C': (left + right, 0)}[spec['variant']]))


def e26_checks(spec, observation):
    expected = e26_targets(spec)
    valid, counts = _bell_counts(observation.get('bell_events'))
    return dict(complete_contact_press_release_history=valid,
                exact_bell_counts=counts == expected,
                released=observation.get('released') is True,
                stable=observation.get('stable') is True)


def score_e26(spec, observation):
    """Score actual press-release evidence against the visible new digit pair."""
    expected = e26_targets(spec); checks = e26_checks(spec, observation)
    valid, counts = _bell_counts(observation.get('bell_events'))
    wrong_side = any(counts[k] > n for k, n in expected.items())
    total = sum(expected.values())
    process = Fraction(0) if not valid or wrong_side else Fraction(90 * sum(min(counts[k], n) for k, n in expected.items()), total)
    if all(checks.values()):process += 10
    return dict(task='E26', variant=spec['variant'], strict_success=all(checks.values()),
                success=all(checks.values()), process_score=float(process), task_score_100=float(process),
                checks=checks, failed_checks=[k for k, v in checks.items() if not v],
                native_physics_verified=False)
