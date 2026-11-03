"""E25 engineering hand switches use achieved clearance, without home resets."""
import numpy as np
from .execution_design_e25_parking import _scope
from .execution_design_segments_e19_e25 import _empty


def distance_from_objects(a,side):
    state,_=_empty(a);geometry=a.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':
        raise RuntimeError('Actual E25 finger mesh clearance required')
    objects={o['id']:o for o in a.scene.spec['objects']};distance=float('inf')
    for finger in geometry['fingers']:
        lo=np.asarray(finger['aabb_min_task_m']);hi=np.asarray(finger['aabb_max_task_m'])
        for name,body in state.items():
            obj=objects[name];r=np.asarray(body['mat']);center=np.asarray(body['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]))
            half=np.abs(r)@np.asarray(obj.get('bounds_half_extent',obj['size']))
            gap=np.maximum(0.,np.maximum(center-half-hi,lo-center-half))
            distance=min(distance,float(np.linalg.norm(gap)))
    return distance


def withdraw_released(a,side):
    _scope(a);_empty(a)
    # About50mm withdrawal, with measured30mm clearance sufficient for a
    # released hand already outside every object's collision bounds.
    before=a.c.steps
    for _ in range(10):
        distance=distance_from_objects(a,side)
        if distance>=.030:
            a.control_report.setdefault('e25_functional_hand_switches',[]).append(dict(
                side=side,actual_object_clearance_m=distance,actions=a.c.steps-before,
                exact_home_or_neutral_wrist_required=False))
            return
        positive=getattr(a,'generated_axis_signs',{}).get(side,{}).get(2,1)
        token='UP'if positive>0 else'DOWN'
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm=5.)
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback.get('status')=='blocked':raise RuntimeError('Actual empty E25 withdrawal blocked')
    raise RuntimeError('Released E25 hand has not cleared actual objects')


def prepare_next_pickup(a,side,name):
    """Orient a released tilted palm before translating toward its next grasp."""
    _scope(a);state,contacts=_empty(a)
    if a.scene.spec.get('variant')not in('A','B'):return
    from .author_orientation import panda_downward_grasp_delta,_axis_angle
    import math
    rotation=np.asarray(a.tcp_rotation_task(side),float)
    # A working downward palm already has a usable approach. There is no
    # neutral/home requirement after a release.
    if float(rotation[:,2]@np.array([0.,0.,-1.]))>=math.cos(math.radians(15)):return
    obj=next(o for o in a.scene.spec['objects']if o['id']==name)
    desired=np.asarray(state[name]['mat'])@np.asarray(obj['grasp_axis_local'])
    initial=np.asarray(a.tip(side),float);errors=[]
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    a.stage='e25-next-pickup-empty-orientation-'+name
    for _ in range(80):
        state,contacts=_empty(a);geometry=a.finger_geometry(side)
        if (geometry.get('source')!='actual_collision_mesh_current_body_pose'
                or geometry['lowest_z_task_m']<.825
                or np.linalg.norm(np.asarray(a.tip(side))-initial)>.025
                or distance_from_objects(a,side)<.010):
            raise RuntimeError('E25 next pickup lacks actual empty-palm rotation clearance')
        fingers=geometry['fingers'];jaw=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
        axis,angle=_axis_angle(panda_downward_grasp_delta(a.tcp_rotation_task(side),jaw,desired))
        if angle<math.radians(5):return
        errors.append(angle)
        if len(errors)>=4 and errors[-4]-min(errors[-3:])<math.radians(.1):
            raise RuntimeError('E25 next pickup public orientation stopped progressing')
        k=int(np.argmax(abs(axis)));token=labels[k][int(axis[k]<0)]
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',
              rotation_deg=min(10.,max(1.,abs(math.degrees(angle*axis[k])))))
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback.get('status')=='blocked'or feedback.get('consecutive_ik_refusals',0):
            raise RuntimeError('E25 next pickup public empty-palm IK blocked')
    raise RuntimeError('E25 next pickup empty-palm orientation exhausted')
