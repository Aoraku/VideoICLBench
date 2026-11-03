"""Acquire the remaining original right shoe after the measured left release."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError

BRANCHES=frozenset(('complete_right_after_left',))


def _native_pair(p):
    from .execution_design_e08_branch import _native_landing_conditions
    rows={actor:_native_landing_conditions(p,dict(actor=actor,support='box'))for actor in('left_shoe','right_shoe')}
    return dict(actors=rows,all_original_conditions=all(all(r[k]for k in('correct_label_direction','inside_original_cavity','actual_supported_in_box'))and not any(r['native_grasp'])and r['hand_force_n']==0 for r in rows.values()))


def run_branch(author,context,branch_name):
    from .execution_design_e08_branch import _policy,prepare_context,prepare_new_source_context,run_branch as suffix,_native_landing_conditions
    from .execution_design_e08_midfoot import SoleAcquisitionGeometry,native_local_com,midfoot_section
    from .execution_design_branch_geometry import install_public_guard,collision_parts_task
    from .execution_design_e08_shape_guard import SourceShoeGeometry as HeldGeometry
    from .execution_design_branch_rotation import turn_to_fixed_goal,finish_accepted_public_rotation
    from .execution_design_thin_edge import material_collision_points_task
    if branch_name not in BRANCHES:raise ValueError('Unknown E08 remaining source-shoe branch')
    p=_policy(author,context);start=p.c.steps;actor='right_shoe';side='right'
    if context.get('branch_params',{}).get('coarse_source_resume')is True:
        from .execution_design_e08_source_resume import run
        return run(author,context)
    if context.get('branch_params',{}).get('capture_native_joint_packing')is True:
        import json,hashlib
        state,_=p.snapshot()
        if any(any(o['grasp'])for o in state.values()):raise ToolExecutionError('Packing geometry capture requires actually empty hands')
        evidence=dict(task='E08',variant=p.variant,native_action=p.c.steps,original_spec=p.spec,objects={})
        for name in('box','left_shoe','right_shoe'):
            pos=np.asarray(state[name]['pos']);r=np.asarray(state[name]['mat']);pieces=collision_parts_task(p,name);source=material_collision_points_task(p,dict(actor=name))
            evidence['objects'][name]=dict(actual_position_task=pos.tolist(),actual_rotation_task=r.tolist(),
                actual_native_cooked_pieces_local=[((a-pos)@r).tolist()for a in pieces],complete_source_collision_points_local=((source-pos)@r).tolist())
        raw=json.dumps(evidence).encode();path=author.out/'e08-native-joint-packing-geometry.private.json';path.write_bytes(raw)
        return dict(branch=branch_name,local_completed=True,public_actions=0,read_only_geometry_capture=True,evidence_path=str(path),evidence_sha256=hashlib.sha256(raw).hexdigest(),whole_task_score=None)
    if (p.variant=='A'and context.get('actor')==actor and context.get('side')==side
            and context.get('e08_pair_phase')=='right_orient_and_place'and context.get('midfoot_grasp_strategy')=='native721_right_upper_near_actual_com_v1'):
        p.require_held(dict(actor=actor),side)
        if context.get('branch_params',{}).get('release_measured_right_here')is True:
            result=suffix(author,context,'release_source_left_here',_source_actor=actor)
            return _pair_readback(p,context,start,branch_name,result)
        if context.get('branch_params',{}).get('up_from_measured1259')is True:
            from .execution_design_e08_shape_guard import UpwardBoxDepartureGeometry
            up=UpwardBoxDepartureGeometry(p,actor,side,context);install_public_guard(p,up)
            while True:
                up();low=float(material_collision_points_task(p,dict(actor=actor))[:,2].min());rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'))
                if low>=rim+.070:break
                p.act(side,'UP',mm=12.)
            context['material_clearance_z']=max(float(context['material_clearance_z']),float(p.point(dict(actor=actor,local=context['control_local']))[2]))
        if context.get('branch_params',{}).get('raise_before_right_orientation')is True:
            # Clear the failed old accepted rotation through a small explicit
            # safe public turn before UP; UP alone retains the old targetR.
            up=HeldGeometry(p,actor,side);install_public_guard(p,up)
            used=int(context.get('rotation_commands_used',0))
            if not 0<=used<120:raise ToolExecutionError('Original right-shoe120 rotation bound exhausted before safe reanchor')
            context['rotation_commands_used']=used+1;p.act(side,'ROTATE_CW',degrees=1.)
            finish_accepted_public_rotation(p,side,up)
            while True:
                up();low=float(material_collision_points_task(p,dict(actor=actor))[:,2].min());rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'))
                if low>=rim+.070:break
                p.act(side,'UP',mm=min(12.,max(p.min_mm,(rim+.075-low)*1000)))
            context['material_clearance_z']=max(float(context['material_clearance_z']),float(p.point(dict(actor=actor,local=context['control_local']))[2]))
            context['right_raised_for_actual_cavity_correction']=dict(actual_payload_min_z=low,actual_cooked_rim_z=rim)
        if context.get('branch_params',{}).get('right_yaw_detour_direction')=='CW':
            context.update(right_yaw_detour_direction='CW',right_yaw_detour_reason='Actual1136 q7lowerstop; public CW from actualpose supersedes unreachable oldCCW target; original actor goal/count unchanged')
        result=suffix(author,context,'complete_left_from_held',_source_actor=actor)
        return _pair_readback(p,context,start,branch_name,result)
    if (p.variant=='A'and context.get('actor')=='right_shoe'and context.get('side')=='right'
            and context.get('e08_pair_phase')in('right_lift','right_transport_stage')and context.get('midfoot_grasp_strategy')=='native721_right_upper_near_actual_com_v1'):
        p.require_held(dict(actor=actor),side)
        return _finish_right_from_hold(p,context,start,branch_name)
    if p.variant!='A'or context.get('actor')!='left_shoe':raise ValueError('Measured E08A completed left-shoe boundary required')
    state,_=p.snapshot()
    if any(any(o['grasp'])for o in state.values())or not p.contact(actor,'table'):
        raise ToolExecutionError('Both hands must be empty and the remaining right shoe supported by Table')
    if p.objects[actor]['source_asset']['sha256']!='d47101e06a14ea63e22b76f3444fce6bd4faf4e1a33ed3c38c0cd603c339e3b2':raise ValueError('Original right source shoe required')
    # Actual empty hand motion supplies fresh native contacts after cold restore.
    park=SoleAcquisitionGeometry(p,actor,'left');install_public_guard(p,park);p.act('left','STILL')
    landed=_native_landing_conditions(p,context)
    if not all(landed[k]for k in('correct_label_direction','inside_original_cavity','actual_supported_in_box')):
        raise ToolExecutionError('Previously released left shoe no longer meets actual native conditions')
    history=context.setdefault('source_actor_rotation_history',{})
    history['left_shoe']=dict(rotation_commands_used=int(context.get('rotation_commands_used',0)),original_rotation_limit=120,actual_landing=landed)
    context['e08_pair_phase']='empty_left_park';tip=p.tip('left');park.move(np.array([tip[0],.48,tip[2]]));park.move(np.array([-.2,.48,p.tip('left')[2]]))
    state,_=p.snapshot();right_context=prepare_context(author,state,p.c.steps,actor=actor)
    right_context['side']='right'  # Explicit measured right-arm route, not Y-based legacy hand selection.
    context.update(right_context);context.update(midfoot_grasp_strategy='native721_right_upper_near_actual_com_v1',e08_pair_phase='right_empty_stage',source_actor_rotation_history=history)
    p=_policy(author,context);p.max_mm=min(12.,float(p.a.scene.embodiment.config['control']['step_mm'][1]));empty=SoleAcquisitionGeometry(p,actor,side);install_public_guard(p,empty)
    tip=p.tip(side);high=max(float(tip[2]),.98);empty.move(np.array([-.2,tip[1],high]));empty.move(np.array([-.2,.18,high]));empty.move(np.array([-.2,.18,.98]))
    state,_=p.snapshot();y=np.asarray(state[actor]['mat'])[:,1].copy();y[2]=0.;y/=np.linalg.norm(y);z=np.array([0.,0.,-1.]);target=np.column_stack((np.cross(y,z),y,z))
    def count():
        used=int(context.get('rotation_commands_used',0))
        if not 0<=used<120:raise ToolExecutionError('Original right-shoe120 rotation bound exhausted')
        context['rotation_commands_used']=used+1
    context['e08_pair_phase']='right_empty_turn';context['right_empty_fixed_turn']=turn_to_fixed_goal(p,side,target,empty,1.,count)
    com,mass=native_local_com(p,actor);position,r=p.frame(dict(actor=actor));points=(material_collision_points_task(p,dict(actor=actor))-position)@r;section=midfoot_section(points,com)
    context.update(right_actual_com_grasp_section=section,midfoot_actual_com_local=com.tolist(),midfoot_actual_mass_kg=mass,midfoot_source_grasp_local=section['grasp_local'],e08_pair_phase='right_approach')
    point=p.point(dict(actor=actor,local=section['grasp_local']));high=float(p.tip(side)[2]);empty.move(np.array([point[0],p.tip(side)[1],high]));empty.move(np.array([*point[:2],high]));empty.move(point,tolerance=.0008)
    empty.check(closing=True);empty.mode='closing';context['e08_pair_phase']='right_native_grasp'
    for _ in range(5):
        p.act(side,'GRASP')
        if p.held(dict(actor=actor),side):break
    else:raise ToolExecutionError('Actual right midfoot COM pinch lacks bilateral hold')
    context.update(midfoot_first_actual_hold_action=p.c.steps,carried_payload=[actor,side],e08_pair_phase='right_lift');empty.mode='held';progress=[]
    return _finish_right_from_hold(p,context,start,branch_name)


def _finish_right_from_hold(p,context,start,branch_name):
    from .execution_design_e08_branch import prepare_new_source_context,run_branch as suffix
    from .execution_design_e08_midfoot import SoleAcquisitionGeometry
    from .execution_design_branch_geometry import install_public_guard,collision_parts_task
    from .execution_design_e08_shape_guard import SourceShoeGeometry as HeldGeometry
    from .execution_design_branch_rotation import finish_accepted_public_rotation
    from .execution_design_thin_edge import material_collision_points_task
    actor='right_shoe';side='right';author=p.a;history=context['source_actor_rotation_history'];progress=[]
    empty=SoleAcquisitionGeometry(p,actor,side,mode='held',allow_table_departure=True);install_public_guard(p,empty)
    def count():
        used=int(context.get('rotation_commands_used',0))
        if not 0<=used<120:raise ToolExecutionError('Original right-shoe120 rotation bound exhausted')
        context['rotation_commands_used']=used+1
    while True:
        empty();cloud=material_collision_points_task(p,dict(actor=actor));rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'));low=float(cloud[:,2].min())
        if low>rim+.025:break
        progress.append(low)
        if len(progress)>=13 and max(progress[-12:])-progress[-13]<.0003:raise ToolExecutionError('Actual right COM pinch makes no lift progress')
        p.act(side,'UP',mm=12.)
    guard=HeldGeometry(p,actor,side);install_public_guard(p,guard)
    context['e08_pair_phase']='right_transport_stage'
    transport_above_rim(p,context,guard,np.array([-.2,-.08]))
    context.update(prepare_new_source_context(author,context));context['midfoot_grasp_strategy']='native721_right_upper_near_actual_com_v1';context['material_clearance_z']=float(p.point(dict(actor=actor,local=context['control_local']))[2]);context['e08_pair_phase']='right_orient_and_place'
    # This measured positive-localY jaw branch begins near negative q7. Move
    # clockwise inward; then keep the unchanged absolute source actor goal.
    from .author_orientation import _axis_angle
    state,_=p.snapshot();_,angle=_axis_angle(np.asarray(context['target_actor_rotation'])@np.asarray(state[actor]['mat']).T)
    if angle>math.radians(170):
        context['right_yaw_detour_direction']='CW';count();p.act(side,'ROTATE_CW',degrees=10.);finish_accepted_public_rotation(p,side,guard)
    result=suffix(author,context,'complete_left_from_held',_source_actor=actor)
    return _pair_readback(p,context,start,branch_name,result)


def _pair_readback(p,context,start,branch_name,result):
    history=context['source_actor_rotation_history']
    history['right_shoe']=dict(rotation_commands_used=int(context['rotation_commands_used']),original_rotation_limit=120)
    context['e08_pair_phase']='native_pair_readback';pair=_native_pair(p)
    if not pair['all_original_conditions']:raise ToolExecutionError('Actual two-shoe native geometry/direction/release/support failed: '+str(pair))
    context['e08_pair_phase']='complete_both_source_shoes'
    return dict(branch=branch_name,task='E08',local_completed=True,actions=p.c.steps-start,right_suffix=result,native_pair_conditions=pair,source_actor_rotation_history=history,
        source_initial_full_acceptance=False,whole_task_score=None)


def transport_above_rim(p,context,guard,xy):
    """Recover real payload height before each horizontal public subaction."""
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_branch_geometry import install_public_guard
    actor='right_shoe';side='right';install_public_guard(p,guard)
    while True:
        guard();cloud=material_collision_points_task(p,dict(actor=actor));rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'));low=float(cloud[:,2].min());tip=p.tip(side);error=np.asarray(xy)-tip[:2]
        context['right_transport_actual_clearance']=dict(payload_min_z=low,actual_cooked_rim_top_z=rim,xy_error_m=error.tolist())
        if low<rim+.025:
            p.act(side,'UP',mm=min(12.,max(p.min_mm,(rim+.035-low)*1000)));continue
        if max(abs(error))<=.002:return
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
        p.act(side,token,mm=min(12.,max(p.min_mm,abs(error[axis])*1000)))
