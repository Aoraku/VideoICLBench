"""Private E34B author grasp on real material nearer the measured mass.

This changes the reference hand target only. Native scene, contacts, mass,
friction and scoring retain their source definitions.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import numpy as np


def grasp_spec(a, obj):
    from .execution_design_e34_reference import scope
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_e34_balanced_grasp import material_midpoint
    scope(a)
    spec = a.scene.spec
    if (spec.get('variant') != 'B' or spec.get('seed') != 4201
            or spec.get('execution_design', {}).get('condition') != 'I'
            or obj.get('id') != 'spoon'):
        raise ValueError('Private fixed E34B I4201 spoon grasp required')
    name = obj['id']
    body = a.c.snapshot()[0][name]
    if any(body['grasp']):
        raise RuntimeError('Near-COM grasp selection requires an empty hand')
    raw = a.scene.objects[name].root_physx_view.get_coms()
    if hasattr(raw, 'detach'):
        raw = raw.detach().cpu().numpy()
    raw = np.asarray(raw, float).reshape(-1, 7)
    if raw.shape != (1, 7) or not np.isfinite(raw).all():
        raise ValueError('One finite native spoon COM required')

    def frame(ref):
        value = a.c.snapshot()[0][ref['actor']]
        return np.asarray(value['pos']), np.asarray(value['mat'])

    parts = collision_parts_task(SimpleNamespace(a=a, frame=frame), name)
    local = [(np.asarray(p) - body['pos']) @ np.asarray(body['mat']) for p in parts]
    point, evidence = material_midpoint(obj['grasp_point_local'], raw[0, :3], local)
    private = deepcopy(obj)
    private['grasp_point_local'] = point.tolist()
    evidence.update(step=a.c.steps, object=name,
        source='actual_enabled_native_collision_material_section',
        actual_native_com_pose_local=raw[0].tolist(), native_grasp_verified=False,
        collision_representation_evidence=getattr(a, '_branch_collision_parts_evidence', {}).get(name))
    with (a.out / 'e34b-near-com-grasp.private.jsonl').open('a') as stream:
        stream.write(json.dumps(evidence) + '\n')
    return private


def run_debug(a, payload):
    """Empty native checkpoint through true grasp and uninterrupted transport."""
    if not getattr(a.c, '_engineering_diagnostic_only', False):
        raise ValueError('Admitted diagnostic checkpoint required')
    from .execution_design_cutlery_grasp import grasp_position
    from .execution_design_e34_acquire import narrow_material_approach, check_pickup_neighbors
    from .execution_design_e34_tail import finish_from_grasp
    side = payload.get('side', 'left')
    state, _ = a.c.snapshot()
    if any(any(body['grasp']) for body in state.values()):
        raise RuntimeError('Balanced diagnostic must start empty-handed')
    baseline = {n: dict(pos=np.asarray(b['pos']).copy(), mat=np.asarray(b['mat']).copy())
        for n, b in state.items() if n != 'spoon'}
    obj = grasp_spec(a, next(o for o in a.scene.spec['objects'] if o['id'] == 'spoon'))
    a.carried_payload = None
    a.stage = 'debug-e34b-near-com-empty-orientation'
    grasp_position(a, side, obj)
    a.stage = 'debug-e34b-near-com-actual-approach'
    narrow_material_approach(a, side, obj)
    a.stage = 'debug-e34b-near-com-real-grasp'
    for _ in range(3):
        a.act('GRASP' if side == 'left' else 'STILL', 'GRASP' if side == 'right' else 'STILL')
        check_pickup_neighbors(a, side, 'spoon', baseline)
    state, _ = a.c.snapshot()
    if not state['spoon']['grasp'][0 if side == 'left' else 1]:
        raise RuntimeError('Balanced pregrasp did not produce actual opposing contact')
    a.carried_payload = ('spoon', side)
    a.act()
    result = finish_from_grasp(a, 'spoon', side)
    return dict(result, segment_passed=True, local_debug_only=True, fixed36_positive=False)
