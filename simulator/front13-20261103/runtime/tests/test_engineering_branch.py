from pathlib import Path
from types import SimpleNamespace
import hashlib,json
import numpy as np
import pytest
from videoicl_isaaclab.engineering_branch import BranchMonitor,run_branch,validate_request


def fixture(tmp_path,*,has_forward=True):
 case=dict(task='E01',variant='A',seed=4201,episode_id='room-00-E01-A-s4201')
 spec=dict(id='E01',variant='A',seed=4201,execution_design={'revision':'embodied50-execution-v3-20261102','condition':'I'})
 c=SimpleNamespace(steps=0,physics_ticks=0,scene=SimpleNamespace(spec=spec),sim=SimpleNamespace(current_time=0.))
 if has_forward:c.sim.forward=lambda:None
 pool=SimpleNamespace(controllers={case['episode_id']:c},physics_ticks=0)
 checkpoint=tmp_path/'source.private.json';checkpoint.write_text(json.dumps({'debug_only':True}))
 req=dict(debug_only=True,**case,condition='I',branch_name='extract_supported_tray',
     checkpoint_path=str(checkpoint),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),action_budget=20)
 saves=[];restores=[];heads=[]
 def restore(controller,payload,author):
  assert controller._engineering_branch_authorized
  restores.append(True);controller.steps=509;controller.physics_ticks=51740
  return {'context':{'origin':'legacy-static-debug','e12_pin_alignment':[{}]},'pose_readback_passed':True}
 def capture(controller,author,context):return dict(debug_only=True,steps=controller.steps,context=context)
 def save(payload,path):
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload));saves.append(payload)
  return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 api=SimpleNamespace(load=lambda path:json.loads(path.read_text()),restore=restore,capture=capture,save=save)
 def factory(controller,out,monitor):
  a=SimpleNamespace(c=controller,scene=controller.scene,out=out,stage='suffix',control_report={},_branch_monitor=monitor)
  monitor.author=a
  def act(token='FWD',delta=.0005,status='reached',idle_status='reached'):
   monitor.before();command=dict(left='STILL',right=token,step_mm=.5,rotation_deg=1.)
   before={s:(np.zeros(3),np.eye(3))for s in ('left','right')};after={s:(np.zeros(3),np.eye(3))for s in ('left','right')}
   after['right'][0][0]=delta;controller.steps+=1;controller.physics_ticks+=100
   receipt=dict(step_before=controller.steps-1,step_after=controller.steps,
       control_feedback={'right':{'status':status,'reason':'test blocked'if status=='blocked'else None},'left':{'status':idle_status}})
   monitor.after(command,receipt,before,after)
  a.act=act;return a
 def head(*args):heads.append(True);return {'path':'render-only-head.png'}
 return c,pool,case,req,api,factory,head,saves,restores,heads


def test_branch_uses_restored_cumulative_steps_and_local_budget_then_stops_without_settle(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path);r['action_budget']=2
 def suffix(a,context,name):
  assert a.c.steps==509 and context['origin']=='legacy-static-debug'
  for _ in range(4):a.act()
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert not report['local_completed'] and report['local_actions']==2
 assert c.steps==511 and len(saves)==4 and saves[-1]['steps']==511
 assert heads==[True] and report['post_failure_settle_ticks']==0
 assert report['debug_only'] and report['eligible_full_acceptance']is False and report['whole_task_score']is None
 assert c._engineering_branch_authorized is False


def test_success_head_is_opt_in_and_does_not_advance_actions_or_physics(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 r['params']={'capture_final_head':True}
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=lambda *args:{'local_completed':True},author_factory=factory,head_renderer=head)
 assert report['local_completed'] and report['final_head']['path']=='render-only-head.png'
 assert len(heads)==1 and c.steps==509 and c.physics_ticks==51740


def test_active_blocked_receipt_is_checkpointed_before_immediate_failure(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 def suffix(a,*args):a.act(status='blocked');a.act()
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_actions']==1 and 'Active hand blocked'in report['error']
 assert saves[-1]['steps']==510 and len(heads)==1


def test_confirmed_eight_action_directional_stall_cannot_continue(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 def suffix(a,*args):
  for _ in range(12):a.act(delta=.00001)
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_actions']==8 and 'insufficient directional progress'in report['error']
 assert len(saves)==10 and c.steps==517


def test_inactive_sibling_blocked_status_does_not_cancel_active_success(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 def suffix(a,*args):a.act(idle_status='blocked');return {'local_completed':True,'original_orientation_reached':False}
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_completed'] and report['local_actions']==1 and not heads
 assert report['whole_task_score']is None and not report['branch_result']['original_orientation_reached']


def test_missing_native_forward_refuses_restore_before_any_state_write(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path,has_forward=False)
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=lambda *args:None,author_factory=factory,head_renderer=head)
 assert not restores and not saves and c.steps==0
 assert 'forward unavailable'in report['error'] and len(heads)==1


@pytest.mark.parametrize('field,value',[('task','E10'),('variant','B'),('seed',4202),('episode_id','other-room'),('condition','R'),('action_budget',501),('debug_only',False)])
def test_case_or_scope_mismatch_never_restores(tmp_path,field,value):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path);r[field]=value
 with pytest.raises(ValueError):run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,author_factory=factory,head_renderer=head)
 assert not restores and not saves


def test_digest_mismatch_and_multi_room_refuse_before_restore(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path);r['checkpoint_sha256']='0'*64
 with pytest.raises(ValueError,match='SHA256 mismatch'):run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,author_factory=factory)
 pool.controllers['another']=c
 with pytest.raises(ValueError,match='exactly one'):run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,author_factory=factory)
 assert not restores


def test_policy_original_bounds_and_material_baseline_are_restored_without_zeroing_history():
 from videoicl_isaaclab.engineering_branch import restore_policy_context
 p=SimpleNamespace(start=509,limit=3000,index=0,operations=[])
 restore_policy_context(p,{'policy_state':{'start':0,'limit':3000,'index':0,
     '_e01_native_com_local':[0,0,0],'_e01_native_bottom_local':[[0,0,0],[1,0,0],[0,1,0]]}})
 assert p.start==0 and p._e01_native_bottom_local.shape==(3,3)
 with pytest.raises(ValueError):restore_policy_context(p,{'policy_state':{'index':1}})


def test_failure_head_verifies_render_did_not_advance_physics(tmp_path):
 from videoicl_isaaclab.engineering_branch import failure_head
 class Pixels:
  def cpu(self):return self
  def numpy(self):return np.zeros((8,8,3),dtype=np.uint8)
  def __getitem__(self,key):return self
 camera=SimpleNamespace(update=lambda *args,**kwargs:None,data=SimpleNamespace(output={'rgb':Pixels()}))
 c=SimpleNamespace(steps=509,physics_ticks=51740,sim=SimpleNamespace(current_time=2.),scene=SimpleNamespace(cameras={'head':camera}))
 pool=SimpleNamespace(physics_ticks=51740,render_room=lambda room,passes,capture:capture())
 record=failure_head(pool,'room',c,tmp_path/'head.png')
 assert len(record['sha256'])==64 and c.steps==509
 def moving(room,passes,capture):c.steps+=1;return capture()
 pool.render_room=moving
 with pytest.raises(RuntimeError,match='advanced physics'):failure_head(pool,'room',c,tmp_path/'bad.png')


def test_explicit_legacy_input_is_converted_on_initialized_controller_and_labeled_partial(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 r['legacy_checkpoint_path']=r.pop('checkpoint_path');r['legacy_checkpoint_sha256']=r.pop('checkpoint_sha256')
 conversions=[]
 def from_legacy(controller,payload,author):
  assert controller._engineering_branch_authorized
  conversions.append(True)
  return {'debug_only':True,'state_quality':'measured_pose_fixture','assumptions':['Unknown historical velocities reset to zero.']}
 api.from_legacy=from_legacy
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,
     dispatcher=lambda author,*args:author.act(),author_factory=factory,head_renderer=head)
 assert conversions==[True] and report['checkpoint_input_kind']=='legacy_boundary_reconstruction'
 assert report['checkpoint_state_quality']=='measured_pose_fixture' and len(saves)==4
 assert report['checkpoints'][-1]['path'].endswith('-local-complete.private.json')
 assert report['eligible_full_acceptance']is False and report['whole_task_score']is None


def test_restore_context_private_report_keeps_first_insertion_history_but_forces_debug_flags(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path);original=api.restore
 def restore(*args,**kwargs):
  row=original(*args,**kwargs);row['context']['author_control_report']={'e12_pin_alignment':[{'actor':'charger_1'}],'eligible_full_acceptance':True}
  return row
 api.restore=restore
 def suffix(a,*args):
  assert a.control_report['e12_pin_alignment'][0]['actor']=='charger_1'
  assert not a.control_report['eligible_full_acceptance']
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_completed'] and report['local_actions']==0


def test_contact_rebuild_uses_actual_hold_and_public_actions_not_old_grasp_label(tmp_path):
 from videoicl_isaaclab.engineering_branch import rebuild_actual_hold
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 monitor=BranchMonitor(c,r,tmp_path/'out',api,{});author=factory(c,tmp_path/'out',monitor)
 count=[0];original=author.act
 def act(**kwargs):
  assert kwargs=={'left':'STILL','right':'STILL','mm':.5,'rotation_deg':.5}
  count[0]+=1;original(token='STILL',delta=0.)
 author.act=act
 c.snapshot=lambda:({'phone':{'pos':np.zeros(3),'mat':np.eye(3),'grasp':[count[0]>=1,False]}},set())
 payload={'objects':{'phone':{'root_state_task':[0,0,0,1,0,0,0,0,0,0,0,0,0]}}}
 record=rebuild_actual_hold(author,monitor,payload,{'actor':'phone','side':'left','max_actions':2})
 assert count==[1] and record['public_still_actions']==1 and c.steps==1


def test_contact_rebuild_pose_drift_is_rejected_without_regrasp(tmp_path):
 from videoicl_isaaclab.engineering_branch import rebuild_actual_hold,CheckpointNotReproduced
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 monitor=BranchMonitor(c,r,tmp_path/'out',api,{});author=factory(c,tmp_path/'out',monitor)
 c.snapshot=lambda:({'phone':{'pos':np.array([.006,0,0]),'mat':np.eye(3),'grasp':[True,False]}},set())
 payload={'objects':{'phone':{'root_state_task':[0,0,0,1,0,0,0,0,0,0,0,0,0]}}}
 with pytest.raises(CheckpointNotReproduced):rebuild_actual_hold(author,monitor,payload,{'actor':'phone','side':'left','max_actions':2})
 assert c.steps==0 and monitor.context['checkpoint_not_reproduced']['position_error_m']==.006


def test_context_patch_cannot_replace_original_target_or_reset_rotation_budget(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 for patch in ({'goal':{'yaw':0}},{'rotation_commands_used':0},{'rotation_commands':7}):
  r['context_patch']=patch
  with pytest.raises(ValueError):validate_request(r,case,c.scene.spec)
 r['context_patch']={'intermediate_actor_rotation':np.eye(3).tolist(),'rotation_commands':6}
 assert validate_request(r,case,c.scene.spec)['context_patch']==r['context_patch']


def test_public_still_after_converged_goal_is_holding_not_directional_failure(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 def suffix(a,*args):
  a.act()
  for _ in range(10):a.act(token='STILL',delta=0.)
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_completed'] and report['local_actions']==11


def test_only_e09_preblue_can_use_remaining_original_long_budget(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 case['task']='E09';c.scene.spec['id']='E09';c.scene.spec['expert_action_budget']=6000
 r.update(task='E09',branch_name='pre_blue',action_budget=2188)
 original=api.restore
 def restore(*args,**kwargs):
  result=original(*args,**kwargs);c.steps=3813;return result
 api.restore=restore
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=lambda *a:None,author_factory=factory,head_renderer=head)
 assert not report['local_completed'] and report['local_actions']==0 and 'original cumulative remaining'in report['error']
 r['action_budget']=2187
 report=run_branch(pool,c,case,tmp_path/'out2',r,checkpoint_api=api,dispatcher=lambda *a:None,author_factory=factory,head_renderer=head)
 assert report['local_completed']
 r['branch_name']='post_local_all'
 with pytest.raises(ValueError):validate_request(r,case,c.scene.spec)


def test_engineering_budget_extension_is_explicit_e09_only_and_keeps_formal_cap(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 case['task']='E09';c.scene.spec.update(id='E09',expert_action_budget=12000)
 r.update(task='E09',branch_name='stage_crate',action_budget=500)
 r['engineering_reference_budget_extension']=dict(parent_budget=6000,new_budget=12000,scope='independent_engineering_only',formal_action_cap_unchanged=True)
 assert validate_request(r,case,c.scene.spec)['engineering_reference_budget_extension']['parent_budget']==6000
 r['engineering_reference_budget_extension']['formal_action_cap_unchanged']=False
 with pytest.raises(ValueError,match='engineering-only'):validate_request(r,case,c.scene.spec)
 r['engineering_reference_budget_extension']['formal_action_cap_unchanged']=True
 c.scene.spec['expert_action_budget']=6000
 with pytest.raises(ValueError,match='engineering-only'):validate_request(r,case,c.scene.spec)


def test_actual_held_fixture_adoption_keeps_drift_visible_and_never_fills_hold(tmp_path):
 from videoicl_isaaclab.engineering_branch import rebuild_actual_hold,CheckpointNotReproduced
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 monitor=BranchMonitor(c,r,tmp_path/'out',api,{});author=factory(c,tmp_path/'out',monitor)
 c.snapshot=lambda:({'phone':{'pos':np.array([.0087,0,0]),'mat':np.eye(3),'grasp':[True,False]}},set())
 payload={'objects':{'phone':{'root_state_task':[0,0,0,1,0,0,0,0,0,0,0,0,0]}}}
 record=rebuild_actual_hold(author,monitor,payload,dict(actor='phone',side='left',max_actions=1,actual_hold_only=True))
 assert not record['checkpoint_pose_reproduced'] and record['position_error_m']==.0087
 assert monitor.context['adopted_actual_held_fixture']['not_exact_source_continuation']
 assert c.steps==0
 c.snapshot=lambda:({'phone':{'pos':np.zeros(3),'mat':np.eye(3),'grasp':[False,False]}},set())
 author.act=lambda **kwargs:None
 with pytest.raises(CheckpointNotReproduced,match='not rebuilt'):
  rebuild_actual_hold(author,monitor,payload,dict(actor='phone',side='left',max_actions=1,actual_hold_only=True))


def test_e10_actual_hold_fixture_cannot_bypass_native_identity_or_phase(tmp_path):
 c,pool,case,r,*_=fixture(tmp_path)
 case.update(task='E10',episode_id='room-00-E10-A-s4201');c.scene.spec.update(id='E10',objects=[{'id':'piece'}])
 r.update(task='E10',episode_id=case['episode_id'],branch_name='thread_precision',params={'actor':'piece','side':'left'},
     rebuild_held={'actor':'piece','side':'left','max_actions':2,'actual_hold_only':True})
 validate_request(r,case,c.scene.spec)
 r['branch_name']='acquire_receiver'
 with pytest.raises(ValueError,match='native diagnostic'):validate_request(r,case,c.scene.spec)
 r['branch_name']='thread_precision';r['checkpoint_input_kind']='legacy_boundary_reconstruction'
 with pytest.raises(ValueError,match='native diagnostic'):validate_request(r,case,c.scene.spec)


def test_coarse_functional_e09_requires_native_checkpoint_and_actual_hold(tmp_path):
 c,pool,case,r,*_=fixture(tmp_path)
 case.update(task='E09',episode_id='room-00-E09-A-s4201');c.scene.spec.update(id='E09',objects=[{'id':'box'}])
 r.update(task='E09',episode_id=case['episode_id'],branch_name='pack_group',params={'functional_mode':True},
     rebuild_held={'actor':'box','side':'right','max_actions':2,'actual_hold_only':True})
 validate_request(r,case,c.scene.spec)
 r['checkpoint_input_kind']='legacy_boundary_reconstruction'
 with pytest.raises(ValueError,match='native diagnostic'):validate_request(r,case,c.scene.spec)


def test_explicit_e01_reference_extension_preserves_cumulative_native_history(tmp_path):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 c.scene.spec['expert_action_budget']=6000
 r['engineering_reference_budget_extension']=dict(parent_budget=3000,new_budget=6000,scope='independent_engineering_only',formal_action_cap_unchanged=True)
 original=api.restore
 def restore(*args,**kwargs):
  result=original(*args,**kwargs)
  result['context'].update(policy_action_budget=3000,policy_state={'start':0,'limit':3000})
  return result
 api.restore=restore
 def suffix(a,context,name):
  assert a.c.steps==509 and a.c.physics_ticks==51740
  assert context['parent_policy_action_budget']==3000 and context['policy_action_budget']==6000
  assert context['policy_state']=={'start':0,'limit':6000}
  a.act();return {'local_completed':True}
 report=run_branch(pool,c,case,tmp_path/'out',r,checkpoint_api=api,dispatcher=suffix,author_factory=factory,head_renderer=head)
 assert report['local_completed'] and report['branch_start_step']==509 and report['branch_end_step']==510
 assert c.physics_ticks==51840 and report['whole_task_score']is None


@pytest.mark.parametrize('field,value',[('new_budget',5000),('formal_action_cap_unchanged',False),('scope','model_evaluation')])
def test_reference_extension_never_changes_formal_scope_or_silently_changes_budget(tmp_path,field,value):
 c,pool,case,r,api,factory,head,saves,restores,heads=fixture(tmp_path)
 c.scene.spec['expert_action_budget']=6000
 r['engineering_reference_budget_extension']=dict(parent_budget=3000,new_budget=6000,scope='independent_engineering_only',formal_action_cap_unchanged=True)
 r['engineering_reference_budget_extension'][field]=value
 with pytest.raises(ValueError):validate_request(r,case,c.scene.spec)
 assert not restores and c.steps==0
