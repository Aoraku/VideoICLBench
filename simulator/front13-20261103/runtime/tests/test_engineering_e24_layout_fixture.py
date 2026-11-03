from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest

from test_engineering_checkpoint import controller, Asset, all_writes
from test_execution_design_inputs_v3 import base, apply
from videoicl_isaaclab import engineering_checkpoint as core
from videoicl_isaaclab import engineering_e24_layout_fixture as fixture


def scenes(monkeypatch):
    monkeypatch.delenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT', raising=False)
    old = apply(base('E24'), 'I')
    old['embodiment_config_sha256'] = 'b' * 64
    monkeypatch.setenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT', '1')
    new = apply(base('E24'), 'I')
    new['embodiment_config_sha256'] = 'b' * 64
    return old, new


def archived_fixture(tmp_path, monkeypatch):
    old, new = scenes(monkeypatch)
    c = controller()
    c.scene.spec = old
    initial = c.scene.objects['object'].data.root_state_w[0].copy()
    c.scene.objects = {o['id']: Asset(initial.copy()) for o in old['objects']}
    c.snapshot = lambda: ({n: dict(grasp=[False, False]) for n in c.scene.objects}, set())
    c.steps = 4
    c.physics_ticks = 401
    checkpoint = core.capture(c, 'four-action-boundary')
    raw = json.dumps(checkpoint).encode()
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(fixture, 'SOURCE_SHA256', digest)
    monkeypatch.setattr(fixture.archive, 'ENGINEERING_BASE', tmp_path)
    root = tmp_path / fixture.SOURCE_ROOT
    def put(relative, value):
        p = root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))
    p = root / fixture.SOURCE_FILE
    p.parent.mkdir(parents=True)
    p.write_bytes(raw)
    prefix = 'result/' + fixture.SOURCE_ROOM + '/'
    put(prefix + 'scene-input.private.json', old)
    put(prefix + 'native-terminal.private.json', dict(room=fixture.SOURCE_ROOM,
        recorder_stopped=True, steps=4, terminal_controller_tick=401))
    put(prefix + 'native-capture/capture.private.json', dict(
        engineering_reference_only=True, native_action_count=4))
    put(prefix + 'reference-final-state.private.json', dict(actions=4, native_physics_tick=401))
    recipe = dict(schema=fixture.SCHEMA, diagnostic_only=True, history_reconstructed=False,
        server_source=dict(engineering_root=str(root), room_id=fixture.SOURCE_ROOM,
                           checkpoint=fixture.SOURCE_FILE, sha256=digest))
    c.scene.spec = new
    return c, recipe, checkpoint


def test_declared_layout_is_exactly_recomputed_from_original(monkeypatch):
    old, new = scenes(monkeypatch)
    before = deepcopy(old)
    assert fixture.verify_layout_only(old, new)['initial_lid_xy'] == [-.03, .365]
    assert old == before


def test_real_loader_preserves_layout_identity_after_contract_merge(tmp_path, monkeypatch):
    from test_execution_design_inputs_v3 import P
    from videoicl_isaaclab.realworld_scenes import load
    binding = json.loads(P.read_text())
    binding['execution_design'] = dict(revision='embodied50-execution-v3-20261102', condition='I')
    path = tmp_path / 'bindings.json'
    path.write_text(json.dumps(binding))
    monkeypatch.delenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT', raising=False)
    old = load('E24', 'A', 4201, path, verify_files=False)
    monkeypatch.setenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT', '1')
    new = load('E24', 'A', 4201, path, verify_files=False)
    assert fixture.verify_layout_only(old, new)['initial_lid_xy'] == [-.03, .365]
    for key in ('assignment_identity_sha256', 'environment_identity', 'paired_input_identity'):
        assert new['execution_design'][key] != old['execution_design'][key]
        assert new['execution_design']['source_' + key] == old['execution_design'][key]


@pytest.mark.parametrize('field', ['mass', 'goal', 'cup_position', 'profile', 'rule', 'marker', 'variant'])
def test_other_geometry_rules_or_identity_changes_are_rejected(monkeypatch, field):
    old, new = scenes(monkeypatch)
    if field == 'mass': new['objects'][0]['mass'] *= 2
    if field == 'goal': new['goals'].append(dict(kind='invented'))
    if field == 'cup_position': next(o for o in new['objects'] if o['id'] != 'lid')['xy'][0] += .02
    if field == 'profile': new['embodiment_config_sha256'] = 'd' * 64
    if field == 'rule': new['execution_design']['source_sha256'] = 'd' * 64
    if field == 'marker': new['e24_lid_initial_layout']['derived_lid_xy'][0] = 0.
    if field == 'variant': new['variant'] = 'B'
    with pytest.raises(ValueError): fixture.verify_layout_only(old, new)


def test_startup_lid_only_migration_preserves_native_states_and_never_writes(tmp_path, monkeypatch):
    c, recipe, source = archived_fixture(tmp_path, monkeypatch)
    result = fixture.materialize(c, recipe, dict(retarget_measured_hold=True))
    assert all_writes(c) == 0
    assert result['state_quality'] == 'measured_pose_fixture'
    assert result['identity'] == core.identity(c)
    assert result['source'] == source['source']
    assert result['robots'] == source['robots']
    assert result['mechanisms'] == source['mechanisms']
    assert result['controller'] == source['controller']
    for name, state in source['objects'].items():
        if name != 'lid': assert result['objects'][name] == state
    a = np.array(source['objects']['lid']['root_state_task'])
    b = np.array(result['objects']['lid']['root_state_task'])
    assert b[:2].tolist() == [-.03, .365]
    assert np.array_equal(a[2:7], b[2:7])
    assert np.array_equal(b[7:], np.zeros(6))
    assert result['context']['requires_native_fk_retarget']
    assert result['context']['e24_layout_migration']['history_reconstructed'] is False
    assert result['readback']['available'] is False
    assert not any(k in result for k in ('evaluator', 'success', 'task_score_100', 'initial_sealed'))
    assert core.reseal(result) == result


@pytest.mark.parametrize('bad', ['selector', 'retarget', 'terminal', 'digest', 'source_identity', 'grasp'])
def test_unreviewed_or_unsealed_source_is_rejected_before_writes(tmp_path, monkeypatch, bad):
    c, recipe, source = archived_fixture(tmp_path, monkeypatch)
    request = dict(retarget_measured_hold=True)
    root = Path(recipe['server_source']['engineering_root'])
    if bad == 'selector': recipe['server_source']['checkpoint'] = '../another-checkpoint'
    if bad == 'retarget': request.clear()
    if bad == 'terminal':
        (root / ('result/' + fixture.SOURCE_ROOM + '/native-terminal.private.json')).write_text('{}')
    if bad in ('digest', 'source_identity', 'grasp'):
        if bad == 'digest': source['stage'] = 'tampered'
        if bad == 'source_identity': source['identity']['physical_geometry_sha256'] = 'd' * 64
        if bad == 'grasp': source['readback']['object_grasps']['lid'] = [True, False]
        if bad != 'digest': source = core.reseal(source)
        raw = json.dumps(source).encode()
        (root / fixture.SOURCE_FILE).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        monkeypatch.setattr(fixture, 'SOURCE_SHA256', digest)
        recipe['server_source']['sha256'] = digest
    with pytest.raises(ValueError): fixture.materialize(c, recipe, request)
    assert all_writes(c) == 0
