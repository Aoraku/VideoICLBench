"""Free the last north-rail triangle with a bounded real southward nudge."""
import numpy as np
from .execution_design_segments_e17_regrasp import TRIANGLE,_tray,_frame
from .execution_design_segments_e17 import TRIANGLE_SHA
from .realworld_tool_expert import ToolExecutionError


def floor_flat(policy,name):
    _,_,floor=_tray(policy);base,box=_frame(policy);pos,rotation=policy.frame({'actor':name})
    points=(TRIANGLE@rotation.T+pos-base)@box
    return bool(rotation[2,2]>.98 and abs(float(rotation[2,0]))<.1
        and abs(float(points[:,2].min()-floor))<.003 and policy.contact(name,'packing_box'))


def pusher_target(policy,name,*,lower_north_edge=False):
    from .execution_design_e17_base_grasp import _finger_clouds
    obj,rails,_=_tray(policy);base,box=_frame(policy);tip=policy.tip('right')
    clouds=[(np.asarray(points)-tip)@box for points in _finger_clouds(policy)]
    if len(clouds)!=2:raise ToolExecutionError('Actual closed two-finger pusher required')
    points=np.concatenate(clouds);low=points.min(0);high=points.max(0)
    pos,rotation=policy.frame({'actor':name});material=(TRIANGLE@rotation.T+pos-base)@box;center=(pos-base)@box
    rail_top=max(r['pos'][2]+r['size'][2]for r in rails);target=center.copy()
    inner=np.asarray(obj['inner_size'],float)
    target[1]=min(float(material[:,1].max()-low[1]+.0005),float(inner[1]-high[1]-.0025))
    target[2]=rail_top+.0025-low[2]
    if lower_north_edge:
        # A99's north tip is below the rail top, at positive box-X. Keep the
        # complete40mm real pushing sweep on that side of every divider.
        north=material[material[:,1]>=material[:,1].max()-.003]
        toe=max(float(_tray(policy)[2]+.0025),float(north[:,2].max()-.002))
        target[0]=max(float(target[0]),max(r['pos'][0]+r['size'][0]for r in rails)+.0026-low[0])
        target[2]=toe-low[2]
    if np.any(target[:2]+low[:2]<-inner[:2]+.0025)or np.any(target[:2]+high[:2]>inner[:2]-.0025):
        raise ToolExecutionError('Actual closed pusher cannot fit between source walls')
    north=material[material[:,1]>=material[:,1].max()-.003]
    if not lower_north_edge and float(north[:,2].max())<rail_top+.003:
        raise ToolExecutionError('Measured north triangle edge is below the rail-clear pusher')
    if lower_north_edge:
        from .execution_design_segments_e17_regrasp import CORNERS
        from .execution_design_e24_collision import separation_certificate
        swept=[np.r_[cloud+target,cloud+target+[0,-.040,0]]for cloud in clouds]
        minimum=min(separation_certificate(c,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)
        if minimum<.0025:raise ToolExecutionError('Actual low north pusher sweep lacks divider clearance')
        if min(material[:,0].max(),target[0]+high[0])-max(material[:,0].min(),target[0]+low[0])<.003:
            raise ToolExecutionError('Low north pusher misses actual triangle material')
    return base+box@target,dict(target_tcp_box_local_m=target.tolist(),rail_clear_pusher_toe_z_m=float(target[2]+low[2]),below_rail_north_edge=lower_north_edge)


def acquire(policy,ref,side,*,lower_north_edge=False,prepared_empty=False,prepared_pusher=False,edge_grip=False):
    name=ref['actor']
    if (policy.task!='E17'or name!='green_triangle'or side!='right'
            or not policy.a.control_report.get('engineering_reference_only')
            or policy.objects[name].get('source_asset',{}).get('sha256')!=TRIANGLE_SHA):
        raise ToolExecutionError('Original north-rail E17 green triangle required')
    from .author_clearance import prepare_single_hand
    from .execution_design_e17_base_grasp import planned_target
    from .execution_design_e20_reference import finish_chip_grip
    from .execution_design_segments_e17_e20 import _held_with_contacts
    def no_wrong_grip():
        state,_=policy.snapshot()
        if any(row['grasp'][1]for n,row in state.items()if n!=name):raise ToolExecutionError('North-rail pusher gripped a different actual body')
    policy.stage('local-e17-north-triangle-empty-pusher-setup')
    if not prepared_empty and not prepared_pusher:
        prepare_single_hand(policy.a,side,policy.clearance);policy.act(side,'RELEASE')
    no_wrong_grip()
    if not floor_flat(policy,name):
        _,box=_frame(policy)
        if not prepared_empty and not prepared_pusher:policy.align_empty_chip_axis(side,box[:,0])
        if not prepared_pusher:policy.act(side,'GRASP')
        no_wrong_grip()
        robot=policy.a.scene.robots[side];q=robot.data.joint_pos[0,policy.c.ids[side][1]]
        if hasattr(q,'detach'):q=q.detach()
        if hasattr(q,'cpu'):q=q.cpu()
        # The actual meshes, including their current measured opening, bound
        # the push. A5mm transient opening does not require a1mm closed latch.
        if not np.isfinite(np.asarray(q,float)).all()or float(np.max(np.asarray(q,float)))>.010:raise ToolExecutionError('Actual empty pusher opening exceeds reviewed10mm')
        if not prepared_pusher:
            target,evidence=pusher_target(policy,name,lower_north_edge=lower_north_edge);policy.operations.append(dict(operation='actual_north_rail_pusher_target',**evidence))
            policy.move(side,[*target[:2],policy.tip(side)[2]],no_wrong_grip);policy.move(side,target,no_wrong_grip)
        else:
            from .execution_design_e17_base_grasp import _finger_clouds
            from .execution_design_segments_e17_regrasp import CORNERS
            from .execution_design_e24_collision import separation_certificate
            obj,rails,floor=_tray(policy);base,box=_frame(policy);clouds=[(c-base)@box for c in _finger_clouds(policy)]
            lowest=float(np.concatenate(clouds)[:,2].min())
            if lowest<floor+.0026:
                policy.act(side,'UP',mm=max(.5,(floor+.003-lowest)*1000));no_wrong_grip()
                base,box=_frame(policy);clouds=[(c-base)@box for c in _finger_clouds(policy)]
            swept=[np.r_[c,c+[0,-.040,0]]for c in clouds];points=np.concatenate(swept);inner=np.asarray(obj['inner_size'])
            if points[:,2].min()<floor+.0025 or np.any(points[:,:2].min(0)<-inner[:2]+.0025)or np.any(points[:,:2].max(0)>inner[:2]-.0025):raise ToolExecutionError('Actual continued pusher lacks floor/wall clearance')
            if min(separation_certificate(c,CORNERS*np.asarray(r['size'])+r['pos'])for c in swept for r in rails)<.0025:raise ToolExecutionError('Actual continued pusher lacks divider clearance')
        policy.stage('local-e17-north-triangle-real-south-nudge')
        for _ in range(10):
            if floor_flat(policy,name):break
            _,box=_frame(policy);policy.move(side,policy.tip(side)-box[:,1]*.004,no_wrong_grip)
        # A transient contact during a closed-finger push is not a loadable
        # pinch. Clear and release it, then acquire the measured source anew.
        policy.move(side,policy.tip(side)+[0,0,.040],no_wrong_grip);policy.act(side,'RELEASE')
    if edge_grip:
        from .execution_design_e17_edge_grasp import acquire as acquire_edges
        return acquire_edges(policy,ref,side)
    _,rotation=policy.frame({'actor':name});heading=rotation[:,0].copy();heading[2]=0.
    if np.linalg.norm(heading)<.1:raise ToolExecutionError('Actual freed triangle base has no horizontal heading')
    policy.align_empty_chip_axis(side,heading)
    target,evidence=planned_target(policy);policy.operations.append(dict(operation='actual_freed_north_base_grasp',**evidence))
    policy.stage('local-e17-north-triangle-real-base-pinch')
    height=max(policy.clearance,float(policy.tip(side)[2]),float(target[2])+.07)
    policy.move(side,[*policy.tip(side)[:2],height],no_wrong_grip);policy.move(side,[*target[:2],height],no_wrong_grip);policy.move(side,target,no_wrong_grip)
    finish_chip_grip(policy,ref,side);_held_with_contacts(policy,name,side);no_wrong_grip()
