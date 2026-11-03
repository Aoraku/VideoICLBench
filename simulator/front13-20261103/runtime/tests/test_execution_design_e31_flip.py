import copy,json,math
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.execution_design_e31_flip import waypoints
from videoicl_isaaclab.execution_design_e31_continuation import screen


def fixture():
    return json.loads((Path(__file__).parent/'fixtures/e31_held_inversion.json').read_text())


def test_original_measured_grasp_has_continuous_inversion_and_return_without_state_writes():
    f=fixture();before=copy.deepcopy(f)
    route=waypoints(f['measured'],f['plate_position'],f['bowl_position'])
    result=screen(f['measured'],route)
    assert result['passed'] and result['minimum_joint_margin_rad']>.25
    assert result['maximum_joint_step_rad']<.45
    assert f==before
    source=np.asarray(f['measured']['rotation_task']);target=np.asarray(route[3]['rotation'])
    q=np.asarray(f['plate_quaternion']);plate=Rotation.from_quat(q[[1,2,3,0]]).as_matrix()
    normal=(target@source.T@plate)[:,2]
    assert -normal[2]>math.cos(math.radians(8.))


def test_inverted_return_is_computed_from_real_carried_plate_offset():
    f=fixture();route=waypoints(f['measured'],f['plate_position'],f['bowl_position'])
    turn=np.asarray(route[3]['rotation'])@np.asarray(f['measured']['rotation_task']).T
    offset=turn@(np.asarray(f['plate_position'])-f['measured']['position'])
    assert np.allclose(np.asarray(route[4]['position'])[:2]+offset[:2],f['bowl_position'][:2])
    assert route[4]['position'][2]==.94
    assert abs(route[-1]['position'][2]+offset[2]-.90)<1e-7


def test_body_correction_stops_when_plate_slips_despite_hand_rotation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e31_flip as flip,execution_design_e31_release as release
    contacts={frozenset(('plate','right_finger1')),frozenset(('plate','right_finger2'))}
    value=dict(pos=np.array([0.,0.,1.]),mat=Rotation.from_euler('x',120,degrees=True).as_matrix(),grasp=[False,True])
    c=SimpleNamespace(steps=0,snapshot=lambda:({'plate':value},contacts),action_feedback=lambda:{'control_feedback':{'right':dict(status='reached',joint_limit_names=[])}})
    def act(*args,**kwargs):c.steps+=1
    spec=dict(id='E31',semantic=dict(plate='plate',bowl='bowl'),objects=[dict(id='plate')])
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),c=c,carried_payload=('plate','right'),out=tmp_path,act=act)
    monkeypatch.setattr(release,'check_actual_limits',lambda *args:None)
    import pytest
    with pytest.raises(RuntimeError,match='body-normal correction stalled'):
        flip.finish_from_actual_plate(a,'plate','right')
    assert c.steps==10


def test_actual_down_face_can_return_without_chasing_extra_hand_precision(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e31_flip as flip,execution_design_e31_release as release
    from videoicl_isaaclab import execution_design_jacobian_reference as jac,execution_design_e31_continuation as continuation
    contacts={frozenset(('plate','right_finger1')),frozenset(('plate','right_finger2'))}
    value=dict(pos=np.array([.02,.02,1.]),mat=Rotation.from_euler('x',160,degrees=True).as_matrix(),grasp=[False,True])
    bowl=dict(pos=np.array([0.,.12,.82]));tip=np.array([0.,0.,1.]);rot=value['mat'].copy()
    c=SimpleNamespace(steps=0,snapshot=lambda:({'plate':value,'bowl':bowl},contacts))
    spec=dict(id='E31',semantic=dict(plate='plate',bowl='bowl'),objects=[dict(id='plate')])
    def move(target,**kw):
        delta=target['right']-tip;tip[:]=target['right'];value['pos']+=delta;c.steps+=1
    def unexpected(*args,**kw):raise AssertionError('No extra rotation is needed for a real down face')
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),c=c,carried_payload=('plate','right'),out=tmp_path,act=unexpected,tip=lambda side:tip.copy(),tcp_rotation_task=lambda side:rot.copy(),move_generated=move)
    monkeypatch.setattr(release,'check_actual_limits',lambda *args:None)
    monkeypatch.setattr(jac,'capture',lambda *args:dict(position=tip.copy(),rotation_task=rot.copy()))
    monkeypatch.setattr(continuation,'screen',lambda *args:dict(passed=True))
    report=flip.finish_from_actual_plate(a,'plate','right')
    assert report['actual_normal'][2]<-.90
    assert c.steps>0 and np.linalg.norm(tip-np.array([-.02,.10,.94]))<.003


def test_measured_inverted_return_uses_small_continuous_joint_steps():
    from videoicl_isaaclab.execution_design_e31_flip import dense_return_poses
    f=json.loads((Path(__file__).parent/'fixtures/e31_inverted_return_cp28.json').read_text())
    poses=dense_return_poses(f['measured'],f['target']);result=screen(f['measured'],poses)
    assert result['passed'] and result['maximum_joint_step_rad']<.18
    assert result['minimum_joint_margin_rad']>=.08


def test_free_yaw_increases_actual_remaining_return_joint_margin():
    f=json.loads((Path(__file__).parent/'fixtures/e31_return_yaw_cp110.json').read_text())
    original=screen(f['measured'],f['baseline']);changed=screen(f['measured'],f['yaw'])
    assert original['passed'] and changed['passed']
    assert original['minimum_joint_margin_rad']<.09
    assert changed['minimum_joint_margin_rad']>.20


def test_orientation_only_preserves_real_down_plate_and_does_not_translate(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e31_flip as flip,execution_design_e31_release as release
    contacts={frozenset(('plate','right_finger1')),frozenset(('plate','right_finger2'))}
    value=dict(pos=np.array([0.,0.,1.]),mat=Rotation.from_euler('x',170,degrees=True).as_matrix(),grasp=[False,True])
    spec=dict(id='E31',semantic=dict(plate='plate',bowl='bowl'),objects=[dict(id='plate')])
    def unexpected(*args,**kwargs):raise AssertionError('An already compliant real face needs no further public action')
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),
        c=SimpleNamespace(snapshot=lambda:({'plate':value},contacts)),carried_payload=('plate','right'),out=tmp_path,act=unexpected)
    monkeypatch.setattr(release,'check_actual_limits',lambda *args:None)
    result=flip.finish_from_actual_plate(a,'plate','right',orientation_only=True)
    assert result['actual_normal'][2]<-.98 and result['native_positive_claimed']is False
