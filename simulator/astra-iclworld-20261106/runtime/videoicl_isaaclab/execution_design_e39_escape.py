"""Leave an already released E39 tray using one measured empty-wrist escape."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_e39_package import _authorized,_empty,_log


def escape_empty_for_lid(policy,rotation_degrees=3.):
    from .execution_design_e39_delivery import open_mesh_preview,_screen_translations
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_local_pose_path import inspect_local_pose_path
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e39_delivery import _static_obstacles
    from .execution_design_e33_grasp import actual_mesh
    from .author_orientation import _axis_angle
    _authorized(policy);side='left';_empty(policy,side,contact_free=True)
    state,contacts=policy.snapshot()
    if any(state['work_tray']['grasp'])or frozenset(('work_tray','protective_box'))not in contacts:
        raise ToolExecutionError('E39 empty escape needs the actually released boxed tray')
    anchors={n:policy.frame(dict(actor=n))for n in policy.d['reference_objects']}
    def guard():
        _empty(policy,side,contact_free=True);now,contact=policy.snapshot()
        if any(now['work_tray']['grasp'])or frozenset(('work_tray','protective_box'))not in contact:
            raise ToolExecutionError('E39 empty escape disturbed boxed tray support')
        if any(frozenset((n,'work_tray'))not in contact for n in policy.d['target_members']):
            raise ToolExecutionError('E39 empty escape disturbed carried pieces')
        for n,(p,r)in anchors.items():
            pp,rr=policy.frame(dict(actor=n))
            if np.linalg.norm(pp-p)>.002 or np.linalg.norm(rr-r)>.02:raise ToolExecutionError('E39 empty escape moved reference')
    current=np.asarray(policy.a.tcp_rotation_task(side));tcp=policy.tip(side).copy()
    if not 0<float(rotation_degrees)<=10.:raise ToolExecutionError('Unreviewed E39 empty escape angle')
    target=_axis_rotation([0,1,0],np.deg2rad(float(rotation_degrees)))@current
    turns=public_rotation_poses(tcp,current,target);local=open_mesh_preview(policy,side)
    obstacles=_static_obstacles(policy,set())
    obstacles.extend(actual_mesh(policy.a,'right',n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers))
    if not rotation_clear(local,tcp,current,turns,obstacles,table_bounds_task(policy.a.scene)['top']):
        raise ToolExecutionError('E39 measured empty escape arc blocked')
    destination=np.array([-.19,float(tcp[1]),float(tcp[2])]);poses=turns+[dict(position=destination.tolist(),rotation=target.tolist())]
    # A restored empty wrist may already be 0.1mrad from its hard limit.
    # Preserve native hard limits and actual author 2mm/0.05rad tolerances;
    # an additional 0.02rad engineering margin cannot describe this escape.
    options=dict(minimum_joint_margin_rad=0.,max_joint_step_rad=.60,max_rotation_step_rad=np.deg2rad(2),position_tolerance_m=.002,orientation_tolerance_rad=.05)
    path=inspect_local_pose_path(policy.a,policy.c,side,poses,**options)
    _log(policy,'empty-pitch-and-retreat-preflight',path=path,rotation_degrees=float(rotation_degrees),source_initial_full_positive=False)
    if not path['feasible']:raise ToolExecutionError('E39 measured empty escape lacks continuous native hard-limit path')
    _screen_translations(policy,side,local,target,[tcp,destination],set())
    policy.stage('e39-empty-pitch-escape')
    actual_path=None
    for _ in range(4):
        guard();axis,angle=_axis_angle(target@np.asarray(policy.a.tcp_rotation_task(side)).T)
        if angle<np.deg2rad(.5):break
        i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
        policy.act(side,token,degrees=min(7.,abs(float(np.rad2deg(angle*axis[i])))))
        from .execution_design_probe import persist_engineering_checkpoint
        persist_engineering_checkpoint(policy.a,policy.a.out.parent.name)
        now=np.asarray(policy.a.tcp_rotation_task(side));actual_path=inspect_local_pose_path(policy.a,policy.c,side,[dict(position=destination.tolist(),rotation=now.tolist())],**options)
        _log(policy,'actual-empty-escape-after-turn',path=actual_path)
        if actual_path['feasible']:break
    else:raise ToolExecutionError('E39 actual reviewed empty turn failed')
    guard()
    if actual_path is None or not actual_path['feasible']:raise ToolExecutionError('Actual E39 empty turn did not unlock nearward route')
    policy.stage('e39-empty-unlocked-nearward-retreat');policy.move(side,destination,guard)
    policy._e39_home[side]=policy.tip(side).copy()
    policy.stage('e39-empty-clear-for-lid');policy.wait(1);guard()
