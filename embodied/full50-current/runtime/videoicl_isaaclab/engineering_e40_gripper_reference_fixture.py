"""Two-field E40 reference migration preserving the existing real spine grip."""
from copy import deepcopy
import math
from .engineering_checkpoint import _hash, identity, reseal
from .engineering_gripper_reference_fixture import FIELDS

OLD_PROFILE = '7a29f9dd0b6c77b0a0c3ebd0904a00208347b5e11c169a0b4b112a6140afa019'
NEW_PROFILE = 'a715c83cde5cc5bd140514fec16e10f3194d7f7c9dbc9b2d9ad2635a94a8db75'
GEOMETRY = '32aa35478a578e66cd674a6cfa04f7d3c56d78b33f2bf05a744a64380b45350b'


def materialize(controller, recipe):
    if (recipe.get('schema') != 'engineering-e40-gripper-reference-migration-v1'
            or recipe.get('diagnostic_only') is not True):
        raise ValueError('Explicit diagnostic E40 gripper migration required')
    checkpoint = deepcopy(recipe['checkpoint'])
    signature = checkpoint.pop('checkpoint_sha256')
    if _hash(checkpoint) != signature:
        raise ValueError('Native checkpoint integrity mismatch')
    checkpoint['checkpoint_sha256'] = signature
    if (checkpoint.get('schema') != 'engineering-native-checkpoint-v1'
            or checkpoint.get('state_quality') != 'measured_native_state'
            or checkpoint.get('diagnostic_only') is not True):
        raise ValueError('Complete measured native diagnostic checkpoint required')
    previous = checkpoint['identity']; old = recipe['source_profile']
    if ((previous['task'], previous['variant'], previous['seed']) != ('E40', 'A', 4201)
            or previous['physical_geometry_sha256'] != GEOMETRY
            or previous['embodiment_config_sha256'] != OLD_PROFILE or _hash(old) != OLD_PROFILE):
        raise ValueError('Reviewed corrected E40 spine-hold checkpoint/profile required')
    if any(key in old['control'] for key in FIELDS):
        raise ValueError('Original profile cannot already have gripper reference fields')
    expected = deepcopy(old); expected['control'].update(FIELDS)
    current = identity(controller)
    if (controller.scene.embodiment.config != expected or _hash(expected) != NEW_PROFILE
            or current['embodiment_config_sha256'] != NEW_PROFILE):
        raise ValueError('Only the two reviewed gripper reference fields may change')
    if ({k: v for k, v in previous.items() if k != 'embodiment_config_sha256'}
            != {k: v for k, v in current.items() if k != 'embodiment_config_sha256'}):
        raise ValueError('E40 migration changed assignment/source/physical geometry')
    controls = checkpoint['controller']
    if any(key in controls for key in ('gripper_reference', 'gripper_reference_velocity')):
        raise ValueError('Original profile cannot declare new ramp state')
    contacts = {frozenset(pair) for pair in checkpoint['readback']['contacts']}
    if checkpoint['readback'].get('available') is not True or any(
            frozenset(('clip1/back', 'right_finger' + str(i))) not in contacts for i in (1, 2)):
        raise ValueError('Both actual right-finger spine contacts required')
    if any(set(pair) & {'left_finger1', 'left_finger2'} for pair in contacts):
        raise ValueError('Receiving left hand must be empty')
    if controls['grips'] != dict(left=.04, right=0.):
        raise ValueError('Exact original open-left/holding-right goals required')
    reference = {}; velocity = {}
    for side, goal in controls['grips'].items():
        robot = checkpoint['robots'][side]
        ids = [robot['joint_names'].index(name) for name in old['gripper']['joints']]
        values = [float(robot['drive_targets']['position'][i]) for i in ids]
        if any(not math.isfinite(x) or abs(x-goal) > 1e-7 for x in values):
            raise ValueError('Captured drive targets must match original binary goal')
        # Starting an already-held hand at measured q would unload its grip.
        # Preserve its captured drive target; future public goals ramp normally.
        reference[side] = [values]; velocity[side] = [[0.] * len(values)]
    controls['gripper_reference'] = reference
    controls['gripper_reference_velocity'] = velocity
    checkpoint['identity'] = current
    checkpoint['context']['e40_gripper_reference_migration'] = dict(
        only_added_control_fields=FIELDS, captured_drive_targets_preserved=True,
        existing_right_spine_grip_not_unloaded=True, original_goals_unchanged=True,
        physics_geometry_material_gains_unchanged=True, diagnostic_only=True)
    checkpoint['limitations'].append('New gripper reference uses captured old drive targets and zero reference velocity')
    return reseal(checkpoint)
