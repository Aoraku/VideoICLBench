"""Source shoe-face section around the actual native COM; no pickup shortcut."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def native_local_com(policy,actor):
    body=policy.a.scene.objects[actor];view=body.root_physx_view
    def array(value):return np.asarray(value.detach().cpu().numpy()if hasattr(value,'detach')else value,float)
    com=array(view.get_coms()).reshape(-1,7);mass=array(view.get_masses()).reshape(-1)
    if com.shape!=(1,7)or mass.shape!=(1,)or not np.isfinite(np.r_[com.ravel(),mass]).all()or mass[0]<=0:
        raise ToolExecutionError('Actual native shoe mass/COM unavailable')
    return com[0,:3],float(mass[0])


def midfoot_section(local_vertices,actual_com_local,grasp_z=.020):
    """Bound the whole pad-height section, not only nearby mesh vertices."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    points=np.asarray(local_vertices,float);com=np.asarray(actual_com_local,float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<8 or com.shape!=(3,)or not np.isfinite(np.r_[points.ravel(),com,grasp_z]).all():
        raise ValueError('Complete source shoe vertices and actual native COM required')
    if np.any(com<points.min(0)-.0001)or np.any(com>points.max(0)+.0001):
        raise ToolExecutionError('Native COM is inconsistent with the source shoe body')
    if not .012<=grasp_z<=.035 or grasp_z<=com[2]:
        raise ToolExecutionError('Shoe face grasp must lie above the real COM')
    hull=ConvexHull(points);a=np.r_[hull.equations[:,:3],[[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]]]
    b=np.r_[-hull.equations[:,3],com[0]+.010,-com[0]+.010,grasp_z+.007,-grasp_z+.007]
    lower=linprog([0,1,0],A_ub=a,b_ub=b,bounds=[(None,None)]*3,method='highs')
    upper=linprog([0,-1,0],A_ub=a,b_ub=b,bounds=[(None,None)]*3,method='highs')
    if not lower.success or not upper.success:raise ToolExecutionError('Whole source midfoot pad-height section unavailable')
    width=float(upper.x[1]-lower.x[1]);opening=.080
    if width>opening-.005:raise ToolExecutionError('Original Panda opening does not clear the source shoe midfoot section')
    local=np.array([com[0],(upper.x[1]+lower.x[1])/2,grasp_z])
    return dict(grasp_local=local.tolist(),actual_native_com_local=com.tolist(),source_pad_band_halfwidth_xz_m=[.010,.007],
        conservative_source_section_width_m=width,panda_opening_residual_m=opening-width,
        horizontal_grasp_com_offset_m=float(np.linalg.norm(local[:2]-com[:2])),grasp_above_com_m=float(grasp_z-com[2]),
        wholehand_public_path_not_yet_verified=True,native_grasp_not_yet_verified=True)


class SoleAcquisitionGeometry:
    def __init__(self,p,actor,side,mode='empty',allow_table_departure=False):
        self.p=p;self.actor=actor;self.side=side;self.mode=mode;self.allow_table_departure=allow_table_departure;self.table_departure_low=None
    def check(self,target=None,rotation=None,closing=False):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
        from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
        from .execution_design_e13_camera import actual_closing_bodies
        p=self.p;tip=p.tip(self.side);table=table_bounds_task(p.a.scene)['top'];target=tip if target is None else np.asarray(target,float);rotation=np.eye(3)if rotation is None else rotation
        bodies=actual_closing_bodies(p,self.side)if closing else{n:actual_mesh(p.a,self.side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
        state,_=p.snapshot();obstacles={n:collision_parts_task(p,n)for n in state if n!=self.actor}
        other='right'if self.side=='left'else'left'
        links=('panda_link0','panda_link1','panda_link2','panda_link3','panda_link4','panda_link5','panda_link6','panda_link7','panda_hand',*p.a.scene.embodiment.fingers)
        obstacles.update({other+'_'+n:[actual_mesh(p.a,other,n)]for n in links})
        report=swept_pose_clearance(bodies,tip,target,rotation,obstacles,table)
        checked=bodies if self.mode=='empty'and not closing else{'panda_hand':bodies['panda_hand']}
        swept_pose_clearance(checked,tip,target,rotation,{self.actor:collision_parts_task(p,self.actor)},table)
        if self.mode=='held':
            p.require_held(dict(actor=self.actor),self.side);points=material_collision_points_task(p,dict(actor=self.actor))
            low=float(points[:,2].min())
            if self.allow_table_departure and low<=table+.001:
                if self.table_departure_low is None:
                    if low<table-.001:raise ToolExecutionError('Initial source shoe is not at the measured Table departure boundary')
                    self.table_departure_low=low
                delta=target-tip
                if not np.allclose(rotation,np.eye(3),atol=1e-8)or np.linalg.norm(delta[:2])>1e-7 or delta[2]<-1e-7:
                    raise ToolExecutionError('Source Table contact departure permits only public UP')
                # Initial supported-source skin is not a new hand collision.
                # Keep the original hand/table test above, allow only this
                # payload to leave its measured Table origin upwards.
                if low<self.table_departure_low-.002:raise ToolExecutionError('Actual source payload sank over2mm during upward Table departure')
                swept_pose_clearance({'payload':points},tip,target,rotation,obstacles,min(table,low-.001))
                report.update(payload_table_departure=True,actual_payload_min_z=low,source_table_origin_min_z=self.table_departure_low)
            else:
                self.allow_table_departure=False
                if not p.contact(self.actor,'table'):swept_pose_clearance({'payload':points},tip,target,rotation,obstacles,table)
        return report
    def __call__(self):return self.check()
    def rotate(self,axis,angle):
        from .realworld_tool_expert import _axis_rotation
        return self.check(rotation=_axis_rotation(axis,angle))
    def move(self,target,tolerance=.002):self.check(target=target);self.p.move(self.side,target,guard=self,tolerance=tolerance);self.check()


def run_branch(author,context,branch_name):
    import math
    from .execution_design_e08_branch import _policy,prepare_new_source_context,run_branch as suffix
    from .execution_design_branch_geometry import install_public_guard,collision_parts_task,HeldGeometry
    from .execution_design_branch_rotation import turn_to_fixed_goal
    from .execution_design_thin_edge import material_collision_points_task
    from .realworld_tool_expert import _axis_rotation
    if branch_name!='sole_com_complete_left':raise ValueError('Unknown E08 supported sole-COM branch')
    p=_policy(author,context);p.max_mm=min(12.,float(p.a.scene.embodiment.config['control']['step_mm'][1]));start=p.c.steps;side='left';actor='left_shoe';state,_=p.snapshot()
    if p.variant!='A'or context.get('actor')!=actor or any(state[actor]['grasp'])or not p.contact(actor,'table'):
        raise ToolExecutionError('Actual unheld Table-supported E08A left shoe required')
    if context.get('e08_table_reset_phase')!='table_supported':raise ValueError('Measured completed native427 table reset required')
    if p.objects[actor]['source_asset']['sha256']!='fdd7d78b574ad7bd52485d063fbb48621a02651cd174235cfd6bd9f7b2e40b32':raise ValueError('Original solid source shoe required')
    com,mass=native_local_com(p,actor);local=np.array([com[0]-.001796686,-.03578066257912408,-.03898736612557417])
    context.update(midfoot_grasp_strategy='native427_exposed_solid_sole_near_actual_com_v1',midfoot_actual_com_local=com.tolist(),midfoot_actual_mass_kg=mass,
        midfoot_source_grasp_local=local.tolist(),midfoot_tcp_above_material_m=.010,midfoot_phase='empty_stage',midfoot_source_action=start)
    empty=SoleAcquisitionGeometry(p,actor,side);install_public_guard(p,empty);tip=p.tip(side);high=max(float(tip[2]),1.04)
    empty.move(np.array([tip[0],.22,high]));empty.move(np.array([-.2,.22,high]))
    state,_=p.snapshot();axis=np.asarray(state[actor]['mat'])[:,2].copy();axis[2]=0
    if np.linalg.norm(axis)<.8:raise ToolExecutionError('Measured shoe no longer exposes the reviewed lateral sole')
    axis/=np.linalg.norm(axis);target=np.column_stack((np.cross(axis,[0,0,-1]),axis,[0,0,-1]))
    context.update(midfoot_phase='empty_turn',midfoot_absolute_hand_goal=target.tolist())
    def count():
        used=int(context.get('rotation_commands_used',0))
        if not 0<=used<120:raise ToolExecutionError('Original120 shoe rotation limit exhausted')
        context['rotation_commands_used']=used+1
    context['midfoot_empty_turn']=turn_to_fixed_goal(p,side,target,empty,1.,count)
    point=p.point(dict(actor=actor,local=local.tolist()))+[0,0,.010];context['midfoot_actual_entry_tcp']=point.tolist();context['midfoot_phase']='approach'
    empty.move(np.array([point[0],p.tip(side)[1],high]));empty.move(np.array([*point[:2],high]));empty.move(point,tolerance=.0008)
    empty.check(closing=True);empty.mode='closing';context['midfoot_phase']='native_grasp'
    for _ in range(5):
        p.act(side,'GRASP')
        if p.held(dict(actor=actor),side):break
    else:raise ToolExecutionError('Solid sole pinch lacks actual bilateral hold')
    context.update(midfoot_first_actual_hold_action=p.c.steps,carried_payload=[actor,side],midfoot_phase='lift')
    empty.mode='held';progress=[]
    while True:
        empty();points=material_collision_points_task(p,dict(actor=actor));rim=max(float(part[:,2].max())for part in collision_parts_task(p,context['support']))
        low=float(points[:,2].min())
        if low>rim+.025:break
        progress.append(low)
        if len(progress)>=13 and max(progress[-12:])-progress[-13]<.0003:raise ToolExecutionError('Actual sole-held shoe does not lift off support')
        p.act(side,'UP',mm=12.)
    held=HeldGeometry(p,actor,side);install_public_guard(p,held);tip=p.tip(side)
    held.move(np.array([tip[0],tip[1],max(1.12,float(tip[2]))]));held.move(np.array([-.2,p.tip(side)[1],p.tip(side)[2]]))
    updated=prepare_new_source_context(author,context);context.update(updated)
    state,_=p.snapshot();body=np.asarray(state[actor]['mat']);axes=p.s['shoe_axes'][actor];toe=body@(np.asarray(axes['toe_local'])-axes['heel_local']);box=state[context['support']]
    label=np.asarray(box['mat'])@np.asarray(p.s['label_end']['point_local']);yaw=math.atan2(label[1],label[0])-math.atan2(toe[1],toe[0])
    side_target=_axis_rotation([0,0,1],yaw)@body
    from .execution_design_e08_source_plan import measured_source_pose_plan
    pts=(material_collision_points_task(p,dict(actor=actor))-np.asarray(state[actor]['pos']))@body
    cavity=p.s['containers']['box'];floor=context['source_geometry_plan']['geometry']['measured_source_floor_local_z_m']
    side_plan=measured_source_pose_plan(pts,side_target,box['pos'],box['mat'],context['control_local'],floor,cavity['lower'],cavity['upper'],p.geometry['box_positions'][actor],np.asarray(axes['toe_local'])-axes['heel_local'],p.s['label_end']['point_local'],1)
    context['measured_side_yaw_candidate_geometry']=side_plan
    if side_plan['acceptable']:
        context.update(target_actor_rotation=side_target.tolist(),midfoot_orientation_strategy='preserve_actual_side_pose_and_correct_native_label_yaw')
    else:context['midfoot_orientation_strategy']='source_nominal_fallback_only_because_actual_side_shape_or_direction_cannot_fit'
    context['midfoot_phase']='orient_and_place'
    context['material_clearance_z']=float(p.point(dict(actor=actor,local=context['control_local']))[2])
    result=suffix(author,context,'complete_left_from_held')
    context['midfoot_phase']='complete_left';result.update(branch=branch_name,actions=p.c.steps-start,actual_native_com_local=com.tolist(),actual_mass_kg=mass,
        first_actual_sole_hold_action=context['midfoot_first_actual_hold_action'],sole_grip_material_local=local.tolist(),source_up_or_flat_gate_added=False)
    return result
