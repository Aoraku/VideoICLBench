from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e15_red_acquire as module


def author(monkeypatch,grip=True):
    from videoicl_isaaclab import execution_design_e15_wrist as wrist
    monkeypatch.setattr(wrist,'_scope',lambda _:None)
    red=dict(id='red_t',source_asset=dict(sha256='98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493'),
             size=[.026,.0195,.004875],grasp_point_local=[0,0,0])
    state={name:dict(pos=np.array(position),mat=np.eye(3),grasp=[False,False])
           for name,position in [('red_t',[0.,0.,.804875]),('blue_t',[.2,.2,.804875])]}
    contacts={frozenset((name,'table'))for name in state};position=np.array([0.,0.,.810]);calls=[]
    c=SimpleNamespace(steps=0,_engineering_checkpoint_readback_passed=True,
        snapshot=lambda:(state,contacts),action_feedback=lambda:{})
    a=SimpleNamespace(c=c,scene=SimpleNamespace(spec=dict(variant='B',seed=4201,
        execution_design=dict(condition='I'),objects=[red,dict(id='blue_t')])),
        _engineering_resume_checkpoint=dict(diagnostic_only=True,source=dict(steps=118,physics_ticks=11802)))
    a.tip=lambda _:position.copy();a.floor_clear_tcp=lambda _: .810
    a.finger_geometry=lambda _:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.802)
    def act(left,token,mm=1.,rotation_deg=None):
        calls.append(token);c.steps+=1
        if token=='GRASP'and grip:
            state['red_t']['grasp'][1]=True
            contacts.update(frozenset(('red_t','right_finger'+str(i)))for i in(1,2))
        elif token=='UP':position[2]+=mm/1000.;state['red_t']['pos'][2]+=mm/1000.
    a.act=act
    def capture(_):
        pts=np.array([[-.01,-.005,-.004875],[.01,.005,.004875]])+state['red_t']['pos']
        model=dict(position=position.copy(),rotation=np.eye(3),q=np.zeros(7),limits=np.tile([-3.,3.],(7,1)),clouds=[])
        return model,[dict(name='table',lo=np.array([-.35,-.6,.75]),hi=np.array([.35,.6,.8])),
            dict(name='object:red_t:part0',points=pts,lo=pts.min(0),hi=pts.max(0))]
    monkeypatch.setattr(module,'_capture',capture)
    monkeypatch.setattr(module,'_preflight',lambda m,*a,**k:dict(candidate_joints_rad=m['q'].tolist()))
    monkeypatch.setattr(module,'screen_joint_segment',lambda *a,**k:None)
    return a,calls


def test_actual_bilateral_grasp_then_public_short_lift_without_any_pose_injection(monkeypatch):
    a,calls=author(monkeypatch);result=module.run_segment(a,'e15_b_grasp_red_hover118',{})
    assert calls==['GRASP']+['UP']*10
    assert result['local_completed']and result['actual_red_rise_m']==pytest.approx(.020)
    assert a.carried_payload==('red_t','right')and not result['full_task_completed']


def test_absent_real_grip_stops_after_original_three_grasp_bound(monkeypatch):
    a,calls=author(monkeypatch,grip=False)
    with pytest.raises(RuntimeError,match='actual bilateral grip'):module.run_segment(a,'e15_b_grasp_red_hover118',{})
    assert calls==['GRASP']*3


def test_unadmitted_boundary_does_not_send_public_actions(monkeypatch):
    a,calls=author(monkeypatch);a._engineering_resume_checkpoint['source']['steps']=117
    with pytest.raises(ValueError,match='hover118'):module.run_segment(a,'e15_b_grasp_red_hover118',{})
    assert calls==[]


def test_safe_native56_closes_real_pad_without_replaying_downward_moves(monkeypatch):
    a,calls=author(monkeypatch);a._engineering_resume_checkpoint['source']=dict(steps=56,physics_ticks=5603)
    result=module.run_segment(a,'e15_b_close_lift_from56',{})
    assert result['local_completed']and calls==['GRASP']+['UP']*10
    assert result['operations'][0]['remaining_nominal_downward_move_omitted']


def test_actual_pad_above_the_T_cannot_be_called_a_grasp(monkeypatch):
    a,calls=author(monkeypatch);a._engineering_resume_checkpoint['source']=dict(steps=56,physics_ticks=5603)
    a.finger_geometry=lambda _:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.82)
    with pytest.raises(RuntimeError,match='pad does not cover real T'):module.run_segment(a,'e15_b_close_lift_from56',{})
    assert calls==[]
