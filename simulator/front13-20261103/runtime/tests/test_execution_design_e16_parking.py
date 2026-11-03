"""Public-action parking guards, not physical acceptance evidence."""
import math
from types import SimpleNamespace as N
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e16_parking as m
from videoicl_isaaclab.execution_design import REVISION_V3


def controller(tmp_path,monkeypatch):
    rotation=m._axis_rotation([0,0,1],math.pi)
    position=np.array([-.2,-.3,.97]);calls=[];moves=[];q=np.zeros(7);q[-1]=-2.85
    limits=np.tile([-3.,3.],(7,1));feedback={'status':'ok','joint_limit_names':[]}
    a=N(scene=N(spec={'id':'E16','execution_design':{'revision':REVISION_V3}},embodiment=N(name='franka',config={'robots':{'right':{'initial_joints':{'panda_joint7':-.7}}}})),
        _execution_design_reference_authorized=True,control_report={'engineering_reference_only':True},smooth=False,
        carried_payload=None,out=tmp_path,_e16_home_rotations={'right':np.eye(3)})
    a.c=N(steps=0,snapshot=lambda:({'piece':{'grasp':[False,False]}},[]),action_feedback=lambda:{'control_feedback':{'right':feedback}})
    a.tip=lambda side:position.copy();a.tcp_rotation_task=lambda side:rotation.copy()
    a.finger_geometry=lambda side:{'source':'actual_collision_mesh_current_body_pose','lowest_z_task_m':position[2]-.02}
    def move(goals,**kwargs):
        position[:]=goals['right'];moves.append(dict(goals))
    a.move_generated=move
    def act(left,right,rotation_deg):
        nonlocal rotation
        axis,sign={'ROLL_LEFT':([1,0,0],1),'ROLL_RIGHT':([1,0,0],-1),'PITCH_UP':([0,1,0],1),'PITCH_DOWN':([0,1,0],-1),'ROTATE_CCW':([0,0,1],1),'ROTATE_CW':([0,0,1],-1)}[right]
        angle=math.radians(rotation_deg)*sign
        rotation=m._axis_rotation(axis,angle)@rotation;q[-1]-=angle if axis[2] else 0
        position[0]+=.0015;calls.append(right);a.c.steps+=1
    a.act=act;monkeypatch.setattr(m,'_joints',lambda a,s:(q,limits))
    good=lambda *args:[dict(kinematically_reachable=True,position_error_m=0.,orientation_error_rad=0.,minimum_joint_margin_rad=.2,joint_distance_rad=.1)for _ in args[-1]]
    return a,calls,moves,good,feedback


def test_released_halfturn_unwinds_in_safe_direction_with_recentering(tmp_path,monkeypatch):
    a,calls,moves,good,_=controller(tmp_path,monkeypatch)
    m.restore_released_wrist(a,'right',.87,good)
    assert calls and set(calls)=={'ROTATE_CW'} and len(moves)>2
    assert m._axis_angle(a.tcp_rotation_task('right'))[1]<math.radians(1.5)
    assert (tmp_path/'e16-empty-wrist.private.jsonl').exists()


def test_held_or_wrong_scope_sends_no_actions(tmp_path,monkeypatch):
    a,calls,moves,good,_=controller(tmp_path,monkeypatch)
    a.carried_payload='piece'
    with pytest.raises(RuntimeError,match='released'):m.restore_released_wrist(a,'right',.87,good)
    a.carried_payload=None;a.scene.spec['id']='E15'
    with pytest.raises(ValueError,match='E16'):m.restore_released_wrist(a,'right',.87,good)
    assert not calls and not moves


def test_invalid_arc_cannot_act(tmp_path,monkeypatch):
    a,calls,moves,good,_=controller(tmp_path,monkeypatch)
    def invalid(*args):
        rows=good(*args);rows[0]['position_error_m']=float('nan');return rows
    with pytest.raises(RuntimeError,match='arc'):m.restore_released_wrist(a,'right',.87,invalid)
    assert not calls and not moves


def test_native_refusal_stops_after_first_action(tmp_path,monkeypatch):
    a,calls,moves,good,feedback=controller(tmp_path,monkeypatch);feedback['status']='blocked'
    with pytest.raises(RuntimeError,match='native limit'):m.restore_released_wrist(a,'right',.87,good)
    assert len(calls)==1


def test_home_measurement_is_readonly_scoped_and_not_replaced():
    a=N(scene=N(spec={'id':'E16','execution_design':{'revision':REVISION_V3}}),_execution_design_reference_authorized=True,tcp_rotation_task=lambda side:np.eye(3))
    m.remember_empty_home(a);saved=a._e16_home_rotations
    a.tcp_rotation_task=lambda side:np.zeros((3,3));m.remember_empty_home(a)
    assert a._e16_home_rotations is saved
    b=N(scene=N(spec={'id':'E15'}));m.remember_empty_home(b);assert not hasattr(b,'_e16_home_rotations')
