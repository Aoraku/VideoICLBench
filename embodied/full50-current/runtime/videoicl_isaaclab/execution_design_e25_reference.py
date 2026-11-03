"""Source-pinned E25 engineering handle grasp, never a task/goal mutation."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3

# Source mesh cross sections at local X=-80mm, including baked source rotation
# and the same source-size normalization as spawn_source_asset. These are grasp
# choices only; the real robot must establish bilateral contacts and lift.
TAIL_GRASPS={
 'knife':dict(sha256='8d7e874a9fa51024264e6a9afb1b5c03cff586fc26f5b1eb417de57445dac18d',
   point=[-.0800232742168226,.001082251082251079,.0036116929665316764],
   section_lower=[-.08598799050411954,-.007308569566634085,-.0033030768514639487],
   section_upper=[-.07405855792952568,.009473071731136243,.010526462784527301]),
 'fork':dict(sha256='134d334cc03851a697ada7cd31bfec4218ba3917a9dae084fcda4c6b62c918d6',
   point=[-.07999784477818203,.0000035047628596839367,-.0013845701510129952],
   section_lower=[-.0859545700137249,-.010462582136235979,-.0043749024922943806],
   section_upper=[-.07404111954263914,.010469591661955347,.0016057621902683902]),
}


def grasp_spec(author,obj):
    spec=author.scene.spec
    if (getattr(author,'_execution_design_reference_authorized',False)
            and spec.get('execution_design',{}).get('revision')==REVISION_V3
            and spec.get('id')=='E25' and spec.get('variant')=='B'
            and obj.get('id')in ('spoon','knife','fork')):
        from .execution_design_e25_b_reference import candidate_grasp
        return candidate_grasp(author,obj)
    if not(getattr(author,'_execution_design_reference_authorized',False)
      and spec.get('execution_design',{}).get('revision')==REVISION_V3
      and spec.get('id')=='E25' and spec.get('variant')=='A' and obj.get('id')in TAIL_GRASPS):return obj
    record=TAIL_GRASPS[obj['id']]
    if obj.get('source_asset',{}).get('sha256')!=record['sha256']:
        raise ValueError('E25 engineering handle grasp requires exact reviewed source mesh')
    point=np.asarray(record['point']);lo=np.asarray(record['section_lower']);hi=np.asarray(record['section_upper'])
    if np.any(point<=lo)or np.any(point>=hi)or not .004<hi[2]-lo[2]<.025 or not .008<hi[1]-lo[1]<.04:
        raise ValueError('Invalid reviewed E25 handle cross section')
    result=deepcopy(obj);result['grasp_point_local']=record['point'].copy()
    return result


def receiver_pitch_candidate(author,side,targets):
    """Reject-only E25A candidate; physical empty-hand rotation is separate."""
    import itertools,math
    from .realworld_tool_expert import _axis_rotation
    s=author.scene.spec
    if (s['id']!='E25' or s['variant']!='A' or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or not getattr(author,'_execution_design_reference_authorized',False)
            or author.scene.embodiment.name!='franka'):
        raise ValueError('E25A v3 Panda engineering receiver candidate required')
    base=np.asarray(author.tcp_rotation_task(side),float)
    # Actual hand Y is the finger-separation axis. Rotating around that axis
    # preserves the physical pinch line; eight degrees was checked against the
    # captured native Jacobian, and is rechecked in every fresh world below.
    delta=_axis_rotation(base[:,1],math.radians(8));chosen=delta@base
    geometry=author.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise ValueError('Measured finger meshes required')
    tip=np.asarray(author.tip(side),float);corners=[]
    for f in geometry['fingers']:
        lo=np.asarray(f['aabb_min_task_m']);hi=np.asarray(f['aabb_max_task_m'])
        corners.extend([np.where(sign,hi,lo)-tip for sign in itertools.product((False,True),repeat=3)])
    floor=.8+ .0003-float((np.asarray(corners)@delta.T)[:,2].min())
    proposals=[]
    for t in targets:
        row=deepcopy(t);row['rotation']=(np.asarray(t['rotation'])@base.T@chosen).tolist()
        row['position']=list(t['position']);row['position'][2]=max(float(row['position'][2]),floor)
        proposals.append(row)
    return chosen,proposals


def prepare_receiver(author,side,name,goal,approach_z,grasp_xy):
    """Apply a checked private receiver pose only through public rotations."""
    if '_e25_receiver_rotation_task'not in goal:return
    import math
    from .author_orientation import _axis_angle
    s=author.scene.spec
    if (s['id']!='E25' or s['variant']not in ('A','B') or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or not getattr(author,'_execution_design_reference_authorized',False)
            or not author.control_report.get('engineering_reference_only') or getattr(author,'smooth',False)
            or '_e07_after_relay'not in goal):raise ValueError('E25 A/B actual released relay required')
    state,contacts=author.c.snapshot()
    if any(any(b.get('grasp',[]))for b in state.values())or frozenset((name,'table'))not in contacts:
        raise RuntimeError('Receiver orientation requires genuinely released supported payload')
    desired=np.asarray(goal['_e25_receiver_rotation_task'],float)
    if desired.shape!=(3,3)or not np.allclose(desired.T@desired,np.eye(3),atol=1e-6)or np.linalg.det(desired)<.999:
        raise ValueError('Invalid checked receiver rotation')
    height=max(.92,float(approach_z),float(author.tip(side)[2]))
    author.stage='e25-receiver-empty-orientation-'+name
    author.move_generated({side:[*author.tip(side)[:2],height]})
    author.move_generated({side:[*grasp_xy,height]})
    if s['variant']=='A'and side=='left'and name=='knife':
        from .execution_design_e25_a_receiver import settled_receiver_rotation
        desired=settled_receiver_rotation(author,side,name,desired)
    initial=np.asarray(author.tip(side),float);labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    # Public rotation receipts may be partial while the measured hand still
    # converges (A native 40-step attempt retained 0.35--0.47deg per action).
    # Bound work with actual angular progress, not an arbitrary 40-call cutoff.
    from .execution_design_e25_b_reference import _joints
    import json
    errors=[]
    for iteration in range(160):
        state,_=author.c.snapshot()
        if any(any(b.get('grasp',[]))for b in state.values()):raise RuntimeError('Empty receiver unexpectedly holds an object')
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose'or geometry['lowest_z_task_m']<.84:
            raise RuntimeError('Actual receiver fingers lack above-table rotation clearance')
        if np.linalg.norm(np.asarray(author.tip(side))-initial)>.025:raise RuntimeError('Receiver rotation left measured TCP envelope')
        joints,limits,names=_joints(author,side)
        if (not np.isfinite(joints).all()or not np.isfinite(limits).all()
                or np.any(joints<=limits[:,0]+.02)or np.any(joints>=limits[:,1]-.02)):
            raise RuntimeError('E25 empty receiver actual joint limit approached')
        axis,angle=_axis_angle(desired@np.asarray(author.tcp_rotation_task(side)).T)
        errors.append(float(angle))
        if angle<math.radians(.75):
            obj=next(o for o in s['objects']if o['id']==name);jaw=state[name]['mat']@np.asarray(obj['grasp_axis_local']);jaw/=np.linalg.norm(jaw)
            if abs(float(desired[:,1]@jaw))<math.cos(math.radians(5)):raise RuntimeError('Settled relay pinch axis changed beyond checked receiver alignment')
            author.control_report['e25_receiver_orientation']=dict(object=name,side=side,actual_error_rad=float(angle),public_rotations_only=True,native_grasp_verified=False,public_rotation_count=iteration)
            return
        if len(errors)>12 and min(errors[-12:])>min(errors[:-12])-math.radians(.1):
            raise RuntimeError('E25 empty receiver actual orientation stopped progressing')
        k=int(np.argmax(np.abs(axis)));token=labels[k][int(axis[k]<0)]
        degrees=min(4.,max(.5,abs(math.degrees(angle*axis[k]))))
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
        feedback=author.c.action_feedback()['control_feedback'][side]
        if hasattr(author,'out'):
            with (author.out/'e25-receiver-orientation.private.jsonl').open('a')as stream:
                stream.write(json.dumps(dict(object=name,side=side,iteration=iteration,measured_error_rad=float(angle),
                    actual_joints_rad=joints.tolist(),joint_names=list(names),joint_limits_rad=limits.tolist(),
                    token=token,requested_degrees=degrees,public_feedback=feedback))+'\n')
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0):
            raise RuntimeError('E25 empty receiver public local IK blocked')
    raise RuntimeError('Checked E25 receiver orientation did not converge through public actions')


def prepare_source_palm(author,side,name,goal):
    """Level the measured empty palm before reviewed source utensil pinches.

    A native failure showed one open finger touching the table while the other
    was 7.7mm higher. This changes only the empty hand, not the source knife,
    its grasp point, receiver pitch, placement goal, or native rule.
    """
    s=author.scene.spec
    if (s.get('id')!='E25' or s.get('variant')not in ('A','B','C')
            or (s.get('variant')=='A'and name!='knife')
            or (s.get('variant')=='C'and name not in ('knife','fork'))
            or (s.get('variant')=='C'and name=='fork'and '_e07_after_relay'in goal)
            or (s.get('variant')=='B'and name not in ('spoon','knife','fork'))
            or ('_e07_after_relay'in goal and s.get('variant')!='C')):return
    from .execution_design import source_sha256
    from .author_orientation import panda_downward_grasp_delta,_axis_angle
    import math
    if (s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('source_sha256')!=source_sha256(REVISION_V3)
            or not getattr(author,'_execution_design_reference_authorized',False)
            or not author.control_report.get('engineering_reference_only') or author.smooth
            or author.scene.embodiment.name!='franka'):
        raise ValueError('Reviewed E25 v3 empty source-palm engineering required')
    obj=next(o for o in s['objects']if o['id']==name)
    if s['variant']=='C':
        # C keeps its original grasp points and zero-yaw goals. Its knife and
        # source fork use the identical reviewed meshes. The native fork lift
        # reached joint6's stop before losing a real bilateral grasp; prepare
        # the empty palm before loading that wrist.
        if obj.get('source_asset',{}).get('sha256')!=TAIL_GRASPS[name]['sha256']:
            raise ValueError('E25 C source palm requires exact reviewed '+name+' mesh')
    else:
        grasp_spec(author,obj)  # Check exact source identity; do not change scene.
    state,contacts=author.c.snapshot()
    if any(any(b.get('grasp',[]))for b in state.values())or frozenset((name,'table'))not in contacts:
        raise RuntimeError('E25 source palm preparation requires actual released table support')
    desired_axis=np.asarray(state[name]['mat'])@np.asarray(obj['grasp_axis_local'])
    if s['variant']=='C'and name=='knife'and abs(float(desired_axis[2]))>np.sin(np.deg2rad(6)):
        # A genuine relay release can leave the handle rolled about its long
        # axis while that long axis still rests horizontally on the table.
        # Use a horizontal real pinch candidate at the unchanged material
        # point; bilateral native contacts remain mandatory after closing.
        longitudinal=np.asarray(state[name]['mat'])[:,0]
        if abs(float(longitudinal[2]))>np.sin(np.deg2rad(6))or np.linalg.norm(desired_axis[:2])<.5:
            raise RuntimeError('E25 C rolled knife lacks a horizontal supported handle')
        observed=desired_axis.copy();desired_axis=desired_axis.copy();desired_axis[2]=0.;desired_axis/=np.linalg.norm(desired_axis)
        author.control_report['e25_c_rolled_knife_pinch_candidate']=dict(actual_source_jaw_axis_task=observed.tolist(),
            horizontal_pinch_heading_task=desired_axis.tolist(),source_grasp_and_axis_unchanged=True,native_grasp_validated=False)
    tip=np.asarray(author.tip(side),float);author.stage='e25-source-empty-palm-'+name
    author.move_generated({side:[*tip[:2],max(.96,float(tip[2]))]})
    initial=np.asarray(author.tip(side),float)
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(40):
        state,contacts=author.c.snapshot()
        if any(any(b.get('grasp',[]))for b in state.values())or frozenset((name,'table'))not in contacts:
            raise RuntimeError('E25 empty source orientation changed actual support/hold')
        geometry=author.finger_geometry(side)
        if (geometry.get('source')!='actual_collision_mesh_current_body_pose'
                or geometry['lowest_z_task_m']<.85 or np.linalg.norm(np.asarray(author.tip(side))-initial)>.025):
            raise RuntimeError('E25 source empty palm lost measured rotation clearance')
        fingers=geometry['fingers'];jaw=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
        delta=panda_downward_grasp_delta(author.tcp_rotation_task(side),jaw,desired_axis)
        axis,angle=_axis_angle(delta)
        if angle<math.radians(.75):
            author.control_report['e25_source_palm']=dict(object=name,side=side,actual_orientation_error_rad=angle,
                finger_lowest_z_task_m=geometry['lowest_z_task_m'],public_actions_only=True,native_grasp_validated=False)
            return
        k=int(np.argmax(np.abs(axis)));token=labels[k][int(axis[k]<0)]
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',
                   rotation_deg=min(4.,max(.5,abs(math.degrees(angle*axis[k])))))
        feedback=author.c.action_feedback()['control_feedback'][side]
        if feedback.get('status')=='blocked' or feedback.get('joint_limit_names'):
            raise RuntimeError('E25 source empty palm public IK blocked')
    raise RuntimeError('E25 actual source palm did not converge through public rotations')
