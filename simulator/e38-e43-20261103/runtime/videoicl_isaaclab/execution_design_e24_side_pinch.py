"""Continue the already pushed, supported lid through one measured pitch arc."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .author_orientation import _axis_angle


def pitch_to_side(policy,target):
    from .execution_design_segments_e23_e24 import _air_check,_air_feedback
    stalled=0;observations=[]
    for _ in range(80):
        state,_=policy.snapshot()
        if any(any(body['grasp'])for body in state.values()):raise ToolExecutionError('Actual E24 pitch hand must remain empty')
        current=np.asarray(policy.a.tcp_rotation_task('left'));axis,error=_axis_angle(target@current.T)
        if error<math.radians(8):return observations
        if abs(axis[1])<.90:raise ToolExecutionError('E24 continuation differs from the selected single pitch arc')
        sign=math.copysign(1.,axis[1]);degrees=min(getattr(policy,'_e24_single_pitch_degrees',10.),max(2.,math.degrees(error)))
        candidate=_axis_rotation([0,1,0],sign*math.radians(degrees))@current
        _air_check(policy,'left',rotation=candidate,target='lid')
        policy.act('left','PITCH_UP'if sign>0 else'PITCH_DOWN',degrees=degrees)
        _air_feedback(policy,'left');_air_check(policy,'left',target='lid')
        after=np.asarray(policy.a.tcp_rotation_task('left'));remaining=_axis_angle(target@after.T)[1]
        improved=error-remaining;stalled=stalled+1 if improved<math.radians(.15)else 0
        observations.append(dict(step=policy.c.steps,actual_error_degrees=math.degrees(remaining),actual_progress_degrees=math.degrees(improved)))
        if stalled>=3:raise ToolExecutionError('E24 single public pitch failed to advance for three actions')
    raise ToolExecutionError('E24 bounded single-axis pitch exhausted')


def side_grasp_local(policy):
    from .execution_design_e24_collision import actual_object_parts
    state,_=policy.snapshot();body=state['lid'];r=np.asarray(body['mat']);pos=np.asarray(body['pos'])
    rows=[o['points']for o in actual_object_parts(policy)if o['name'].startswith('object:lid:')]
    if not rows:raise ToolExecutionError('Actual enabled E24 lid collision parts required')
    vertices=(np.concatenate(rows)-pos)@r
    # Open fingers straddle the entire44mm lid/rim, rather than centering the
    # jaw on the roof plate20mm above its collision-bounds midpoint.
    return np.array([0.,.098,float((vertices[:,2].min()+vertices[:,2].max())*.5)])


def run_segment(a,segment,parameters):
    from .execution_design_segments_e23_e24 import _scope,_air_move,_air_check
    from .execution_design_e24_reference import MeasuredE24Author
    from .execution_design_e24_lid import table_bounds,finger_table_clearance,side_grasp_rotation,LID_SHA
    _scope(a,'E24');spec=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{})
    continuing=segment in('e24_down_pitch_and_cover_from3','e24_down_two_mm_and_cover_from6')
    source=(6,611)if segment=='e24_down_two_mm_and_cover_from6'else(3,311)if continuing else(310,31011)
    if(segment not in('e24_side_pinch_and_cover_from310','e24_down_pitch_and_cover_from3','e24_down_two_mm_and_cover_from6')or parameters!={}or spec.get('variant')!='A'
            or spec.get('seed')!=4201 or spec['execution_design'].get('condition')!='I'
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=source
            or cp.get('diagnostic_only')is not True or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted actual E24 derived-layout native310/31011 boundary required')
    p=MeasuredE24Author(a);p._engineering_coarse_free_space=True
    p._engineering_translation_joint_increment=.35
    p._engineering_air_joint_reserve=.05
    state,_=p.snapshot();body=state['lid'];lo,hi=table_bounds(p)
    if(any(any(o['grasp'])for o in state.values())or p.objects['lid'].get('source_asset',{}).get('sha256')!=LID_SHA
            or np.asarray(body['mat'])[2,2]<.98 or not lo[0]+.035<float(body['pos'][0])<lo[0]+.070):
        raise ToolExecutionError('Original real flat supported overhang/empty hands required')
    p.stage('local-E24-empty-down60-before-single-pitch')
    target=p.tip('left').copy();target[2]=.9208680941820043 if continuing else target[2]-.060
    _air_move(p,'left',target,target='lid',tolerance=.006,maximum_step=.002 if continuing else .005)
    p._e24_single_pitch_degrees=2.5
    p.stage('local-E24-single-public-side-pitch')
    observations=pitch_to_side(p,side_grasp_rotation(np.asarray(body['mat'])))
    p.stage('local-E24-whole-lid-height-real-side-pinch')
    local=side_grasp_local(p);ref=dict(actor='lid',local=local.tolist(),jaw_axis_local=[0,0,1])
    point=p.point(ref);rotation=np.asarray(p.snapshot()[0]['lid']['mat']);outside=point+rotation[:,1]*.10
    def move(target,tolerance=.006):
        finger_table_clearance(p,'left',lo,hi)
        _air_move(p,'left',target,target='lid',allow_target_finger_contact=True,tolerance=tolerance,maximum_step=.008)
        finger_table_clearance(p,'left',lo,hi)
    move([outside[0],outside[1],p.tip('left')[2]])
    move(outside)
    move(point,tolerance=.002)
    for _ in range(3):
        p.act('left','GRASP');finger_table_clearance(p,'left',lo,hi)
        if p.held(ref,'left'):break
    else:raise ToolExecutionError('Whole-height actual lid lacks bilateral grip')
    p.require_held(ref,'left')
    # The source lid starts in legitimate table contact. Lift vertically off
    # that support with the original held/finger guards before applying the
    # free-space payload/table separation certificate.
    def initial_lift_guard():
        p.require_held(ref,'left');finger_table_clearance(p,'left',lo,hi)
        _air_check(p,'left',target='lid',allow_target_finger_contact=True)
    p.move('left',p.tip('left')+[0,0,.020],initial_lift_guard,tolerance=.006)
    _air_move(p,'left',p.tip('left')+[0,0,.060],payload='lid',held_guards=((ref,'left'),),tolerance=.006,maximum_step=.006)
    # The third-cup hand otherwise remains inside the descending lid's
    # footprint. Withdraw that genuinely empty hand before closing the box.
    p.stage('local-E24-empty-right-withdraw-before-cover')
    _air_move(p,'right',p.tip('right')+[-.150,0,0],target='lid',
              held_guards=((ref,'left'),),tolerance=.008,maximum_step=.008)
    # Continue the unverified remaining close in this same real world. The
    # original source cover point, box target, release and native rubric stay.
    lid=p.s['lid_geometry'];target=p.body_point(lid['box_ref'],lid['box_rim_center_local']);matrix=p.frame(lid['box_ref'])[1]
    target+=matrix[:,2]*lid['closed_offset_m'];p.stage('local-E24-original-real-cover-after-side-grasp')
    p.lower_place('lid',ref,'left',lid['cover_center_local'],target,matrix,
                  support=lid['box_ref'].get('actor',lid['box_ref'].get('contact_body')))
    p.operations.append(dict(stage='measured-single-axis-side-pinch',pitch=observations,actual_source_grasp_local=local.tolist(),extra_settle_required=False))
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start,
                original_lid_cover_attempt_completed=True,full_task_acceptance=False)
