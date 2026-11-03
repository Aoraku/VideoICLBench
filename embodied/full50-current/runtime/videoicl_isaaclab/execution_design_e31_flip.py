"""Private E31 inversion through a screened clear site, using public motion.

The joint continuation only rejects proposed routes. Actual native grip,
clearance, tracking and final body normal are checked during execution.
"""
import json
import math
import numpy as np
from .author_orientation import _axis_angle


def waypoints(measured,plate_position,bowl_position,*,axis_degrees=330.,turn_degrees=178.):
    from scipy.spatial.transform import Rotation
    p=np.asarray(measured['position'],float);r=np.asarray(measured['rotation_task'],float)
    axis=np.array([math.cos(math.radians(axis_degrees)),math.sin(math.radians(axis_degrees)),0.])
    turn=Rotation.from_rotvec(math.radians(turn_degrees)*axis).as_matrix();target=turn@r
    offset=turn@(np.asarray(plate_position,float)-p)
    over=np.r_[np.asarray(bowl_position,float)[:2]-offset[:2],.94]
    low=over.copy();low[2]=.90-offset[2]
    poses=[([*p[:2],1.08],r),([0.,p[1],1.08],r),([0.,-.15,1.08],r),
           ([0.,-.15,1.08],target),(over,target),(low,target)]
    return [dict(position=np.asarray(x,float).tolist(),rotation=y.tolist())for x,y in poses]


def invert_at_clear_site(a,name,side,*,orientation_only=False):
    from .execution_design_jacobian_reference import capture
    from .execution_design_e31_continuation import screen
    from .execution_design_e31_release import check_actual_limits
    from .execution_design_author_rotation import command_degrees,update_loss
    spec=a.scene.spec;semantic=spec['semantic'];index=0 if side=='left'else 1
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and name==semantic['plate']):raise ValueError('Private E31 held-plate inversion required')
    obj=next(o for o in spec['objects']if o['id']==name);up=np.asarray(obj.get('up_axis',[0,0,1]))
    def guard():
        state,contacts=a.c.snapshot();body=state[name]
        if a.carried_payload!=(name,side)or not body['grasp'][index]or any(
                frozenset((name,side+'_finger'+str(i)))not in contacts for i in(1,2)):
            raise RuntimeError('E31 inversion lost real bilateral plate grip')
        if any(frozenset((name,other))in contacts for other in('table',semantic['bowl'])):
            raise RuntimeError('E31 inversion lacks true obstacle clearance')
        bottom=float(body['pos'][2]-(abs(np.asarray(body['mat']))@np.asarray(obj['size']))[2])
        if bottom<.810:raise RuntimeError('E31 inversion lacks actual tabletop clearance')
        check_actual_limits(a,side)
        return body
    state,_=a.c.snapshot();measured=capture(a,a.c,side)
    poses=waypoints(measured,state[name]['pos'],state[semantic['bowl']]['pos'])
    trial=screen(measured,poses[:4]if orientation_only else poses)
    (a.out/'e31-inversion-continuation.private.json').write_text(json.dumps(dict(
        source_actions=a.c.steps,measured=measured,waypoints=poses,result=trial,
        kinematic_screen_only=True,native_positive_claimed=False),indent=2)+'\n')
    if not trial['passed']:raise RuntimeError('E31 full held inversion/return continuation rejected')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    def translate(target):
        target=np.asarray(target,float)
        for _ in range(100):
            guard();now=np.asarray(a.tip(side));delta=target-now
            if np.max(abs(delta))<.003:return
            axis=int(np.argmax(abs(delta)));next_pose=now.copy();next_pose[axis]+=np.clip(delta[axis],-.012,.012)
            a.move_generated({side:next_pose},tolerance=.002)
        raise RuntimeError('E31 clear-site translation failed its bounded measured target')
    def orient(target):
        loss=0.;history=[]
        for _ in range(24):
            guard();current=np.asarray(a.tcp_rotation_task(side));axis,angle=_axis_angle(target@current.T)
            if angle<math.radians(1.):return
            component=int(np.argmax(abs(axis)));token=labels[component][int(axis[component]<0)]
            request=command_degrees(angle*axis[component],loss,maximum=8.)
            a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=request)
            guard();feedback=a.c.action_feedback()['control_feedback'][side]
            if feedback['status']=='blocked'or feedback.get('joint_limit_names'):
                raise RuntimeError('E31 screened inversion rejected by actual IK/limit feedback')
            loss,_=update_loss(current,a.tcp_rotation_task(side),component,axis[component],request,loss)
            history.append(angle)
            if len(history)>=10 and min(history[-10:-5])-min(history[-5:])<math.radians(.2):
                raise RuntimeError('E31 actual clear-site rotation stalled')
        raise RuntimeError('E31 incremental clear-site orientation failed to converge')
    a.stage='checkpoint-e31-clear-inversion-approach'
    for pose in poses[:3]:translate(pose['position'])
    a.stage='checkpoint-e31-clear-inversion-turn'
    for row in trial['samples']:
        if row['phase']==3:
            orient(np.asarray(row['rotation']))
            if np.linalg.norm(np.asarray(a.tip(side))-poses[3]['position'])>.008:
                translate(poses[3]['position'])
    # A rim pinch can remain bilateral while the dish pivots between pads.
    # The actual body, rather than a promised rigid hand offset, determines
    # whether more turning is needed and where the return TCP must go.
    guard()
    return finish_from_actual_plate(a,name,side,orientation_only=orientation_only)


def dense_return_poses(measured,target):
    start=np.asarray(measured['position'],float);target=np.asarray(target,float)
    count=max(1,math.ceil(float(np.linalg.norm(target-start))/.008))
    return [dict(position=(start+(target-start)*i/count).tolist(),rotation=measured['rotation_task'])for i in range(1,count+1)]


def yaw_for_material_release(a,name,side):
    """Change free yaw, then let actual body-centre/material control place it."""
    from scipy.spatial.transform import Rotation
    from .execution_design_jacobian_reference import capture
    from .execution_design_e31_continuation import screen
    from .execution_design_e31_release import check_actual_limits
    from .execution_design_author_rotation import command_degrees,update_loss
    semantic=a.scene.spec['semantic'];index=0 if side=='left'else 1
    if not(getattr(a,'_execution_design_reference_authorized',False)and a.scene.spec['id']=='E31'
           and name==semantic['plate']):raise ValueError('Private E31 material yaw required')
    def guard():
        state,contacts=a.c.snapshot();body=state[name]
        if a.carried_payload!=(name,side)or not body['grasp'][index]or any(
                frozenset((name,side+'_finger'+str(i)))not in contacts for i in(1,2)):
            raise RuntimeError('E31 material yaw lost actual bilateral grip')
        if -float(np.asarray(body['mat'])[2,2])<=.85:raise RuntimeError('E31 material yaw requires an actual down face')
        check_actual_limits(a,side)
        return state
    state=guard();measured=capture(a,a.c,side);start=np.asarray(measured['position']);r=np.asarray(measured['rotation_task'])
    turn=Rotation.from_euler('z',15.,degrees=True).as_matrix();target=turn@r
    offset=turn@(np.asarray(state[name]['pos'])-start)
    over=np.r_[np.asarray(state[semantic['bowl']]['pos'])[:2]-offset[:2],start[2]]
    low=over.copy();low[2]=.90-offset[2]
    poses=[dict(position=start.tolist(),rotation=target.tolist())]
    for dst in(over,low):
        begin=np.asarray(poses[-1]['position']);count=max(1,math.ceil(float(np.linalg.norm(dst-begin))/.008))
        poses.extend(dict(position=(begin+(dst-begin)*i/count).tolist(),rotation=target.tolist())for i in range(1,count+1))
    result=screen(measured,poses)
    (a.out/'e31-material-yaw-screen.private.json').write_text(json.dumps(dict(measured=measured,poses=poses,result=result),indent=2)+'\n')
    if not result['passed']:raise RuntimeError('E31 material yaw/XY/lower route rejected')
    loss=0.;a.stage='checkpoint-e31-material-free-yaw'
    for _ in range(16):
        guard();before=np.asarray(a.tcp_rotation_task(side));axis,angle=_axis_angle(target@before.T)
        if angle<math.radians(1.):return
        i=int(np.argmax(abs(axis)));labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        token=labels[i][int(axis[i]<0)];requested=command_degrees(angle*axis[i],loss,maximum=8.)
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=requested)
        guard();feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback['status']=='blocked'or feedback.get('joint_limit_names'):raise RuntimeError('E31 material yaw refused by native IK/limit')
        loss,_=update_loss(before,a.tcp_rotation_task(side),i,axis[i],requested,loss)
    raise RuntimeError('E31 material free-yaw orientation did not converge')


def finish_from_actual_plate(a,name,side,*,only_return=False,orientation_only=False):
    """Finish a measured partial inversion, tracking the body rather than hand."""
    from .author_face_orientation import face_alignment
    from .execution_design_jacobian_reference import capture
    from .execution_design_e31_continuation import screen
    from .execution_design_e31_release import check_actual_limits
    from .execution_design_author_rotation import command_degrees,update_loss
    spec=a.scene.spec;semantic=spec['semantic'];index=0 if side=='left'else 1
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and name==semantic['plate']):raise ValueError('Private measured E31 finish required')
    obj=next(o for o in spec['objects']if o['id']==name);up=np.asarray(obj.get('up_axis',[0,0,1]))
    def body():
        state,contacts=a.c.snapshot();value=state[name]
        if a.carried_payload!=(name,side)or not value['grasp'][index]or any(
                frozenset((name,side+'_finger'+str(i)))not in contacts for i in(1,2)):
            raise RuntimeError('E31 measured finish lost actual bilateral grip')
        if any(frozenset((name,other))in contacts for other in('table',semantic['bowl'])):
            raise RuntimeError('E31 measured finish lacks free rotation clearance')
        check_actual_limits(a,side)
        return value
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    loss=0.;history=[];a.stage='checkpoint-e31-actual-plate-correction'
    for _ in range(50):
        value=body();before=np.asarray(value['mat']).copy();normal=before@up
        if -float(normal[2])>(.85 if only_return or orientation_only else .90):break
        if only_return:raise RuntimeError('E31 return-only checkpoint is not actually inverted')
        alignment=face_alignment(before,up,'down',tolerance_degrees=1.)
        axis,angle=_axis_angle(alignment['delta_task']);i=int(np.argmax(abs(axis)))
        requested=command_degrees(angle*axis[i],loss,maximum=8.)
        token=labels[i][int(axis[i]<0)]
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=requested)
        value=body();feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback['status']=='blocked'or feedback.get('joint_limit_names'):
            raise RuntimeError('E31 actual plate correction hit real IK/limit feedback')
        loss,actual=update_loss(before,value['mat'],i,axis[i],requested,loss)
        history.append(-float((np.asarray(value['mat'])@up)[2]))
        with(a.out/'e31-actual-plate-correction.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=a.c.steps,normal=(np.asarray(value['mat'])@up).tolist(),requested_degrees=requested,actual_component_degrees=actual))+'\n')
        if len(history)>=10 and max(history[-5:])-max(history[-10:-5])<.003:
            raise RuntimeError('E31 body-normal correction stalled despite hand rotation')
    else:raise RuntimeError('E31 measured plate inversion correction action bound')
    if orientation_only:
        return dict(actual_normal=(np.asarray(body()['mat'])@up).tolist(),native_positive_claimed=False)
    state,_=a.c.snapshot();offset=np.asarray(state[name]['pos'])-np.asarray(a.tip(side))
    over=np.r_[np.asarray(state[semantic['bowl']]['pos'])[:2]-offset[:2],.94]
    measured=capture(a,a.c,side)
    result=screen(measured,dense_return_poses(measured,over))
    (a.out/'e31-actual-inverted-return-screen.private.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:raise RuntimeError('E31 actual corrected plate return route rejected')
    a.stage='checkpoint-e31-actual-inverted-return'
    for _ in range(100):
        value=body()
        if -float((np.asarray(value['mat'])@up)[2])<=.85:
            raise RuntimeError('E31 actual down face lost during return')
        now=np.asarray(a.tip(side));delta=over-now;distance=float(np.linalg.norm(delta))
        # These are free-space intermediate targets. A 4mm author envelope
        # avoids chasing a 2mm last-axis residual that may be locally blocked;
        # real plate centring/gap/contact are still measured by the release.
        if distance<.006:break
        a.move_generated({side:now+delta*min(1.,.008/distance)},tolerance=.004)
    else:raise RuntimeError('E31 actual corrected return target did not converge')
    return dict(actual_normal=(np.asarray(body()['mat'])@up).tolist(),native_positive_claimed=False)
