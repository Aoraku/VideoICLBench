"""E31 plate reference pickup: follow a real rim pivot through public actions.

This is an engineering author, never an evaluator or model-action controller.
A table-supported plate can pivot at its edge during a vertical pinch lift.
Follow the measured change before the rim slides out of the finger pads.
All body transforms, contacts and grasp flags are read-only observations.
"""
import json
import numpy as np
from .execution_design import REVISION_V3
from .author_orientation import _axis_angle, _quaternion_matrix, _numpy, _rotation


def relative_grasp_delta(initial_object,initial_hand,current_object,current_hand):
    ro,rh,co,ch=[_rotation(x,'measured plate/hand') for x in
                 (initial_object,initial_hand,current_object,current_hand)]
    return co@ro.T@rh@ch.T


def contact_point(position,rotation,initial_local_tcp):
    rotation=_rotation(rotation,'measured plate contact frame')
    position=np.asarray(position,float);local=np.asarray(initial_local_tcp,float)
    if position.shape!=(3,)or local.shape!=(3,)or not np.isfinite(np.r_[position,local]).all():
        raise ValueError('Finite measured plate contact point required')
    return position+rotation@local


def reseat_waypoint(current,desired):
    current=np.asarray(current,float);desired=np.asarray(desired,float)
    if current.shape!=(3,)or desired.shape!=(3,)or not np.isfinite(np.r_[current,desired]).all():
        raise ValueError('Finite measured TCP/contact positions required')
    drift=desired-current
    axis=2 if abs(drift[2])>.001 else int(np.argmax(abs(drift[:2])))
    goal=current.copy();goal[axis]+=float(np.clip(drift[axis],-.002,.002))
    return goal


def hand_rotation(a,side):
    robot=a.scene.robots[side]
    ids=robot.find_bodies(a.scene.embodiment.hand)[0]
    if len(ids)!=1:raise RuntimeError('Unique real hand body required for E31 pickup')
    world=_quaternion_matrix(_numpy(robot.data.body_quat_w[0,int(ids[0])]))
    return np.asarray(a.scene.layout.task_rotation).T@world


def lift_plate(a,name,side,target_z):
    spec=a.scene.spec
    if not (getattr(a,'_execution_design_reference_authorized',False)
            and spec.get('id')=='E31'
            and spec.get('execution_design',{}).get('revision')==REVISION_V3
            and name==spec['semantic']['plate'] and side in ('left','right')):
        raise ValueError('Explicit E31 v3 engineering plate pickup required')
    if getattr(a,'smooth',False):raise ValueError('Public discrete E31 plate pickup required')
    target_z=float(target_z)
    if not np.isfinite(target_z) or not .82<=target_z<=1.20:
        raise ValueError('Finite reviewed E31 lift height required')
    index=0 if side=='left' else 1
    fingers=[frozenset((name,side+'_finger'+str(i)))for i in (1,2)]
    obj=next(o for o in spec['objects']if o['id']==name)
    def measured():
        state,contacts=a.c.snapshot();body=state[name]
        if a.carried_payload!=(name,side) or not body['grasp'][index]:
            raise RuntimeError('E31 pivot pickup lost actual plate grasp')
        if not all(pair in contacts for pair in fingers):
            raise RuntimeError('E31 pivot pickup requires both actual finger contacts')
        others={o['id'] for o in spec['objects']if o['id']!=name}
        if any(frozenset((name,other)) in contacts for other in others):
            raise RuntimeError('E31 pickup plate collided with another task object')
        return body,contacts
    body,contacts=measured();initial_object=np.array(body['mat'],copy=True)
    initial_hand=hand_rotation(a,side);anchor=np.array(a.tip(side),copy=True)
    initial_local_tcp=initial_object.T@(anchor-np.asarray(body['pos']))
    # The original clearance assumes a level plate. A pivoting plate needs its
    # full measured rim-to-body radius above the table before face alignment.
    from .execution_design_e31_orientation import swept_radius
    radius=swept_radius(body['pos'],body['mat'],obj.get('bounds_half_extent',obj['size']),
                        obj.get('local_bounds_center',[0,0,0]),anchor)
    target_z=max(target_z,.8+radius+.025)
    if target_z>1.20:raise RuntimeError('E31 actual plate sweep exceeds reviewed lift workspace')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    def evidence(body,contacts,error,kind):
        with (a.out/'e31-plate-pivot-pickup.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=a.c.steps,kind=kind,object=name,side=side,
                tcp=np.asarray(a.tip(side)).tolist(),plate_position=np.asarray(body['pos']).tolist(),
                plate_rotation=np.asarray(body['mat']).tolist(),relative_grasp_error_degrees=float(error),
                two_finger_contact=True,table_contact=frozenset((name,'table'))in contacts,
                target_z=target_z,initial_local_tcp=initial_local_tcp.tolist(),
                current_local_tcp=(np.asarray(body['mat']).T@(np.asarray(a.tip(side))-body['pos'])).tolist(),
                native_score_modified=False))+'\n')
    if getattr(a,'_e31_edge_grasp',None)==(name,side):
        # Opposed pads now pinch the exposed upper/lower rim surfaces. Lift
        # directly with real grip/contact checks; do not chase rim-slip poses.
        for _ in range(100):
            body,contacts=measured();evidence(body,contacts,0.,'edge_loaded_lift')
            tip=np.asarray(a.tip(side))
            if tip[2]>=target_z-.003:
                if frozenset((name,'table'))in contacts:
                    raise RuntimeError('Edge-gripped plate still contacts table at clearance')
                return
            a.move_generated({side:[*tip[:2],min(target_z,float(tip[2])+.005)]},tolerance=.0015)
        raise RuntimeError('Bounded edge plate lift did not reach clearance')
    for _ in range(110):
        body,contacts=measured()
        delta=relative_grasp_delta(initial_object,initial_hand,body['mat'],hand_rotation(a,side))
        _,angle=_axis_angle(delta);error=float(np.degrees(angle))
        evidence(body,contacts,error,'before_lift')
        if error>18.:raise RuntimeError('E31 measured rim slip exceeded bounded follow window')
        # Real v3 failure retained angular alignment but pulled the contact
        # 8.55mm out of the plate normal and2.98mm toward its outer edge.
        # Re-seat small measured translational slip while the table still
        # supports the plate; never chase a rigid airborne contact offset.
        for _seat in range(3):
            if frozenset((name,'table'))not in contacts:break
            desired=contact_point(body['pos'],body['mat'],initial_local_tcp)
            current=np.asarray(a.tip(side));drift=desired-current
            distance=float(np.linalg.norm(drift))
            if distance<=.0015:break
            if distance>.012:raise RuntimeError('E31 measured rim translation exceeds bounded re-seat window')
            # Lower toward the captured contact before lateral alignment;
            # lateral-only correction would push the pinch farther off the rim.
            goal=reseat_waypoint(current,desired)
            a.move_generated({side:goal},tolerance=.0008)
            body,contacts=measured()
            after=float(np.linalg.norm(contact_point(body['pos'],body['mat'],initial_local_tcp)-a.tip(side)))
            evidence(body,contacts,error,'contact_point_reseat')
            if after>=distance-.0001:break
        anchor=np.array(a.tip(side),copy=True)
        if float(a.tip(side)[2])>=target_z-.003:
            rot=np.asarray(body['mat']);center=np.asarray(body['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
            bottom=float(center[2]-(np.abs(rot)@np.asarray(obj.get('bounds_half_extent',obj['size'])))[2])
            if frozenset((name,'table'))in contacts or bottom<.810:
                raise RuntimeError('E31 plate is not actually clear of the table after pickup')
            return
        # Bound each loaded lift before checking the real plate and finger poses.
        next_z=min(target_z,float(a.tip(side)[2])+.004)
        a.move_generated({side:[*anchor[:2],next_z]},tolerance=.0015)
        body,contacts=measured()
        # While the table supports the plate, the wrist follows its real pivot.
        # Once airborne, a small fixed contact-angle residual is allowed: turning
        # a rigidly held object cannot erase that residual and must not loop.
        for correction in range(5):
            delta=relative_grasp_delta(initial_object,initial_hand,body['mat'],hand_rotation(a,side))
            axis,angle=_axis_angle(delta);error=float(np.degrees(angle))
            evidence(body,contacts,error,'follow')
            if error>18.:raise RuntimeError('E31 measured rim slip exceeded bounded follow window')
            if error<=2.:break
            if frozenset((name,'table'))not in contacts:
                # Do not chase a rigid airborne contact offset: rotating the
                # hand also rotates its held plate, leaving that offset equal.
                # Repeating it on each lift would spin the payload needlessly.
                if error>12.:raise RuntimeError('E31 airborne rim slip exceeds safe contact offset')
                break
            component=int(np.argmax(abs(axis)));token=labels[component][int(axis[component]<0)]
            old_z=float(a.tip(side)[2])
            a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',
                  rotation_deg=min(3.,max(.5,abs(float(np.degrees(angle*axis[component]))))))
            body,contacts=measured()
            if np.max(abs(np.asarray(a.tip(side))-np.r_[anchor[:2],old_z]))>.003:
                a.move_generated({side:[*anchor[:2],old_z]},tolerance=.002)
                body,contacts=measured()
            remaining=relative_grasp_delta(initial_object,initial_hand,body['mat'],hand_rotation(a,side))
            after=float(np.degrees(_axis_angle(remaining)[1]))
            if after>=error-.25:
                # The plate may have begun moving rigidly with the hand while
                # one edge still touches the table. Do not repeat rotations
                # which fail to reduce the measured contact-angle error.
                evidence(body,contacts,after,'follow_did_not_reduce_contact_offset')
                break
    raise RuntimeError('E31 bounded public plate pickup did not reach clearance')
