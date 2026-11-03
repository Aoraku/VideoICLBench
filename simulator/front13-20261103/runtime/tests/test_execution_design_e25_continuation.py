"""Native-failure regressions; CPU fixtures never certify physical success."""
import json,math
from types import SimpleNamespace as N
import numpy as np
import pytest
from test_execution_design_e07_reference import author,feasible
from test_execution_design_e25_reference import source_palm_author,scene
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_e07_reference import plan_transfers
from videoicl_isaaclab.execution_design_e25_parking import source_pickup_spec,restore_before_return
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.author_orientation import _axis_angle


def test_b_real_relay_uses_original_handle_before_new_receiving_pinch(tmp_path):
    a=author(tmp_path,variant='B',task='E25');old=json.dumps(a.scene.spec,sort_keys=True)
    plan=plan_transfers(a,a.scene.spec['goals'],feasible)
    from videoicl_isaaclab.execution_design_e25_reference import grasp_spec
    for pickup,receive in zip(plan[::2],plan[1::2]):
        obj=next(o for o in a.scene.spec['objects']if o['id']==pickup['object'])
        narrowed=grasp_spec(a,obj);actual=source_pickup_spec(a,narrowed,pickup)
        assert actual['grasp_point_local']==obj['grasp_point_local']
        assert actual['grasp_point_local'][0]<0<narrowed['grasp_point_local'][0]
        assert '_e25_pickup_grasp_local'not in receive
        assert '_e07_after_relay'in receive
    assert json.dumps(a.scene.spec,sort_keys=True)==old
    with pytest.raises(ValueError):source_pickup_spec(a,narrowed,dict(pickup,_e25_pickup_grasp_local=[0,0,0]))


def test_c_relay_receiver_also_levels_empty_fingers(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C')
    old=json.dumps(a.scene.spec,sort_keys=True)
    prepare_source_palm(a,'right','knife',{'_e07_after_relay':{}})
    assert a.actions==['move','ROLL_RIGHT','ROLL_RIGHT']
    assert json.dumps(a.scene.spec,sort_keys=True)==old
    a.actions.clear();state['knife']['grasp']=[True,False]
    with pytest.raises(RuntimeError,match='released table support'):prepare_source_palm(a,'right','knife',{'_e07_after_relay':{}})
    assert not a.actions


def parking(tmp_path,monkeypatch,fault=None):
    import videoicl_isaaclab.execution_design_e25_b_reference as b
    r=_axis_rotation([0,0,1],math.radians(40));p=np.array([.16,.18,.89]);calls=[]
    state={'spoon':{'grasp':[False,False]}};q=np.zeros(7);limits=np.tile([-3.,3.],(7,1))
    feedback={'status':'partial','joint_limit_names':[]}
    a=N(scene=N(spec={'id':'E25','variant':'A','execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}},embodiment=N(name='franka')),
        _execution_design_reference_authorized=True,control_report={'engineering_reference_only':True},smooth=False,
        carried_payload=None,out=tmp_path,_e25_home_rotations={'left':np.eye(3)})
    a.c=N(snapshot=lambda:(state,set()),action_feedback=lambda:{'control_feedback':{'left':feedback}})
    a.tip=lambda s:p.copy();a.tcp_rotation_task=lambda s:r.copy()
    a.finger_geometry=lambda s:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(p[2]-.01))
    a.move_generated=lambda goals,**kwargs:p.__setitem__(slice(None),goals['left'])
    def act(left,right,rotation_deg):
        nonlocal r
        assert right=='STILL';calls.append(left)
        if fault=='stall':return
        axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[left]
        r=_axis_rotation(axis,math.radians(rotation_deg)*.8)@r
        if fault=='joint':q[5]=2.999
        if fault=='blocked':feedback['status']='blocked'
    a.act=act;monkeypatch.setattr(b,'_joints',lambda a,s:(q,limits,list('abcdefg')))
    def probe(a,c,s,targets):return [dict(kinematically_reachable=fault!='ik',position_error_m=0.,orientation_error_rad=0.,minimum_joint_margin_rad=.3,joint_distance_rad=.05)for _ in targets]
    return a,calls,state,probe


def test_empty_return_unwinds_before_horizontal_translation(tmp_path,monkeypatch):
    a,calls,state,probe=parking(tmp_path,monkeypatch)
    restore_before_return(a,'left',.89,probe)
    assert calls and set(calls)=={'ROTATE_CW'}
    assert _axis_angle(a.tcp_rotation_task('left'))[1]<math.radians(1.5)
    assert not state['spoon']['grasp'][0]


def test_C_low_empty_return_lifts_before_first_rotation_without_lowering_floor(tmp_path,monkeypatch):
    a,calls,state,probe=parking(tmp_path,monkeypatch);a.scene.spec['variant']='C'
    original=a.act;observed=[]
    def act(*args,**kwargs):
        observed.append(a.finger_geometry('left')['lowest_z_task_m'])
        original(*args,**kwargs)
    a.act=act
    restore_before_return(a,'left',.94,probe)
    assert observed and min(observed)>=.915


def test_B_selects_retracted_rotation_site_before_unwinding_at_far_workspace(tmp_path,monkeypatch):
    a,calls,state,probe=parking(tmp_path,monkeypatch);a.scene.spec['variant']='B'
    start=a.tip('left').copy();restore_before_return(a,'left',.89,probe)
    assert calls and a.tip('left')[0]==pytest.approx(start[0]-.08)


@pytest.mark.parametrize('fault',['ik','stall','joint','blocked','held','scope'])
def test_empty_return_preserves_all_native_rejection_guards(tmp_path,monkeypatch,fault):
    a,calls,state,probe=parking(tmp_path,monkeypatch,fault)
    if fault=='held':state['spoon']['grasp']=[True,False]
    if fault=='scope':a.scene.spec['id']='E16'
    with pytest.raises((RuntimeError,ValueError)):restore_before_return(a,'left',.89,probe)
    if fault in ('held','scope','ik'):assert not calls
    if fault in ('joint','blocked'):assert len(calls)==1
