"""Pinch real horizontal in-plane edges, rather than a sloping thin face.

Triangle uses its flat base opposite its tip (local Y); square uses opposite
parallel Y edges. Rail screening stops at predicted material contact, not an
impossible closed-through-solid-object pose. Public GRASP and actual contacts
verify whether that predicted stop really occurs.
"""
import numpy as np
from .execution_design_e17_rail_top_grasp import material_vertices
from .execution_design_e17_base_grasp import _finger_clouds
from .execution_design_segments_e17_regrasp import CORNERS,_tray,_frame
from .execution_design_e24_collision import separation_certificate
from .realworld_tool_expert import ToolExecutionError


def planned_target(p,name):
    obj,rails,floor=_tray(p);base,box=_frame(p);pos,rotation=p.frame({'actor':name});vertices,_=material_vertices(p.objects[name]);material=(vertices@rotation.T+pos-base)@box;tip=p.tip('right')
    fingers=p.a.finger_geometry('right')['fingers'];axis=(np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m'])@box;axis/=np.linalg.norm(axis)
    if abs(axis[2])>.1:raise ToolExecutionError('Actual edge pinch exceeds horizontal5.7degree setup')
    clouds=[(np.asarray(c)-tip)@box for c in _finger_clouds(p)];clouds.sort(key=lambda c:float(np.mean(c@axis)));target=(pos-base)@box
    low=np.concatenate(clouds).min(0);high=np.concatenate(clouds).max(0);inner=np.asarray(obj['inner_size'])
    for i in(0,1):
        a=-inner[i]-low[i]+.0026;b=inner[i]-high[i]-.0026
        if a>=b:raise ToolExecutionError('Original fully open edge fingers do not fit tray walls')
        target[i]=max(a,min(b,target[i]))
    target[2]=floor+.0026-low[2];projection=material@axis
    def contact_sweep(point):
        jawlo=float(point@axis+np.max(clouds[0]@axis));jawhi=float(point@axis+np.min(clouds[1]@axis))
        if projection.min()<jawlo or projection.max()>jawhi:raise ToolExecutionError('Actual material is outside the full open edge jaws')
        strokes=[float(projection.min()-jawlo),float(jawhi-projection.max())]
        return [np.r_[c,c+axis*stroke*(1 if i==0 else -1)]for i,(c,stroke)in enumerate(zip(clouds,strokes))],strokes
    swept,strokes=contact_sweep(target)
    target[2]+=max(0.,floor+.0026-float(np.concatenate(swept)[:,2].min()+target[2]))
    minimum=min(separation_certificate(c+target,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)
    adjustment=np.zeros(2)
    if minimum<.0025:
        # One minimum planar translation from actual separating planes; no
        # trial direction loop and no object/joint state modification.
        from scipy.optimize import linprog
        inequalities=[];rhs=[]
        for cloud in swept:
            for rail in rails:
                a=cloud+target;b=CORNERS*np.asarray(rail['size'])+rail['pos'];gap=separation_certificate(a,b)
                if gap>=.010:continue
                fit=linprog([0,0,0,0,-1],A_ub=np.r_[np.c_[a,-np.ones(len(a)),np.zeros(len(a))],np.c_[-b,np.ones(len(b)),np.ones(len(b))]],b_ub=np.zeros(len(a)+len(b)),bounds=[(-1,1)]*3+[(None,None)]*2,method='highs')
                if not fit.success or np.linalg.norm(fit.x[:3])<1e-8:raise ToolExecutionError('No actual edge/divider separating plane')
                normal=fit.x[:3]/np.linalg.norm(fit.x[:3]);inequalities.append([*normal[:2],0,0]);rhs.append(gap-.0026)
        points=np.concatenate(swept)+target
        for i in(0,1):
            row=[0,0,0,0];row[i]=1;inequalities.append(row);rhs.append(float(inner[i]-points[:,i].max()-.0026))
            row=[0,0,0,0];row[i]=-1;inequalities.append(row);rhs.append(float(points[:,i].min()+inner[i]-.0026))
        inequalities.extend([[1,0,-1,0],[-1,0,-1,0],[0,1,0,-1],[0,-1,0,-1]]);rhs.extend([0,0,0,0])
        fit=linprog([0,0,1,1],A_ub=inequalities,b_ub=rhs,bounds=[(-.006,.006),(-.006,.006),(0,.006),(0,.006)],method='highs')
        if not fit.success:raise ToolExecutionError('No bounded6mm source edge clearance adjustment')
        adjustment=fit.x[:2];target[:2]+=adjustment;swept,strokes=contact_sweep(target)
        minimum=min(separation_certificate(c+target,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)
        if minimum<.0025:raise ToolExecutionError('Actual adjusted material-contact stroke still hits a divider')
        points=np.concatenate(swept)+target
        if np.any(points[:,:2].min(0)<-inner[:2]+.0025)or np.any(points[:,:2].max(0)>inner[:2]-.0025):raise ToolExecutionError('Adjusted actual edge grip leaves original tray walls')
    if float(np.concatenate(swept)[:,2].min()+target[2])<floor+.0025:raise ToolExecutionError('Original edge stroke lacks source floor clearance')
    pad=np.concatenate(clouds)+target;transverse=np.array([-axis[1],axis[0],0.]);transverse/=np.linalg.norm(transverse)
    span=material@transverse;strip=pad@transverse
    if min(span.max(),strip.max())-max(span.min(),strip.min())<.003 or min(material[:,2].max(),pad[:,2].max())-max(material[:,2].min(),pad[:,2].min())<.002:
        raise ToolExecutionError('Actual edge pads cannot contact the measured material')
    return base+box@target,dict(target_tcp_box_local_m=target.tolist(),planned_xy_clearance_adjustment_m=adjustment.tolist(),predicted_material_contact_strokes_m=strokes,minimum_nominal_edge_stroke_rail_clearance_m=minimum,actual_grasp_not_yet_verified=True)


def acquire(p,ref,side):
    name=ref['actor']
    if p.task!='E17'or name not in p.d['target_members']or side!='right':raise ToolExecutionError('Explicit original E17 right chip edge grip required')
    from .author_clearance import prepare_single_hand
    from .execution_design_e20_reference import finish_chip_grip
    from .execution_design_segments_e17_e20 import _held_with_contacts
    p.stage('local-e17-source-in-plane-edge-grip');prepare_single_hand(p.a,side,p.clearance);p.act(side,'RELEASE')
    if any(row['grasp'][1]for row in p.snapshot()[0].values()):raise ToolExecutionError('Edge grip setup requires actual empty hand')
    _,rotation=p.frame({'actor':name})
    from .execution_design_e17_rail_top_grasp import TRIANGLE_SHA
    index=1 if p.objects[name].get('source_asset',{}).get('sha256')==TRIANGLE_SHA else int(np.argmin(abs(rotation[2,:2])))
    desired=rotation[:,index]
    if abs(float(desired[2]))>.1:raise ToolExecutionError('Measured original local-Y edges are not horizontal')
    p.align_empty_chip_axis(side,desired);target,evidence=planned_target(p,name);p.operations.append(dict(operation='original_in_plane_edge_grip',actor=name,**evidence))
    height=max(float(p.tip(side)[2]),float(target[2])+.040)
    p.move(side,[*p.tip(side)[:2],height],tolerance=.006);p.move(side,[*target[:2],height],tolerance=.006);p.move(side,target,tolerance=.0005)
    finish_chip_grip(p,ref,side);_held_with_contacts(p,name,side)
