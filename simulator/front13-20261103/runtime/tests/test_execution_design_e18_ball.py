import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_ball import floor_clear_grasp
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def geometry(bottom):
    cloud = np.array([[-.004, -.01, bottom], [.004, .01, .02]])
    return dict(source='actual_native_collision_mesh_current_body_pose',
                clouds_tcp=[cloud.copy(), cloud.copy(), cloud.copy()])


def test_original_center_collides_floor_and_only_reference_height_is_raised():
    point = np.array([-.074, .111, .861])
    original = point.copy()
    target, proof = floor_clear_grasp(point, .015, geometry(-.021), np.eye(3))
    assert point.tolist() == original.tolist()
    assert target[:2].tolist() == point[:2].tolist()
    assert target[2] == pytest.approx(.868)
    assert proof['planned_floor_clearance_m'] == pytest.approx(.001)
    assert not proof['native_grip_verified']


def test_clear_fingers_keep_original_ball_center_reference():
    target, _ = floor_clear_grasp([0., 0., .86], .015, geometry(-.01), np.eye(3))
    assert target.tolist() == [0., 0., .86]


def test_rotation_uses_measured_world_floor_instead_of_tcp_local_z():
    rotation = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]])
    target, proof = floor_clear_grasp([0., 0., .86], .015, geometry(-.03), rotation)
    assert target[2] == pytest.approx(.86)
    assert proof['hand_lowest_relative_z_m'] == pytest.approx(-.004)


def test_unreachable_pad_overlap_rejects_instead_of_declaring_grip():
    with pytest.raises(MechanismExecutionError, match='overlap pads'):
        floor_clear_grasp([0., 0., .86], .015, geometry(-.04), np.eye(3))


@pytest.mark.parametrize('bad', ['missing_palm', 'nonfinite', 'radius', 'source'])
def test_complete_native_geometry_is_required(bad):
    g = geometry(-.02)
    radius = .015
    if bad == 'missing_palm': g['clouds_tcp'].pop()
    if bad == 'nonfinite': g['clouds_tcp'][0][0][0] = np.nan
    if bad == 'radius': radius = float('nan')
    if bad == 'source': g['source'] = 'nominal'
    with pytest.raises(ValueError): floor_clear_grasp([0., 0., .86], radius, g, np.eye(3))


@pytest.mark.parametrize('entry', ['e18_grasp_lift_ball_from616', 'e18_grasp_lift_ball_from_open483', 'e18_roll_selected_ball_from160','e18_roll_selected_ball_from_closed3','e18_roll_selected_ball_from_tilted40','e18_closed_cap_from3'])
def test_native_existing_drawer_admission_registers_only_the_explicit_ball_entry(monkeypatch, entry):
    from types import SimpleNamespace
    from test_execution_design_inputs_v3 import base, apply
    from videoicl_isaaclab.realworld_mechanism_expert import _Author
    from videoicl_isaaclab.execution_design_e18_reference import E18MeasuredAuthor
    spec = apply(base('E18'), 'I')
    spec['engineering_checkpoint_resume'] = dict(diagnostic_only=True, entry=entry)
    author = SimpleNamespace(scene=SimpleNamespace(spec=spec), c=SimpleNamespace(steps=0),
                             control_report=dict(engineering_reference_only=True))
    monkeypatch.setattr(_Author, 'mechanisms', lambda self: {})
    monkeypatch.setattr(_Author, 'displacement', lambda self, *a: .095)
    monkeypatch.setattr(_Author, 'point', lambda self, *a: np.zeros(3))
    monkeypatch.setattr(_Author, 'axis', lambda self, *a: np.array([-1., 0., 0.]))
    worker = E18MeasuredAuthor(author, allow_existing_e18_drawer=True)
    assert worker.task == 'E18'
    spec['engineering_checkpoint_resume']['entry'] = 'unregistered'
    with pytest.raises(MechanismExecutionError):
        E18MeasuredAuthor(author, allow_existing_e18_drawer=True)


def test_whole_cabinet_cap_dispatch_preserves_explicit_parameters(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import engineering_front25_suffix as module
    calls=[]
    def load(name,package):
        assert name=='.execution_design_e18_closed_cap'
        return SimpleNamespace(run_segment=lambda *args:calls.append(args)or {'routed':True})
    monkeypatch.setattr(module.importlib,'import_module',load)
    author=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E18'}))
    result=module.solve(author,{},dict(entry='e18_closed_cap_from3',parameters={}))
    assert result['routed']is True
    assert result['full_task_acceptance']is False
    assert calls==[(author,'e18_closed_cap_from3',{})]
