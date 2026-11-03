"""Single-room engineering checkpoint branches; never full acceptance evidence."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,math,re,time
import numpy as np


class BranchStopped(RuntimeError):pass
class CheckpointNotReproduced(BranchStopped):pass


DIRECTIONS={
 'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1),
 'ROLL_LEFT':(3,1),'ROLL_RIGHT':(3,-1),'PITCH_UP':(4,1),'PITCH_DOWN':(4,-1),
 'ROTATE_CCW':(5,1),'ROTATE_CW':(5,-1)}
EXTENSIONS={'E05':'execution_design_e05_branch','E08':'execution_design_e08_branch',
 'E09':'execution_design_e09_branch','E13':'execution_design_e13_branch'}
OWN_PHASES={'E01':{'extract_supported_tray','acquire_tray_rim','transport_tray','food_local','stage_meal_box_for_loading','settle_loading_carton','load_meal_tray','load_meal_tray_left','load_meal_tray_balanced','complete_meal_shipment','complete_remaining_workflow','escape_lid_arm','close_loading_lid','deliver_meal_box'},
 'E10':{'acquire_receiver','acquire_and_lift','close_prepared_and_lift','lift_piece','thread_piece','thread_precision','release_threaded','post_remaining_functional','native_empty_motion_smoke'},
 'E12':{'rotate_second','insert_charger','prepare_second_toe','grasp_second_toe','complete_second_toe','complete_second_tilted_toe','complete_second_toe28','resume_second_pin','release_second_pin','complete_first_pin'}}
EXTENSION_PHASES={'E08':{'stage_ccw','yaw_ccw_chunk','yaw_short_chunk','place_left_to_release','adopt_source_plan','complete_left_from_held','reset_left_on_table','sole_com_complete_left','release_source_left_here','complete_right_after_left'},
 'E09':{'pre_blue','park_blue','blue_grip','blue_transport','blue_local','post_local_all','close_lid','stage_crate','pack_group','deliver_crate'},'E13':{'stage_inside','rotate_chunk','rotate_intermediate_chunk','hold_pending','escape_pending_stage','place_to_release','complete_from_held','camera_end_acquire','camera_end_resume_entry','camera_end_reacquire','camera_end_finish_lift','camera_end_complete_supported','shortwidth_complete_supported','edge_face_complete_supported'}}
E09_PHASE_BUDGETS={'pre_blue':2200,'blue_local':2200,'blue_transport':2200,
 'park_blue':100,'blue_grip':100,'close_lid':1600,'stage_crate':600,'pack_group':1200,'deliver_crate':800,'post_local_all':500}


def _json(value):
 if hasattr(value,'detach'):value=value.detach().cpu().numpy()
 if hasattr(value,'tolist'):return value.tolist()
 if isinstance(value,Path):return str(value)
 if isinstance(value,(set,frozenset)):return list(value)
 raise TypeError(type(value).__name__)


def write_json(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(value,default=_json,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(path)


def validate_request(request,case,spec):
 if request.get('debug_only')is not True:raise ValueError('Explicit debug_only branch request required')
 task=case['task']
 if task not in OWN_PHASES and task not in EXTENSIONS:raise ValueError('Task has no registered engineering branch')
 for key in ('task','variant','seed','episode_id'):
  if request.get(key)!=case[key]:raise ValueError('Branch case identity mismatch: '+key)
 if spec.get('id')!=task or spec.get('variant')!=case['variant'] or spec.get('seed')!=case['seed']:
  raise ValueError('Initialized scene differs from branch identity')
 design=spec.get('execution_design',{})
 if design.get('revision')!='embodied50-execution-v3-20261102' or request.get('condition')!=design.get('condition'):
  raise ValueError('Explicit matching v3 condition required')
 if request.get('assignment_identity_sha256') is not None and request['assignment_identity_sha256']!=design.get('assignment_identity_sha256'):
  raise ValueError('Branch assignment identity differs')
 budget=request.get('action_budget',60)
 maximum=E09_PHASE_BUDGETS.get(request.get('branch_name'),100)if task=='E09'else 500
 params=request.get('params',{})
 if not isinstance(params,dict):raise ValueError('Branch params must be an object')
 if(task=='E10'and request.get('branch_name')=='post_remaining_functional'
    and params.get('functional_mode')is True and 'legacy_checkpoint_path'not in request):maximum=2000
 if(task=='E01'and request.get('branch_name')=='complete_remaining_workflow'
    and params.get('functional_mode')is True and 'legacy_checkpoint_path'not in request):maximum=2000
 packaging_resume=(params.get('resume_packaging_after_closed')is True
    and 'legacy_checkpoint_path'not in request and request.get('checkpoint_input_kind')!='legacy_boundary_reconstruction')
 if(task=='E09'and(request.get('new_design_fixture')is True or packaging_resume)and request.get('branch_name')=='close_lid'
    and params.get('complete_packaging_if_healthy')is True):maximum=4000
 if type(budget)is not int or not 1<=budget<=maximum:raise ValueError('Branch action budget exceeds registered phase bound')
 name=request.get('branch_name','')
 if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_]+',name):raise ValueError('Explicit branch_name required')
 if task in OWN_PHASES and name not in OWN_PHASES[task]:raise ValueError('Unregistered branch phase for task')
 if task in EXTENSION_PHASES and name not in EXTENSION_PHASES[task]:raise ValueError('Unregistered branch phase for task')
 legacy_alias='legacy_checkpoint_path'in request
 legacy=legacy_alias or request.get('checkpoint_input_kind')=='legacy_boundary_reconstruction'
 if legacy_alias and 'checkpoint_path'in request:raise ValueError('Choose native or legacy checkpoint input, not both')
 checkpoint=Path(request.get('legacy_checkpoint_path'if legacy_alias else'checkpoint_path',''))
 if not checkpoint.is_absolute():raise ValueError('Absolute checkpoint_path required')
 digest=request.get('legacy_checkpoint_sha256'if legacy_alias else'checkpoint_sha256','')
 if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Checkpoint SHA256 required')
 if not isinstance(request.get('params',{}),dict):raise ValueError('Branch params must be an object')
 if request.get('rebuild_held')is not None:
  rebuild=request['rebuild_held'];actors={obj['id']for obj in spec.get('objects',[])}
  if not isinstance(rebuild,dict)or rebuild.get('actor')not in actors or rebuild.get('side')not in ('left','right') or type(rebuild.get('max_actions'))is not int or not 1<=rebuild['max_actions']<=2:
   raise ValueError('Explicit actual held reconstruction requires known actor/side and 1..2 public actions')
  actual_only=rebuild.get('actual_hold_only',False)
  e01_empty=(task=='E01'and request.get('branch_name')=='transport_tray'and rebuild.get('actor')=='tray'
      and rebuild.get('side')=='left'and request.get('params',{}).get('single_side')=='left'
      and request.get('params',{}).get('empty_tray_only')is True)
  e10_thread=(task=='E10'and request.get('branch_name')=='thread_precision'
      and rebuild.get('actor')==request.get('params',{}).get('actor')
      and rebuild.get('side')==request.get('params',{}).get('side'))
  coarse_native=(task in('E01','E09','E10','E12')and request.get('params',{}).get('functional_mode')is True)
  if type(actual_only)is not bool or actual_only and(legacy or not(task in('E08','E13')or e01_empty or e10_thread or coarse_native)):
   raise ValueError('Actual-held fixture adoption requires an explicitly supported native diagnostic checkpoint')
 patch=request.get('context_patch',{})
 if not isinstance(patch,dict)or set(patch)-{'intermediate_actor_rotation','rotation_commands','staging_tcp'}:
  raise ValueError('Branch patch cannot replace original goal, identity, or cumulative budgets')
 if 'intermediate_actor_rotation'in patch:
  rotation=np.asarray(patch['intermediate_actor_rotation'],float)
  if rotation.shape!=(3,3)or not np.isfinite(rotation).all()or not np.allclose(rotation.T@rotation,np.eye(3),atol=2e-5)or np.linalg.det(rotation)<.999:
   raise ValueError('Finite proper intermediate actor rotation required')
 if 'staging_tcp'in patch:
  point=np.asarray(patch['staging_tcp'],float)
  if point.shape!=(3,)or not np.isfinite(point).all():raise ValueError('Finite three-axis branch staging target required')
 rotation_max=120 if task=='E08'else 6
 if 'rotation_commands'in patch and(type(patch['rotation_commands'])is not int or not 1<=patch['rotation_commands']<=rotation_max):
  raise ValueError('Explicit bounded rotation chunk required')
 extension=request.get('engineering_reference_budget_extension')
 if extension is not None:
  bounds={'E01':(3000,6000),'E09':(6000,12000)}.get(task)
  if bounds is None:raise ValueError('No registered engineering-only budget extension for task')
  required=dict(parent_budget=bounds[0],new_budget=bounds[1],scope='independent_engineering_only',formal_action_cap_unchanged=True)
  if extension!=required or spec.get('expert_action_budget')!=bounds[1]:
   raise ValueError('Explicit task engineering-only budget lineage required')
 normalized={key:value for key,value in request.items()if key not in ('legacy_checkpoint_path','legacy_checkpoint_sha256')}
 return dict(normalized,action_budget=budget,checkpoint_path=str(checkpoint),checkpoint_sha256=digest,
     checkpoint_input_kind='legacy_boundary_reconstruction'if legacy else'native_checkpoint')


class BranchMonitor:
 def __init__(self,controller,request,out,checkpoint_api,context):
  self.c=controller;self.request=request;self.out=Path(out);self.api=checkpoint_api
  self.context=context;self.start=int(controller.steps);self.stopped=False;self.last_motion={}
  self.streak={};self.author=None;self.checkpoints=[];self.receipts=[];self.last_active=()
 def before(self):
  if self.stopped:raise BranchStopped('Branch already stopped; subsequent actions prohibited')
  if self.c.steps-self.start>=self.request['action_budget']:
   self.stopped=True;raise BranchStopped('Local branch action budget exhausted')
 def save(self,label):
  context=deepcopy(self.context)
  context.update(branch_name=self.request['branch_name'],branch_start_step=self.start,
      branch_local_actions=int(self.c.steps-self.start),debug_only=True,eligible_full_acceptance=False)
  policy=getattr(self.author,'_branch_policy',None)
  if policy is not None:
   context['policy_state']={key:getattr(policy,key)for key in ('start','index','limit','operations',
      '_e01_native_bottom_local','_e01_native_com_local')if hasattr(policy,key)}
   if hasattr(policy,'_e01_support_grip_local'):context['policy_state']['_e01_support_grip_local']=policy._e01_support_grip_local
   for key in ('_e01_rim_acquisition','_e01_verified_rim_grips','_e01_transport_state','_e01_food_progress','_e01_package_progress','_e01_balance_progress','_e12_toe_preparation'):
    if hasattr(policy,key):context['policy_state'][key]=deepcopy(getattr(policy,key))
  payload=self.api.capture(self.c,author=self.author,context=context)
  path=self.out/'checkpoints'/(str(int(self.c.steps)).zfill(6)+'-'+label+'.private.json')
  receipt=self.api.save(payload,path);self.checkpoints.append(dict(path=str(path),receipt=receipt))
 def after(self,command,receipt,before,after):
  self.receipts.append(receipt);failure=None
  feedback=receipt.get('control_feedback',{})
  explicit=tuple(side for side in ('left','right')if command[side].removeprefix('MV_')!='STILL')
  if explicit:self.last_active=explicit
  active_sides=explicit or self.last_active
  for side in ('left','right'):
   token=command[side].removeprefix('MV_')
   if token in DIRECTIONS:self.last_motion[side]=(token,float(command['step_mm']),float(command['rotation_deg']))
   elif token!='STILL':self.last_motion.pop(side,None);self.streak.pop(side,None)
   active=side in active_sides
   row=feedback.get(side,{})
   if active and row.get('status')=='blocked':failure='Active hand blocked: '+side+': '+str(row.get('reason'))
   if token=='STILL'and row.get('status')=='reached'and not row.get('continuing_rotation_target',False):
    self.last_motion.pop(side,None);self.streak.pop(side,None)
   motion=self.last_motion.get(side)
   if not motion or not active:continue
   original,mm,degrees=motion;axis,sign=DIRECTIONS[original]
   if axis<3:progress=sign*float(np.asarray(after[side][0])[axis]-np.asarray(before[side][0])[axis]);requested=mm/1000
   else:
    from scipy.spatial.transform import Rotation
    vector=Rotation.from_matrix(np.asarray(after[side][1])@np.asarray(before[side][1]).T).as_rotvec()
    progress=sign*float(vector[axis-3]);requested=math.radians(degrees)
   # Eight consecutive responses below a tenth of the public request are a
   # local failure, rather than hundreds of q4-boundary repetitions.
   low=progress<max(requested*.1,1e-6 if axis<3 else 1e-5)
   old_key,count=self.streak.get(side,(None,0));key=(original,self.author.stage)
   self.streak[side]=(key,count+1 if low and old_key==key else int(low))
   if self.streak[side][1]>=8:
    failure='Confirmed insufficient directional progress: '+side+' '+original
  # Save the accepted physical action even if its feedback latches failure.
  self.save('action')
  if failure:
   self.stopped=True;raise BranchStopped(failure)


def branch_author_class(base,pool,room,monitor):
 class BranchAuthor(base):
  def __init__(self,c,out):
   import torch
   self.c=c;self.scene=c.scene;self.out=Path(out);self.stage='branch-restored'
   self.smooth=False;self.joint_velocity_feedforward=False;self.carried_payload=None
   self.offset=torch.tensor([self.scene.embodiment.tcp],device=c.device)
   self.neutral_tcp_quaternions={side:c.pose(side)[1].clone()for side in self.scene.robots}
   self.control_report=dict(engineering_reference_only=True,debug_only=True,
       eligible_full_acceptance=False,eligible_as_model_demo=False,whole_task_score=None)
   self._execution_design_reference_authorized=True
   self._branch_monitor=monitor
  def note(self,stage):
   self.stage=stage
   with(self.out/'branch-stages.private.jsonl').open('a')as f:
    f.write(json.dumps(dict(stage=stage,steps=self.c.steps,debug_only=True))+'\n')
  def act(self,left='STILL',right='STILL',mm=20,rotation_deg=10.):
   from .execution_design_probe import engineering_action_plan,engineering_robot_diagnostics
   monitor.before()
   requested,plan=engineering_action_plan(left,right,mm,rotation_deg,
       self.scene.embodiment.config['control'],monitor.request['action_budget']-(self.c.steps-monitor.start))
   receipts=[]
   for index,command in enumerate(plan):
    monitor.before()
    guard=getattr(self,'_engineering_action_guard',None)
    if guard is not None:guard()
    before={side:(self.tip(side),self.tcp_rotation_task(side))for side in ('left','right')}
    receipt=pool.action_batch({room:command})[room];receipts.append(receipt)
    after={side:(self.tip(side),self.tcp_rotation_task(side))for side in ('left','right')}
    measured_state,measured_contacts=self.c.snapshot()
    row=dict(stage=self.stage,requested_action=requested,subaction_index=index,subaction_count=len(plan),
        **command,**receipt,tips={side:value[0]for side,value in after.items()},robot_diagnostics=engineering_robot_diagnostics(self),
        measured_native_grasps={actor:list(value['grasp'])for actor,value in measured_state.items()},
        measured_native_contacts=sorted(sorted(pair)for pair in measured_contacts))
    with(self.out/'demo-actions.private.jsonl').open('a')as f:f.write(json.dumps(row,default=_json)+'\n')
    monitor.after(command,receipt,before,after)
    if guard is not None:guard()
   return receipts[0]if len(receipts)==1 else dict(step_before=receipts[0]['step_before'],
       step_after=receipts[-1]['step_after'],subaction_receipts=receipts,requested_action=requested)
 return BranchAuthor


def dispatch(author,context,branch_name):
 task=author.scene.spec['id'];params=dict(context.get('branch_params',{}))
 if task in EXTENSIONS:
  from importlib import import_module
  module_name=EXTENSIONS[task]
  if task=='E08'and branch_name=='sole_com_complete_left':module_name='execution_design_e08_midfoot'
  elif task=='E08'and branch_name=='complete_right_after_left':module_name='execution_design_e08_pair'
  if task=='E13':
   if branch_name=='edge_face_complete_supported':module_name='execution_design_e13_reedge'
   elif branch_name=='shortwidth_complete_supported':module_name='execution_design_e13_shortwidth'
   elif branch_name=='camera_end_complete_supported':module_name='execution_design_e13_camera_place'
   elif branch_name in {'camera_end_acquire','camera_end_resume_entry','camera_end_reacquire','camera_end_finish_lift'}:module_name='execution_design_e13_camera'
  module=import_module('.'+module_name,__package__)
  if task=='E09':
   def save_boundary(controller,author=None,context=None):
    monitor=author._branch_monitor;monitor.context.update(context or {})
    entry=monitor.context.get('e09_entry')
    labels={'post_local_all':'post-local-all','blue_local':'blue-source-above','blue_lifted':'blue-native-lifted'}
    monitor.save(labels.get(entry,'e09-phase-boundary'))
    return monitor.checkpoints[-1]
   return module.run_branch(author,branch_name,checkpoint_context=context,
       save_checkpoint=save_boundary,stop_after_local=branch_name in('pre_blue','blue_local','blue_transport'))
  return module.run_branch(author,context,branch_name)
 if task=='E01':
  from .execution_design_expert import ExecutionDesignAuthor
  policy=ExecutionDesignAuthor(author);author._branch_policy=policy
  restore_policy_context(policy,context)
  if 'source_grip_local'in params:
   local=np.asarray(params['source_grip_local'],float)
   if local.shape!=(3,)or not np.isfinite(local).all():raise ValueError('Original finite material-point baseline required')
   policy._e01_support_grip_local=local
  if branch_name=='extract_supported_tray':
   from .execution_design_e01_contact_diagnostic import install
   from .execution_design_e01_tray_reference import extract_whole_tray_from_lower_shelf
   if not hasattr(policy,'_e01_native_bottom_local'):install(policy)
   extract_whole_tray_from_lower_shelf(policy,params.get('side','right'))
  elif branch_name=='acquire_tray_rim':
   from .execution_design_e01_tray_reference import acquire_tray_rim
   return acquire_tray_rim(policy,params['side'],params['other'],rim_x=params.get('rim_x',-.055))
  elif branch_name=='transport_tray':
   from .execution_design_e01_tray_reference import transport_tray
   return transport_tray(policy,params['target'],params['support'],existing_side=params.get('existing_side'),already_dual=params.get('already_dual',False),single_side=params.get('single_side'),settle_in_place=params.get('settle_in_place',False))
  elif branch_name=='food_local':
   from .execution_design_e01_food import food_local
   return food_local(policy)
  elif branch_name=='load_meal_tray_balanced':
   from .execution_design_e01_balance import complete_balanced_load
   return complete_balanced_load(policy)
  elif branch_name=='complete_meal_shipment':
   from .execution_design_e01_functional import complete_shipment
   return complete_shipment(policy)
  elif branch_name=='complete_remaining_workflow':
   from .execution_design_e01_remaining import complete_remaining
   return complete_remaining(policy,params)
  elif branch_name in ('stage_meal_box_for_loading','settle_loading_carton','load_meal_tray','load_meal_tray_left','escape_lid_arm'):
   from . import execution_design_e01_package
   return getattr(execution_design_e01_package,branch_name)(policy)
  elif branch_name=='close_loading_lid':
   from .execution_design_e01_lid import close_loading_lid
   return close_loading_lid(policy)
  elif branch_name=='deliver_meal_box':policy.deliver()
 elif task=='E10':
  from .realworld_structural_expert import StructuralAuthor
  policy=StructuralAuthor(author);author._branch_policy=policy;restore_policy_context(policy,context);name=params['actor'];side=params['side']
  if branch_name=='native_empty_motion_smoke':
   import time
   if params.get('performance_only')is not True or any(bool(v['grasp'][1])for v in policy.snapshot()[0].values()):
    raise ValueError('Five-step timing requires an explicitly empty right hand')
   samples=[]
   for token in ('UP','UP','DOWN','DOWN','STILL'):
    before=time.monotonic();policy.act('right',token,mm=5.)
    samples.append(dict(action=token,seconds=time.monotonic()-before,actual_tcp=policy.tip('right').tolist()))
   return dict(local_completed=True,performance_only=True,public_actions=5,timing=samples,whole_task_score=None)
  if branch_name=='post_remaining_functional':
   from .execution_design_e10_insertion import finish_functional_remaining
   return finish_functional_remaining(policy)
  if branch_name in {'acquire_receiver','acquire_and_lift'}:
   from .execution_design_e10_reference import acquire_thin_piece,near_side_piece_ref,lift_thin_piece
   acquire_thin_piece(policy,near_side_piece_ref(policy,policy.ref(name)),side,local_reacquire=params.get('local_reacquire',False))
   if branch_name=='acquire_and_lift':return lift_thin_piece(policy,policy.ref(name),side,height=params.get('height',.020))
  elif branch_name=='close_prepared_and_lift':
   from .execution_design_e10_reference import close_prepared_thin_piece,near_side_piece_ref,lift_thin_piece
   ref=near_side_piece_ref(policy,policy.ref(name))
   close_prepared_thin_piece(policy,ref,side,warm_support=True)
   return lift_thin_piece(policy,ref,side,height=params.get('height',.020))
  elif branch_name=='lift_piece':
   from .execution_design_e10_reference import lift_thin_piece
   return lift_thin_piece(policy,policy.ref(name),side,height=params.get('height',.020))
  else:
   from .execution_design_e10_insertion import thread_piece,thread_precision,release_engaged_piece
   placement=policy.geometry['threading_targets'][name]
   indices=params.get('post_indices',placement['post_indices']);post=policy.s['posts'][indices[0]]
   args=(policy,name,params.get('ref',policy.ref(name)),side,params['target'],
       params.get('rotation',placement['rotation']),indices,params.get('support',post['ref'].get('actor')))
   if branch_name=='release_threaded':return release_engaged_piece(*args)
   if branch_name=='thread_precision':
    retreat=params.get('backoff_before_turn_mm')
    if retreat is not None:
     from .execution_design_e10_insertion import post_clearances
     if not isinstance(retreat,(int,float))or not .5<=retreat<=10. or min(x['gap_above_tip_m']for x in post_clearances(policy,name,indices))<=.010:
      raise ValueError('E10 retreat requires a bounded public BACK wholly above every post')
     policy.require_held({'actor':name},side);policy.act(side,'BACK',mm=retreat)
    return thread_precision(*args,descent_mm=params.get('descent_step_mm',.5),release=params.get('release',False))
   thread_piece(*args)
 elif task=='E12':
  from .realworld_structural_expert import StructuralAuthor
  from .execution_design_e12_reference import rotate_charger_with_public_holds,insert_charger_precisely
  policy=StructuralAuthor(author);author._branch_policy=policy;restore_policy_context(policy,context);name=params.get('actor','charger_2');side=params.get('side','right')
  if branch_name=='complete_first_pin':
   from .execution_design_e12_branch import complete_first_pin
   return complete_first_pin(policy)
  if branch_name=='resume_second_pin':
   from .execution_design_e12_branch import resume_second_pin
   return resume_second_pin(policy)
  if branch_name=='release_second_pin':
   from .execution_design_e12_branch import release_second_pin
   return release_second_pin(policy)
  if branch_name in('prepare_second_toe','grasp_second_toe','complete_second_toe','complete_second_tilted_toe','complete_second_toe28'):
   from .execution_design_e12_branch import run_branch as run_toe_branch
   return run_toe_branch(policy,context,branch_name)
  if branch_name=='rotate_second':
   if not author.control_report.get('e12_pin_alignment'):raise BranchStopped('First insertion context required')
   rotate_charger_with_public_holds(policy,name,side,params['rotation'])
  else:insert_charger_precisely(policy,name,params.get('ref',policy.ref(name)),side,
       params['slot_id'],params['rotation'],params['depth'])
 else:raise ValueError('No branch implementation')
 return dict(local_completed=True,whole_task_success_asserted=False)


def restore_policy_context(policy,context):
 for key,value in context.get('policy_state',{}).items():
  if key in ('start','limit'):
   if type(value)is not int or value<0:raise ValueError('Invalid saved policy action bounds')
   setattr(policy,key,value)
  elif key=='index':
   if value!=policy.index:raise ValueError('Saved policy variant differs')
  elif key=='operations':policy.operations=deepcopy(value)
  elif key in('_e01_rim_acquisition','_e01_transport_state','_e01_food_progress','_e01_package_progress','_e01_balance_progress','_e12_toe_preparation'):
   if not isinstance(value,dict):raise ValueError('Invalid saved E01 acquisition context')
   setattr(policy,key,deepcopy(value))
  elif key=='_e01_verified_rim_grips':
   if not isinstance(value,dict)or set(value)-{'left','right'}:
    raise ValueError('Invalid saved E01 measured rim grips')
   grips={side:np.asarray(local,float)for side,local in value.items()}
   if any(local.shape!=(3,)or not np.isfinite(local).all()for local in grips.values()):
    raise ValueError('Invalid saved E01 measured rim grips')
   setattr(policy,key,grips)
  elif key in ('_e01_native_bottom_local','_e01_native_com_local','_e01_support_grip_local'):
   array=np.asarray(value,float)
   if not np.isfinite(array).all() or (key.endswith(('com_local','grip_local'))and array.shape!=(3,)) or (key.endswith('bottom_local')and (array.ndim!=2 or array.shape[1]!=3 or len(array)<3)):
    raise ValueError('Invalid saved native tray geometry')
   setattr(policy,key,array)


def failure_head(pool,room,c,path):
 before=(pool.physics_ticks,c.physics_ticks,c.steps,float(c.sim.current_time))
 def capture():
  from PIL import Image
  camera=c.scene.cameras['head'];camera.update(0.,force_recompute=True)
  Image.fromarray(camera.data.output['rgb'][0,:,:,:3].cpu().numpy()).save(path)
 pool.render_room(room,passes=1,capture=capture)
 if before!=(pool.physics_ticks,c.physics_ticks,c.steps,float(c.sim.current_time)):
  raise RuntimeError('Branch failure render advanced physics/actions')
 return dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def rebuild_actual_hold(author,monitor,payload,request):
 from scipy.spatial.transform import Rotation
 actor=request['actor'];side=request['side'];index=0 if side=='left'else 1
 root=np.asarray(payload['objects'][actor]['root_state_task'],float)
 expected=Rotation.from_quat([*root[4:7],root[3]]).as_matrix()
 monitor.last_active=(side,)
 for count in range(request['max_actions']+1):
  state,_=author.c.snapshot();body=state[actor]
  distance=float(np.linalg.norm(np.asarray(body['pos'])-root[:3]))
  angle=float(np.linalg.norm(Rotation.from_matrix(np.asarray(body['mat'])@expected.T).as_rotvec()))
  reproduced=distance<=.005 and angle<=math.radians(3)
  record=dict(actor=actor,side=side,public_still_actions=count,position_error_m=distance,rotation_error_rad=angle,
      checkpoint_pose_reproduced=reproduced)
  if not reproduced and not request.get('actual_hold_only',False):
   monitor.context['checkpoint_not_reproduced']=record;monitor.save('not-reproduced')
   raise CheckpointNotReproduced('Checkpoint pose departed5mm/3degree reconstruction envelope')
  if body['grasp'][index]:
   if not reproduced:
    monitor.context['adopted_actual_held_fixture']=dict(record,not_exact_source_continuation=True,
        reason='Actual cold-restored held state adopted only for diagnostic suffix; whole-task acceptance remains ineligible')
   monitor.context['actual_restored_hold']=record;monitor.save('contact-verified');return record
  if count<request['max_actions']:author.act(left='STILL',right='STILL',mm=.5,rotation_deg=.5)
 raise CheckpointNotReproduced('Actual held contact not rebuilt within explicit public STILL budget')


def run_branch(pool,controller,case,out,request,*,checkpoint_api=None,dispatcher=None,author_factory=None,head_renderer=failure_head):
 """Restore one debug checkpoint and execute only its named bounded suffix."""
 if len(pool.controllers)!=1 or pool.controllers.get(case['episode_id'])is not controller:
  raise ValueError('Engineering branches require exactly one matching room')
 request=validate_request(request,case,controller.scene.spec);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 path=Path(request['checkpoint_path']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if digest!=request['checkpoint_sha256']:raise ValueError('Checkpoint SHA256 mismatch')
 if checkpoint_api is None:
  from . import front13_engineering_checkpoint as checkpoint_api
 legacy=request['checkpoint_input_kind']=='legacy_boundary_reconstruction'
 payload=json.loads(path.read_bytes())if legacy else checkpoint_api.load(path)
 if author_factory is None:
  from .demonstration import Demonstration
  factory=lambda c,p,m:branch_author_class(Demonstration,pool,case['episode_id'],m)(c,p)
 else:factory=author_factory
 monitor=BranchMonitor(controller,request,out,checkpoint_api,{})
 author=factory(controller,out,monitor);monitor.author=author
 controller._engineering_branch_authorized=True
 report=dict(debug_only=True,eligible_full_acceptance=False,whole_task_score=None,
     case={key:case[key]for key in ('task','variant','seed','episode_id')},branch_name=request['branch_name'],
     checkpoint_path=str(path),checkpoint_sha256=digest,action_budget=request['action_budget'],
     checkpoint_input_kind=request['checkpoint_input_kind'],
     model_launch_enabled=False,api_used=False,restore_succeeded=False,branch_start_step=None)
 started=time.monotonic();result=None
 try:
  if not callable(getattr(controller.sim,'forward',None)):
   raise RuntimeError('Native SimulationContext.forward unavailable; restore refused before state writes')
  if legacy:
   payload=checkpoint_api.from_legacy(controller,payload,author=author)
   report['imported_checkpoint']=checkpoint_api.save(payload,out/'imported-debug-checkpoint.private.json')
  report['checkpoint_state_quality']=payload.get('state_quality','native_captured')
  report['checkpoint_assumptions']=payload.get('assumptions',[])
  readback=checkpoint_api.restore(controller,payload,author=author)
  monitor.start=int(controller.steps);monitor.context=dict(readback.get('context')or{})
  extension=request.get('engineering_reference_budget_extension')
  if extension is not None:
   parent,new=extension['parent_budget'],extension['new_budget']
   if monitor.context.get('policy_action_budget')not in(parent,new):
    raise ValueError('Parent engineering budget lineage differs')
   monitor.context['parent_policy_action_budget']=parent
   monitor.context['policy_action_budget']=new
   monitor.context['engineering_reference_budget_extension']=deepcopy(extension)
   if 'policy_state'in monitor.context:monitor.context['policy_state']['limit']=new
   report['engineering_reference_budget_extension']=deepcopy(extension)
  if case['task']=='E09'and request['branch_name']in('pre_blue','blue_local','blue_transport'):
   remaining=int(controller.scene.spec.get('expert_action_budget',0))-monitor.start
   if request['action_budget']>min(2200,remaining):
    raise ValueError('E09 pre_blue branch budget exceeds original cumulative remaining budget')
  if case['task']=='E01'and request['branch_name']=='complete_remaining_workflow':
   remaining=int(monitor.context.get('policy_action_budget',0))-(monitor.start-int(monitor.context.get('policy_start_step',0)))
   if request['action_budget']>min(2000,remaining):
    raise ValueError('E01 functional branch budget exceeds original cumulative remaining budget')
  monitor.context.update(request.get('context_patch',{}))
  monitor.context['branch_params']={**monitor.context.get('branch_params',{}),**request.get('params',{})}
  private=monitor.context.get('author_control_report',{})
  if not isinstance(private,dict):raise ValueError('Checkpoint private control report must be a dictionary')
  author.control_report.update(private)
  author.control_report.update(engineering_reference_only=True,debug_only=True,
      eligible_full_acceptance=False,eligible_as_model_demo=False,whole_task_score=None)
  report.update(restore_readback=readback,branch_start_step=monitor.start,restore_succeeded=True)
  pool.physics_ticks=controller.physics_ticks
  report['native_clock_at_restore_seconds']=float(controller.sim.current_time)
  monitor.save('restored')
  if request.get('rebuild_held')is not None:
   report['held_reconstruction']=rebuild_actual_hold(author,monitor,payload,request['rebuild_held'])
  result=(dispatcher or dispatch)(author,monitor.context,request['branch_name'])
  report.update(local_completed=bool(result.get('local_completed',True))if isinstance(result,dict)else True,branch_result=result)
  if report['local_completed']:
   monitor.save('local-complete')
   if request.get('params',{}).get('capture_final_head')is True:
    before=(pool.physics_ticks,controller.physics_ticks,controller.steps,float(controller.sim.current_time))
    try:report['final_head']=head_renderer(pool,case['episode_id'],controller,out/'branch-functional-final-head.png')
    except Exception as exc:
     if before!=(pool.physics_ticks,controller.physics_ticks,controller.steps,float(controller.sim.current_time)):raise
     report['final_head_error']=type(exc).__name__+': '+str(exc)
 except Exception as exc:
  monitor.stopped=True;report.update(local_completed=False,error=type(exc).__name__+': '+str(exc))
  if isinstance(exc,CheckpointNotReproduced):report['checkpoint_not_reproduced']=True
  if report.get('restore_succeeded'):
   try:monitor.save('branch-failure')
   except Exception as save_exc:report['failure_checkpoint_error']=type(save_exc).__name__+': '+str(save_exc)
  try:report['failure_head']=head_renderer(pool,case['episode_id'],controller,out/'branch-failure-head.png')
  except Exception as render_exc:report['failure_head_error']=type(render_exc).__name__+': '+str(render_exc)
 finally:
  monitor.stopped=True
  controller._engineering_branch_authorized=False
  report.update(branch_end_step=int(controller.steps),local_actions=len(monitor.receipts),
      wall_seconds=time.monotonic()-started,checkpoints=monitor.checkpoints,post_failure_settle_ticks=0)
  if 'native_clock_at_restore_seconds'in report:
   report['native_elapsed_seconds']=float(controller.sim.current_time)-report['native_clock_at_restore_seconds']
  write_json(out/'engineering-branch-report.private.json',report)
 return report
