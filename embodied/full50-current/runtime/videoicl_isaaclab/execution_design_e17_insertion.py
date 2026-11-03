"""E17 v3 engineering-only measured south ingress for the derived stand.

The route was screened from native action510 with the source URDF and actual
collision meshes, including opened fingers and the idle arm. That establishes
a candidate, not a native success. All movement remains public recorded action.
"""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e17_stand import descriptor


def front_lower_slot(author, index, count):
    if count > 2 or not 0 <= index < count:
        raise ToolExecutionError('E17 reviewed front-row lower capacity exceeded')
    return [-.044 + .088 * index, -.044, .016795216]


def _reviewed_frame(author, actor, target_local):
    d=author.spec.get('execution_design',{})
    if (author.task!='E17' or not author.a.control_report.get('engineering_reference_only')
            or d.get('condition')!='I' or author.objects[actor].get('e17_stand_geometry')!=descriptor()):
        raise ToolExecutionError('E17 reviewed derived-stand I engineering required')
    xy=np.asarray(target_local,float)[:2]
    if not any(np.allclose(xy,[x,-.044],atol=1e-6)for x in (-.044,.044)):
        raise ToolExecutionError('E17 lower slot outside screened corridor')
    base,stand_rotation=author.frame({'actor':actor})
    base=np.asarray(base,float).copy();stand_rotation=np.asarray(stand_rotation,float).copy()
    if np.linalg.norm(stand_rotation-np.eye(3))>.025:
        raise ToolExecutionError('E17 screened stand orientation differs from initial layout')
    return base,stand_rotation


def place_lower(author, name, actor, target_local):
    before=_reviewed_frame(author,actor,target_local)
    ref,side=author.pickup(name,side_override='right')
    return place_held_lower(author,name,actor,target_local,ref,side,expected_stand_frame=before)


def place_held_lower(author,name,actor,target_local,ref,side,*,expected_stand_frame=None):
    """Continue a real held piece; no pickup/release/reset before insertion."""
    base,stand_rotation=_reviewed_frame(author,actor,target_local)
    if expected_stand_frame is not None:
        base,stand_rotation=(np.asarray(v,float).copy()for v in expected_stand_frame)
    if side!='right' or ref.get('actor')!=name:
        raise ToolExecutionError('E17 screened insertion requires actual right-hand payload')
    author.require_held(ref,side)
    xy=np.asarray(target_local,float)[:2]
    control={'actor':name,'local':[0.,0.,0.]}
    def guard():
        author.require_held(ref,side)
        position,rotation=author.frame({'actor':actor})
        if np.linalg.norm(np.asarray(position)-base)>.005 or np.linalg.norm(np.asarray(rotation)-stand_rotation)>.12:
            raise ToolExecutionError('E17 actual stand moved during lower insertion')
        if getattr(author.a,'stage','')=='workflow-measured-south-insert-'+name:
            from .execution_design_segments_e17_upper import _check
            _check(author,payload=name,carrying=True)
    # Same physical stand-frame corridor as the continuous mesh screen.
    rz=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    c,s=math.cos(-math.pi/3),math.sin(-math.pi/3)
    desired=stand_rotation@rz@np.array([[c,0.,s],[0.,1.,0.],[-s,0.,c]])
    half=np.asarray(author.objects[name]['size'],float)
    height=.016795216+float(np.abs((stand_rotation.T@desired)[2])@half)+.040
    goal=base+stand_rotation@np.r_[xy,height]
    entry=base+stand_rotation@np.array([xy[0],-.230,height])
    high=float(base[2]+.320)
    author.stage('workflow-measured-south-carry-'+name)
    author.move_point(side,control,[*author.point(control)[:2],high],guard,tolerance=.006)
    author.move_point(side,control,[*entry[:2],high],guard,tolerance=.006)
    # Refine actual pose beyond the legacy four-degree orientation tolerance.
    from .author_orientation import _axis_angle
    for _ in range(180):
        guard();current=author.frame({'actor':name})[1]
        axis,angle=_axis_angle(desired@np.asarray(current).T)
        if angle<math.radians(5.):break
        index=int(np.argmax(np.abs(axis)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[index][int(axis[index]<0)]
        author.act(side,token,degrees=min(2.,abs(math.degrees(angle*axis[index]))))
    else:raise ToolExecutionError('E17 measured insertion orientation did not converge')
    author.move_point(side,control,[*entry[:2],high],guard,tolerance=.006)
    author.stage('workflow-measured-south-insert-'+name)
    author.move_point(side,control,entry,guard,tolerance=.006)
    author.move_point(side,control,goal,guard,tolerance=.006)
    tip_at_release=np.asarray(author.tip(side),float).copy()
    author.release(ref,side)
    author.wait(1)
    if not author.contact(name,actor):
        raise ToolExecutionError('E17 released lower piece lacks real stand support')
    # Empty full-open fingers leave on the same screened low corridor.
    author.move(side,tip_at_release+entry-goal)
    author.move(side,tip_at_release+np.r_[entry[:2],high]-goal)
    author.wait(1)
    if not author.contact(name,actor) or any(author.snapshot()[0][name]['grasp']):
        raise ToolExecutionError('E17 lower support did not survive empty-hand retreat')

