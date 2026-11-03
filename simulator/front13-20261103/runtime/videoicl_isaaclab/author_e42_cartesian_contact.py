"""Explicit private short contact translation; no FCL-path certification claim."""
from __future__ import annotations
import numpy as np

CONTACT_STAGES=frozenset(('E42-feedback-push-group','E42-bounded-recontact','E42-seek-real-edge-contact','E42-disengage-completed-group','E42-lift-after-push'))


def contact_tcp_goal(tcp,tool,edge_local,edge_goal):
    tcp=np.asarray(tcp,float);tool=np.asarray(tool,float);edge=np.asarray(edge_local,float);goal=np.asarray(edge_goal,float)
    if tcp.shape!=(4,4)or tool.shape!=(4,4)or edge.shape!=(3,)or goal.shape!=(3,)or not all(np.isfinite(x).all()for x in(tcp,tool,edge,goal)):
        raise ValueError('Measured finite TCP/tool/edge frames required')
    actual=tool[:3,:3]@edge+tool[:3,3];delta=goal-actual
    if np.linalg.norm(delta)>.007:raise ValueError('Contact translation exceeds bounded7mm measured edge displacement')
    target=tcp.copy();target[:3,3]+=delta
    return target,dict(actual_edge_task=actual.tolist(),logical_edge_goal_task=goal.tolist(),translation_task=delta.tolist(),whole_path_FCL_certified=False,orientation='Hold actual measured hand orientation; no source object pose assignments')


def relative_grip_stop(initial,current):
    initial=np.asarray(initial);current=np.asarray(current)
    position=float(np.linalg.norm(current[:3,3]-initial[:3,3]));d=current[:3,:3]@initial[:3,:3].T
    u,_,v=np.linalg.svd(d);d=u@v
    angle=float(np.rad2deg(np.arccos(np.clip((np.trace(d)-1)/2,-1,1))))
    return dict(stop=position>.001 or angle>1.,position_m=position,angle_deg=angle)


def bounded_edge_target(actual,goal):
    actual=np.asarray(actual,float);goal=np.asarray(goal,float);delta=goal-actual;length=float(np.linalg.norm(delta))
    if actual.shape!=(3,)or goal.shape!=(3,)or not np.isfinite(delta).all():raise ValueError('Finite measured source edge goal required')
    return goal.copy()if length<=.006 else actual+delta*(.006/length)
