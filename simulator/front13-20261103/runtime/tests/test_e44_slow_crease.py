"""No minimum folding speed; retain force attribution and final physical rules."""
import math
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.crease_motion import contact_driven_motion, accumulate_driven
from videoicl_isaaclab.realworld_semantic_checks import check_task
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator


def trace(final=90.,delta=.05):
 n=round((175-final)/delta)
 values=[175-i*(175-final)/n for i in range(n+1)]+[final]
 return [dict(step=i,angle_deg=a,hand_contact_force=.2 if 0<i<len(values)-1 else 0.,joint_pos=math.radians(180-a)) for i,a in enumerate(values)]


def observation(samples,**kw):
 return dict(released=True,stable=True,dihedral_angle_deg=samples[-1]['angle_deg'],base_table_contact_force=1.,external_support_contacts=[],fold_samples=samples,**kw)


@pytest.mark.parametrize('variant,angle',[('A',90),('B',125),('C',55)])
def test_slow_force_driven_fold_accepted_for_each_category(variant,angle):
 samples=trace(angle)
 assert max(abs(b['angle_deg']-a['angle_deg'])for a,b in zip(samples,samples[1:]))<.1
 assert check_task('E44',variant,observation(samples))['success']


def test_no_force_motion_and_subthreshold_jitter_rejected():
 samples=trace()
 for s in samples:s['hand_contact_force']=0.
 assert not check_task('E44','A',observation(samples))['success']
 jitter=[dict(step=i,angle_deg=175+(.02 if i%2 else -.02),hand_contact_force=.2)for i in range(100)]
 assert not contact_driven_motion(jitter)
 # Then let it drift to final angle without a hand: jitter cannot authorize it.
 drift=[dict(step=100+i,angle_deg=175-i*.05,hand_contact_force=0.)for i in range(1701)]
 assert not check_task('E44','A',observation(jitter+drift))['success']


def test_small_disconnected_work_below_five_degrees_is_insufficient():
 samples=[dict(step=i,angle_deg=175-i*.04,hand_contact_force=.2 if i%2 else 0.)for i in range(200)]
 assert not contact_driven_motion(samples)


@pytest.mark.parametrize('field,value',[('released',False),('stable',False),('base_table_contact_force',0.),('external_support_contacts',['prop'])])
def test_final_independent_standing_requirements_unchanged(field,value):
 obs=observation(trace());obs[field]=value
 assert not check_task('E44','A',obs)['success']


def test_total_five_degree_and_final_angle_checks_remain():
 samples=[dict(step=i,angle_deg=94-i*.04,hand_contact_force=.2 if i<100 else 0.)for i in range(101)]
 assert not check_task('E44','A',observation(samples))['success']
 obs=observation(trace());obs['dihedral_angle_deg']=125
 assert not check_task('E44','A',obs)['success']


@pytest.mark.parametrize('locked_joint',[False,True])
def test_native_update_uses_cumulative_contact_motion_and_actual_joint(locked_joint):
 e=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
 e.crease=dict(mechanism='card',base=dict(body='base',normal_local=[0,0,1]),fold=dict(body='fold',normal_local=[0,0,1],contact_body='fold'))
 e.fold_samples=[];e.crease_driven=False;e.extra_checks={}
 for s in trace():
  theta=math.radians(180-s['angle_deg']);r=np.array([[math.cos(theta),0,math.sin(theta)],[0,1,0],[-math.sin(theta),0,math.cos(theta)]])
  e.body=lambda mechanism,name:(np.zeros(3),np.eye(3)if name=='base'else r)
  e.joint=lambda c:0. if locked_joint else theta
  e.hand_force=lambda name:s['hand_contact_force'];e.steps=s['step']
  e._crease_history()
 assert e.crease_driven is (not locked_joint)


def drift_after_touch(driven_degrees):
 # Each actual contact tick folds only .05 degrees; speed is not the criterion.
 count=round(driven_degrees/.05)
 samples=[dict(step=i,angle_deg=175-i*.05,hand_contact_force=.2 if i else 0.,joint_pos=math.radians(i*.05)) for i in range(count+1)]
 start=samples[-1]['angle_deg']
 for i in range(1,1001):
  angle=start+(90-start)*i/1000
  samples.append(dict(step=count+i,angle_deg=angle,hand_contact_force=0.,joint_pos=math.radians(180-angle)))
 return samples


@pytest.mark.parametrize('driven_degrees,accepted',[(.15,False),(4.95,False),(5.,True),(6.,True)])
def test_force_attribution_requires_five_degrees_before_passive_continuation(driven_degrees,accepted):
 samples=drift_after_touch(driven_degrees)
 assert contact_driven_motion(samples) is accepted
 assert check_task('E44','A',observation(samples))['success'] is accepted


def test_contact_run_cannot_bridge_missing_or_out_of_order_physics_ticks():
 a=dict(step=0,angle_deg=175.,joint_pos=0.,hand_contact_force=0.)
 b=dict(step=10,angle_deg=165.,joint_pos=.2,hand_contact_force=.2)
 assert accumulate_driven(a,b,None,require_joint=True)['angle']==0.
 for index in [1,100,500]:
  samples=trace();samples[index]['step']+=1
  assert not contact_driven_motion(samples)
  assert not check_task('E44','A',observation(samples))['success']


@pytest.mark.parametrize('driven_degrees,accepted',[(.15,False),(5.,True)])
def test_native_adapter_does_not_latch_a_tiny_touch_as_a_completed_fold(driven_degrees,accepted):
 e=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
 e.crease=dict(mechanism='card',base=dict(body='base',normal_local=[0,0,1]),fold=dict(body='fold',normal_local=[0,0,1],contact_body='fold'))
 e.fold_samples=[];e.crease_driven=False;e.extra_checks={}
 for s in drift_after_touch(driven_degrees):
  theta=math.radians(180-s['angle_deg']);r=np.array([[math.cos(theta),0,math.sin(theta)],[0,1,0],[-math.sin(theta),0,math.cos(theta)]])
  e.body=lambda mechanism,name:(np.zeros(3),np.eye(3)if name=='base'else r)
  e.joint=lambda c:theta;e.hand_force=lambda name:s['hand_contact_force'];e.steps=s['step']
  e._crease_history()
 assert e.crease_driven is accepted


def segmented_trace(active_changes, final=90.):
 samples=[dict(step=0,angle_deg=175.,hand_contact_force=0.,joint_pos=math.radians(5.))]
 angle=175.
 for change in active_changes:
  n=max(1,round(abs(change)/.05))
  for _ in range(n):
   angle+=change/n
   samples.append(dict(step=len(samples),angle_deg=angle,hand_contact_force=.2,joint_pos=math.radians(180-angle)))
  samples.append(dict(step=len(samples),angle_deg=angle,hand_contact_force=0.,joint_pos=math.radians(180-angle)))
 samples.append(dict(step=len(samples),angle_deg=final,hand_contact_force=0.,joint_pos=math.radians(180-final)))
 return samples


@pytest.mark.parametrize('changes,expected',[([-2.,-2.,-2.],True),([-1.]*85,True),([-2.,2.]*20,False),([2.,2.,2.],False)])
def test_multiple_regrasps_count_signed_work_not_absolute_travel(changes,expected):
 samples=segmented_trace(changes)
 assert contact_driven_motion(samples) is expected
 assert check_task('E44','A',observation(samples))['success'] is expected
 totals=None
 for previous,current in zip(samples[:-1],samples[1:]):
  totals=accumulate_driven(previous,current,totals,require_joint=True)
 from videoicl_isaaclab.crease_motion import driven_toward_final
 assert driven_toward_final(totals,175.,90.,require_joint=True) is expected
