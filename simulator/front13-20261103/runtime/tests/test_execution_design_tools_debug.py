from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_tools_debug as debug


def base(task):
 spec=dict(id=task,variant='A',seed=4201,execution_design=dict(source_sha256='source',assignment_identity_sha256='assignment'))
 author=SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report=dict(engineering_reference_only=True))
 payload=dict(schema='engineering-native-checkpoint-v1',diagnostic_only=True,identity=dict(task=task,variant='A',seed=4201,source_sha256='source',assignment_identity_sha256='assignment'),context={})
 return author,payload


def test_tools_suffix_rejects_wrong_identity_or_model_context():
 author,payload=base('E37');payload['identity']['seed']=4202
 with pytest.raises(ValueError,match='mismatch'):debug.run_e37(author,payload)
 author,payload=base('E37');author.control_report['engineering_reference_only']=False
 with pytest.raises(ValueError,match='model evaluation'):debug.run_e37(author,payload)


def test_e37_suffix_starts_at_real_held_driver_not_acquisition(monkeypatch):
 author,payload=base('E37');payload['context']={'role':'left'}
 desired=np.array([[0.,-1.,0.],[0.,0.,1.],[-1.,0.,0.]])
 policy=SimpleNamespace(a=author,index=0,variant='A',limit=3000,start=0,c=SimpleNamespace(steps=0),geometry={'driver_grasp':{'local':[0,0,0]}},calls=[],act=lambda *args,**kw:None)
 policy.s={'screw_roles':{'left':dict(driver=dict(actor='driver',axis_local=[1,0,0]),fixture=dict(ref={},axis_local=[0,0,1]),screw='screw',head_socket_local=[0,0,0],radial_local=[0,1,0])}}
 policy.require_held=lambda ref,side:policy.calls.append('real-grip-check')
 policy.frame=lambda ref:(np.zeros(3),np.eye(3));policy.body_point=lambda *args:np.zeros(3)
 policy.snapshot=lambda:({'driver':{'mat':desired},'screw':{'mat':np.eye(3)}},set())
 policy.acquire=lambda *args:pytest.fail('A suffix must not acquire from the initial scene')
 monkeypatch.setattr(debug,'StructuralAuthor',lambda a:policy)
 monkeypatch.setattr('videoicl_isaaclab.engineering_robot_table_contacts.install',
     lambda *args,**kw:dict(snapshot=lambda:dict(measurement_completed=True,
         all_link_table_peak_force_n={'left/panda_link6':0.}),close=lambda:None))
 def above(*args,**kw):assert kw=={'resume_at_current_pose':True};policy.calls.append('orientation-suffix')
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_approach.above_head',above)
 result=debug.run_e37(author,payload)
 assert policy.calls==['real-grip-check','orientation-suffix']
 assert result['segment_finished']and not result['native_task_acceptance']and not result['source_initial_episode']


def test_e28_suffix_reuses_placed_open_backstop_and_tests_independent_lift(monkeypatch):
 author,payload=base('E28');payload['context']=dict(food='food',backstop_already_placed=True,backstop_side='left',backstop_park_task=[-.19,.3,1.02])
 tool=dict(actor='spatula',grasp_local=[0,0,0],jaw_axis_local=[0,1,0],working_local=[.1,0,0],edge_segment=[[.133,-.03,-.012],[.133,.03,-.012]],support_bounds={'lower':[.07,-.038,-.012],'upper':[.125,.038,.01]})
 policy=SimpleNamespace(spec={'objects':[{'id':'food','size':[.02,.017,.007]}]},s={'tools':{'main':tool},'groups':{'active':['food']}},index=0,variant='A',limit=3000,start=0,c=SimpleNamespace(steps=0,grips={'left':.04,'right':0.}),lift=0.)
 policy.snapshot=lambda:({'food':dict(pos=np.array([.1,0,.807+policy.lift]),mat=np.eye(3),grasp=[False,False]),'spatula':dict(pos=np.array([0,0,.807+policy.lift]),mat=np.eye(3))},set())
 policy.require_held=lambda *args:None;policy.stage=lambda s:None
 policy.point=lambda ref:np.array([.1,0,.807+policy.lift])
 policy.contact=lambda food,other:other=='spatula'or(other=='table'and policy.lift==0.)
 policy.tool=lambda:pytest.fail('A suffix must not re-acquire its tool')
 def move(side,ref,target,guard,tolerance):guard();policy.lift+=.02;policy.c.steps+=1
 policy.move_point=move
 monkeypatch.setattr(debug,'ToolAuthor',lambda a:policy)
 def insert(*args,**kw):
  assert kw=={'backstop_side':'left'}
  assert np.allclose(policy._e28_backstop_park,[-.19,.3,1.02])
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_backstop.insert',insert)
 result=debug.run_e28(author,payload)
 assert result['segment_finished']and result['actual_food_lift_m']>.019
 assert not result['native_task_acceptance']and not result['source_initial_episode']


def test_neck_candidate_uses_actual_collision_section_and_jaw_capacity(tmp_path,monkeypatch):
 tool=dict(actor='spatula',support_bounds={'lower':[.07,-.038,-.012]},jaw_axis_local=[0,1,0])
 points=np.array([[x,y,z]for x in (.055,.061)for y in (-.018,.018)for z in (-.008,.008)])
 policy=SimpleNamespace(a=SimpleNamespace(out=tmp_path),_e28_local_collision_vertices=points)
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_reference.actual_leading_surfaces',lambda *args:None)
 ref=debug._near_blade_ref(policy,tool)
 assert np.allclose(ref['local'],[.058,0.,0.])
 assert ref['actor']=='spatula'
 policy._e28_local_collision_vertices=points*np.array([1.,3.,1.])
 with pytest.raises(debug.ToolExecutionError,match='cross-section'):debug._near_blade_ref(policy,tool)


def test_neck_regrip_refuses_a_tool_without_real_table_support(monkeypatch):
 policy=SimpleNamespace(point=lambda ref:np.zeros(3),contact=lambda *args:False)
 monkeypatch.setattr(debug,'_near_blade_ref',lambda *args:{'actor':'spatula','local':[0,0,0]})
 with pytest.raises(debug.ToolExecutionError,match='table-supported'):
  debug._regrip_neck(policy,{'actor':'spatula'},'right',{},'food')
