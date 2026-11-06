"""Same-server E24 diagnostic fixture for the declared clear-lid layout.

Only the lid receives an engineered startup XY and zero velocity. All other
native states come from the closed four-action source boundary. This fixture
does not represent a source-initial episode or restore task history.
"""
from copy import deepcopy
from types import SimpleNamespace
import json

from . import engineering_checkpoint as core
from . import engineering_front25_server_source as archive
from .execution_design_e24_layout import apply_layout, bind_identity, LID_XY, VERSION
from .execution_design_inputs_v3 import physical_input_signature

SCHEMA = 'engineering-e24-lid-layout-migration-v1'
SOURCE_ROOT = 'execution-design-v3-20261102-e24-checkpoint-contact-alias1-slot07-v15-s4201'
SOURCE_ROOM = 'room-00-E24-A-s4201'
SOURCE_FILE = 'result/' + SOURCE_ROOM + '/engineering-reference/checkpoints/failure-after-last-action.private.json'
SOURCE_SHA256 = 'd726844fd284562a06590d23fc14bebc4d5ade824fa9c8796c97d032c1eef52b'


def _different_paths(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict):
        return [path for key in sorted(set(a) | set(b))
                for path in (_different_paths(a[key], b[key], prefix + '/' + key)
                             if key in a and key in b else [prefix + '/' + key])]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [path for index, (x, y) in enumerate(zip(a, b))
                for path in _different_paths(x, y, prefix + '/' + str(index))]
    return [] if a == b else [prefix]


def verify_layout_only(old, new):
    if (old.get('id'), old.get('variant'), old.get('seed')) != ('E24', 'A', 4201):
        raise ValueError('Reviewed E24 A/I/4201 source required')
    if old.get('execution_design', {}).get('condition') != 'I':
        raise ValueError('Reviewed E24 condition I required')
    expected = deepcopy(old)
    apply_layout(expected)
    expected['execution_design']['paired_physical_input_sha256'] = physical_input_signature(expected)
    bind_identity(expected)
    keys = (*core.PHYSICAL_KEYS, 'id', 'variant', 'seed', 'execution_design',
            'embodiment', 'embodiment_config_sha256', 'e24_lid_initial_layout')
    differences = _different_paths({k: expected.get(k) for k in keys},
                                  {k: new.get(k) for k in keys})
    if differences:
        # Key paths only: source specifications and values stay server-local.
        raise ValueError('E24 fixture permits only the declared lid XY and derived identities; differing paths=' +
                         json.dumps(differences[:30], separators=(',', ':')))
    return dict(version=VERSION, initial_lid_xy=list(LID_XY),
                other_geometry_and_rules_unchanged=True)


def materialize(controller, recipe, request):
    if (recipe.get('schema') != SCHEMA or recipe.get('diagnostic_only') is not True
            or recipe.get('history_reconstructed') is not False
            or request.get('retarget_measured_hold') is not True):
        raise ValueError('Explicit E24 debug migration and native measured-joint hold required')
    selector = recipe.get('server_source')
    root = archive.ENGINEERING_BASE / SOURCE_ROOT
    expected_selector = dict(engineering_root=str(root), room_id=SOURCE_ROOM,
                             checkpoint=SOURCE_FILE, sha256=SOURCE_SHA256)
    if selector != expected_selector or root.is_symlink() or not root.is_dir():
        raise ValueError('Pinned closed E24 source archive required')
    raw, checkpoint_proof = archive._read(root, SOURCE_FILE)
    if checkpoint_proof['sha256'] != SOURCE_SHA256:
        raise ValueError('Pinned E24 source checkpoint SHA mismatch')
    checkpoint = json.loads(raw)
    signature = checkpoint.pop('checkpoint_sha256', None)
    if signature != core._hash(checkpoint):
        raise ValueError('Original native E24 checkpoint integrity mismatch')
    if (checkpoint.get('schema') != core.SCHEMA
            or checkpoint.get('diagnostic_only') is not True
            or checkpoint.get('state_quality') != 'measured_native_state'
            or checkpoint.get('source', {}).get('steps') != 4
            or checkpoint.get('source', {}).get('physics_ticks') != 401):
        raise ValueError('Exact measured four-action E24 boundary required')
    room = archive._sealed_room_source(root, SOURCE_ROOM,
        dict(actions=4, shared_tick=401, native_physics_tick=401))
    raw, scene_proof = archive._read(root, 'result/' + SOURCE_ROOM + '/scene-input.private.json')
    old = json.loads(raw)
    old_identity = core.identity(SimpleNamespace(scene=SimpleNamespace(spec=old)))
    if checkpoint['identity'] != old_identity:
        raise ValueError('Native E24 checkpoint and original scene identity mismatch')
    change = verify_layout_only(old, controller.scene.spec)
    grasps = checkpoint.get('readback', {}).get('object_grasps', {})
    if (set(grasps) != set(checkpoint['objects'])
            or any(flags != [False, False] for flags in grasps.values())):
        raise ValueError('Reviewed E24 migration requires both hands empty')
    root_state = core._array(checkpoint['objects']['lid']['root_state_task'], (13,), 'lid root')
    original_lid = root_state.tolist()
    root_state[:2] = LID_XY
    root_state[7:] = 0.
    checkpoint['objects']['lid']['root_state_task'] = root_state.tolist()
    checkpoint['identity'] = core.identity(controller)
    checkpoint['state_quality'] = 'measured_pose_fixture'
    checkpoint['context']['requires_native_fk_retarget'] = True
    checkpoint['context']['e24_layout_migration'] = dict(
        diagnostic_only=True, source_initial_episode=False, history_reconstructed=False,
        source_identity=old_identity, change=change, source_checkpoint=checkpoint_proof,
        source_scene=scene_proof, source_room=room,
        old_lid_root_state_task=original_lid,
        lid_pose_source='engineered_startup_XY; measured_Z_and_orientation',
        lid_velocity_source='explicit_zero_startup_assumption',
        other_native_actor_states_and_drive_targets_preserved=True)
    # Old contact pairs describe the old lid placement. Actual new contacts
    # must be measured by the normal native settling/readback admission.
    checkpoint['readback'] = dict(available=False, object_grasps=grasps)
    checkpoint['assumptions'].append(
        'E24 lid startup XY is explicitly engineered to [-0.03, 0.365] m with zero '
        'linear/angular velocity; its Z/orientation and all other native actor, joint '
        'and drive states are preserved. Native FK/contact readback is required.')
    checkpoint['limitations'].append(
        'Declared clear-lid layout diagnostic only; old physical task history and '
        'contact caches are not restored. Full acceptance requires a fresh source-initial run.')
    return core.reseal(checkpoint)
