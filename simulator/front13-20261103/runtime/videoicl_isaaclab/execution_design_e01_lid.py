"""Close the original hinged meal lid from its physical free edge."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def close_loading_lid(p):
    from .execution_design_e01_balance import _coarse
    if _coarse(p):
        from .execution_design_e01_functional import close_lid
        return close_lid(p)
    from .execution_design_e01_package import _state
    from .execution_design_e01_food import park_empty_other
    from .execution_design_e13_release import actual_opening_bodies
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    state=_state(p)
    if state['phase']in('lid_released','closed','delivered'):
        return dict(local_completed=True,phase=state['phase'],whole_task_score=None)
    if state['phase']!='loaded':raise ToolExecutionError('E01 original tray must be physically loaded before its lid')
    package=next(item for item in p.d['packages']if item['container']=='meal_box')
    joint=p.spec['joints'][package['hinge_joint_index']];name=package['lid']
    if joint['type']!='revolute'or joint['parent']!='meal_box'or joint['child']!=name or joint['axis']!='X':
        raise ToolExecutionError('Reviewed E01 original X hinge required')
    park_empty_other(p,'right',{},None)
    hy=float(p.objects[name]['size'][1])
    # At the free edge, the palm stays beyond the panel throughout closure.
    # A side-edge grip leaves the palm intersecting the upright thin panel.
    ref=dict(actor=name,local=[0.,hy-.010,0.],jaw_axis_local=[0,0,1])
    p.stage('close-original-lid-free-edge-acquire');p.acquire(ref,'right')
    def guard():p.require_held(ref,'right')
    base,rotation=p.frame({'actor':'meal_box'});child_rotation=p.frame({'actor':name})[1]
    relative=rotation.T@child_rotation
    angle=math.atan2(float(relative[2,1]-relative[1,2])/2,float((np.trace(relative)-1)/2))
    if np.linalg.norm(relative-_axis_rotation([1,0,0],angle))>.08:
        raise ToolExecutionError('E01 actual lid is not on its original hinge arc')
    release_angle=math.radians(20.)
    if angle<0 or angle>math.radians(100)+.05:raise ToolExecutionError('E01 lid lies outside its original hinge range')
    p.stage('close-original-lid-through-physical-hinge')
    for sample in np.linspace(angle,min(angle,release_angle),max(2,1+math.ceil(max(0.,angle-release_angle)/math.radians(5)))):
        guard();base,rotation=p.frame({'actor':'meal_box'});desired=rotation@_axis_rotation([1,0,0],float(sample))
        anchor=base+rotation@np.asarray(joint['anchor0']);goal=anchor+desired@(np.asarray(ref['local'])-np.asarray(joint['anchor1']))
        p.move_point('right',ref,goal,guard,tolerance=.003);p.rotate_actor(name,'right',desired)
    guard();tip=p.tip('right');snapshot,_=p.snapshot()
    obstacles={actor:collision_parts_task(p,actor)for actor in snapshot if actor!=name}
    opening=swept_pose_clearance(actual_opening_bodies(p,'right'),tip,tip,np.eye(3),obstacles,
        table_bounds_task(p.a.scene)['top'],margin=.0003)
    p.stage('release-hinged-lid-before-underfinger-trap');p.act('right','RELEASE')
    if p.held(ref,'right'):raise ToolExecutionError('E01 original lid did not actually release')
    # Leave over the free edge while the lower finger is still above the wall.
    # Gravity closes the unchanged passive hinge as the hand clears it.
    direction=p.frame({'actor':'meal_box'})[1][:,1]
    p.move('right',p.tip('right')+direction*.08);p.move('right',p.tip('right')+[0,0,.07])
    base,rotation=p.frame({'actor':'meal_box'});position,child_rotation=p.frame({'actor':name})
    center_error=float(np.linalg.norm(rotation.T@(position-base)-np.asarray(package['lid_local_center'])))
    orientation_error=float(np.linalg.norm(rotation.T@child_rotation-np.eye(3)))
    closed=bool(center_error<=package.get('lid_position_tolerance',.008)
        and orientation_error<=package.get('lid_orientation_tolerance',.08))
    state['phase']='closed'if closed else'lid_released'
    measured=dict(grip_original_panel_local=ref['local'],release_proposal_degrees=20.,opening_sweep=opening,
        actual_center_error_m=center_error,actual_orientation_matrix_error=orientation_error,
        original_closed_geometry_observed=closed,original_passive_hinge=True,extra_stability_waits=0)
    p.a.control_report['e01_original_lid_free_edge_closure']=measured
    return dict(local_completed=True,phase=state['phase'],measured_lid=measured,whole_task_score=None)
