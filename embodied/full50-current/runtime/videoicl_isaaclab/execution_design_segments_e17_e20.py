"""Private local engineering segments, entered from real restored state.

Restoration, native checkpoint identity and complete-task acceptance belong to
the caller. This module never assigns a pose, a joint state, history or score.
"""
from copy import deepcopy
import numpy as np
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


SEGMENTS = {
    'e17_insert_held_green': ('E17', {'target_index'}),
    'e20_grasp_blue': ('E20', set()),
    'e20_grasp_and_lift_blue': ('E20', set()),
    'e20_b_grasp_and_lift_blue1': ('E20', set()),
    'e20_liftoff_red': ('E20', {'measured_grips_before'}),
}
DISK_SHA = '0a52a9c5b908277e7e408155316a3fc55f889405d6ab0331f0922e8bb4047120'
GREEN_SHA = 'fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'


def _same_size(value, expected, tolerance):
    try:
        value = np.asarray(value, float)
        return value.shape == (3,) and bool(np.allclose(value, expected, atol=tolerance, rtol=0))
    except (TypeError, ValueError):
        return False


def _source(policy, name, digest, size):
    obj = policy.objects.get(name, {})
    if (obj.get('kind') != 'source_mesh' or obj.get('source_asset', {}).get('sha256') != digest
            or not _same_size(obj.get('size'), size, 1e-7)):
        raise ToolExecutionError('Local segment source geometry mismatch: ' + name)


def _held_with_contacts(policy, name, side):
    policy.require_held({'actor': name}, side)
    state, contacts = policy.snapshot()
    if not all(frozenset((name, f'{side}_finger{i}')) in contacts for i in (1, 2)):
        raise ToolExecutionError('Local segment requires actual bilateral finger contact: ' + name)
    other = 1 if side == 'left' else 0
    other_side = 'right' if side == 'left' else 'left'
    if any(v['grasp'][other] for v in state.values()) or any(
            frozenset((actor, f'{other_side}_finger{i}')) in contacts
            for actor in state for i in (1, 2)):
        raise ToolExecutionError('Local segment other hand must be actually empty')


def _source_rail(policy, name, index):
    support = f'fixture{index}'
    fixtures = policy.spec.get('fixtures', [])
    if (policy.d.get('initial_storage', {}).get(name) != support or len(fixtures) <= index
            or fixtures[index].get('type') != 'box'
            or not _same_size(fixtures[index].get('size'), [.003, .012, .014], 1e-9)
            or not policy.contact(name, support)):
        raise ToolExecutionError('Local segment lacks actual original source-rail contact: ' + name)


def run_segment(author, segment, parameters):
    """Create the original policy and execute one guarded public-action tail.

    Parameters do not contain saved poses, scores or assumed grasp flags.
    Successful return certifies only completion of this local segment.
    """
    if segment not in SEGMENTS or not isinstance(parameters, dict):
        raise ToolExecutionError('Unknown E17/E20 local segment or invalid parameters')
    task, allowed = SEGMENTS[segment]
    if set(parameters) - allowed:
        raise ToolExecutionError('Unreviewed E17/E20 segment parameters')
    spec = author.scene.spec
    design = spec.get('execution_design', {})
    if (not author.control_report.get('engineering_reference_only')
            or spec.get('id') != task or design.get('revision') != REVISION_V3
            or design.get('condition') != 'I'):
        raise ToolExecutionError('Explicit v3/I independent engineering segment required')
    if segment in ('e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1'):
        checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
        variant,steps,tick=('B',522,53040)if segment=='e20_b_grasp_and_lift_blue1'else('C',276,28440)
        b_held_boundary=(variant=='B'and source.get('steps')==1 and source.get('physics_ticks')==111)
        if (spec.get('variant')!=variant or spec.get('seed')!=4201 or checkpoint.get('diagnostic_only')is not True
                or(not b_held_boundary and(source.get('steps')!=steps or source.get('physics_ticks')!=tick))):
            raise ToolExecutionError('Blue short lift requires the real '+variant+str(steps)+' diagnostic boundary')
    policy = ExecutionDesignAuthor(author)
    # Constructor initializes real grasps, geometry, action origin and budget.
    # No completed prefix or accepted action is reconstructed here.
    if segment == 'e17_insert_held_green':
        name = 'green_square'
        _source(policy, name, GREEN_SHA, [.02, .02, .003])
        _held_with_contacts(policy, name, 'right')
        from .execution_design_e17_stand import descriptor, native_readback
        if policy.objects.get('stand', {}).get('e17_stand_geometry') != descriptor():
            raise ToolExecutionError('Local E17 segment requires reviewed 70mm derived stand')
        actual = native_readback(author.scene)
        try:
            mass = np.asarray(actual.get('mass_kg'), float)
            valid_mass = mass.size > 0 and bool(np.isfinite(mass).all()) and bool(np.allclose(
                mass, descriptor()['empty_mass_estimate_kg'], atol=1e-5, rtol=0))
        except (AttributeError, TypeError, ValueError):
            valid_mass = False
        if (not actual or actual.get('measured') is not True
                or actual.get('derived_geometry_sha256') != descriptor()['derived_geometry_sha256']
                or actual.get('kinematic_enabled') is not False
                or actual.get('gravity_disabled') is not False or not valid_mass):
            raise ToolExecutionError('Local E17 live stand geometry/dynamics readback rejected')
        regions = [r for r in policy.d['local_regions'] if r['id'] == 'lower']
        if len(regions) != 1 or name not in regions[0].get('members', []):
            raise ToolExecutionError('Green square is not an actual lower-layer member')
        members = regions[0]['members']
        index = members.index(name)
        requested = parameters.get('target_index', index)
        if type(requested) is not int or requested != index:
            raise ToolExecutionError('E17 local target must match actual layer assignment')
        from .execution_design_e17_insertion import front_lower_slot, place_held_lower
        policy.stage('local-e17-insert-held-green')
        place_held_lower(policy, name, 'stand', front_lower_slot(policy, index, len(members)),
                         policy.ref(name), 'right')
    elif segment in ('e20_grasp_blue','e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1'):
        is_b=segment=='e20_b_grasp_and_lift_blue1'
        name = 'blue_supply_1'if is_b else'blue_supply_3'
        _source(policy, name, DISK_SHA, [.016, .01603, .000988])
        _source_rail(policy, name, 3 if is_b else 2)
        state, _ = policy.snapshot()
        held_start=is_b and b_held_boundary
        if held_start:
            _held_with_contacts(policy,name,'right')
        elif any(any(v['grasp']) for v in state.values()):
            raise ToolExecutionError('Blue grip tail starts before any actual grip')
        ref = policy.ref(name)
        side='right'if is_b else'left'
        if not held_start and np.max(np.abs(policy.point(ref) - policy.tip(side))) > .0025:
            raise ToolExecutionError('Blue grip segment must start at measured pre-grasp waypoint')
        from .execution_design_e20_reference import finish_chip_grip
        policy.stage('local-e20-blue-three-grasp-tail')
        if is_b:
            # Real B522/core1 remains held while being drawn off its narrow
            # rail. Source extraction can move 7mm without a grip failure.
            # Resume core1's remaining two squeezes; transportation starts
            # from the actual completed pinch, not the original rail centre.
            source_xy=np.asarray(policy.objects[name]['xy'],float)
            for _ in range(2 if held_start else 3):
                policy.act(side,'GRASP');_held_with_contacts(policy,name,side)
                if np.linalg.norm(np.asarray(policy.snapshot()[0][name]['pos'])[:2]-source_xy)>.012:
                    raise ToolExecutionError('Blue B extraction exceeds 12mm during actual grasp')
        else:finish_chip_grip(policy, ref, side)
        _held_with_contacts(policy, name, side)
        if segment in ('e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1'):
            initial=np.asarray(policy.snapshot()[0][name]['pos'],float).copy()
            policy.stage('local-e20-blue-three-grasp-short-lift')
            for _ in range(3):
                # Original workflow's public 10mm lift increments; no new wait.
                policy.act(side,'UP',mm=10.)
                _held_with_contacts(policy,name,side)
                current=np.asarray(policy.snapshot()[0][name]['pos'],float)
                if np.linalg.norm(current[:2]-initial[:2])>.006:
                    raise ToolExecutionError('Blue slides sideways over 6mm during short lift')
            rise=float(current[2]-initial[2])
            if rise<.020:
                raise ToolExecutionError('Blue short lift did not actually rise at least 20mm')
            policy.operations.append(dict(operation='actual_blue_short_lift',requested_public_lift_m=.030,
                measured_object_rise_m=rise,measured_xy_slide_m=float(np.linalg.norm(current[:2]-initial[:2]))))
    else:
        name = 'red_supply_1'
        _source(policy, name, DISK_SHA, [.016, .01603, .000988])
        _source_rail(policy, name, 7)
        _held_with_contacts(policy, name, 'right')
        before = parameters.get('measured_grips_before', 2)
        if type(before) is not int or before not in (1, 2):
            raise ToolExecutionError('Red local prefix must contain one or two measured held receipts')
        from .execution_design_e20_reference import require_measured_red_grip_ready, verify_grip_during_small_liftoff
        require_measured_red_grip_ready(policy, policy.ref(name), 'right')
        policy.stage('local-e20-red-measured-liftoff')
        verify_grip_during_small_liftoff(policy, policy.ref(name), 'right', initial_measured_grips=before)
        _held_with_contacts(policy, name, 'right')
    return dict(local_completed=True, operations=deepcopy(policy.operations))
