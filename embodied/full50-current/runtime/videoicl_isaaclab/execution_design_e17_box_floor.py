"""Actual flat A33 triangle: pinch across the tray, between real dividers."""
import numpy as np
from .execution_design_segments_e17_regrasp import TRIANGLE,CORNERS,_tray,_frame
from .execution_design_e17_base_grasp import _finger_clouds
from .execution_design_e24_collision import separation_certificate
from .realworld_tool_expert import ToolExecutionError


def planned_target(p):
    obj,rails,floor=_tray(p);base,box=_frame(p);pos,rot=p.frame({'actor':'green_triangle'});material=(TRIANGLE@rot.T+pos-base)@box;tip=p.tip('right')
    if abs(float(material[:,2].min()-floor))>.003:raise ToolExecutionError('Actual triangle has not reached the real tray floor')
    fingers=p.a.finger_geometry('right')['fingers'];axis=(np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m'])@box;axis/=np.linalg.norm(axis)
    if abs(axis[0])<.99 or abs(axis[2])>.02:raise ToolExecutionError('Actual box-X floor pinch axis required')
    clouds=[(np.asarray(c)-tip)@box for c in _finger_clouds(p)];swept=[]
    for c in clouds:
        sign=1 if np.mean(c@axis)>0 else -1;swept.append(np.r_[c,c-sign*.04*axis])
    points=np.concatenate(swept);low=points.min(0);high=points.max(0);desired=(pos+rot@np.array([0,-.017320508/3,0])-base)@box;inner=np.asarray(obj['inner_size'])
    lower=max([float(-inner[1])]+[r['pos'][1]+r['size'][1]for r in rails if r['pos'][1]+r['size'][1]<desired[1]])
    upper=min([float(inner[1])]+[r['pos'][1]-r['size'][1]for r in rails if r['pos'][1]-r['size'][1]>desired[1]])
    limits=[(-inner[0]-low[0]+.0026,inner[0]-high[0]-.0026),(lower-low[1]+.0026,upper-high[1]-.0026)]
    if any(a>=b for a,b in limits):raise ToolExecutionError('Actual full-closing fingers cannot fit the source floor bay')
    target=desired.copy()
    for i,(a,b)in enumerate(limits):target[i]=max(a,min(b,target[i]))
    target[2]=floor+.0026-low[2]
    minimum=min(separation_certificate(c+target,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)
    if minimum<.0025:raise ToolExecutionError('Actual box-X full-closing sweep lacks divider clearance')
    clouds.sort(key=lambda c:float(np.mean(c@axis)));jawlo=float(target@axis+np.max(clouds[0]@axis));jawhi=float(target@axis+np.min(clouds[1]@axis));projection=material@axis
    if projection.min()<jawlo+.0005 or projection.max()>jawhi-.0005:raise ToolExecutionError('Actual floor triangle is outside the open jaws')
    transverse=np.array([-axis[1],axis[0],0]);strip=(np.concatenate(clouds)+target)@transverse;piece=material@transverse
    if min(strip.max(),piece.max())-max(strip.min(),piece.min())<.003:raise ToolExecutionError('Actual box-axis pads miss the floor triangle')
    return base+box@target,dict(target_tcp_box_local_m=target.tolist(),source_floor_bay_y_m=[lower,upper],minimum_actual_closing_rail_clearance_m=minimum)


def acquire(p,ref,side):
    if p.task!='E17'or p.variant!='A'or side!='right'or ref['actor']!='green_triangle':raise ToolExecutionError('Explicit actual A33 floor triangle required')
    if any(row['grasp'][1]for row in p.snapshot()[0].values()):raise ToolExecutionError('A33 requires actual empty hand')
    _,box=_frame(p);p.stage('local-e17a33-align-actual-box-x-floor-pinch');p.align_empty_chip_axis(side,box[:,0])
    target,evidence=planned_target(p);p.operations.append(dict(operation='actual_box_axis_floor_pinch',**evidence));height=max(float(p.tip(side)[2]),float(target[2])+.030)
    p.move(side,[*p.tip(side)[:2],height]);p.move(side,[*target[:2],height]);p.move(side,target,tolerance=.0005)
    from .execution_design_e20_reference import finish_chip_grip
    from .execution_design_segments_e17_e20 import _held_with_contacts
    finish_chip_grip(p,ref,side);_held_with_contacts(p,'green_triangle',side)
