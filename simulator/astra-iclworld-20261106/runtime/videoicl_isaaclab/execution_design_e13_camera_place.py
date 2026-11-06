"""Source bottom-edge/stand-ledge geometry for a measured camera-end hold."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def bottom_front_edge(local_vertices):
    points=np.asarray(local_vertices,float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<8 or not np.isfinite(points).all():
        raise ValueError('Actual complete phone collision vertices required')
    span=np.ptp(points,axis=0)
    if not .145<span[0]<.155 or not .070<span[1]<.080 or not .007<span[2]<.012:
        raise ValueError('Reviewed original phone body frame required')
    band=points[points[:,0]<=points[:,0].min()+.001]
    front=band[band[:,2]<=band[:,2].min()+.001]
    if len(front)<2:raise ToolExecutionError('Original phone bottom/front edge is missing')
    return np.array([band[:,0].min(),(band[:,1].min()+band[:,1].max())/2,front[:,2].mean()])


def measured_stand_ledge(stand,semantic,position,rotation):
    """Transform the original source landmark with the actual stand body."""
    position=np.asarray(position,float);rotation=np.asarray(rotation,float)
    landmark=np.asarray(semantic['stand_ledge_point_task'],float)
    if position.shape!=(3,)or rotation.shape!=(3,3)or landmark.shape!=(3,)or not np.isfinite(np.r_[position,rotation.ravel(),landmark]).all()or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-4)or np.linalg.det(rotation)<.999:
        raise ValueError('Actual proper stand pose and original source ledge required')
    nominal=np.r_[stand['xy'],float(stand['bottom'])+float(stand['size'][2])]
    source_r=_axis_rotation([0,0,1],float(stand.get('yaw',0.)))
    return position+rotation@source_r.T@(landmark-nominal)


def edge_height_target(edge_local,local_vertices,rotation,ledge):
    """Stage both bottom-edge corners above the actual source ledge."""
    points=np.asarray(local_vertices,float);edge=np.asarray(edge_local,float);r=np.asarray(rotation,float);ledge=np.asarray(ledge,float)
    band=points[points[:,0]<=points[:,0].min()+.001]
    relative=(band-edge)@r.T
    target=ledge.copy();target[2]+=.002-float(relative[:,2].min())
    return target


BRANCHES=frozenset(('camera_end_place','camera_end_complete_supported'))


def _align_stand_plane(p,context,guard):
    import math
    from .execution_design_e13_branch import goal_rotation
    from .execution_design_branch_rotation import turn_to_fixed_goal
    state,_=p.snapshot();objects={o['id']:o for o in p.spec['objects']};stand=objects[p.s['stand']]
    nominal=_axis_rotation([0,0,1],float(stand.get('yaw',0.)))
    plane=np.asarray(state[p.s['stand']]['mat'])@nominal.T@goal_rotation(context['goal'])[:,2]
    if 'camera_end_stand_plane_hand_goal'not in context:
        normal=np.asarray(state['phone']['mat'])[:,2];axis=np.cross(normal,plane);angle=math.acos(float(np.clip(normal@plane,-1,1)))
        if angle<=math.radians(5):return
        if np.linalg.norm(axis)<1e-8:raise ToolExecutionError('Phone back plane is opposite the original stand plane')
        target=_axis_rotation(axis/np.linalg.norm(axis),angle)@np.asarray(p.a.tcp_rotation_task('right'))
        context['camera_end_stand_plane_hand_goal']=target.tolist()
    def count_rotation():
        baseline=int(context.get('camera_end_legacy_held_commands_before_empty',context.get('rotation_commands_used',0)))
        used=int(context.get('camera_end_additional_held_rotation_commands_used',0))
        if baseline+used>=80:raise ToolExecutionError('Original80 held rotation limit exhausted')
        context['camera_end_additional_held_rotation_commands_used']=used+1
    context['camera_end_stand_plane_turn']=turn_to_fixed_goal(p,'right',context['camera_end_stand_plane_hand_goal'],guard,5.,count_rotation)


def run_branch(author,context,branch_name):
    from .execution_design_e13_branch import _policy
    from .execution_design_branch_geometry import HeldGeometry,install_public_guard,collision_parts_task
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_tool_tracking import move_material
    from .execution_design_e13_release import native_orientation,landing_conditions
    if branch_name not in BRANCHES:raise ValueError('Unknown camera-end supported placement branch')
    start=author.c.steps
    if branch_name=='camera_end_complete_supported':
        from .execution_design_e13_camera import run_branch as acquire
        phase=context.get('camera_end_phase');state,_=author.c.snapshot()
        if phase=='empty_right_turn':acquire(author,context,'camera_end_resume_entry')
        elif phase in('lift_above_stand','inset_raise'):
            result=acquire(author,context,'camera_end_finish_lift'if phase=='lift_above_stand'and state['phone']['grasp'][1]else'camera_end_inset_regrasp')
            if result.get('native_already_landed'):return dict(result,branch=branch_name,actions=author.c.steps-start)
        elif phase=='camera_descent'and not any(state['phone']['grasp']):acquire(author,context,'camera_end_finish_entry')
        elif phase=='native_grasp'and not any(state['phone']['grasp']):acquire(author,context,'camera_end_reacquire')
        elif phase!='free_held_above_stand'and not context.get('camera_end_place_phase'):
            raise ValueError('Measured camera entry, grasp/lift, or placement context required')
    p=_policy(author,context);p._camera_context=context;side='right';p.require_held(dict(actor='phone'),side)
    if p.variant!='A'or context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1':
        raise ValueError('Reviewed measured camera-end E13A strategy required')
    guard=HeldGeometry(p,'phone',side,allowed_payload=(p.s['stand'],));install_public_guard(p,guard)
    phase=context.get('camera_end_place_phase','align_stand_plane')
    phases=('align_stand_plane','travel_over_ledge','lower_to_support','open_release','empty_hand_up','complete')
    if phase not in phases:raise ValueError('Known camera-end place phase required')
    # A held restore cannot be used after RELEASE. The released native boundary
    # needs an explicit empty-hand branch, not a repeated grasp or release.
    if phases.index(phase)>=phases.index('empty_hand_up'):
        raise ValueError('Released camera placement cannot restart through held entry')
    context['camera_end_place_phase']=phase
    if phase=='align_stand_plane':
        _align_stand_plane(p,context,guard)
        state,_=p.snapshot()
        if not native_orientation(state['phone']['mat'],p.s,p.variant)['allowed']:
            raise ToolExecutionError('Camera-end hold does not satisfy native orientation after the physical stand-plane turn')
        context['camera_end_place_phase']='travel_over_ledge';phase='travel_over_ledge'
    state,_=p.snapshot();phone=state['phone'];points=material_collision_points_task(p,dict(actor='phone'))
    local=(points-np.asarray(phone['pos']))@np.asarray(phone['mat'])
    context.setdefault('camera_end_bottom_front_edge_local',bottom_front_edge(local).tolist())
    ref=dict(actor='phone',local=context['camera_end_bottom_front_edge_local']);objects={o['id']:o for o in p.spec['objects']}
    support=state[p.s['stand']];ledge=measured_stand_ledge(objects[p.s['stand']],p.s,support['pos'],support['mat'])
    context['camera_end_actual_stand_ledge_task']=ledge.tolist()
    def move(point):move_material(p,side,ref,np.asarray(point,float),guard=guard,tolerance=.002)
    if phase=='travel_over_ledge':
        edge=p.point(ref);top=max(float(part[:,2].max())for part in collision_parts_task(p,p.s['stand']))
        high=max(float(edge[2]),top+.015-float((points-edge)[:,2].min()))
        context['camera_end_edge_high_z']=high
        move([*edge[:2],high]);move([ledge[0],p.point(ref)[1],high]);move([*ledge[:2],high])
        context['camera_end_place_phase']='lower_to_support';phase='lower_to_support'
    if phase=='lower_to_support':
        state,_=p.snapshot();phone=state['phone'];points=material_collision_points_task(p,dict(actor='phone'))
        local=(points-np.asarray(phone['pos']))@np.asarray(phone['mat'])
        destination=edge_height_target(ref['local'],local,phone['mat'],ledge)
        context['camera_end_edge_approach_target']=destination.tolist();move(destination)
        previous=p.point(ref)[2]
        while True:
            guard()
            if p.contact('phone',p.s['stand']):break
            state,_=p.snapshot();vertices=material_collision_points_task(p,dict(actor='phone'));body=state['phone'];local_now=(vertices-np.asarray(body['pos']))@np.asarray(body['mat'])
            band=vertices[local_now[:,0]<=local_now[:,0].min()+.001]
            if band[:,2].min()<ledge[2]-.010:raise ToolExecutionError('Phone bottom passed the actual stand ledge without support')
            p.act(side,'DOWN',mm=2.)
            current=p.point(ref)[2]
            if current>=previous-.0002:raise ToolExecutionError('Phone bottom edge does not descend toward actual stand contact')
            previous=current
        context['camera_end_place_phase']='open_release';phase='open_release'
    state,_=p.snapshot();orientation=native_orientation(state['phone']['mat'],p.s,p.variant)
    if not orientation['allowed']or not p.contact('phone',p.s['stand']):
        raise ToolExecutionError('Actual native orientation and stand contact are required before camera-end release')
    from .execution_design_e13_camera import AcquisitionGeometry
    opening=AcquisitionGeometry(p,side,mode='closing').check(opening=True)
    context['camera_end_actual_release_opening']=opening;collision_parts_task(p,'phone')
    context['camera_end_empty_retreat_tcp']=(p.tip(side)+[0,0,.040]).tolist()
    p.act(side,'RELEASE');state,_=p.snapshot()
    if any(state['phone']['grasp']):raise ToolExecutionError('Camera-end stand release did not physically release phone')
    context['camera_end_place_phase']='empty_hand_up'
    free=AcquisitionGeometry(p,side);install_public_guard(p,free)
    free.move(np.asarray(context['camera_end_empty_retreat_tcp']));landing=landing_conditions(p)
    if not landing['local_geometry_contact_allowed']or not landing['native_current_conditions_passed']:
        import json
        raise ToolExecutionError('Camera-end stand placement failed original native conditions: '+json.dumps(landing))
    context['camera_end_place_phase']='complete'
    return dict(branch=branch_name,task='E13',local_completed=True,actions=p.c.steps-start,actual_stand_supported_release=True,
        native_landing_conditions=landing,actual_release_opening=opening,whole_task_score=None,original_task_success_asserted=False)
