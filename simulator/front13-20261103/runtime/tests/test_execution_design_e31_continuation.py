import copy,json
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e31_continuation import pinch_rotations,screen


def fixture():
    return json.loads((Path(__file__).parent/'fixtures/e31_postpush_continuation.json').read_text())


def test_actual_postpush_state_has_continuous_oblique_rim_route():
    f=fixture();before=copy.deepcopy(f);result=screen(f['measured'],f['waypoints'])
    assert result['passed'] and len(result['samples'])>50
    assert result['minimum_joint_margin_rad']>=.08
    assert result['maximum_joint_step_rad']<.45
    assert f==before


def test_near_hard_stop_is_rejected_before_solving():
    f=fixture();f['measured']['q'][3]=f['measured']['limits'][3][0]+.000192
    result=screen(f['measured'],f['waypoints'])
    assert result==dict(passed=False,reason='initial_joint_margin',samples=[])


def test_nonfinite_reference_is_rejected():
    f=fixture();f['measured']['jacobian'][0][0]=float('nan')
    with pytest.raises(ValueError,match='Finite native'):screen(f['measured'],f['waypoints'])


def test_oblique_pinches_preserve_vertical_opposed_fingers():
    rotations=list(pinch_rotations([-1,0,0]));assert len(rotations)==6
    for r in rotations:
        assert np.allclose(r.T@r,np.eye(3)) and np.linalg.det(r)==pytest.approx(1.)
        assert np.allclose(abs(r[:,1]),[0,0,1])
        assert r[2,2]==pytest.approx(0.)
    with pytest.raises(ValueError):list(pinch_rotations([0,1,0]))


@pytest.mark.parametrize(('deadband','fault'),[(0.,None),(3.5,None),(0.,'ik'),(3.5,'limit')])
def test_empty_wrist_tracks_actual_rotation_and_rejects_ik_failures(deadband,fault,monkeypatch):
    from types import SimpleNamespace
    from scipy.spatial.transform import Rotation
    from videoicl_isaaclab.execution_design_e31_continuation import orient_empty
    from videoicl_isaaclab import execution_design_thin_edge
    monkeypatch.setattr(execution_design_thin_edge,'table_bounds_task',lambda s:{'top':.8})
    cur=np.eye(3);target=Rotation.from_euler('xyz',[60,30,70],degrees=True).as_matrix();requests=[]
    q=np.array([[0.,0.,0.,-1.5,0.,1.5,0.]])
    lim=np.array([[[-2.9,2.9],[-1.76,1.76],[-2.9,2.9],[-3.07,-.07],[-2.9,2.9],[-.017,3.75],[-2.9,2.9]]])
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=q,joint_pos_limits=lim))
    c=SimpleNamespace(ids={'right':(list(range(7)),None,None)},snapshot=lambda:({'plate':{'grasp':[False,False]}},set()),action_feedback=lambda:{'control_feedback':{'right':{'status':'blocked'if fault=='ik'else'reached','joint_limit_names':['panda_joint4']if fault=='limit'else[],'reason':'no_safe_ik_step'if fault=='ik'else None}}})
    def act(left,right,rotation_deg):
        requests.append((right,rotation_deg));axis,sign={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}[right]
        delta=np.zeros(3);delta[axis]=sign*max(0.,rotation_deg-deadband)
        cur[:]=Rotation.from_rotvec(np.radians(delta)).as_matrix()@cur
    a=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot}),c=c,tcp_rotation_task=lambda s:cur.copy(),finger_geometry=lambda s:{'lowest_z_task_m':1.0},act=act)
    if fault:
        with pytest.raises(RuntimeError,match='actual IK/limit feedback'):orient_empty(a,'right',target)
        assert len(requests)==1
        return
    orient_empty(a,'right',target)
    assert np.degrees(Rotation.from_matrix(target@cur.T).magnitude())<1.
    assert len(requests)<180 and all(.5<=degrees<=8. for _,degrees in requests)
