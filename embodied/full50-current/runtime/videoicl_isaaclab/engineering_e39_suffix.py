"""Engineering-only E39 phase suffixes after a separately validated reset.

No native state writes or pickup replay. The checkpoint dispatcher owns reset
validation; this module rechecks real contact invariants before public actions.
A suffix result is never a full source-initial-state task positive.
"""
from .execution_design_expert import ExecutionDesignAuthor
from .realworld_tool_expert import ToolExecutionError


def verify_released_boxed_tray(policy,package):
    import numpy as np
    from itertools import product
    state,contacts=policy.snapshot();box=package['container']
    if any(state['work_tray']['grasp']):return False
    if frozenset(('work_tray',box))not in contacts:return False
    if any(frozenset((n,'work_tray'))not in contacts for n in policy.d['target_members']):return False
    box_p=np.asarray(state[box]['pos']);box_r=np.asarray(state[box]['mat'])
    for n in ['work_tray',*policy.d['target_members']]:
        obj=policy.objects[n];body=state[n];half=np.asarray(obj['size']);center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
        points=np.asarray(list(product(*zip(center-half,center+half))))@np.asarray(body['mat']).T+np.asarray(body['pos'])
        inside=(points-box_p)@box_r
        tolerance=float(policy.d.get('geometry_tolerance_m',.003))
        if np.any(inside.min(0)<np.asarray(package['lower'])-tolerance)or np.any(inside.max(0)>np.asarray(package['upper'])+tolerance):return False
    return True


def bounded_down_rotation(current,full,tray_rotation,maximum_degrees=3.):
    import numpy as np
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import _axis_rotation
    axis,angle=_axis_angle(np.asarray(full)@np.asarray(current).T)
    allowed=min(angle,np.deg2rad(maximum_degrees))
    while allowed>=np.deg2rad(.25):
        delta=_axis_rotation(axis,allowed)
        if float((delta@np.asarray(tray_rotation))[2,2])>=.996:
            return delta@np.asarray(current)
        allowed-=np.deg2rad(.25)
    raise ToolExecutionError('No additional down correction fits retained tray tilt margin')


def correct_held_wrist(policy,maximum_degrees=3.):
    """Small public correction after lifting the measured assembly clear.

    v17's axis-only acquisition left a 7.48 degree palm tilt, unlike the full
    downward pose used by its original endpoint screen. Do not rewrite q or
    claim a new grip: at most three degrees may be corrected under the real
    retained grip and actual carried-piece support, with mesh/path checks.
    """
    import numpy as np
    from itertools import product
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import _axis_rotation
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_local_pose_path import inspect_local_pose_path
    from .execution_design_e39_package import body_bounds
    from .execution_design_thin_edge import table_bounds_task
    if not 0<maximum_degrees<=3.:raise ToolExecutionError('E39 held correction exceeds reviewed bound')
    a=policy.a;side='left';ref=policy.ref('work_tray');state=policy.snapshot()[0]
    anchors={n:(np.asarray(state[n]['pos']).copy(),np.asarray(state[n]['mat']).copy())for n in policy.d['reference_objects']}
    def guard():
        policy.require_held(ref,side);now,contacts=policy.snapshot()
        if float(now['work_tray']['mat'][2,2])<.995:raise ToolExecutionError('Held E39 tray exceeded its existing tilt guard')
        if any(frozenset((n,'work_tray'))not in contacts for n in policy.d['target_members']):
            raise ToolExecutionError('Held E39 correction lost actual T support')
        for n,(p,r)in anchors.items():
            if np.linalg.norm(np.asarray(now[n]['pos'])-p)>.002 or np.linalg.norm(np.asarray(now[n]['mat'])-r)>.02:
                raise ToolExecutionError('Held E39 correction disturbed reference')
    def geometry():
        tcp=np.asarray(a.tip(side));rotation=np.asarray(a.tcp_rotation_task(side));local=[];obstacles=[]
        for n in ('panda_hand',*a.scene.embodiment.fingers):local.append((actual_mesh(a,side,n)-tcp)@rotation)
        carried={'work_tray',*policy.d['target_members']}
        for n in policy.objects:
            lo,hi=body_bounds(policy,n);vertices=np.asarray(list(product(*zip(lo,hi))))
            (local if n in carried else obstacles).append((vertices-tcp)@rotation if n in carried else vertices)
        for n in ('panda_hand',*a.scene.embodiment.fingers):obstacles.append(actual_mesh(a,'right',n))
        for fixture in policy.spec.get('fixtures',[]):
            if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed held E39 fixture')
            c=np.asarray([*fixture['xy'],fixture['z']]);h=np.asarray(fixture['size']);obstacles.append(np.asarray(list(product(*zip(c-h,c+h)))))
        return tcp,rotation,local,obstacles
    guard();tcp,current,local,obstacles=geometry()
    full=min(physical_grasp_targets(a,policy.c,side,[0,0,1],[1,0,0]),key=lambda r:_axis_angle(np.asarray(r)@current.T)[1])
    desired=bounded_down_rotation(current,full,policy.snapshot()[0]['work_tray']['mat'],maximum_degrees)
    lift_amount=None
    for candidate in (0.,.008,.013,.018):
        lifted=tcp+[0,0,candidate]
        turns=public_rotation_poses(lifted,current,desired)
        if not rotation_clear(local,lifted,current,turns,obstacles,table_bounds_task(a.scene)['top']):continue
        poses=([dict(position=lifted.tolist(),rotation=current.tolist())]if candidate else[])+turns
        path=inspect_local_pose_path(a,policy.c,side,poses,minimum_joint_margin_rad=.02)
        if path['feasible']:lift_amount=candidate;break
    if lift_amount is None:raise ToolExecutionError('Held E39 lift/turn lacks a clear continuous native joint path')
    if lift_amount:
        policy.stage('e39-held-wrist-clearance-lift')
        policy.move_point(side,ref,policy.point(ref)+[0,0,lift_amount],guard)
    tcp,current,local,obstacles=geometry()
    desired=bounded_down_rotation(current,full,policy.snapshot()[0]['work_tray']['mat'],maximum_degrees)
    poses=public_rotation_poses(tcp,current,desired)
    if not rotation_clear(local,tcp,current,poses,obstacles,table_bounds_task(a.scene)['top']):
        raise ToolExecutionError('Actual lifted E39 partial wrist arc is blocked')
    path=inspect_local_pose_path(a,policy.c,side,poses,minimum_joint_margin_rad=.02)
    if not path['feasible']:raise ToolExecutionError('Actual lifted E39 wrist path is locally inaccessible')
    policy.stage('e39-held-partial-down-correction')
    for _ in range(12):
        guard();axis,angle=_axis_angle(desired@np.asarray(a.tcp_rotation_task(side)).T)
        if angle<np.deg2rad(1.):return
        i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
        policy.act(side,token,degrees=min(3.,abs(float(np.rad2deg(angle*axis[i])))))
    raise ToolExecutionError('Held E39 partial wrist correction did not converge')


def solve(author,checkpoint,context):
    policy=ExecutionDesignAuthor(author)
    if policy.task!='E39' or not author.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E39 suffix requires isolated engineering authorization')
    if checkpoint.get('schema')!='engineering-native-checkpoint-v1':
        raise ToolExecutionError('E39 suffix requires the validated engineering checkpoint schema')
    entry=context.get('entry');options=context.get('context',{})
    package=next(p for p in policy.d['packages']if p['container']=='protective_box')
    old=getattr(author,'_execution_design_reference_authorized',False)
    author._execution_design_reference_authorized=True
    segment_passed=False
    try:
        if entry in ('e39-blue-place-and-complete','e39-held-piece-place-and-complete'):
            from .execution_design_e39_piece import complete_blue_suffix
            from .execution_design_e39_delivery import station_axis_contains
            complete_blue_suffix(policy,options)
            segment_passed=verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
            if not segment_passed:raise ToolExecutionError('E39 blue suffix lacks complete physical delivery')
        elif entry=='e39-packed-lid-and-complete':
            from .execution_design_e39_package import prepare_lid_from_empty_checkpoint,close_lid_by_contact
            from .execution_design_e39_delivery import station_axis_contains
            if not verify_released_boxed_tray(policy,package):raise ToolExecutionError('E39 lid suffix lost real packaged support')
            prepare_lid_from_empty_checkpoint(policy,options.get('initial_right_rotation_task'),force_neutral=bool(options.get('force_neutral_lid',False)))
            close_lid_by_contact(policy,package);policy.deliver()
            segment_passed=verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
            if not segment_passed:raise ToolExecutionError('E39 packed suffix lacks complete physical delivery')
        elif entry=='e39-tray-physical-insertion-and-complete':
            from .execution_design_e39_tray_yaw import align_loaded_yaw,center_for_insertion
            from .execution_design_e39_reference import carry_held_work_tray
            from .execution_design_e39_package import preflight_lid_phase,close_lid_by_contact
            from .execution_design_e39_delivery import station_axis_contains
            policy.require_held(policy.ref('work_tray'),'left')
            align_loaded_yaw(policy,package['container'],functional_insertion=True)
            center_for_insertion(policy,package['container'])
            carry_held_work_tray(policy,package['container'],[0,0,package['lower'][2]],policy.ref('work_tray'),'left',entry='seat')
            preflight_lid_phase(policy);close_lid_by_contact(policy,package);policy.deliver()
            segment_passed=verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
            if not segment_passed:raise ToolExecutionError('E39 physical-insertion suffix lacks actual complete delivery')
        elif entry=='e39-tray-align-and-complete':
            from .execution_design_e39_reference import carry_held_work_tray
            from .execution_design_e39_package import preflight_lid_phase,close_lid_by_contact
            from .execution_design_e39_delivery import station_axis_contains
            ref=policy.ref('work_tray');policy.require_held(ref,'left')
            carry_held_work_tray(policy,package['container'],[0,0,package['lower'][2]],ref,'left',entry='align')
            preflight_lid_phase(policy);close_lid_by_contact(policy,package);policy.deliver()
            segment_passed=verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
            if not segment_passed:raise ToolExecutionError('E39 loaded-align suffix lacks complete physical delivery')
        elif entry=='e39-pregrip-down-and-seat':
            # v3's latest held state cannot be repaired by more wrist turns:
            # the true tray is already tilted 5.21 degrees. Resume the last
            # measured pre-GRASP stage and physically establish the corrected
            # complete downward pose before acquiring this same tray.
            from .execution_design_e39_reference import place_work_tray
            if any(v['grasp'][0]for v in policy.snapshot()[0].values()):
                raise ToolExecutionError('E39 pregrip suffix unexpectedly holds a payload')
            place_work_tray(policy,package['container'],[0,0,package['lower'][2]])
            segment_passed=verify_released_boxed_tray(policy,package)
            if not segment_passed:raise ToolExecutionError('E39 regrip suffix lacks released contained physical end state')
        elif entry in ('e39-held-wrist-correction-and-seat','e39-tray-x-and-seat','e39-tray-align-and-seat','e39-tray-seat'):
            from .execution_design_e39_reference import carry_held_work_tray
            ref=policy.ref('work_tray');side=options.get('hand','left')
            policy.require_held(ref,side)
            if entry=='e39-held-wrist-correction-and-seat':correct_held_wrist(policy)
            stage={'e39-held-wrist-correction-and-seat':'x','e39-tray-x-and-seat':'x','e39-tray-align-and-seat':'align','e39-tray-seat':'seat'}[entry]
            carry_held_work_tray(policy,package['container'],[0,0,package['lower'][2]],ref,side,entry=stage)
            segment_passed=verify_released_boxed_tray(policy,package)
            if not segment_passed:raise ToolExecutionError('E39 tray suffix lacks released contained physical end state')
        elif entry=='e39-package-wall-only':
            if options.get('clear_protected_rim_first',False):
                from .execution_design_e39_delivery import lift_clear_of_protected_rim
                lift_clear_of_protected_rim(policy)
            if options.get('yaw_finish',False):
                from .execution_design_e39_delivery import push_wall,wall_yaw_offset,station_axis_contains
                push_wall(policy,'right',0,.233,resume_contact=True,cross_offset=wall_yaw_offset(policy,maximum=.060),yaw_feedback=True,yaw_correction=True)
                segment_passed=verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
                if not segment_passed:raise ToolExecutionError('E39 measured wall yaw correction did not enter actual whole-package station')
            else:
                from .execution_design_e39_delivery import deliver_wall_package
                segment_passed=deliver_wall_package(policy,resume_left=bool(options.get('resume_left_contact',False)),from_right=bool(options.get('from_right_handover',False)))
                if not segment_passed:raise ToolExecutionError('E39 wall-only suffix lacks actual complete delivery')
        elif entry=='e39-package-wall-left':
            from .execution_design_e39_delivery import deliver_supported_package
            segment_passed=deliver_supported_package(policy,resume_left=bool(options.get('resume_contact',False)))
            if not segment_passed:raise ToolExecutionError('E39 left wall suffix lacks actual box endpoint')
        elif entry=='e39-package-cover-drag':
            from .execution_design_e39_delivery import deliver_supported_package
            segment_passed=deliver_supported_package(policy,from_cover=True,resume_cover=bool(options.get('resume_top_contact',False)))
            if not segment_passed:raise ToolExecutionError('E39 cover suffix lacks actual box endpoint')
        elif entry=='e39-package-wall-right-x':
            from .execution_design_e39_delivery import push_wall,wall_yaw_offset,station_axis_contains,record_loaded_package_com
            record_loaded_package_com(policy)
            segment_passed=push_wall(policy,'right',0,.225,cross_offset=wall_yaw_offset(policy),yaw_feedback=True)
            segment_passed=segment_passed and verify_released_boxed_tray(policy,package)and station_axis_contains(policy,0)and station_axis_contains(policy,1)
            if not segment_passed:raise ToolExecutionError('E39 final wall suffix lacks actual box endpoint')
        elif entry=='e39-empty-escape-and-lid':
            from .execution_design_e39_escape import escape_empty_for_lid
            from .execution_design_e39_package import preflight_lid_phase,close_lid_by_contact,_hinge_angle
            escape_empty_for_lid(policy,rotation_degrees=float(options.get('escape_degrees',8.)))
            preflight_lid_phase(policy);close_lid_by_contact(policy,package)
            segment_passed=verify_released_boxed_tray(policy,package)and abs(_hinge_angle(policy,package))<=package['lid_orientation_tolerance']
        elif entry=='e39-lid-contact':
            from .execution_design_e39_package import preflight_lid_phase,close_lid_by_contact
            preflight_lid_phase(policy)
            close_lid_by_contact(policy,package)
        elif entry=='e39-package-push':
            from .execution_design_e39_package import deliver_closed_package
            deliver_closed_package(policy)
        else:raise ToolExecutionError('Unknown E39 engineering suffix phase: '+str(entry))
        policy.wait(1)
        if segment_passed and options.get('original_source_initial_poses'):
            import json
            from .execution_design_e39_assisted_evidence import check
            state,contacts=policy.snapshot()
            proof=check(policy.spec,state,contacts,options['original_source_initial_poses'])
            (author.out/'checkpoint-assisted-native-predicates.private.json').write_text(json.dumps(proof,indent=2))
            if not proof['passed']:raise ToolExecutionError('E39 assisted endpoint fails original native snapshot predicates')
    finally:author._execution_design_reference_authorized=old
    return dict(task='E39',diagnostic_only=True,engineering_suffix_entry=entry,
        source_initial_state_full_positive=False,execution_finished=False,
        native_acceptance=False,segment_passed=segment_passed,actions=policy.c.steps-policy.start)
