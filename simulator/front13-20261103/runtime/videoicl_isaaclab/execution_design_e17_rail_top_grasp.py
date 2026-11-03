"""Pinch the actual tilted triangle section above the source rail tops."""
import numpy as np
from .execution_design_segments_e17_regrasp import TRIANGLE,CORNERS,_tray,_frame
from .execution_design_segments_e17 import TRIANGLE_SHA
from .execution_design_e17_tilted_grasp import _finger_state
from .execution_design_e24_collision import separation_certificate
from .realworld_tool_expert import ToolExecutionError

EDGES=((0,1),(2,3),(4,5),(0,2),(2,4),(4,0),(1,3),(3,5),(5,1))
SQUARE_SHA='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'


def material_vertices(obj):
    sha=obj.get('source_asset',{}).get('sha256')
    if sha==TRIANGLE_SHA:return TRIANGLE,EDGES
    if sha==SQUARE_SHA:
        edges=tuple((i,j)for i,a in enumerate(CORNERS)for j,b in enumerate(CORNERS)if i<j and np.count_nonzero(a!=b)==1)
        return CORNERS*np.asarray(obj['size']),edges
    raise ToolExecutionError('Original E17 source chip geometry required')


def horizontal_slice(points,height,edges=EDGES):
    result=[]
    for i,j in edges:
        a=points[i];b=points[j];da=float(a[2]-height);db=float(b[2]-height)
        if abs(da)<1e-10:result.append(a.copy())
        if da*db<0:result.append(a+(b-a)*(-da/(db-da)))
    if len(result)<3:raise ToolExecutionError('Measured triangle has no above-rail gripping section')
    return np.asarray(result)


def planned_target(policy,name):
    obj,rails,_=_tray(policy);base,box=_frame(policy);tip=policy.tip('right');pos,rotation=policy.frame({'actor':name})
    clouds,axis=_finger_state(policy);axis=axis@box
    if abs(float(axis[2]))>.1:raise ToolExecutionError('Actual rail-top grip axis exceeds reviewed5.7degree tilt')
    local=[(np.asarray(c)-tip)@box for c in clouds];swept=[]
    for c in local:
        sign=1 if float(np.mean(c@axis))>0 else-1;swept.append(np.r_[c,c-sign*.04*axis])
    envelope=np.concatenate(swept);lo=envelope.min(0);hi=envelope.max(0);rail_top=max(r['pos'][2]+r['size'][2]for r in rails)
    vertices,edges=material_vertices(policy.objects[name])
    height=rail_top+.0026-lo[2];material=(vertices@rotation.T+pos-base)@box
    material_top=float(material[:,2].max());toe=rail_top+.0026
    if material_top-toe<.003:raise ToolExecutionError('Measured triangle is too low for a rail-top pinch')
    working_height=height if material_top-height>=.001 else toe+.15*(material_top-toe)
    section=horizontal_slice(material,working_height,edges);target=(section.min(0)+section.max(0))/2;target[2]=height
    inner=np.asarray(obj['inner_size'],float)
    for i in(0,1):
        low=-inner[i]-lo[i]+.0025;high=inner[i]-hi[i]-.0025
        if low>=high:raise ToolExecutionError('Actual rail-top finger sweep cannot fit original tray walls')
        target[i]=max(low,min(high,target[i]))
    local.sort(key=lambda c:float(np.mean(c@axis)))
    jaw_low=float(target@axis+np.max(local[0]@axis));jaw_high=float(target@axis+np.min(local[1]@axis));projection=section@axis
    if projection.min()<jaw_low+.0005 or projection.max()>jaw_high-.0005:
        raise ToolExecutionError('Actual above-rail section does not fit open jaws')
    transverse=np.array([-axis[1],axis[0],0.]);transverse/=np.linalg.norm(transverse)
    pads=(np.concatenate(local)+target)@transverse;span=section@transverse
    overlap=min(pads.max(),span.max())-max(pads.min(),span.min())
    if overlap<.003:raise ToolExecutionError('Actual above-rail section has insufficient real pad overlap')
    minimum=min(separation_certificate(c+target,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)
    if minimum<.0025:raise ToolExecutionError('Actual rail-top full closing sweep lacks2.5mm source clearance')
    return base+box@target,dict(target_tcp_box_local_m=target.tolist(),material_section_z_m=working_height,actual_material_section_width_m=float(overlap),
        minimum_closing_sweep_rail_clearance_m=float(minimum),minimum_wall_clearance_m=.0025)


def acquire(policy,ref,side):
    name=ref['actor']
    if (policy.task!='E17'or name not in('blue_triangle','green_triangle','blue_square','green_square')or side!='right'
            or not policy.a.control_report.get('engineering_reference_only')
            or policy.objects[name].get('source_asset',{}).get('sha256')not in(TRIANGLE_SHA,SQUARE_SHA)):
        raise ToolExecutionError('Original source E17 triangle rail-top grip required')
    from .execution_design_e20_reference import finish_chip_grip
    from .execution_design_segments_e17_e20 import _held_with_contacts
    def no_wrong_grip():
        if any(row['grasp'][1]for n,row in policy.snapshot()[0].items()if n!=name):raise ToolExecutionError('Rail-top setup holds a different actual body')
    no_wrong_grip()
    if policy.held(ref,side):_held_with_contacts(policy,name,side);return
    policy.stage('local-e17-actual-rail-top-empty-clear')
    base,_=_frame(policy)
    if policy.tip(side)[2]<float(base[2]+.070):policy.move(side,policy.tip(side)+[0,0,.050],no_wrong_grip)
    if policy.held(ref,side):_held_with_contacts(policy,name,side);return
    from .author_clearance import prepare_single_hand
    prepare_single_hand(policy.a,side,policy.clearance);policy.act(side,'RELEASE');no_wrong_grip()
    _,rotation=policy.frame({'actor':name});heading=rotation[:,2].copy();heading[2]=0.
    if np.linalg.norm(heading)<.1:raise ToolExecutionError('Actual triangle lacks a tilted horizontal normal')
    heading/=np.linalg.norm(heading);policy.align_empty_chip_axis(side,heading)
    target,evidence=planned_target(policy,name);policy.operations.append(dict(operation='actual_source_rail_top_pinch',actor=name,**evidence))
    height=max(policy.clearance,float(policy.tip(side)[2]),float(target[2])+.07)
    policy.stage('local-e17-actual-rail-top-source-pinch')
    policy.move(side,[*policy.tip(side)[:2],height],no_wrong_grip);policy.move(side,[*target[:2],height],no_wrong_grip);policy.move(side,target,no_wrong_grip)
    finish_chip_grip(policy,ref,side);_held_with_contacts(policy,name,side)
