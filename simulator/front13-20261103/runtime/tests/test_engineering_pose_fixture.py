import copy
import numpy as np
import pytest
from test_engineering_checkpoint import controller
from videoicl_isaaclab.engineering_checkpoint import capture, restore_startup
from videoicl_isaaclab.engineering_checkpoint import _hash
from videoicl_isaaclab.engineering_pose_fixture import materialize, SCHEMA, REVIEWED_SMOOTH_FIELDS
from videoicl_isaaclab.layout import rotation_matrix


def recipe_and_controller():
    c = controller()
    c.ids = {'left': ([0], [1], 0)}
    c.scene.embodiment.gripper_values = lambda opening: [.04 * opening]
    template = capture(c, 'source')
    root = template['mechanisms']['cardboard']['root_state_task']
    mechanism = dict(body_names=['Base'], body_pos_task={'Base': root[:3]},
                     body_mat_task={'Base': rotation_matrix(root[3:7]).tolist()},
                     joint_names=['crease'], joint_pos=[.3], joint_vel=[0.])
    c.snapshot_mechanisms = lambda: {'cardboard': mechanism}
    recipe = dict(schema=SCHEMA, diagnostic_only=True, stage='before-contact',
        source_scene=copy.deepcopy(c.scene.spec), source_actions=76, grips={'left': 0.},
        robot_diagnostics={'left': dict(arm_joints=dict(names=['j1'], positions_rad=[.4]),
                                      finger_joints=dict(names=['j2'], positions_m=[.015]))},
        frame=dict(dt=.004, native_physics_tick=8240,
            state={'object': dict(pos=[.15, .1, .84], mat=np.eye(3).tolist(), grasp=[False, False])},
            mechanisms={'cardboard': mechanism}),
        passive_material=template['passive_material'], assumptions=['Crease material state taken from captured pre-fold source.'])
    return c, recipe


def test_old_pose_reconstruction_is_explicit_and_does_not_invent_dynamics_or_completion():
    c, recipe = recipe_and_controller()
    before = copy.deepcopy(recipe)
    fixture = materialize(c, recipe)
    assert fixture['state_quality'] == 'measured_pose_fixture'
    assert fixture['source']['steps'] == 76 and fixture['assumptions']
    assert fixture['objects']['object']['root_state_task'][:3] == [.15, .1, .84]
    assert fixture['robots']['left']['joint_pos'] == [.4, .015]
    assert fixture['robots']['left']['joint_vel'] == [0., 0.]
    assert fixture['robots']['left']['drive_targets']['position'] == [.4, 0.]
    assert fixture['mechanisms']['cardboard']['joint_pos'] == [.3]
    assert recipe == before
    restore_startup(c, fixture)
    assert c.steps == 0 and c.evaluator.completion_label == 'untouched'


def test_material_history_cannot_be_invented_and_foreign_source_is_rejected():
    c, recipe = recipe_and_controller()
    recipe.pop('passive_material')
    with pytest.raises(ValueError, match='passive material'):
        materialize(c, recipe)


def test_only_pinned_five_field_control_adaptation_preserves_the_physical_robot():
    c, recipe = recipe_and_controller()
    old = copy.deepcopy(c.scene.embodiment.config)
    old['physics'] = dict(dt=.004, action_seconds=.4, render_hz=5)
    old['asset'] = dict(path='same-reviewed-panda.usd')
    new = copy.deepcopy(old)
    for (section, key), value in REVIEWED_SMOOTH_FIELDS.items():
        new.setdefault(section, {})[key] = value
    c.scene.embodiment.config = new
    c.scene.spec['embodiment_config_sha256'] = _hash(new)
    recipe['source_scene']['embodiment_config_sha256'] = _hash(old)
    recipe['source_profile_config'] = old
    recipe['allow_reviewed_smooth_control_profile'] = True
    fixture = materialize(c, recipe)
    assert fixture['identity']['embodiment_config_sha256'] == _hash(new)
    assert any('five smooth-control' in text for text in fixture['assumptions'])
    c.scene.embodiment.config['asset']['path'] = 'different-robot.usd'
    c.scene.spec['embodiment_config_sha256'] = _hash(c.scene.embodiment.config)
    with pytest.raises(ValueError, match='Physical robot'):
        materialize(c, recipe)
    c, recipe = recipe_and_controller()
    recipe['source_scene']['seed'] = 4202
    with pytest.raises(ValueError, match='mismatch'):
        materialize(c, recipe)
