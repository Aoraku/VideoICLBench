"""Measured material-point tracking for isolated E42/43/45/46 references.

Only public actions are issued. Native grasp guards and endpoint tolerance
remain mandatory; a TCP waypoint is never used as a proxy for material arrival.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def move_material(author, side, ref, target, guard=None, follower=None, tolerance=.002):
    target=np.asarray(target,dtype=float)
    if target.shape!=(3,) or not np.isfinite(target).all() or not np.isfinite(tolerance) or tolerance<=0:
        raise ToolExecutionError('Invalid tool material target')
    if side not in ('left','right') or follower not in (None,'left','right'):
        raise ToolExecutionError('Invalid tool material hand')
    history=[];limit_streak=0
    for iteration in range(600):
        if guard:guard()
        point=np.asarray(author.point(ref),dtype=float)
        if point.shape!=(3,) or not np.isfinite(point).all():
            raise ToolExecutionError('Invalid measured tool material point')
        error=target-point;residual=float(np.max(np.abs(error)))
        out=getattr(author.a,'out',None)
        if out is not None:
            with (out/'tool-material-feedback.private.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(stage=author.a.stage,step=author.c.steps,
                    point=point.tolist(),target=target.tolist(),residual_m=residual,
                    tcp=author.tip(side).tolist(),iteration=iteration))+'\n')
        if residual<=tolerance:return
        history.append(residual)
        feedback=(author.c.action_feedback().get('control_feedback',{}).get(side,{})
                  if callable(getattr(author.c,'action_feedback',None)) else {})
        limit_streak=limit_streak+1 if feedback.get('joint_limit_names') else 0
        if limit_streak>=12 and len(history)>=13 and history[-13]-min(history[-12:])<.0025:
            raise ToolExecutionError('Actual tool joint limit without material progress: '+
                str(feedback['joint_limit_names'])+' residual_m='+str(residual))
        if len(history)>=25 and history[-25]-min(history[-24:])<.0003:
            raise ToolExecutionError('Actual tool material stalled: '+author.a.stage+' residual_m='+str(residual))
        axis=int(np.argmax(np.abs(error)))
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        author.act(side,token,mm=min(abs(float(error[axis]))*1000.,author.max_mm),follower=follower)
    raise ToolExecutionError('Actual tool material action bound exhausted')


def guide_intercept_outside_launcher(point,incoming,launcher_position,launcher_rotation,launcher_half,guide_half,clearance=.01):
    """Put the whole yawing guide beyond the measured launcher projection.

    A gravity-released ball continues on the table to this point; its source
    release and target region are unchanged. Native crossing still must occur.
    """
    point=np.asarray(point,float).copy();direction=np.asarray(incoming,float).copy();direction[2]=0
    if direction.shape!=(3,) or not np.isfinite(direction).all() or np.linalg.norm(direction)<1e-9:
        raise ToolExecutionError('Invalid guide incoming direction')
    direction/=np.linalg.norm(direction)
    center=np.asarray(launcher_position,float);rotation=np.asarray(launcher_rotation,float)
    half=np.asarray(launcher_half,float);guide=np.asarray(guide_half,float)
    if any(not np.isfinite(x).all()for x in (point,center,rotation,half,guide)) or np.any(half<=0) or np.any(guide<=0):
        raise ToolExecutionError('Invalid guide obstacle geometry')
    support=float(np.abs(rotation.T@direction)@half)
    # Rotation about vertical is chosen afterwards. XY circumradius safely
    # bounds every candidate yaw, rather than using the unrotated long axis.
    required=support+float(np.linalg.norm(guide[:2]))+clearance
    progress=float((point-center)@direction)
    if progress<required:point+=direction*(required-progress)
    return point


def handle_level_push_rotation(outward_local, direction_task):
    """Yaw the source horizontal handle; do not flatten its sloped blade.

    The source spatula has a blade raised relative to the grasp when its plane
    is artificially leveled. At ball height this sends the hand below the table.
    """
    a=np.asarray(outward_local,float).copy();b=np.asarray(direction_task,float).copy()
    if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ToolExecutionError('Invalid source spatula push direction')
    if np.linalg.norm(a[:2])<1e-9 or np.linalg.norm(b[:2])<1e-9:
        raise ToolExecutionError('Missing source spatula horizontal push direction')
    angle=np.arctan2(b[1],b[0])-np.arctan2(a[1],a[0]);c=np.cos(angle);s=np.sin(angle)
    return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
