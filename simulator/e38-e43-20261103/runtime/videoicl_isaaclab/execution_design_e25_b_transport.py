"""E25B measured rotation/translation interleave, using public actions only.

A relay-centred half turn passed natively but its subsequent Cartesian return
exhausted joint7. Screen the complete interleaved route from the current native
kinematics. A candidate is neither collision proof nor native task completion.
"""
import json
import math
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from .execution_design_drawer_ik_probe import forward_at_delta
from .execution_design_e25_b_reference import require_scope,_joints
from .author_orientation import _axis_angle
from .realworld_tool_expert import _axis_rotation


def _finite(value,shape):
    value=np.asarray(value,float)
    if value.shape!=shape or not np.isfinite(value).all():raise ValueError('Complete measured E25B route geometry required')
    return value


def solve_path(measured,targets):
    """Reject-only continuous POE solve; candidate joints never become commands."""
    p0=_finite(measured['position'],(3,));r0=_finite(measured['rotation_task'],(3,3))
    jac=_finite(measured['jacobian'],(6,7));q=_finite(measured['q'],(7,));limits=_finite(measured['limits'],(7,2))
    if not np.allclose(np.linalg.norm(jac[3:],axis=0),1,atol=.002):raise ValueError('Measured native unit joint axes required')
    lower=limits[:,0]-q+.0501;upper=limits[:,1]-q-.0501
    if np.any(lower>=0)or np.any(upper<=0):raise ValueError('Actual E25B starting joints lack 50.1mrad screening margin')
    previous=np.zeros(7);old_p=p0;old_r=r0;rows=[]
    for index,target in enumerate(targets):
        goal_p=_finite(target['position'],(3,));goal_r=_finite(target['rotation'],(3,3))
        rv=Rotation.from_matrix(goal_r@old_r.T).as_rotvec()
        count=max(1,math.ceil(np.linalg.norm(goal_p-old_p)/.01),math.ceil(np.linalg.norm(rv)/math.radians(5)))
        smallest=float('inf');largest=0.;valid=True
        for sample in range(1,count+1):
            f=sample/count;desired_p=old_p+(goal_p-old_p)*f;desired_r=Rotation.from_rotvec(rv*f).as_matrix()@old_r
            def residual(delta):
                p,r=forward_at_delta(p0,r0,jac,delta)
                return np.r_[10*(p-desired_p),Rotation.from_matrix(desired_r@r.T).as_rotvec(),.01*(delta-previous)]
            result=least_squares(residual,previous,bounds=(lower,upper),max_nfev=180,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            p,r=forward_at_delta(p0,r0,jac,result.x)
            pe=float(np.linalg.norm(p-desired_p));ae=float(np.linalg.norm(Rotation.from_matrix(desired_r@r.T).as_rotvec()))
            margin=float(np.min(np.minimum(q+result.x-limits[:,0],limits[:,1]-q-result.x)))
            increment=float(np.linalg.norm(result.x-previous));smallest=min(smallest,margin);largest=max(largest,increment)
            valid=pe<.001 and ae<math.radians(1.5)and margin>.05 and increment<.35
            if not valid:break
            previous=result.x
        rows.append(dict(index=index,kinematically_reachable=bool(valid),minimum_joint_margin_rad=smallest,
            maximum_nearby_joint_increment_rad=largest,position_error_m=pe,orientation_error_rad=ae,
            candidate_joints_rad=(q+result.x).tolist(),sample=sample,sample_count=count))
        if not valid:break
        old_p=goal_p;old_r=goal_r
    return rows


def route_targets(position,tcp_rotation,body_position,body_rotation,destination_xy,desired_body_rotation,winding):
    """Eight real turn/translate pairs keep the original final object pose."""
    tip=_finite(position,(3,));tcp=_finite(tcp_rotation,(3,3));pos=_finite(body_position,(3,));body=_finite(body_rotation,(3,3))
    xy=_finite(destination_xy,(2,));desired=_finite(desired_body_rotation,(3,3));axis,angle=_axis_angle(desired@body.T)
    if angle<math.radians(150)or not any(abs(float(winding)-v)<1e-8 for v in (angle,angle-2*math.pi)):
        raise ValueError('Actual E25B original half-turn winding required')
    local_offset=body.T@(tip-pos);relative_tcp=body.T@tcp;previous=tip.copy();targets=[]
    for f in np.linspace(0,1,9)[1:]:
        obj=_axis_rotation(axis,float(winding)*f)@body;rotation=obj@relative_tcp
        targets.append(dict(phase='rotate',fraction=float(f),position=previous.tolist(),rotation=rotation.tolist(),body_rotation=obj.tolist()))
        body_xy=pos[:2]+(xy-pos[:2])*f;destination=np.r_[body_xy+(obj@local_offset)[:2],tip[2]]
        # Match public move_generated's largest-axis ordering. These points are
        # screening targets only; execution remeasures the actual held offset.
        while np.max(abs(destination-previous))>1e-9:
            delta=destination-previous;k=int(np.argmax(abs(delta)));previous=previous.copy();previous[k]+=np.sign(delta[k])*min(.008,abs(delta[k]))
            targets.append(dict(phase='translate',fraction=float(f),position=previous.tolist(),rotation=rotation.tolist(),body_xy=body_xy.tolist()))
    return targets


def _destination(a,name,goal):
    original=next(g for g in a.scene.spec['goals']if g['object']==name)
    if ('_e07_after_relay'not in goal or goal.get('object')!=name or goal.get('target')!=original.get('target')
            or any(k in goal for k in ('roll','pitch'))or abs(float(goal['yaw'])-float(original['yaw']))>1e-8):
        raise ValueError('Original E25B receiver goal required')
    target=next(z for z in a.scene.spec['zones']if z['id']==original['target']);state,_=a.c.snapshot()
    xy=np.asarray(original.get('placement_xy',target['xy']),float)
    if target.get('anchor_object'):
        anchor=state[target['anchor_object']];xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(target.get('anchor_local_center',[0,0,0])))[:2]
    return _finite(xy,(2,)),_axis_rotation([0,0,1],float(original['yaw']))


def rotate_transport_payload(a,name,side,goal,*,measured=None,solver=solve_path):
    """Rotate and translate a genuinely held receiver payload; never release it."""
    require_scope(a)
    if side!='left'or name not in ('spoon','knife','fork'):raise ValueError('Reviewed left E25B receiving hand required')
    xy,desired=_destination(a,name,goal);state,_=a.c.snapshot();tip0=np.asarray(a.tip(side),float)
    obj=next(o for o in a.scene.spec['objects']if o['id']==name)
    half=np.asarray(obj.get('bounds_half_extent',obj['size']),float);center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    def guard():
        state,contacts=a.c.snapshot();body=state[name]
        allowed={frozenset((name,f'{side}_finger{i}'))for i in (1,2)}
        if not body.get('grasp',[False,False])[0]or not allowed.issubset(contacts):raise RuntimeError('E25B interleave requires actual bilateral grip')
        if any(any(row.get('grasp',[False,False])[i]for i in (0,1)if actor!=name or i!=0)for actor,row in state.items()):raise RuntimeError('E25B interleave requires empty peer and one actual payload')
        if any((name in pair or any(f'{side}_finger{i}'in pair for i in (1,2)))and pair not in allowed for pair in contacts):raise RuntimeError('E25B unexpected actual interleave collision')
        q,limits,_=_joints(a,side)
        if not np.isfinite(q).all()or np.any(q<=limits[:,0]+.015)or np.any(q>=limits[:,1]-.015):raise RuntimeError('E25B actual intermediate joint limit approached')
        geometry=a.finger_geometry(side);bottom=float((np.asarray(body['pos'])+np.asarray(body['mat'])@center)[2]-(np.abs(body['mat'])@half)[2])
        if geometry.get('source')!='actual_collision_mesh_current_body_pose'or geometry['lowest_z_task_m']<.815 or bottom<.815:raise RuntimeError('E25B interleave lacks actual table clearance')
        return body,q
    body,q=guard()
    if measured is None:
        from .execution_design_jacobian_reference import capture
        measured=capture(a,a.c,side)
    if np.max(abs(_finite(measured['q'],(7,))-q))>1e-5 or np.linalg.norm(_finite(measured['position'],(3,))-tip0)>.0001:
        raise RuntimeError('E25B measured route model differs from actual starting state')
    angle=_axis_angle(desired@np.asarray(body['mat']).T)[1];paths=[]
    for winding in (angle,angle-2*math.pi):
        targets=route_targets(tip0,a.tcp_rotation_task(side),body['pos'],body['mat'],xy,desired,winding)
        rows=solver(measured,targets);passed=len(rows)==len(targets)and all(x.get('kinematically_reachable')for x in rows)
        paths.append(dict(winding_rad=float(winding),targets=targets,candidates=rows,screen_passed=bool(passed)))
    evidence=dict(object=name,side=side,measured=measured,paths=paths,collision_verified=False,native_passed=False,actuation_performed=False)
    log=a.out/'e25-b-interleaved-transport.private.jsonl'
    def record(row):
        with log.open('a')as stream:stream.write(json.dumps(row,default=lambda x:x.tolist()if isinstance(x,np.ndarray)else x)+'\n')
    choices=[p for p in paths if p['screen_passed']]
    if not choices:record(dict(phase='screen_rejected',**evidence));raise RuntimeError('E25B no connected measured interleaved transport')
    selected=max(choices,key=lambda p:min(r['minimum_joint_margin_rad']for r in p['candidates']));evidence['selected_winding_rad']=selected['winding_rad'];record(dict(phase='screen_selected',**evidence))
    old_stage=a.stage;a.stage='grasped-'+name;labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'));moves=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    def act(token,**kwargs):
        guard();a.act(token,'STILL',**kwargs);body,q=guard();feedback=a.c.action_feedback()['control_feedback'][side]
        record(dict(phase='public_step',active_actions=a.c.steps,measured_joints_rad=q.tolist(),measured_body_position=np.asarray(body['pos']).tolist(),measured_body_rotation=np.asarray(body['mat']).tolist(),feedback=feedback))
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0):raise RuntimeError('E25B interleave public local IK rejected')
    initial_xy=np.asarray(body['pos'])[:2].copy()
    for f in np.linspace(0,1,9)[1:]:
        turn=next(t for t in selected['targets']if t['phase']=='rotate'and abs(t['fraction']-f)<1e-8);rotation=np.asarray(turn['body_rotation']);rotation_tip=np.asarray(a.tip(side)).copy();errors=[]
        for _ in range(40):
            body,_=guard();axis,error=_axis_angle(rotation@np.asarray(body['mat']).T);errors.append(error)
            if error<math.radians(1.2):break
            if np.linalg.norm(np.asarray(a.tip(side))-rotation_tip)>.025:raise RuntimeError('E25B interleave rotation left actual TCP envelope')
            if len(errors)>12 and min(errors[-12:])>min(errors[:-12])-math.radians(.1):raise RuntimeError('E25B actual interleave rotation stopped progressing')
            k=int(np.argmax(abs(axis)));act(labels[k][int(axis[k]<0)],rotation_deg=min(4.,max(.5,abs(math.degrees(error*axis[k])))))
        else:raise RuntimeError('E25B actual interleave rotation did not converge')
        body_xy=initial_xy+(xy-initial_xy)*f;progress=[]
        for _ in range(120):
            body,_=guard();tip=np.asarray(a.tip(side));offset=tip-np.asarray(body['pos']);destination=np.r_[body_xy+offset[:2],tip0[2]];delta=destination-tip
            if np.max(abs(delta))<.002:break
            progress.append(float(np.linalg.norm(delta)))
            if len(progress)>=32 and min(progress[-32:-24])-min(progress[-8:])<.0005:raise RuntimeError('E25B actual interleave translation stopped progressing')
            k=int(np.argmax(abs(delta)));sign=getattr(a,'generated_axis_signs',{}).get(side,{}).get(k,1);token=moves[k][0 if (1 if delta[k]>0 else -1)==sign else 1]
            act(token,mm=min(8.,max(.5,abs(delta[k])*1000)))
        else:raise RuntimeError('E25B actual interleave translation did not converge')
    body,_=guard();error=_axis_angle(desired@np.asarray(body['mat']).T)[1]
    if error>math.radians(1.5)or np.max(abs(np.asarray(body['pos'])[:2]-xy))>.004:raise RuntimeError('E25B original transport endpoint not reached')
    record(dict(phase='transport_complete',actual_original_goal_error_rad=float(error),actual_original_goal_xy_error_m=float(np.linalg.norm(np.asarray(body['pos'])[:2]-xy)),native_passed=False))
    a.control_report.setdefault('e25_b_interleaved_transports',[]).append(dict(object=name,side=side,public_actions_only=True,native_passed=False));a.stage=old_stage
