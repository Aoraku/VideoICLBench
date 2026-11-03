"""Engineering-only read-only Panda screw-axis IK candidate diagnostics.

No robot state writes, controller calls, limit relaxation, or collision promises.
The native measured Jacobian defines spatial screw axes at the current state.
"""
import json,math
import numpy as np

def record_action_dynamics(author,controller,side,token):
 """Persist actual tracking evidence after a public action; never actuate."""
 robot=author.scene.robots[side];arm,_,_=controller.ids[side]
 q=robot.data.joint_pos[0,arm].detach().cpu().numpy()
 row=dict(step=controller.steps,side=side,token=token,q=q.tolist(),stage=author.stage)
 for field in ('joint_pos_target','joint_vel','applied_torque','computed_torque'):
  value=getattr(robot.data,field,None)
  if value is not None:row[field]=value[0,arm].detach().cpu().numpy().tolist()
 if 'joint_pos_target'in row:row['joint_tracking_error_rad']=(np.asarray(row['joint_pos_target'])-q).tolist()
 row['body_origins_task']={name:np.asarray(author.scene.world_to_task(position),float).tolist()for name,position in zip(robot.body_names,robot.data.body_pos_w[0].detach().cpu().numpy())}
 row['feedback']=controller.action_feedback()
 # Keep the physical slider/contact state beside each actual public action.
 # Stage-only summaries miss threshold crossings inside an acquisition.
 snapshot=getattr(controller,'snapshot_mechanisms',None)
 if callable(snapshot):row['mechanisms']=snapshot()
 if callable(getattr(controller,'snapshot',None)):
  _,contacts=controller.snapshot();row['contacts']=sorted([sorted(p)for p in contacts])
 with (author.out/'drawer-action-dynamics.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')

def skew(a):
 x,y,z=a;return np.array([[0,-z,y],[z,0,-x],[-y,x,0]])

def forward_at_delta(position,rotation,jacobian,delta):
 transform=np.eye(4)
 for j,angle in enumerate(delta):
  axis=jacobian[3:,j];axis=axis/np.linalg.norm(axis)
  pivot=position+np.cross(axis,jacobian[:3,j])
  k=skew(axis);r=np.eye(3)+math.sin(angle)*k+(1-math.cos(angle))*(k@k)
  joint=np.eye(4);joint[:3,:3]=r;joint[:3,3]=pivot-r@pivot;transform=transform@joint
 return transform[:3,:3]@position+transform[:3,3],transform[:3,:3]@rotation

def solve_candidates(position,rotation,jacobian,q,limits,targets):
 from scipy.optimize import least_squares
 from .author_orientation import _axis_angle
 position=np.asarray(position,float);rotation=np.asarray(rotation,float);jacobian=np.asarray(jacobian,float);q=np.asarray(q,float);limits=np.asarray(limits,float)
 assert jacobian.shape==(6,7)and q.shape==(7,)and limits.shape==(7,2)
 assert np.isfinite(jacobian).all()and np.allclose(np.linalg.norm(jacobian[3:],axis=0),1,atol=.002)
 lo=limits[:,0]-q+1e-5;hi=limits[:,1]-q-1e-5
 if not np.all(lo<0)or not np.all(hi>0):raise ValueError('Current joints already at limit; candidate probe refused')
 rng=np.random.default_rng(4201);rows=[]
 for index,target in enumerate(targets):
  desired_position=np.asarray(target.get("position",position),float)if isinstance(target,dict)else position
  target=np.asarray(target["rotation"] if isinstance(target,dict)else target,float)
  def residual(delta):
   p,r=forward_at_delta(position,rotation,jacobian,delta);axis,angle=_axis_angle(target@r.T)
   return np.r_[10*(p-desired_position),axis*angle]
  trials=[]
  for start in [np.zeros(7),*(np.clip(rng.normal(0,.5,7),lo+1e-6,hi-1e-6)for _ in range(5))]:
   result=least_squares(residual,start,bounds=(lo,hi),max_nfev=220,ftol=1e-8,xtol=1e-8,gtol=1e-8)
   p,r=forward_at_delta(position,rotation,jacobian,result.x);angle=_axis_angle(target@r.T)[1];margin=float(np.min(np.minimum(q+result.x-limits[:,0],limits[:,1]-q-result.x)))
   trials.append(dict(position_error_m=float(np.linalg.norm(p-desired_position)),orientation_error_rad=float(angle),minimum_joint_margin_rad=margin,joint_distance_rad=float(np.linalg.norm(result.x)),candidate_joints_rad=(q+result.x).tolist()))
  valid=[x for x in trials if x['position_error_m']<.001 and x['orientation_error_rad']<math.radians(1.5)]
  best=min(valid,key=lambda x:(x['joint_distance_rad']))if valid else min(trials,key=lambda x:x['position_error_m']*10+x['orientation_error_rad'])
  rows.append(dict(index=index,target_position=desired_position.tolist(),target_rotation=target.tolist(),kinematically_reachable=bool(valid),**best))
 return rows

def inspect(author,controller,side,targets):
 from .author_orientation import _axis_angle
 from .execution_design_jacobian_reference import capture
 measured=capture(author,controller,side)
 jac=np.asarray(measured['jacobian']);q=np.asarray(measured['q']);limits=np.asarray(measured['limits'])
 position=np.asarray(measured['position']);rotation=np.asarray(measured['rotation_task'])
 # Numerical local calibration checks the POE matches the measured Jacobian.
 for j in range(7):
  dq=np.zeros(7);dq[j]=1e-5;p,r=forward_at_delta(position,rotation,jac,dq);axis,angle=_axis_angle(r@rotation.T)
  assert np.linalg.norm((p-position)/1e-5-jac[:3,j])<1e-3
  assert np.linalg.norm(axis*angle/1e-5-jac[3:,j])<.01
 result=solve_candidates(position,rotation,jac,q,limits,targets)
 row=dict(schema='e30-measured-native-ik-candidates-v1',side=side,step=controller.steps,position=position.tolist(),rotation_task=rotation.tolist(),q=q.tolist(),limits=limits.tolist(),jacobian=jac.tolist(),native_reference=measured['reference'],candidates=result,collision_verified=False,actuation_performed=False)
 with (author.out/'drawer-ik-candidates.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
 return result

def physical_grasp_targets(author,controller,side,outward,pinch_axis=None):
 """Derive pinch and approach axes from actual hand/finger body geometry."""
 robot=author.scene.robots[side];ids=[robot.find_bodies(name)[0][0]for name in author.scene.embodiment.fingers];_,_,hand=controller.ids[side]
 points=robot.data.body_pos_w[0,ids].detach().cpu().numpy();palm=robot.data.body_pos_w[0,hand].detach().cpu().numpy()
 task=np.asarray(author.scene.layout.task_rotation,float).T;current=np.asarray(author.tcp_rotation_task(side),float)
 jaw=task@(points[0]-points[1]);jaw/=np.linalg.norm(jaw)
 forward=task@(points.mean(axis=0)-palm);forward-=jaw*np.dot(jaw,forward)
 if np.linalg.norm(forward)<.001:raise ValueError('Actual palm-to-finger axis is degenerate')
 forward/=np.linalg.norm(forward)
 local_jaw=current.T@jaw;local_forward=current.T@forward;local=np.column_stack((local_jaw,local_forward,np.cross(local_jaw,local_forward)))
 desired_forward=-np.asarray(outward,float);desired_forward/=np.linalg.norm(desired_forward);desired_jaw=np.cross([0.,0.,1.],outward)if pinch_axis is None else np.asarray(pinch_axis,float);desired_jaw/=np.linalg.norm(desired_jaw)
 targets=[]
 for sign in (1.,-1.):
  desired=np.column_stack((sign*desired_jaw,desired_forward,np.cross(sign*desired_jaw,desired_forward)))
  target=desired@local.T
  assert np.linalg.det(target)>.999 and np.allclose(target.T@target,np.eye(3),atol=1e-6)
  targets.append(target)
 return targets
