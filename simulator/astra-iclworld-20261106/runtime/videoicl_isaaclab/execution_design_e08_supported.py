"""Public supported reset after a measured rolling heel grip; original task unchanged."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_branch_geometry import HeldGeometry,install_public_guard,collision_parts_task,swept_pose_clearance


def table_release_footprint(points,bounds,margin=.001):
    points=np.asarray(points,float);lo=np.asarray(bounds['lower'],float);hi=np.asarray(bounds['upper'],float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Actual source shoe vertices required')
    gaps=np.minimum(points[:,:2].min(0)-lo[:2],hi[:2]-points[:,:2].max(0))
    if np.any(gaps<margin):raise ToolExecutionError('Supported shoe reset release footprint is outside finite table')
    return dict(actual_footprint_margin_xy_m=gaps.tolist(),source_vertices=len(points))


def reset_left_on_table(policy,context):
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
    from .execution_design_e13_release import actual_opening_bodies
    from .author_orientation import _axis_angle
    p=policy;actor=context['actor'];side=context['side'];start=p.c.steps
    if actor!='left_shoe'or side!='left'or p.variant!='A':raise ValueError('Reviewed actual389 E08A left-shoe reset required')
    if not context.get('new_reference_strategy')or context.get('historical_166_parameters_available')is not False:
        raise ValueError('Explicit new source reference lineage required')
    guard=HeldGeometry(p,actor,side);install_public_guard(p,guard);guard()
    bounds=table_bounds_task(p.a.scene)
    phase=context.get('e08_table_reset_phase')
    if phase is not None and phase!='unfold_wrist':
        raise ValueError('Table reset restart may only continue the saved native unfold boundary')
    if phase=='unfold_wrist':
        target=np.asarray(context['supported_reset_hand_target'],float)
    else:
        target=_axis_rotation([0,1,0],-math.radians(30.))@np.asarray(p.a.tcp_rotation_task(side),float)
        context.update(supported_reset_strategy='actual_heel_roll_to_empty_table_v1',e08_table_reset_phase='unfold_wrist',
            supported_reset_source_action=p.c.steps,supported_reset_hand_target=target.tolist())
    from .execution_design_branch_rotation import turn_to_fixed_goal
    def count_rotation():
        used=int(context.get('rotation_commands_used',0))
        if not 0<=used<120:raise ToolExecutionError('Original120 shoe rotation bound exhausted during supported reset')
        context['rotation_commands_used']=used+1
    context['supported_reset_public_rotation']=turn_to_fixed_goal(p,side,target,guard,5.,count_rotation)
    context['e08_table_reset_phase']='empty_table_y'
    for _ in range(30):
        state,_=p.snapshot();dy=.020-float(state[actor]['pos'][1])
        if abs(dy)<=.002:break
        p.act(side,'LEFT'if dy>0 else'RIGHT',mm=min(8.,abs(dy)*1000))
    else:raise ToolExecutionError('Shoe did not reach reviewed empty table band')
    context['e08_table_reset_phase']='short_forward'
    goal=p.tip(side).copy();goal[0]+=.010;guard.move(goal)
    context['e08_table_reset_phase']='toe_above_table'
    for _ in range(30):
        guard();points=material_collision_points_task(p,dict(actor=actor));gap=float(points[:,2].min()-bounds['top'])
        if gap<=.014:break
        p.act(side,'DOWN',mm=min(8.,(gap-.012)*1000))
    else:raise ToolExecutionError('Shoe toe did not reach the table release band')
    guard();points=material_collision_points_task(p,dict(actor=actor));footprint=table_release_footprint(points,bounds)
    collision_parts_task(p,actor)  # Cache native payload pieces before opening.
    state,_=p.snapshot();obstacles={name:collision_parts_task(p,name)for name in state if name!=actor};tip=p.tip(side)
    opening=swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),obstacles,bounds['top'])
    context.update(e08_table_reset_phase='release_on_table',supported_reset_release_geometry=dict(footprint=footprint,opening=opening,
        actual_min_height_over_table_m=float(points[:,2].min()-bounds['top'])))
    p.act(side,'RELEASE');state,_=p.snapshot()
    if any(state[actor]['grasp']):raise ToolExecutionError('Supported reset did not physically release the left shoe')
    free=HeldGeometry(p,actor,side,require_hold=False);install_public_guard(p,free)
    context['e08_table_reset_phase']='empty_hand_back'
    free.move(p.tip(side)+[-.040,0,0]);state,_=p.snapshot()
    actual=dict(actual_table_contact=bool(p.contact(actor,'table')),native_grasp=list(state[actor]['grasp']),
        actual_source_up_cosine=float(state[actor]['mat'][2,2]),actual_actor_position=list(map(float,state[actor]['pos'])))
    if not actual['actual_table_contact']or any(actual['native_grasp']):
        raise ToolExecutionError('Reset shoe lacks actual released table support')
    context['e08_table_reset_phase']='table_supported';context['supported_reset_actual']=actual
    return dict(branch='reset_left_on_table',task='E08',local_completed=True,actions=p.c.steps-start,
        actual_supported_reset=actual,release_geometry=context['supported_reset_release_geometry'],
        original_cumulative_rotation_commands=int(context.get('rotation_commands_used',0)),
        new_reference_strategy=True,historical_166_parameters_available=False,whole_task_score=None,
        original_task_success_asserted=False,midfoot_regrasp_not_yet_executed=True)
