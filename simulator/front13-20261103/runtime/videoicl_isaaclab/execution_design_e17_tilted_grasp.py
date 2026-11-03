"""Horizontal public pinch of C's genuinely tilted source triangle.

The flat-piece source axis can be vertical at native93. Use a horizontal tray
axis, and fit actual finger open-to-closed sweeps beside the narrow rails.
Only the TCP target changes; no object, robot, history or score is assigned.
"""
import numpy as np
from .execution_design_segments_e17_regrasp import CORNERS,TRIANGLE,_tray,_frame
from .execution_design_segments_e17 import TRIANGLE_SHA
from .execution_design_e24_collision import separation_certificate
from .realworld_tool_expert import ToolExecutionError


def _finger_state(policy):
    from .execution_design_e24_transit import capture_model
    model,_=capture_model(policy,'right')
    clouds=[c['points']for c in model['clouds']if c['name']in('panda_leftfinger','panda_rightfinger')]
    fingers=policy.a.finger_geometry('right')['fingers']
    if len(clouds)!=2 or len(fingers)!=2:raise ToolExecutionError('Actual tilted-triangle finger geometry required')
    axis=np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m']
    if np.linalg.norm(axis)<.001:raise ToolExecutionError('Actual tilted-triangle jaw axis unavailable')
    axis/=np.linalg.norm(axis)
    robot=policy.a.scene.robots['right'];values=robot.data.joint_pos[0,policy.c.ids['right'][1]]
    if hasattr(values,'detach'):values=values.detach()
    if hasattr(values,'cpu'):values=values.cpu()
    q=np.asarray(values,float)
    if q.shape!=(2,)or not np.isfinite(q).all()or np.min(q)<.039 or np.max(q)>.0401:
        raise ToolExecutionError('Tilted source triangle requires real full-open fingers')
    return clouds,axis


def planned_target(policy,name):
    obj,rails,floor=_tray(policy);base,box=_frame(policy);tip=policy.tip('right')
    pos,rotation=policy.frame({'actor':name});clouds,axis=_finger_state(policy)
    axis=axis@box
    if abs(float(axis[2]))>.02:raise ToolExecutionError('Actual source pinch axis remains nonhorizontal')
    local=[(np.asarray(points)-tip)@box for points in clouds]
    # Include the entire possible4cm closing stroke for each prismatic finger.
    # Payload contact is intentional; walls, floor and every separate rail are
    # still outside this complete sweep by2.5mm.
    swept=[]
    for points in local:
        sign=1 if float(np.mean(points@axis))>0 else-1
        swept.append(np.r_[points,points-sign*.04*axis])
    all_points=np.concatenate(swept);lo=all_points.min(0);hi=all_points.max(0);inner=np.asarray(obj['inner_size'],float)
    center=(pos-base)@box;target=center.copy();target[2]=floor+.0025-lo[2]
    body=box.T@rotation;gradient=body[2,:2];height=float(target[2]-center[2])
    if np.linalg.norm(gradient)>.1:
        offset=gradient*height/float(gradient@gradient)
        if np.linalg.norm(offset)>.015:raise ToolExecutionError('Source triangle grip plane misses measured material')
        target[:2]=(center+body@np.r_[offset,0.])[:2]
    limits=[(-inner[i]-lo[i]+.0025,inner[i]-hi[i]-.0025)for i in(0,1)]
    if any(a>=b for a,b in limits):raise ToolExecutionError('Actual tilted-pinch sweeps do not fit original tray')
    rail_low=min(r['pos'][0]-r['size'][0]for r in rails);rail_high=max(r['pos'][0]+r['size'][0]for r in rails)
    if center[0]<0:limits[0]=(limits[0][0],min(limits[0][1],rail_low-.0026-hi[0]))
    else:limits[0]=(max(limits[0][0],rail_high+.0026-lo[0]),limits[0][1])
    if any(a>=b for a,b in limits):raise ToolExecutionError('Actual finger closing sweep cannot pass beside source rail')
    for i,(low,high)in enumerate(limits):target[i]=max(low,min(high,target[i]))
    material=(TRIANGLE@rotation.T+pos-base)@box
    local.sort(key=lambda p:float(np.mean(p@axis)));projection=material@axis
    jaw_low=float(target@axis+np.max(local[0]@axis));jaw_high=float(target@axis+np.min(local[1]@axis))
    if projection.min()<jaw_low+.0005 or projection.max()>jaw_high-.0005:
        raise ToolExecutionError('Measured tilted triangle does not fit real open jaw interval')
    transverse=np.array([-axis[1],axis[0],0.]);transverse/=np.linalg.norm(transverse)
    pads=(np.concatenate(local)+target)@transverse;body_strip=material@transverse
    overlap=min(pads.max(),body_strip.max())-max(pads.min(),body_strip.min())
    if overlap<.003:raise ToolExecutionError('Measured tilted triangle has too little actual pad overlap')
    minimum=min(separation_certificate(points+target,CORNERS*np.asarray(r['size'])+r['pos'])for points in swept for r in rails)
    if minimum<.0025:raise ToolExecutionError('Actual tilted finger closing sweep touches a source rail')
    return base+box@target,dict(target_tcp_box_local_m=target.tolist(),minimum_closing_sweep_rail_clearance_m=float(minimum),
        measured_material_strip_overlap_m=float(overlap),wall_floor_clearance_m=.0025)


def acquire(policy,ref,side):
    name=ref['actor']
    if (policy.task!='E17'or policy.variant!='C'or name!='blue_triangle'or side!='right'
            or policy.objects[name].get('source_asset',{}).get('sha256')!=TRIANGLE_SHA
            or not policy.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('Explicit original C blue triangle tilted-source pickup required')
    from .author_clearance import prepare_single_hand
    policy.stage('local-e17c93-tilted-blue-horizontal-source-pinch');prepare_single_hand(policy.a,side,policy.clearance)
    policy.act(side,'RELEASE')
    if any(row['grasp'][1]for row in policy.snapshot()[0].values()):raise ToolExecutionError('Tilted source pickup requires an actual empty right hand')
    _,box=_frame(policy);policy.align_empty_chip_axis(side,box[:,1])
    target,evidence=planned_target(policy,name);policy.operations.append(dict(operation='actual_tilted_source_pinch',actor=name,**evidence))
    height=max(policy.clearance,float(target[2])+.07,float(policy.tip(side)[2]))
    policy.move(side,[*policy.tip(side)[:2],height]);policy.move(side,[*target[:2],height]);policy.move(side,target)
    from .execution_design_e20_reference import finish_chip_grip
    from .execution_design_segments_e17_e20 import _held_with_contacts
    finish_chip_grip(policy,ref,side);_held_with_contacts(policy,name,side)
