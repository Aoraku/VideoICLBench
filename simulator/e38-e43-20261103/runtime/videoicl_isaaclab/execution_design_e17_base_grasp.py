"""One measured base-heading grasp target for native A18; no pose writes."""
import numpy as np
from scipy.optimize import linprog
from .execution_design_e24_collision import separation_certificate
from .execution_design_segments_e17_regrasp import NAME,CORNERS,TRIANGLE,_tray,_bounds,_frame
from .realworld_tool_expert import ToolExecutionError


def _finger_clouds(policy):
    from .execution_design_e24_transit import capture_model
    model,_=capture_model(policy,'right')
    return [c['points']for c in model['clouds']if c['name']in('panda_leftfinger','panda_rightfinger')]


def clear_rails_once(clouds,rails,target):
    """One separating-plane translation, at most3mm in negative box X."""
    target=np.asarray(target,float).copy()
    def pairs(point):
        return [(i,j,separation_certificate(c+point,CORNERS*np.asarray(r['size'])+r['pos']))for i,c in enumerate(clouds)for j,r in enumerate(rails)]
    bad=[r for r in pairs(target)if r[2]<.0025]
    if not bad:return target,0.
    if len(bad)!=1 or bad[0][1]!=2:raise ToolExecutionError('Unreviewed A18 finger/rail clearance pattern')
    i,j,gap=bad[0];a=clouds[i]+target;b=CORNERS*np.asarray(rails[j]['size'])+rails[j]['pos']
    fit=linprog([0,0,0,0,-1],A_ub=np.r_[np.c_[a,-np.ones(len(a)),np.zeros(len(a))],np.c_[-b,np.ones(len(b)),np.ones(len(b))]],
        b_ub=np.zeros(len(a)+len(b)),bounds=[(-1,1)]*3+[(None,None)]*2,method='highs')
    if not fit.success or np.linalg.norm(fit.x[:3])<1e-8:raise ToolExecutionError('Actual A18 separating plane unavailable')
    normal=fit.x[:3]/np.linalg.norm(fit.x[:3])
    if normal[0]<.3:raise ToolExecutionError('A18 rail plane does not support the one negative-X adjustment')
    shift=(.0025-gap+.0001)/normal[0]
    if not 0<shift<=.003:raise ToolExecutionError('A18 one analytic rail clearance adjustment exceeds3mm')
    target[0]-=shift
    if any(gap<.0025 for _,_,gap in pairs(target)):raise ToolExecutionError('A18 actual fingers still lack2.5mm rail clearance')
    return target,float(shift)


def planned_target(policy):
    obj,rails,floor=_tray(policy);lo,hi,_=_bounds(policy)
    if abs(float(lo[2]-floor))>.003:raise ToolExecutionError('A18 triangle must actually be flat on the inner floor')
    pos,rotation=policy.frame({'actor':NAME});base,box=_frame(policy);tip=policy.tip('right')
    desired=(pos+rotation@np.array([0.,-.017320508/3.,0.])-base)@box
    clouds=[(np.asarray(points)-tip)@box for points in _finger_clouds(policy)]
    if len(clouds)!=2:raise ToolExecutionError('Actual native two-finger collision meshes required')
    points=np.concatenate(clouds);finger_lo=points.min(0);finger_hi=points.max(0);inner=np.asarray(obj['inner_size'],float)
    limits=[(-inner[i]-finger_lo[i]+.0025,inner[i]-finger_hi[i]-.0025)for i in(0,1)]
    if any(a>=b for a,b in limits):raise ToolExecutionError('A18 actual base-oriented open fingers cannot clear walls')
    for i,(lower,upper)in enumerate(limits):desired[i]=max(lower,min(upper,desired[i]))
    desired[2]=floor+.0025-finger_lo[2];desired,shift=clear_rails_once(clouds,rails,desired)
    if any(not lower<=desired[i]<=upper for i,(lower,upper)in enumerate(limits)):
        raise ToolExecutionError('A18 analytic rail adjustment leaves real wall clearance')
    fingers=policy.a.finger_geometry('right')['fingers']
    axis=(np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m'])@box
    axis[2]=0.;length=float(np.linalg.norm(axis))
    if length<.001:raise ToolExecutionError('Actual A18 open-jaw axis unavailable')
    axis/=length;perpendicular=np.array([-axis[1],axis[0],0.]);pieces=(TRIANGLE@rotation.T+pos-base)@box
    clouds.sort(key=lambda p:float(np.mean(p@axis)))
    jaw_low=float(desired@axis+np.max(clouds[0]@axis));jaw_high=float(desired@axis+np.min(clouds[1]@axis));projection=pieces@axis
    if projection.min()<jaw_low+.0005 or projection.max()>jaw_high-.0005:
        raise ToolExecutionError('Actual triangle is not between base-oriented open jaws')
    strip=(points+desired)@perpendicular;material=pieces@perpendicular
    overlap=min(strip.max(),material.max())-max(strip.min(),material.min())
    if overlap<.003:raise ToolExecutionError('Actual base-oriented finger strip cannot reach triangle material')
    return base+box@desired,dict(target_tcp_box_local_m=desired.tolist(),negative_x_clearance_adjustment_m=shift,
        triangle_material_strip_overlap_m=float(overlap),actual_open_jaw_interval_m=[jaw_low,jaw_high],
        planned_heading='actual original triangle base',minimum_wall_floor_rail_clearance_m=.0025)
