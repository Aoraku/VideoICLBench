"""Nominal geometry tests, not physical acceptance."""
import numpy as np
import pytest
from types import SimpleNamespace
from videoicl_isaaclab import execution_design_e24_transit as m
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

def model():
 return dict(position=np.array([1.,0,0]),rotation=np.eye(3),jacobian=np.array([[0.],[1.],[0.],[0.],[0.],[1.]]),q=np.array([0.]),limits=np.array([[-3.,3.]]),clouds=[dict(name='panda_link1',influence=1,points=np.array([[1.,0,0],[1.01,0,0]]))])
def obstacle(name,center,width=.01):return dict(name=name,lo=np.array(center)-width,hi=np.array(center)+width)
def test_prefix_matches_existing_screw_forward():
 a=model();delta=np.array([.43]);t=m.prefix_transforms(a['position'],a['jacobian'],delta)[-1];p,r=m.forward_at_delta(a['position'],a['rotation'],a['jacobian'],delta)
 np.testing.assert_allclose(t[:3,:3]@a['position']+t[:3,3],p,atol=1e-12);np.testing.assert_allclose(t[:3,:3],r,atol=1e-12)
def test_clear_endpoints_hide_midarc_collision():
 a=model();o=obstacle('thin-post',[1,0,0],.005)
 m.screen_joint_segment(a,[-.2],[-.2],[o]);m.screen_joint_segment(a,[.2],[.2],[o])
 with pytest.raises(ToolExecutionError,match='swept clearance'):m.screen_joint_segment(a,[-.2],[.2],[o])
def test_bound_encloses_vertex_travel_and_safe_path_passes():
 a=model();delta=np.array([.31]);bound=m.swept_vertex_bound(a,a['clouds'][0],delta);start=a['clouds'][0]['points'];t=m.prefix_transforms(a['position'],a['jacobian'],delta)[-1];end=start@t[:3,:3].T+t[:3,3]
 assert np.max(np.linalg.norm(end-start,axis=1))<=bound
 assert m.swept_vertex_bound(a,dict(influence=0),delta)==0
 assert m.screen_joint_segment(a,[0],[.31],[obstacle('remote',[3,0,0])])['minimum_clearance_lower_bound_m']>.5

def test_height_uses_lowest_finger_and_swept_xy():
 a=dict(position=np.array([0.,0,1.]),clouds=[dict(name='panda_leftfinger',points=np.array([[-.02,0,.94],[.02,0,1.01]]))])
 h,rows=m.measured_height(a,[.3,0,.82],[obstacle('table',[.15,0,.79]),obstacle('remote',[2,2,3])]);assert h==pytest.approx(.88);assert [r['obstacle']for r in rows]==['table']
def test_unreachable_nominal_target_rejects():
 with pytest.raises(ToolExecutionError,match='nearby IK'):m.plan_transit(model(),[[1.02,0,0]],[])
@pytest.mark.parametrize('name,n',[('panda_link0',0),('panda_link6',6),('panda_link7',7),('panda_hand',7),('panda_leftfinger',7)])
def test_reviewed_chain(name,n):assert m.body_influence(name)==n
def test_unknown_body():
 with pytest.raises(ToolExecutionError,match='Unreviewed'):m.body_influence('attachment')
def test_held_arm_rejected_before_geometry():
 p=SimpleNamespace(snapshot=lambda:({'lid':{'grasp':[True,False]}},[]))
 with pytest.raises(ToolExecutionError,match='holding'):m.obstacles_at_snapshot(p,'left',{})
@pytest.mark.parametrize('task,rev,eng',[('E23','embodied50-execution-v3-20261102',True),('E24','old',True),('E24','embodied50-execution-v3-20261102',False)])
def test_scope_before_native_access(task,rev,eng):
 p=SimpleNamespace(task=task,spec={'execution_design':{'revision':rev}},a=SimpleNamespace(control_report={'engineering_reference_only':eng}))
 with pytest.raises(ToolExecutionError,match='engineering transit only'):m.empty_pusher_transfer(p,'left',[0,0,.9])
def test_plan_failure_sends_no_public_actions(monkeypatch,tmp_path):
 p=SimpleNamespace(task='E24',spec={'execution_design':{'revision':'embodied50-execution-v3-20261102'}},a=SimpleNamespace(control_report={'engineering_reference_only':True},out=tmp_path),c=SimpleNamespace(steps=17))
 monkeypatch.setattr(m,'capture_model',lambda *_:(model(),{}));monkeypatch.setattr(m,'obstacles_at_snapshot',lambda *_:[]);monkeypatch.setattr(m,'measured_height',lambda *_:(.9,[]))
 with pytest.raises(ToolExecutionError):m.empty_pusher_transfer(p,'left',[1.,0,.9])


def test_grouped_move_runs_full_guard_before_and_after_each_public_action():
 actual=np.zeros(3);events=[]
 p=SimpleNamespace(a=SimpleNamespace(stage='grouped'),c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'left':{}}}),tip=lambda _:actual.copy())
 def act(side,token,mm):
  events.append(('act',actual.copy()));actual[0]+=mm/1000
 p.act=act
 def guard():events.append(('guard',actual.copy()))
 m.move_grouped_public(p,'left',[.005,0,0],guard)
 assert [r[0]for r in events]==['guard','act','guard','guard']
 np.testing.assert_allclose(events[0][1],[0,0,0]);np.testing.assert_allclose(events[2][1],[.005,0,0])


def test_post_action_guard_failure_does_not_issue_another_public_action():
 actual=np.zeros(3);counts={'guard':0,'act':0}
 p=SimpleNamespace(a=SimpleNamespace(stage='grouped'),c=SimpleNamespace(action_feedback=lambda:{}),tip=lambda _:actual.copy())
 def act(*args,**kwargs):counts['act']+=1;actual[0]+=.002
 p.act=act
 def guard():
  counts['guard']+=1
  if counts['guard']==2:raise ToolExecutionError('actual full-arm clearance rejected')
 with pytest.raises(ToolExecutionError,match='full-arm'):m.move_grouped_public(p,'left',[.005,0,0],guard)
 assert counts=={'guard':2,'act':1}


def test_actual_grouped_branch_is_checked_against_retained_dense_path():
 plan=[dict(point=[i*.001,0,0],q=[i*.01])for i in range(1,6)]
 group=m.group_dense_waypoints(plan,[0,0,0],[0])[0]
 assert m.dense_branch_deviation([.0025,0,0],[.025],group)==pytest.approx(0.)
 assert m.dense_branch_deviation([.0025,0,0],[.0851],group)>.05


@pytest.mark.parametrize('motion_bound',[.001,.005])
def test_coarse_certificate_retains_between_sample_collision_rejection(motion_bound):
 a=model();o=obstacle('thin-post',[1,0,0],.005)
 with pytest.raises(ToolExecutionError,match='swept clearance'):
  m.screen_joint_segment(a,[-.2],[.2],[o],maximum_motion_bound=motion_bound)
 assert m.screen_joint_segment(a,[0],[.31],[obstacle('remote',[3,0,0])],maximum_motion_bound=motion_bound)['minimum_clearance_lower_bound_m']>.5


def test_uncertified_motion_bound_rejected():
 with pytest.raises(ValueError):m.screen_joint_segment(model(),[0],[.1],[],maximum_motion_bound=.006)
