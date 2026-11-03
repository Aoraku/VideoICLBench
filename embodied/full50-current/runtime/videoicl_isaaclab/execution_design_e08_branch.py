"""Public-action E08 branches starting after a restored held-shoe checkpoint."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_e08_reference import MeasuredShoeAuthor
from .execution_design_branch_geometry import install_public_guard,public_rotation_holds
from .execution_design_e08_shape_guard import SourceShoeGeometry as HeldGeometry

REVISION='embodied50-execution-v3-20261102'
BRANCHES=frozenset(('adopt_source_plan','stage_ccw','yaw_ccw_chunk','yaw_short_chunk','place_left_to_release','complete_left_from_held','reset_left_on_table','release_source_left_here'))


def prepare_context(author,pickup_state,checkpoint_action=225,actor='left_shoe'):
    """Read original pickup-complete state to preserve lower_place parameters."""
    p=MeasuredShoeAuthor(author);side=p.hand_for(actor);state=pickup_state[actor];r=np.asarray(state['mat'],float)
    half=np.asarray(p.objects[actor]['size'],float);down=r.T@np.array([0.,0.,-1.]);active=abs(down)>1e-8
    local=np.asarray(p.objects[actor].get('local_bounds_center',[0,0,0]),float)+down*float(np.min(half[active]/abs(down[active])))
    box=p.s['containers']['box'];boxname=box['ref']['actor'];b=pickup_state[boxname];br=np.asarray(b['mat'],float)
    target=np.asarray(b['pos'],float)+br@np.asarray(p.geometry['box_positions'][actor],float)
    label=p.s['label_end'];labelbody=pickup_state[label['ref']['actor']];direction=np.asarray(labelbody['mat'])@np.asarray(label['point_local'])
    g=p.s['shoe_axes'][actor];axis=r@(np.asarray(g['toe_local'])-g['heel_local'])
    signs=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})[p.index]
    wanted=direction*signs[actor];yaw=math.atan2(wanted[1],wanted[0])-math.atan2(axis[1],axis[0]);rotation=_axis_rotation([0,0,1],yaw)@r
    return dict(task='E08',variant=p.variant,seed=int(p.spec['seed']),condition='I',revision=REVISION,checkpoint_action=int(checkpoint_action),policy_start_step=0,
                policy_action_budget=p.limit,actor=actor,side=side,control_local=local.tolist(),destination_point_task=target.tolist(),
                target_actor_rotation=rotation.tolist(),material_clearance_z=p.clearance,support=boxname,rotation_round_limit=120,rotation_commands_used=0)


def _policy(author,context):
    spec=author.scene.spec
    if (spec.get('id')!='E08' or spec.get('execution_design',{}).get('revision')!=REVISION
            or spec.get('seed')!=4201 or spec.get('execution_design',{}).get('condition')!='I'
            or not author.control_report.get('engineering_reference_only') or author.scene.embodiment.name!='franka'):
        raise ValueError('E08 v3 Panda engineering branch required')
    required=('task','variant','seed','condition','revision','checkpoint_action','policy_start_step','policy_action_budget','actor','side','support')
    if any(k not in context for k in required):raise ValueError('Complete original E08 checkpoint context required')
    if context['task']!='E08'or context['variant']!=spec['variant']or context['revision']!=REVISION or context['seed']!=4201 or context['condition']!='I':raise ValueError('E08 checkpoint identity mismatch')
    if author.c.steps<int(context['checkpoint_action']):raise ValueError('Original cumulative action counter must be restored')
    p=MeasuredShoeAuthor(author);p.start=int(context['policy_start_step']);p.limit=int(context['policy_action_budget'])
    if p.limit!=spec.get('expert_action_budget',1500):raise ValueError('Original E08 action budget required')
    return p


def prepare_new_source_context(author,context):
    """Build a new strategy from current source geometry, never fill old166 data."""
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_e08_source_plan import make_source_plan
    from .execution_design_branch_geometry import collision_parts_task,cooked_floor_height
    p=_policy(author,context);actor=context['actor'];side=context['side'];p.require_held(dict(actor=actor),side)
    state,_=p.snapshot();body=state[actor];box=state[context['support']]
    points=(material_collision_points_task(p,dict(actor=actor))-np.asarray(body['pos']))@np.asarray(body['mat'])
    plan=make_source_plan(p.spec,actor,box['pos'],box['mat'],points)
    sole_xy=(np.asarray(plan['destination_point_task'])-np.asarray(box['pos']))@np.asarray(box['mat'])
    cavity=p.s['containers']['box'];parts=collision_parts_task(p,context['support'])
    collision_parts_task(p,actor)  # Validate/cache payload cook before any later release.
    floor=cooked_floor_height(parts,box['pos'],box['mat'],sole_xy[:2],cavity['upper'][2])
    plan=make_source_plan(p.spec,actor,box['pos'],box['mat'],points,measured_floor_local_z=floor)
    updated=dict(context)
    for key in('target_actor_rotation','control_local','destination_point_task','material_clearance_z','support','reference_orientation_acceptance'):
        updated[key]=plan[key]
    updated.update(new_reference_strategy=True,reference_strategy_origin=plan['reference_strategy'],historical_166_parameters_available=False,
                   original_placement_parameters_available=False,reference_placement_parameters_available=True,
                   source_geometry_plan=plan,checkpoint_action=p.c.steps,reference_release_mode='above_cooked_rim',release_clearance_over_rim_m=.012)
    for key in('reference_orientation_tolerance_degrees','release_horizontal_velocity_limit_m_s','release_angular_velocity_limit_rad_s'):updated.pop(key,None)
    return updated



def _source_settled_geometry(policy,context):
    from .execution_design_e08_source_plan import settled_pose_geometry
    from .execution_design_branch_geometry import collision_parts_task,cooked_floor_height
    from .execution_design_thin_edge import material_collision_points_task
    import itertools
    actor=context['actor'];state,_=policy.snapshot();body=state[actor];box=state[context['support']]
    r=np.asarray(body['mat']);br=np.asarray(box['mat']);bp=np.asarray(box['pos']);pos=np.asarray(body['pos'])
    physical=(material_collision_points_task(policy,dict(actor=actor))-pos)@r
    obj=policy.objects[actor];corners=np.array(list(itertools.product((-1,1),repeat=3)))*np.asarray(obj['size'])+np.asarray(obj.get('local_bounds_center',[0,0,0]))
    cavity=policy.s['containers']['box'];destination=np.asarray(context['destination_point_task']);xy=((destination-bp)@br)[:2]
    floor=cooked_floor_height(collision_parts_task(policy,context['support']),bp,br,xy,cavity['upper'][2])
    axes=policy.s['shoe_axes'][actor];toe=np.asarray(axes['toe_local'])-axes['heel_local']
    expected=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})['ABC'.index(policy.variant)][actor]
    if context.get('midfoot_grasp_strategy'):
        from .execution_design_e08_source_plan import measured_source_pose_plan
        result=measured_source_pose_plan(physical,r,bp,br,context['control_local'],floor,cavity['lower'],cavity['upper'],policy.geometry['box_positions'][actor],toe,policy.s['label_end']['point_local'],expected)
        if result['acceptable']:
            context.setdefault('source_reference_nominal_destination_point_task',context['destination_point_task'])
            context['destination_point_task']=result['destination_point_task'];context['actual_source_pose_placement']=result
        return result
    return settled_pose_geometry(physical,corners,r,bp,br,context['control_local'],destination,floor,cavity['lower'],cavity['upper'],toe,policy.s['label_end']['point_local'],expected)

def _release_measurement(policy,actor):
    asset=policy.a.scene.objects[actor];rotation=np.asarray(policy.a.scene.layout.task_rotation,float).T
    try:
        linear=rotation@asset.data.root_lin_vel_w[0].detach().cpu().numpy()
        angular=rotation@asset.data.root_ang_vel_w[0].detach().cpu().numpy()
        gravity=rotation@np.asarray(policy.c.sim.cfg.gravity,float)
    except (AttributeError,TypeError)as exc:raise ToolExecutionError('Native payload velocity/gravity readback unavailable')from exc
    return linear,angular,gravity


def _source_release_envelope(policy,context):
    from .execution_design_branch_geometry import collision_parts_task,cooked_floor_height,swept_pose_clearance
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_e08_source_plan import drop_envelope
    import itertools
    actor=context['actor'];state,_=policy.snapshot();body=state[actor];box=state[context['support']];r=np.asarray(body['mat']);br=np.asarray(box['mat']);bp=np.asarray(box['pos']);pos=np.asarray(body['pos'])
    obj=policy.objects[actor];corners=np.array(list(itertools.product((-1,1),repeat=3)))*np.asarray(obj['size'])+np.asarray(obj.get('local_bounds_center',[0,0,0]));world=corners@r.T+pos;local=(world-bp)@br
    point=policy.point(dict(actor=actor,local=context['control_local']));xy=((point-bp)@br)[:2];cavity=policy.s['containers']['box'];parts=collision_parts_task(policy,context['support'])
    floor=cooked_floor_height(parts,bp,br,xy,cavity['upper'][2]);floor_world=bp+br@np.r_[xy,floor]
    physical=material_collision_points_task(policy,dict(actor=actor))
    if context.get('midfoot_grasp_strategy'):local=(physical-bp)@br
    height=float(physical[:,2].min()-floor_world[2]);radius=float(np.linalg.norm(physical-pos,axis=1).max());linear,angular,gravity=_release_measurement(policy,actor)
    result=drop_envelope(local,height,float(floor_world[2]),bp,br,linear,angular,gravity,radius,cavity['lower'],cavity['upper'])
    # Permit the intended floor impact, while preserving actual cooked walls.
    walls=[part for part in parts if float(((np.asarray(part)-bp)@br)[:,2].max())>floor+.002]
    flight=result['flight_seconds'];shift=np.r_[linear[:2]*flight,-height]
    padding=result['rotation_displacement_bound_m']+float(np.linalg.norm(linear[:2]))*flight+max(0.,float(linear[2]))**2/(2*(-gravity[2]))
    result['actual_cooked_wall_sweep']=swept_pose_clearance({'payload':physical},pos,pos+shift,np.eye(3),{'actual_box_walls':walls},table_bounds_task(policy.a.scene)['top'],margin=.001+padding)
    result['actual_cooked_wall_piece_count']=len(walls);result['intended_low_floor_pieces']=len(parts)-len(walls)
    return result


def _native_landing_conditions(policy,context):
    # Reuse the unchanged native geometry/contact methods, never policy return
    # as a success assertion. This is one-shoe current-state evidence only.
    from .realworld_structural_evidence import StructuralTaskEvaluator
    verifier=StructuralTaskEvaluator(policy.spec);state,contacts=policy.snapshot();verifier.state=state;verifier.contacts=contacts;verifier.forces=dict(policy.c.contact_forces)
    names=verifier.group('shoes',[]);inside,supported=verifier.contained('box',names);actor=context['actor'];label=verifier.semantic['label_end'];origin,rotation=verifier.frame(label['ref']);direction=rotation@np.asarray(label['point_local']);direction/=np.linalg.norm(direction)
    axes=verifier.semantic['shoe_axes'][actor];axis=np.asarray(state[actor]['mat'])@(np.asarray(axes['toe_local'])-axes['heel_local']);axis/=np.linalg.norm(axis);cosine=float(axis@direction)
    expected=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})['ABC'.index(policy.variant)][actor]
    recorded_inside=actor in inside;recorded_support=actor in supported
    raw_bbox_inside=recorded_inside;raw_bbox_support=recorded_support
    if verifier.semantic.get('source_acceptance_geometry'):
        from copy import deepcopy
        bbox=deepcopy(verifier);bbox.semantic.pop('source_acceptance_geometry',None)
        for obj in bbox.objects.values():
            obj.pop('containment_points_local',None);obj.pop('containment_points_source_sha256',None)
        bbox_inside,bbox_support=bbox.contained('box',names);raw_bbox_inside=actor in bbox_inside;raw_bbox_support=actor in bbox_support
    source='unchanged_native_contained_and_force_methods'
    if context.get('midfoot_grasp_strategy'):
        from copy import deepcopy
        from .execution_design_thin_edge import material_collision_points_task
        spec=deepcopy(policy.spec)
        for obj in spec['objects']:
            if obj['id']not in names:continue
            body=state[obj['id']];points=(material_collision_points_task(policy,dict(actor=obj['id']))-np.asarray(body['pos']))@np.asarray(body['mat'])
            obj['containment_points_local']=points.tolist();obj['containment_points_source_sha256']=obj['source_asset']['sha256']
        exact=StructuralTaskEvaluator(spec);exact.state=state;exact.contacts=contacts;exact.forces=dict(policy.c.contact_forces)
        inside,supported=exact.contained('box',names)
        source='same_original_native_cavity_tolerances_and_force_methods_with_complete_source_collision_points'
    return dict(source=source,actor=actor,correct_label_direction=cosine*expected>.9,inside_original_cavity=actor in inside,actual_supported_in_box=actor in supported,
                native_evaluator_bbox_inside=raw_bbox_inside,native_evaluator_bbox_supported=raw_bbox_support,native_evaluator_current_inside=recorded_inside,native_evaluator_current_supported=recorded_support,native_evaluator_not_modified=True,
                toe_label_cosine=cosine,hand_force_n=float(verifier.hand_force(actor)),native_grasp=list(state[actor]['grasp']),whole_task_score=None)


def right_clockwise_detour(context,current,target):
    """Keep the source goal while leaving the measured right q7 lower stop."""
    if context.get('right_yaw_detour_direction')!='CW'or context.get('right_yaw_detour_complete'):return None
    now=math.atan2(current[1,0],current[0,0]);goal=math.atan2(target[1,0],target[0,0]);remaining=(now-goal)%(2*math.pi)
    if min(remaining,2*math.pi-remaining)<=math.radians(10.)or remaining<=math.pi-math.radians(10.):
        context['right_yaw_detour_complete']=True;return None
    return 'ROTATE_CW',min(10.,math.degrees(remaining))


def run_branch(author,context,branch_name,*,_source_actor='left_shoe'):
    if branch_name not in BRANCHES:raise ValueError('Unknown E08 checkpoint branch')
    if _source_actor not in('left_shoe','right_shoe')or context.get('actor')!=_source_actor:
        raise ValueError('Explicit original source shoe branch scope required')
    if _source_actor=='right_shoe'and context.get('midfoot_grasp_strategy')not in('native721_right_upper_near_actual_com_v1','sourceinitial_upper_com_pair_v1'):
        raise ValueError('Measured right source COM acquisition context required')
    if branch_name=='release_source_left_here':return release_source_left_here(author,context,**({}if _source_actor=='left_shoe'else dict(_source_actor=_source_actor)))
    if branch_name=='reset_left_on_table':
        from .execution_design_e08_supported import reset_left_on_table
        return reset_left_on_table(_policy(author,context),context)
    if branch_name=='complete_left_from_held':
        p=_policy(author,context);start=p.c.steps
        if (context.get('actor')!=_source_actor or not context.get('new_reference_strategy')
                or context.get('reference_strategy_origin')!='new_source_axes_and_measured_cavity_v1'
                or context.get('historical_166_parameters_available')is not False):
            raise ValueError('Explicit new source left-shoe strategy required for completion')
        used=int(context.get('rotation_commands_used',0))
        if not 0<=used<=120:raise ValueError('Original120-round shoe limit required')
        context['rotation_commands']=120;context['e08_held_completion_phase']='orient_left'
        rotation=None;scope={}if _source_actor=='left_shoe'else dict(_source_actor=_source_actor)
        if used<120:
            rotation=run_branch(author,context,'yaw_short_chunk',**scope)
            if not rotation['reference_orientation_reached']:
                raise ToolExecutionError('Left shoe exhausted original rotation bound before native cavity/direction acceptance')
        context['e08_held_completion_phase']='place_left'
        result=run_branch(author,context,'place_left_to_release',**scope)
        context['e08_held_completion_phase']='complete_left'
        result.update(branch=branch_name,actions=p.c.steps-start,
                      rotation_phase_actions=0 if rotation is None else rotation['actions'],
                      original_cumulative_rotation_commands=int(context.get('rotation_commands_used',0)),
                      completion_phases=['native_orientation_and_cavity','place_release_retreat_native_readback'])
        return result
    p=_policy(author,context);actor=context['actor'];side=context['side'];start=p.c.steps
    if actor!=_source_actor:raise ValueError('This failure checkpoint differs from the explicit source shoe')
    if branch_name=='adopt_source_plan':context.update(prepare_new_source_context(author,context))
    new_strategy=bool(context.get('new_reference_strategy',False))
    tolerance=4.  # Original policy threshold; new strategy uses actual native geometry.
    if new_strategy:
        context['reference_orientation_acceptance']='native_direction_and_actual_shape_cavity_margin'
        for key in('reference_orientation_tolerance_degrees','release_horizontal_velocity_limit_m_s','release_angular_velocity_limit_rad_s'):context.pop(key,None)
    target=None
    if 'target_actor_rotation'in context:
        target=np.asarray(context['target_actor_rotation'],float)
        if target.shape!=(3,3)or not np.isfinite(target).all()or not np.allclose(target.T@target,np.eye(3),atol=1e-5)or np.linalg.det(target)<.999:raise ValueError('Original proper finite E08 rotation required')
    if branch_name in('yaw_short_chunk','place_left_to_release')and target is None:
        raise ValueError('Original pickup-complete actor rotation is unavailable; this branch cannot guess it')
    if branch_name=='place_left_to_release'and any(k not in context for k in('control_local','destination_point_task','material_clearance_z')):
        raise ValueError('Original E08 placement parameters are unavailable; placement branch refused')
    guard=HeldGeometry(p,actor,side,allowed_payload=(context['support'],)if branch_name=='place_left_to_release'else())
    install_public_guard(p,guard);guard()
    from .author_orientation import _axis_angle
    state,_=p.snapshot();landing=None;release_envelope=None;orientation_geometry=None;free_guard=None;retreated=False;angle=None if target is None else _axis_angle(target@np.asarray(state[actor]['mat']).T)[1];holds=[]
    if branch_name=='adopt_source_plan':
        p.act(side,'STILL')
    elif branch_name=='stage_ccw':
        tip=p.tip(side);stage=np.asarray(context.get('staging_tcp',[-.2,float(tip[1]),1.12]),float)
        for axis in range(3):
            goal=p.tip(side).copy();goal[axis]=stage[axis];guard.move(goal)
    elif branch_name in('yaw_ccw_chunk','yaw_short_chunk'):
        count=int(context.get('rotation_commands',6));used=int(context.get('rotation_commands_used',0))
        if not 1<=count<=120 or not 0<=used<120:raise ValueError('Original120-round shoe limit and <=120command chunks required')
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        for _ in range(min(count,120-used)):
            guard();state,_=p.snapshot();current=np.asarray(state[actor]['mat'])
            if target is not None:
                axis,angle=_axis_angle(target@current.T)
                if new_strategy:
                    orientation_geometry=_source_settled_geometry(p,context)
                    if orientation_geometry['acceptable']:break
                elif angle<math.radians(tolerance):break
            if branch_name=='yaw_ccw_chunk':
                if target is None:degrees=5.
                else:
                    now=current[:,0];wanted=target[:,0];remaining=(math.atan2(wanted[1],wanted[0])-math.atan2(now[1],now[0]))%(2*math.pi)
                    if min(remaining,2*math.pi-remaining)<math.radians(tolerance):break
                    degrees=min(5.,math.degrees(remaining))
                token='ROTATE_CCW'
            else:
                detour=right_clockwise_detour(context,current,target)if _source_actor=='right_shoe'else None
                if detour is not None:token,degrees=detour
                else:
                    k=int(np.argmax(abs(axis)));token=labels[k][int(axis[k]<0)];degrees=min(10. if context.get('midfoot_grasp_strategy')else 5.,max(.5,abs(math.degrees(angle*axis[k]))))
            context['rotation_commands_used']=int(context.get('rotation_commands_used',0))+1
            p.act(side,token,degrees=degrees)
            task_accepted=(lambda:_source_settled_geometry(p,context)['acceptable'])if new_strategy else None
            if context.get('midfoot_grasp_strategy'):
                from .execution_design_branch_rotation import finish_accepted_public_rotation
                holds.append(dict(step=p.c.steps,public_still_actions=finish_accepted_public_rotation(p,side,guard)))
            else:holds.extend(public_rotation_holds(p,side,guard,task_accepted=task_accepted))
    else:
        if new_strategy:
            orientation_geometry=_source_settled_geometry(p,context)
            if not orientation_geometry['acceptable']:raise ToolExecutionError('New source actual orientation does not fit original native cavity/direction')
        elif angle>=math.radians(tolerance):raise ToolExecutionError('Original E08 orientation must converge before placement branch')
        ref=dict(actor=actor,local=list(context['control_local']));destination=np.asarray(context['destination_point_task'],float)
        if new_strategy and context.get('reference_release_mode')=='above_cooked_rim':
            from .execution_design_branch_geometry import collision_parts_task
            from .execution_design_e33_grasp import actual_mesh
            from .execution_design_thin_edge import material_collision_points_task
            tip=p.tip(side);point=p.point(ref);rim=max(float(part[:,2].max())for part in collision_parts_task(p,context['support']))
            if context.get('midfoot_grasp_strategy'):
                from .execution_design_e13_release import actual_opening_bodies
                robot_low=min(float(points[:,2].min())for points in actual_opening_bodies(p,side).values())
            else:robot_low=min(float(actual_mesh(author,side,name)[:,2].min())for name in('panda_hand',*author.scene.embodiment.fingers))
            payload_low=float(material_collision_points_task(p,dict(actor=actor))[:,2].min());margin=float(context['release_clearance_over_rim_m'])
            if not .003<=margin<=.02:raise ValueError('Reviewed above-rim release margin required')
            destination=destination.copy();destination[2]=max(destination[2],rim+margin-(robot_low-tip[2])+(point[2]-tip[2]),rim+margin-(payload_low-point[2]))
            context['measured_above_rim_release_control_point']=destination.tolist()
        height=max(float(context['material_clearance_z']),float(destination[2])+.07)
        p.move_point(side,ref,[*p.point(ref)[:2],height],guard)
        p.move_point(side,ref,[*destination[:2],height],guard)
        p.move_point(side,ref,destination+[0,0,.001],guard)
        if new_strategy:
            guard();orientation_geometry=_source_settled_geometry(p,context)
            if not orientation_geometry['acceptable']:raise ToolExecutionError('Actual source pose drifted outside native cavity/direction before release')
            context.update(source_ballistic_guarantee_required=False,source_release_strategy='legal_box_wall_guidance_then_actual_native_landing')
        if context.get('midfoot_grasp_strategy'):
            from .execution_design_e13_release import actual_opening_bodies
            from .execution_design_branch_geometry import swept_pose_clearance,collision_parts_task
            from .execution_design_thin_edge import table_bounds_task
            state,_=p.snapshot();tip=p.tip(side)
            context['actual_shoe_release_opening_guard']=swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),{n:collision_parts_task(p,n)for n in state if n!=actor},table_bounds_task(p.a.scene)['top'])
        p.act(side,'RELEASE')
        if new_strategy:
            state,_=p.snapshot()
            if any(state[actor]['grasp']):raise ToolExecutionError('Source release did not physically release the shoe')
            free_guard=HeldGeometry(p,actor,side,require_hold=False);install_public_guard(p,free_guard)
            free_guard.move(p.tip(side)+[0,0,.06]);retreated=True
            landing=_native_landing_conditions(p,context)
            if not all(landing[k]for k in('correct_label_direction','inside_original_cavity','actual_supported_in_box')):
                import json
                raise ToolExecutionError('New source landing failed native local conditions: '+json.dumps(landing))
    state,_=p.snapshot();angle=None if target is None else _axis_angle(target@np.asarray(state[actor]['mat']).T)[1]
    if new_strategy and branch_name in('yaw_short_chunk','yaw_ccw_chunk'):
        orientation_geometry=_source_settled_geometry(p,context)
    return dict(branch=branch_name,task='E08',actions=p.c.steps-start,local_completed=True,
                original_orientation_reached=None if angle is None or new_strategy else angle<math.radians(4),
                reference_orientation_reached=(None if orientation_geometry is None else orientation_geometry['acceptable'])if new_strategy else(None if angle is None else angle<math.radians(tolerance)),reference_pose_geometry=orientation_geometry,remaining_rotation_degrees=None if angle is None else math.degrees(angle),
                new_reference_strategy=new_strategy,reference_strategy_origin=context.get('reference_strategy_origin'),historical_166_parameters_available=False if new_strategy else None,
                original_placement_parameters_available=not new_strategy and all(k in context for k in('target_actor_rotation','control_local','destination_point_task','material_clearance_z')),
                reference_placement_parameters_available=all(k in context for k in('target_actor_rotation','control_local','destination_point_task','material_clearance_z')),
                collision_guard_evidence=getattr(guard,'last_report',None),
                post_release_guard_evidence=None if free_guard is None else getattr(free_guard,'last_report',None),
                original_support_contact=p.contact(actor,context['support']),holds=holds,
                context_updates={'rotation_commands_used':int(context.get('rotation_commands_used',0))},
                source_release_envelope=release_envelope,native_landing_conditions=landing,
                post_release_retreat_executed=retreated,whole_task_score=None,physics_success_not_asserted=True)


def release_source_left_here(author,context,*,_source_actor='left_shoe'):
    """Real box walls may guide the drop; only native landing is decisive."""
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_e13_release import actual_opening_bodies
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    p=_policy(author,context);start=p.c.steps;actor=context['actor'];side=context['side']
    expected_side=context['side']if context.get('midfoot_grasp_strategy')=='sourceinitial_upper_com_pair_v1'and context.get('source_initial_physical_route')is True else'left'if _source_actor=='left_shoe'else'right'
    if actor!=_source_actor or side!=expected_side or not context.get('new_reference_strategy')or context.get('historical_166_parameters_available')is not False:
        raise ValueError('Measured original-source E08 source-shoe release required')
    if actor=='right_shoe'and context.get('midfoot_grasp_strategy')not in('native721_right_upper_near_actual_com_v1','sourceinitial_upper_com_pair_v1'):raise ValueError('Measured right-source near-COM strategy required')
    p.require_held(dict(actor=actor),side);state,_=p.snapshot();box=state[context['support']]
    points=material_collision_points_task(p,dict(actor=actor));local=(points-np.asarray(box['pos']))@np.asarray(box['mat'])
    cavity=p.s['containers']['box'];lo=np.asarray(cavity['lower']);hi=np.asarray(cavity['upper'])
    margin=np.minimum(local[:,:2].min(0)-(lo[:2]-.002),(hi[:2]+.002)-local[:,:2].max(0))
    if np.any(margin<0):raise ToolExecutionError('Actual source shoe footprint is outside original native cavity bounds')
    axes=p.s['shoe_axes'][actor];toe=np.asarray(state[actor]['mat'])@(np.asarray(axes['toe_local'])-axes['heel_local']);label=np.asarray(box['mat'])@np.asarray(p.s['label_end']['point_local'])
    cosine=float(toe@label/np.linalg.norm(toe)/np.linalg.norm(label))
    wanted=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})[p.index][actor]
    if cosine*wanted<=.9:raise ToolExecutionError('Actual original native shoe direction is incorrect before release')
    guard=HeldGeometry(p,actor,side,allowed_payload=(context['support'],));install_public_guard(p,guard)
    tip=p.tip(side);opening=swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),{n:collision_parts_task(p,n)for n in state if n!=actor},table_bounds_task(p.a.scene)['top'])
    context.update(source_release_strategy='legal_box_wall_guidance_then_actual_native_landing',source_ballistic_guarantee_required=False,
        source_release_current_footprint_margin_xy_m=margin.tolist(),source_release_current_native_direction_cosine=cosine,actual_shoe_release_opening_guard=opening)
    p.act(side,'RELEASE');state,_=p.snapshot()
    if any(state[actor]['grasp']):raise ToolExecutionError('Source shoe was not physically released')
    free=HeldGeometry(p,actor,side,require_hold=False);install_public_guard(p,free);free.move(p.tip(side)+[0,0,.060])
    landing=_native_landing_conditions(p,context);context['actual_released_source_landing']=landing
    if not all(landing[k]for k in('correct_label_direction','inside_original_cavity','actual_supported_in_box')):
        import json
        raise ToolExecutionError('Actual released source shoe failed original native conditions: '+json.dumps(landing))
    return dict(branch='release_source_left_here',task='E08',local_completed=True,actions=p.c.steps-start,native_landing_conditions=landing,
        original_cavity_bounds_and_tolerances_unchanged=True,source_ballistic_guarantee_required=False,whole_task_score=None)
