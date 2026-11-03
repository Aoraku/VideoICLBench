"""Thin-layer side-band and multi-grasp regressions; CPU, not physics proof."""
from types import SimpleNamespace
import copy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e14_reference import (
    align_single_layer, measured_layer_band, require_single_layer_grasp)


class Reference:
    def __init__(self):
        self._execution_design_reference_authorized = True
        self.obj = dict(id='yellow', size=[.02, .02, .003])
        self.scene = SimpleNamespace(spec=dict(id='E14', execution_design=dict(revision=REVISION_V3),
            objects=[self.obj], semantic=dict(groups=dict(blocks=['yellow', 'red']))))
        self.state = {'yellow': dict(pos=[.08, -.0007, .823], mat=np.eye(3), grasp=[False, False]),
                      'red': dict(pos=[.08, -.0007, .8163], mat=np.eye(3), grasp=[False, False])}
        self.c = SimpleNamespace(snapshot=lambda: (self.state, set()))
        self.tcp = np.array([.08, -.0007, .8231])
        self.low = .81361  # Measured old run pinched yellow and red together.
        self.moves = []
        self.blocked = False

    def tip(self, side):
        return self.tcp.copy()

    def finger_geometry(self, side):
        return dict(source='actual_collision_mesh_current_body_pose', lowest_z_task_m=self.low)

    def move_generated(self, goals, tolerance):
        target = np.array(next(iter(goals.values())))
        self.moves.append(target)
        if not self.blocked:
            self.low += .9 * (target[2] - self.tcp[2])
            self.tcp = target


def test_measured_two_layer_failure_is_raised_into_target_only_band():
    a = Reference(); original = copy.deepcopy(a.scene.spec)
    align_single_layer(a, 'right', 'yellow')
    assert .8215 <= a.low <= .8225
    assert a.low > a.state['red']['pos'][2] + .003
    assert len(a.moves) >= 3
    assert a.scene.spec == original


def test_actual_two_layer_grasp_is_rejected_before_lifting():
    a = Reference()
    a.state['yellow']['grasp'][1] = True
    a.state['red']['grasp'][1] = True
    with pytest.raises(RuntimeError, match='exactly one'):
        require_single_layer_grasp(a, 'right', 'yellow')
    a.state['red']['grasp'][1] = False
    require_single_layer_grasp(a, 'right', 'yellow')


def test_no_hold_is_not_a_success():
    with pytest.raises(RuntimeError, match='exactly one'):
        require_single_layer_grasp(Reference(), 'right', 'yellow')


def test_remeasure_actual_lowest_layer_after_relay():
    a = Reference(); a.state['yellow']['pos'][2] = .803
    _, toe, top = measured_layer_band(a.state['yellow'], a.obj)
    assert toe == pytest.approx(.802)
    assert top == pytest.approx(.806)


def test_tilt_uses_highest_lower_face_and_lowest_upper_face():
    a = Reference(); theta = .01
    a.state['yellow']['mat'] = np.array([[1, 0, 0], [0, np.cos(theta), -np.sin(theta)], [0, np.sin(theta), np.cos(theta)]])
    _, toe, top = measured_layer_band(a.state['yellow'], a.obj)
    assert toe > .822 and top < .826


def test_blocked_waypoint_is_not_assumed_to_have_moved():
    a = Reference(); a.blocked = True
    with pytest.raises(RuntimeError, match='did not converge'):
        align_single_layer(a, 'right', 'yellow')
    assert len(a.moves) == 8


@pytest.mark.parametrize('change', [
    lambda a: setattr(a, '_execution_design_reference_authorized', False),
    lambda a: a.scene.spec.update(id='E15'),
    lambda a: a.scene.spec['execution_design'].update(revision='old')])
def test_no_formal_or_other_task_application(change):
    a = Reference(); change(a)
    with pytest.raises(ValueError): align_single_layer(a, 'right', 'yellow')
    assert not a.moves


def test_nonfinite_and_non_upright_layer_refuse():
    a = Reference(); a.state['yellow']['pos'][2] = float('nan')
    with pytest.raises(ValueError): measured_layer_band(a.state['yellow'], a.obj)
    a.state['yellow']['pos'][2] = .823
    a.state['yellow']['mat'][2, 2] = .9
    with pytest.raises(ValueError): measured_layer_band(a.state['yellow'], a.obj)
