"""Public-action E13 suffixes after restored native phone grip/lift."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e13_edge import PhoneMoves
from .execution_design_branch_geometry import HeldGeometry,install_public_guard,public_rotation_holds
from .execution_design_e13_release import native_orientation,release_height,actual_opening_clearance,landing_conditions

REVISION='embodied50-execution-v3-20261102'
BRANCHES=frozenset(('stage_inside','escape_pending_stage','rotate_chunk','rotate_intermediate_chunk','hold_pending','place_to_release','complete_from_held'))


def goal_rotation(goal):
    roll,pitch,yaw=[float(goal.get(k,0.))for k in('roll','pitch','yaw')]
    cx,sx=math.cos(roll),math.sin(roll);cy,sy=math.cos(pitch),math.sin(pitch);cz,sz=math.cos(yaw),math.sin(yaw)
    return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])


def prepare_context(author,goal,zone,clear_z,policy_action_budget,checkpoint_action=1036):
    """Save original generated placement parameters without executing pickup."""
    state,_=author.c.snapshot();xy=np.asarray(goal.get('placement_xy',zone['xy']),float)
    if zone.get('anchor_object'):
        anchor=state[zone['anchor_object']];xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(zone.get('anchor_local_center',[0,0,0]),float))[:2]
    return dict(task='E13',variant=author.scene.spec['variant'],seed=int(author.scene.spec['seed']),condition='I',revision=REVISION,checkpoint_action=int(checkpoint_action),
                policy_start_step=0,policy_action_budget=int(policy_action_budget),goal=dict(goal),placement_xy_task=xy.tolist(),
                target_surface_z=float(zone.get('surface_z',.8)),clear_z=float(clear_z),support=goal.get('required_support','stand'),
                carried_payload=['phone','left'],rotation_round_limit=80,rotation_commands_used=0)


def _policy(author,context):
    spec=author.scene.spec
    if (spec.get('id')!='E13'or spec.get('execution_design',{}).get('revision')!=REVISION
            or spec.get('seed')!=4201 or spec.get('execution_design',{}).get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.scene.embodiment.name!='franka'):
        raise ValueError('E13 v3 Panda engineering branch required')
    required=('task','variant','seed','condition','revision','checkpoint_action','policy_start_step','policy_action_budget','goal','placement_xy_task','target_surface_z','clear_z','support')
    if any(k not in context for k in required):raise ValueError('Complete original E13 checkpoint context required')
    if context['task']!='E13'or context['variant']!=spec['variant']or context['revision']!=REVISION or context['seed']!=4201 or context['condition']!='I':raise ValueError('E13 checkpoint identity mismatch')
    if author.c.steps<int(context['checkpoint_action']):raise ValueError('Original cumulative action counter must be restored')
    p=PhoneMoves(author);p.start=int(context['policy_start_step']);p.limit=int(context['policy_action_budget'])
    if p.limit<=0:raise ValueError('Original E13 action budget required')
    return p


def run_branch(author,context,branch_name):
    if branch_name not in BRANCHES:raise ValueError('Unknown E13 checkpoint branch')
    if branch_name=='complete_from_held':
        p=_policy(author,context);start=p.c.steps;rotation_actions=0
        if not 0<=int(context.get('rotation_commands_used',0))<=80:
            raise ToolExecutionError('Phone original80 rotation bound was exceeded')
        context['e13_held_completion_phase']='orient_phone'
        while True:
            state,_=p.snapshot()
            if native_orientation(state['phone']['mat'],p.s,p.variant)['allowed']:break
            used=int(context.get('rotation_commands_used',0))
            if not 0<=used<80:raise ToolExecutionError('Phone exhausted original80 rotation bound before native orientation acceptance')
            context['rotation_commands']=min(6,80-used)
            rotation=run_branch(author,context,'rotate_chunk');rotation_actions+=rotation['actions']
            if int(context.get('rotation_commands_used',0))<=used:
                raise ToolExecutionError('Phone orientation phase made no accepted public rotation progress')
        context['e13_held_completion_phase']='place_phone'
        result=run_branch(author,context,'place_to_release')
        context['e13_held_completion_phase']='complete_phone'
        result.update(branch=branch_name,actions=p.c.steps-start,rotation_phase_actions=rotation_actions,
                      original_cumulative_rotation_commands=int(context.get('rotation_commands_used',0)),
                      completion_phases=['native_orientation','place_release_retreat_native_readback'])
        return result
    p=_policy(author,context);side='left';start=p.c.steps;support=context['support']
    guard=HeldGeometry(p,'phone',side,allowed_payload=(support,)if branch_name=='place_to_release'else())
    install_public_guard(p,guard);guard();original=goal_rotation(context['goal']);target=original
    if branch_name=='rotate_intermediate_chunk':
        if 'intermediate_actor_rotation'not in context:raise ValueError('Explicit reviewed intermediate rotation required')
        target=np.asarray(context['intermediate_actor_rotation'],float)
    if target.shape!=(3,3)or not np.allclose(target.T@target,np.eye(3),atol=1e-5)or np.linalg.det(target)<.999:raise ValueError('Proper original/intermediate actor rotation required')
    from .author_orientation import _axis_angle
    state,_=p.snapshot();_,angle=_axis_angle(target@np.asarray(state['phone']['mat']).T);holds=[];release_plan=None;landing=None;retreated=False
    if branch_name=='hold_pending':
        holds.extend(public_rotation_holds(p,side,guard))
    elif branch_name in('stage_inside','escape_pending_stage'):
        tip=p.tip(side);stage=np.asarray(context.get('staging_tcp',[-.2,float(tip[1]),float(tip[2])]),float)
        if stage.shape!=(3,)or not np.isfinite(stage).all():raise ValueError('Finite reviewed interior staging required')
        if branch_name=='escape_pending_stage':
            # An explicit recovery strategy after the bounded old-target hold
            # failed. Translation would preserve that stuck angular target.
            # This public turn intentionally supersedes it from measured pose;
            # the original phone goal and cumulative80-round count survive.
            if context.get('variant')!='A'or not np.allclose(stage,[-.28,.24,.98],atol=1e-8):
                raise ValueError('Reviewed E13A pending escape staging required')
            pending=float(p.c.action_feedback()['control_feedback'][side]['orientation_error_rad'])
            used=int(context.get('rotation_commands_used',0))
            if not np.isfinite(pending)or pending<=math.radians(.5):
                raise ValueError('Explicit unfinished accepted target required for pending escape')
            if not 0<=used<80:raise ValueError('Original80-round phone rotation limit required')
            context.update(pending_escape_strategy='public_pitch_down2_then_axis_stage_v1',
                           superseded_pending_error_rad=pending,rotation_commands_used=used+1)
            p.act(side,'PITCH_DOWN',degrees=2.)
            holds.extend(public_rotation_holds(p,side,guard))
        for axis in range(3):
            goal=p.tip(side).copy();goal[axis]=stage[axis];guard.move(goal)
    elif branch_name in('rotate_chunk','rotate_intermediate_chunk'):
        count=int(context.get('rotation_commands',6));used=int(context.get('rotation_commands_used',0))
        if not 1<=count<=6 or not 0<=used<80:raise ValueError('Original80-round phone rotation limit and <=6command chunks required')
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        for _ in range(min(count,80-used)):
            guard();state,_=p.snapshot();axis,angle=_axis_angle(target@np.asarray(state['phone']['mat']).T)
            if branch_name=='rotate_intermediate_chunk':
                if angle<math.radians(1):break
            elif native_orientation(state['phone']['mat'],p.s,p.variant)['allowed']:break
            k=int(np.argmax(abs(axis)));token=labels[k][int(axis[k]<0)]
            context['rotation_commands_used']=int(context.get('rotation_commands_used',0))+1
            p.act(side,token,degrees=min(10.,max(.5,abs(math.degrees(angle*axis[k])))))
            holds.extend(public_rotation_holds(p,side,guard))
    else:
        _,angle=_axis_angle(original@np.asarray(state['phone']['mat']).T)
        if not native_orientation(state['phone']['mat'],p.s,p.variant)['allowed']:
            raise ToolExecutionError('Native phone orientation must converge to original task conditions before placement branch')
        spec=next(o for o in p.spec['objects']if o['id']=='phone');offset=p.tip(side)-np.asarray(state['phone']['pos'])
        height=float((np.abs(state['phone']['mat'])@np.asarray(spec['size']))[2]);xy=np.asarray(context['placement_xy_task'])+offset[:2]
        current=p.tip(side);high=float(context['clear_z'])
        for goal in ([*current[:2],high],[xy[0],current[1],high],[*xy,high]):guard.move(np.asarray(goal,float))
        goal_z=float(context['target_surface_z'])+height+float(offset[2])+.004
        release_plan=release_height(p,side,goal_z);context['actual_phone_release_plan']=release_plan
        guard.move(np.array([*xy,release_plan['tcp_z']]))
        release_plan['achieved_opening_clearance']=actual_opening_clearance(p,side)
        p.act(side,'RELEASE')
        state,_=p.snapshot()
        if any(state['phone']['grasp']):raise ToolExecutionError('Phone release did not physically release the object')
        free_guard=HeldGeometry(p,'phone',side,require_hold=False);install_public_guard(p,free_guard)
        free_guard.move(p.tip(side)+[0,0,.04]);retreated=True;landing=landing_conditions(p)
        if not landing['local_geometry_contact_allowed']or not landing['native_current_conditions_passed']:
            import json
            raise ToolExecutionError('Phone landing failed original native task conditions: '+json.dumps(landing))
    state,_=p.snapshot();actual=np.asarray(state['phone']['mat']);_,remaining=_axis_angle(original@actual.T)
    intermediate_remaining=None
    if 'intermediate_actor_rotation'in context:
        intermediate_remaining=_axis_angle(np.asarray(context['intermediate_actor_rotation'])@actual.T)[1]
    return dict(branch=branch_name,task='E13',actions=p.c.steps-start,local_completed=True,
                original_orientation_reached=remaining<math.radians(6),remaining_rotation_degrees=math.degrees(remaining),
                intermediate_orientation_reached=None if intermediate_remaining is None else intermediate_remaining<math.radians(1),
                intermediate_remaining_degrees=None if intermediate_remaining is None else math.degrees(intermediate_remaining),
                native_orientation=native_orientation(actual,p.s,p.variant),actual_release_plan=release_plan,native_landing_conditions=landing,
                original_support_contact=p.contact('phone',support),holds=holds,context_updates={'rotation_commands_used':int(context.get('rotation_commands_used',0))},
                pending_escape_strategy=context.get('pending_escape_strategy'),
                superseded_pending_error_rad=context.get('superseded_pending_error_rad'),
                post_release_retreat_executed=retreated,whole_task_score=None,physics_success_not_asserted=True)
