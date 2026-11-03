from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e11_reference import checked_plan
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.realworld_scenes import load
from pathlib import Path
P=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

def author(variant='A',condition='I',seed=4201):
 s=apply_execution_inputs(load('E11',variant,0,P,verify_files=False),condition=condition,seed=seed,revision=REVISION_V3)
 state={o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=np.eye(3),grasp=[False,False])for o in s['objects']}
 return SimpleNamespace(scene=SimpleNamespace(spec=s),_execution_design_reference_authorized=True,c=SimpleNamespace(snapshot=lambda:(state,set())))

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('condition',['R','I','E'])
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_physical_tray_move_preserves_contract_and_clears_original_cargo(variant,condition,seed):
 a=author(variant,condition,seed);before=deepcopy(a.scene.spec);point,target,start=checked_plan(a)
 assert target==pytest.approx(start+[-.06,0,0]);assert point==pytest.approx(start+[-.112,.045,.010]);assert a.scene.spec==before

def test_no_formal_or_legacy_entry():
 a=author();a._execution_design_reference_authorized=False
 with pytest.raises(ValueError,match='explicit'):checked_plan(a)
 a._execution_design_reference_authorized=True;a.scene.spec['execution_design']['revision']='legacy'
 with pytest.raises(ValueError,match='explicit'):checked_plan(a)

def test_reject_changed_asset_and_static_tray():
 a=author();a.scene.spec['objects'][0]['role']='fixture'
 with pytest.raises(ValueError,match='dynamic'):checked_plan(a)
 a=author();a.scene.spec['objects'][0]['source_asset']['sha256']='changed'
 with pytest.raises(ValueError,match='dynamic'):checked_plan(a)

def test_reject_cargo_on_sweep():
 a=author();state,_=a.c.snapshot();state['red_block']['pos'][:2]=[.10,0]
 with pytest.raises(ValueError,match='sweep'):checked_plan(a)

def test_failed_physical_grasp_stops_before_tray_transfer():
 from videoicl_isaaclab.execution_design_e11_reference import move_empty_tray
 a=author();commands=[];a.note=lambda s:None;a.act=lambda *x:commands.append(x)
 a.tip=lambda s:np.array([0,.1,.96]);a.move_generated=lambda *x,**k:None;a.align_gripper_axis=lambda *x:None
 with pytest.raises(RuntimeError,match='not physically held'):move_empty_tray(a)
 assert commands.count(('GRASP','STILL'))==3
 assert not hasattr(a,'carried_payload')

def test_successful_grasp_does_not_override_later_real_grip_loss():
 from videoicl_isaaclab.execution_design_e11_reference import move_empty_tray
 a=author();state,_=a.c.snapshot();commands=[];a.note=lambda s:None
 def act(*args):
  commands.append(args)
  if args==('GRASP','STILL'):state['tray']['grasp']=[True,False]
  elif getattr(a,'carried_payload',None):state['tray']['grasp']=[False,False]
 def move(*args,**kw):
  if getattr(a,'carried_payload',None):state['tray']['grasp']=[False,False]
 a.act=act;a.tip=lambda s:np.array([0,.1,.96]);a.move_generated=move;a.align_gripper_axis=lambda *x:None
 with pytest.raises(RuntimeError,match='grip lost'):move_empty_tray(a)
 assert commands.count(('RELEASE','STILL'))==0

def test_main_body_error_progresses_despite_submillimeter_cross_axis_residual(monkeypatch):
 from videoicl_isaaclab.execution_design_e11_reference import move_empty_tray
 a=author();state,_=a.c.snapshot();a.c.snapshot=lambda:(state,{frozenset(('tray','table'))})
 a.note=lambda s:None;a.tip=lambda s:np.array([.035,.045,.83]);a.move_generated=lambda *x,**k:None;axes=[];a.align_gripper_axis=lambda side,axis:axes.append((side,axis));pull=[]
 def act(*args):
  if args==('GRASP','STILL'):
   state['tray']['grasp']=[True,False];state['tray']['pos'][:2]=[.129,.001]
  elif args==('RELEASE','STILL'):state['tray']['grasp']=[False,False]
  elif getattr(a,'carried_payload',None):
   pull.append(args);assert args[0]=='BACK'
   state['tray']['pos'][0]-=args[2]/1000
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e11_reference.restore_cargo_axis',lambda a,side:axes.append((side,[0,1,0])))
 a.act=act;move_empty_tray(a)
 assert len(pull)>3 and state['tray']['pos'][0]==pytest.approx(.09,abs=.002)
 assert not state['tray']['grasp'][0]
 assert axes==[('left',[1,0,0]),('left',[0,1,0])]


def test_recorded_wrist_saturation_selects_feasible_equivalent_pinch():
 from videoicl_isaaclab.execution_design_e11_reference import cargo_orientation_delta
 from videoicl_isaaclab.author_orientation import _quaternion_matrix,_axis_angle
 current=_quaternion_matrix([.060274512302992245,.30541709558734514,-.9501107161565352,.019420921399408774])
 arm=dict(joint_names=['panda_joint7'],joint_positions_rad=[2.8971049785614014],measured_sensors={'joint_soft_limits_rad':{'available':True,'value':[[-2.8972997665405273,2.8972997665405273]]}})
 delta=cargo_orientation_delta(current,current[:,1],arm);axis,angle=_axis_angle(delta)
 predicted=arm['joint_positions_rad'][0]+angle*float(axis@current[:,2])
 assert -2.8973<predicted<2.8973
 assert axis[2]>0 # move away from the observed clockwise upper-limit trap
 assert np.allclose((delta@current)[:,2],[0,0,-1])
 assert abs(float((delta@current)[:,1]@np.array([0,1,0])))>.999

def test_absent_native_wrist_limits_rejected():
 from videoicl_isaaclab.execution_design_e11_reference import cargo_orientation_delta
 arm=dict(joint_names=['panda_joint7'],joint_positions_rad=[0],measured_sensors={'joint_soft_limits_rad':{'available':False}})
 with pytest.raises(ValueError,match='native wrist limits'):cargo_orientation_delta(np.eye(3),[0,1,0],arm)

@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('condition','RIE')
def test_near_edge_grasp_and_waypoint_inside_original_compartment(variant,condition,monkeypatch):
 from videoicl_isaaclab.execution_design_e11_reference import grasp_spec,reachable_cell_xy
 a=author(variant,condition);before=deepcopy(a.scene.spec);state,_=a.c.snapshot()
 import json
 fixture=json.loads((Path(__file__).parent/'data/e11-source-plate-collision-vertices.json').read_text())
 mesh=np.asarray(fixture['vertices'])
 def points(policy,ref):
  pos,rot=policy.frame(ref);return mesh@rot.T+pos
 monkeypatch.setattr('videoicl_isaaclab.execution_design_thin_edge.material_collision_points_task',points)
 state['tray']['pos'][0]-=.06
 for goal in a.scene.spec['goals']:
  obj=next(o for o in a.scene.spec['objects']if o['id']==goal['object'])
  candidate=grasp_spec(a,obj)
  assert candidate['grasp_point_local']==[-.01,0,0] and candidate['grasp_axis_local']==[0,1,0]
  target=next(t for t in a.scene.spec['zones']if t['id']==goal['target'])
  xy=reachable_cell_xy(a,goal['object'],target);local=xy-state['tray']['pos'][:2]
  bounds=a.scene.spec['semantic']['compartment_bounds'][target['id']]
  assert np.all(local-np.asarray(obj['size'][:2])>=np.asarray(bounds['lower'][:2])+.00299)
  assert np.all(local+np.asarray(obj['size'][:2])<=np.asarray(bounds['upper'][:2])-.00299)
  assert xy[0]-.01<=.10801 if target['id'].startswith('far') else xy[0]<.09
 assert a.scene.spec==before

def test_oversized_or_changed_object_cannot_use_cell_waypoint(monkeypatch):
 from videoicl_isaaclab.execution_design_e11_reference import reachable_cell_xy
 a=author()
 import itertools
 monkeypatch.setattr('videoicl_isaaclab.execution_design_thin_edge.material_collision_points_task',lambda policy,ref:np.array(list(itertools.product((-.2,.2),(-.2,.2),(-.003,.003))))+policy.frame(ref)[0])
 with pytest.raises(RuntimeError,match='cannot fit'):reachable_cell_xy(a,'red_block',a.scene.spec['zones'][0])


@pytest.mark.parametrize('yaw',[-.2,0,.2])
@pytest.mark.parametrize('pitch',[-.08,0,.08])
def test_full_source_collision_cloud_respects_all_original_cell_bounds(yaw,pitch):
 import json
 from videoicl_isaaclab.execution_design_e11_reference import cell_point_from_vertices,PLATE_SHA
 from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
 fixture=json.loads((Path(__file__).parent/'data/e11-source-plate-collision-vertices.json').read_text())
 assert fixture['source_sha256']==PLATE_SHA
 points=np.asarray(fixture['vertices']);rotation=_axis_rotation([0,0,1],yaw)@_axis_rotation([0,1,0],pitch)
 a=author();state,_=a.c.snapshot();position=np.array([-.06,.06,.803]);world=points@rotation.T+position
 for zone in a.scene.spec['zones']:
  bounds=a.scene.spec['semantic']['compartment_bounds'][zone['id']]
  local,proof=cell_point_from_vertices(position,world,state['tray'],bounds,zone['anchor_local_center'])
  assert proof['vertices']==392
  assert np.all(np.asarray(proof['predicted_min_local'])>=bounds['lower'])
  assert np.all(np.asarray(proof['predicted_max_local'])<=bounds['upper'])


def test_rim_release_uses_highest_real_rim_and_both_fingers():
 from videoicl_isaaclab.execution_design_e11_reference import rim_release_height
 mesh=np.array([[0,0,.81],[0,.1,.842],[.1,0,.840],[.1,.1,.841]])
 fingers=dict(source='actual_collision_mesh_current_body_pose',fingers=[{'aabb_min_task_m':[0,0,.811]},{'aabb_min_task_m':[0,0,.813]}])
 height,proof=rim_release_height(mesh,fingers,[.1,.04,.823],.824)
 assert height==pytest.approx(.862)
 assert proof['predicted_finger_clearance_m']==pytest.approx(.008)
 assert not proof['native_release_verified']

def test_missing_real_rim_or_finger_data_rejected():
 from videoicl_isaaclab.execution_design_e11_reference import rim_release_height
 with pytest.raises(ValueError,match='collision cloud'):rim_release_height([[0,0,.84]],{},[0,0,.83],.824)
 with pytest.raises(ValueError,match='Both actual'):rim_release_height(np.zeros((4,3)),{},[0,0,.83],.824)
