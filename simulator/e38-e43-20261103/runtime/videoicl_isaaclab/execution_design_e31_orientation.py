"""E31 engineering-only face alignment with a measured swept-volume lift.

All motion uses public actions. Native scoring and body transforms are untouched.
"""
import itertools
import json
import numpy as np
from .execution_design import REVISION_V3
from .author_face_orientation import face_alignment
from .author_orientation import _axis_angle


def swept_radius(position,rotation,half,center,tcp):
    position,rotation,half,center,tcp=map(lambda x:np.asarray(x,float),(position,rotation,half,center,tcp))
    if (position.shape!=(3,)or rotation.shape!=(3,3)or half.shape!=(3,)or center.shape!=(3,)or tcp.shape!=(3,)
            or not np.isfinite(np.r_[position,rotation.ravel(),half,center,tcp]).all()or np.any(half<=0)):
        raise ValueError('Finite measured held-body bounds required')
    points=np.asarray(list(itertools.product((-1.,1.),repeat=3)))*half+center
    return float(np.linalg.norm(points@rotation.T+position-tcp,axis=1).max())


def requested_face(semantic,role,goal=None):
    # Counterexample authors change only their private requested orientation.
    # Keep that request; the native evaluator still sees the original semantic.
    if goal is None:return semantic[role+'_face']
    roll,pitch=[float(goal.get(k,0.))for k in ('roll','pitch')]
    vertical=float(np.cos(roll)*np.cos(pitch))
    if not np.isfinite(vertical)or abs(vertical)<.999:
        raise ValueError('E31 reference requires an explicit upright/inverted face goal')
    return 'up'if vertical>0 else'down'


def align_face(a,name,side,goal=None):
    spec=a.scene.spec
    if not (getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
            and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('Explicit E31 v3 engineering face alignment required')
    from .execution_design_e33_grasp import actual_mesh
    semantic=spec['semantic'];role=next((k for k in ('plate','bowl')if semantic[k]==name),None)
    if role is None:raise ValueError('Declared E31 bowl/plate required')
    obj=next(o for o in spec['objects']if o['id']==name);face=requested_face(semantic,role,goal);up=obj.get('up_axis',[0,0,1])
    def measured():
        state,_=a.c.snapshot()
        if a.carried_payload!=(name,side)or not state[name]['grasp'][0 if side=='left'else 1]:
            raise RuntimeError('E31 face alignment requires actual held payload')
        return state,face_alignment(np.asarray(state[name]['mat']),up,face,tolerance_degrees=8.)
    state,alignment=measured()
    _,contacts=a.c.snapshot()
    if alignment['reached'] and frozenset((name,'table'))not in contacts:
        with (a.out/'e31-face-clearance.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=a.c.steps,object=name,face=face,normal_error_degrees=alignment['normal_error_degrees'],rotation_needed=False,unrequested_yaw_preserved=True))+'\n')
        return
    tcp=np.asarray(a.tip(side));body=state[name]
    radius=swept_radius(body['pos'],body['mat'],obj.get('bounds_half_extent',obj['size']),obj.get('local_bounds_center',[0,0,0]),tcp)
    for part in (a.scene.embodiment.hand,*a.scene.embodiment.fingers):
        radius=max(radius,float(np.linalg.norm(actual_mesh(a,side,part)-tcp,axis=1).max()))
    tops=[.8]
    for other in spec['objects']:
        if other['id']==name:continue
        value=state[other['id']];rot=np.asarray(value['mat']);center=np.asarray(value['pos'])+rot@np.asarray(other.get('local_bounds_center',[0,0,0]))
        tops.append(float(center[2]+(np.abs(rot)@np.asarray(other.get('bounds_half_extent',other['size'])))[2]))
    anchor=tcp.copy();anchor[2]=max(float(tcp[2]),max(tops)+radius+.025)
    with (a.out/'e31-face-clearance.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(step=a.c.steps,object=name,face=face,sweep_radius_m=radius,obstacle_top_z=max(tops),rotation_tcp=anchor.tolist(),native_reachability_verified=False))+'\n')
    a.move_generated({side:anchor},tolerance=.003)
    def clear_of_obstacles():
        values,contacts=a.c.snapshot()
        if any(frozenset((name,other))in contacts for other in ('table',*[o['id']for o in spec['objects']if o['id']!=name])):
            raise RuntimeError('E31 held plate still contacts table or another object before free rotation')
        current=values[name];rot=np.asarray(current['mat']);center=np.asarray(current['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        bottom=float(center[2]-(np.abs(rot)@np.asarray(obj.get('bounds_half_extent',obj['size'])))[2])
        if bottom<max(tops)+.010:
            raise RuntimeError('E31 actual payload bottom lacks measured rotation clearance')
    clear_of_obstacles()
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    from .execution_design_author_rotation import command_degrees,update_loss
    loss=0.
    for _ in range(160):
        state,alignment=measured()
        clear_of_obstacles()
        if alignment['reached']:return
        axis,angle=_axis_angle(alignment['delta_task']);component=int(np.argmax(abs(axis)))
        token=labels[component][int(axis[component]<0)]
        before=np.asarray(state[name]['mat'],float).copy()
        requested=command_degrees(angle*axis[component],loss,maximum=8.)
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=requested)
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback['status']=='blocked' or feedback.get('joint_limit_names'):
            raise RuntimeError('E31 held face rotation refused by actual IK/limit feedback: '+str(feedback.get('reason')))
        loss,_=update_loss(before,a.c.snapshot()[0][name]['mat'],component,axis[component],requested,loss)
        measured()
        clear_of_obstacles()
        # The source constrains the plate face, not an arbitrary air-space
        # TCP anchor. Public rotation may drift; retain real clearance by
        # raising only when the measured payload bottom nears an obstacle.
        value=a.c.snapshot()[0][name];rot=np.asarray(value['mat']);center=np.asarray(value['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        bottom=float(center[2]-(np.abs(rot)@np.asarray(obj.get('bounds_half_extent',obj['size'])))[2])
        if bottom<max(tops)+.055:
            now=np.asarray(a.tip(side));now[2]+=max(tops)+.065-bottom
            a.move_generated({side:now},tolerance=.003)
    raise RuntimeError('E31 public face alignment did not converge')
