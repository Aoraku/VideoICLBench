import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from videoicl_isaaclab import engineering_e40_gripper_reference_fixture as migration
from videoicl_isaaclab.engineering_checkpoint import reseal
from videoicl_isaaclab.engineering_pose_fixture import REVIEWED_SMOOTH_FIELDS


def example(monkeypatch):
    old = json.loads((Path(__file__).parents[1] / 'configs/embodiments/franka.json').read_text())
    old['physics']['render_hz'] = 5
    for (section, key), value in REVIEWED_SMOOTH_FIELDS.items():
        old[section][key] = value
    previous = dict(task='E40', variant='A', seed=4201,
        physical_geometry_sha256=migration.GEOMETRY, embodiment_config_sha256=migration.OLD_PROFILE,
        assignment_identity_sha256='assignment', source_sha256='source')
    checkpoint = reseal(dict(schema='engineering-native-checkpoint-v1', state_quality='measured_native_state',
        diagnostic_only=True, identity=previous, context={}, limitations=[],
        controller=dict(grips=dict(left=.04, right=0.)),
        robots={side: dict(joint_names=old['gripper']['joints'], joint_pos=[.017, .017],
                          drive_targets=dict(position=[value, value]))
                for side, value in (('left', .04), ('right', 0.))},
        readback=dict(available=True, contacts=[['clip1/back', 'right_finger1'], ['clip1/back', 'right_finger2']])) )
    current = dict(previous, embodiment_config_sha256=migration.NEW_PROFILE)
    config = deepcopy(old); config['control'].update(migration.FIELDS)
    controller = SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config=config)))
    monkeypatch.setattr(migration, 'identity', lambda c: current)
    recipe = dict(schema='engineering-e40-gripper-reference-migration-v1', diagnostic_only=True,
                  checkpoint=checkpoint, source_profile=old)
    return controller, recipe, current


def test_existing_payload_keeps_captured_zero_drive_not_measured_seventeen_mm(monkeypatch):
    controller, recipe, current = example(monkeypatch)
    original = deepcopy(recipe)
    result = migration.materialize(controller, recipe)
    assert result['identity'] == current
    assert result['controller']['gripper_reference'] == dict(left=[[.04, .04]], right=[[0., 0.]])
    assert result['controller']['gripper_reference_velocity'] == dict(left=[[0., 0.]], right=[[0., 0.]])
    assert result['robots'] == original['checkpoint']['robots']
    assert recipe == original


@pytest.mark.parametrize('bad', ['physics', 'source', 'contact', 'drive', 'integrity'])
def test_migration_rejects_unreviewed_changes(monkeypatch, bad):
    controller, recipe, current = example(monkeypatch)
    if bad == 'physics': controller.scene.embodiment.config['physics']['dt'] *= 2
    elif bad == 'source': current['source_sha256'] = 'different'
    else:
        checkpoint = recipe['checkpoint']
        if bad == 'contact': checkpoint['readback']['contacts'].pop()
        elif bad == 'drive': checkpoint['robots']['right']['drive_targets']['position'] = [.017, .017]
        elif bad == 'integrity': checkpoint['robots']['right']['joint_pos'][0] += .001
        if bad != 'integrity': recipe['checkpoint'] = reseal(checkpoint)
    with pytest.raises(ValueError): migration.materialize(controller, recipe)
