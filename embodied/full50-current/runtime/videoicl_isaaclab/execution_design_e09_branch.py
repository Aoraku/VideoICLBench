"""Fail-fast E09 checkpoint branch dispatcher; never claims whole-chain success.

Restoration is owned by the common engineering checkpoint runner. This module
only validates the restored native boundary and issues remaining public actions.
"""
from copy import deepcopy
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design import REVISION_V3

PACK_PHASES=('stage_crate','pack_group','close_lid','deliver_crate')
ENTRIES=('pre_blue','park_blue','blue_local','blue_grip','blue_transport','post_local_all',*PACK_PHASES)
from .execution_design_e09_reference import SOURCE_TRIANGLE_PREGRIP_LOCAL as NATIVE_TRIANGLE_PREGRIP_LOCAL


def validate_context(spec,entry,steps,context):
    if entry not in ENTRIES:raise ToolExecutionError('Unknown E09 checkpoint entry')
    design=spec.get('execution_design',{})
    if (spec.get('id')!='E09'or spec.get('variant')not in('A','B','C')or spec.get('seed')!=4201
            or design.get('revision')!=REVISION_V3 or design.get('condition')!='I'):
        raise ToolExecutionError('Fixed E09 ABC/I/4201 engineering checkpoint required')
    if not isinstance(context,dict)or not context.get('parent_checkpoint'):
        raise ToolExecutionError('Native checkpoint source lineage is required')
    if context.get('assignment_identity_sha256')!=design.get('assignment_identity_sha256'):
        raise ToolExecutionError('Checkpoint and original physical assignment differ')
    saved_source=context.get('source_cumulative_steps')
    park_source=(entry=='park_blue'and context.get('e09_entry')=='pre_blue'
        and saved_source==3813 and context.get('branch_name')=='pre_blue'
        and context.get('branch_start_step')==3813
        and type(context.get('branch_local_actions'))is int
        and 3813+context['branch_local_actions']==steps)
    grip_source=(entry=='blue_grip'and context.get('e09_entry')=='blue_local'
        and saved_source==3963 and context.get('branch_name')=='blue_local'
        and context.get('branch_start_step')==3963
        and type(context.get('branch_local_actions'))is int
        and 3963+context['branch_local_actions']==steps)
    original_lift=(context.get('branch_name')=='blue_grip'and context.get('branch_start_step')==3980
        and type(context.get('branch_local_actions'))is int
        and 3980+context['branch_local_actions']==steps and steps==4027)
    hold=context.get('actual_restored_hold',{})
    continued_lift=(context.get('branch_name')=='blue_transport'
        and type(context.get('branch_start_step'))is int and context['branch_start_step']>=4027
        and type(context.get('branch_local_actions'))is int
        and context['branch_start_step']+context['branch_local_actions']==steps
        and hold.get('actor')=='blue_triangle'and hold.get('side')=='left')
    lifted_native_source=(entry=='blue_transport'and context.get('e09_entry')=='blue_local'
        and saved_source==3963 and(original_lift or continued_lift))
    continued_packaging=(entry in PACK_PHASES and context.get('branch_name')in PACK_PHASES
        and type(context.get('branch_start_step'))is int
        and type(context.get('branch_local_actions'))is int
        and context['branch_start_step']+context['branch_local_actions']==steps)
    if saved_source!=steps and not(park_source or grip_source or lifted_native_source or continued_packaging):
        raise ToolExecutionError('Restored cumulative native action count was not preserved')
    if entry=='pre_blue':
        if steps!=3813 or spec['variant']!='A':
            raise ToolExecutionError('Existing pre-blue3813 native checkpoint is A only')
    elif entry=='park_blue':
        if not park_source or spec['variant']!='A' or not 3813<steps<3964:
            raise ToolExecutionError('Idle-arm parking needs the actual pre-grasp native blue prefix')
    elif entry=='blue_local':
        if (context.get('e09_entry')!='blue_local'or context.get('created_by')!='physical_e09_park_blue_branch'
                or context.get('actual_empty_arm_parked')is not True):
            raise ToolExecutionError('Blue suffix needs the completed actual idle-arm parking checkpoint')
    elif entry=='blue_grip':
        if not grip_source or steps!=3980 or spec['variant']!='A':
            raise ToolExecutionError('Blue-grip debug needs the original untouched native3980 pre-contact checkpoint')
    elif entry=='blue_transport':
        if not lifted_native_source and (context.get('e09_entry')!='blue_lifted'or context.get('created_by')!='physical_e09_blue_grip_branch'
                or context.get('actual_held_actor')!='blue_triangle'or context.get('actual_held_side')!='left'):
            raise ToolExecutionError('Blue transport needs the actual native lifted-triangle checkpoint')
    elif entry in PACK_PHASES:
        if (context.get('local_stage_native_completed')is not True
                or context.get('created_by')not in('physical_e09_pre_blue_branch','physical_e09_packaging_branch')):
            raise ToolExecutionError('Packaging needs the actual completed original nine-piece native boundary')
    elif (context.get('e09_entry')!='post_local_all'
          or context.get('local_stage_native_completed')is not True
          or context.get('created_by')!='physical_e09_pre_blue_branch'):
        raise ToolExecutionError('Post-local checkpoint must come from actual completed blue branch')


def verify_open_group(policy,index):
    """Original region membership and native support, before any lid handling."""
    from .execution_design_e09_geometry import world_vertices
    region=policy.d['local_regions'][index];name=region['actor'];state,contacts=policy.snapshot()
    body=state[name];center=np.asarray(body['pos']);rotation=np.asarray(body['mat'])
    if any(body['grasp'])or float(rotation[2,2])<.995:raise ToolExecutionError('Restored original sorting box is held or tilted')
    if frozenset((name,'table'))not in contacts:raise ToolExecutionError('Restored original sorting box lacks actual table support')
    from .execution_design_e09_reference import connected_group_support
    members=policy.d['unordered_expected_groups'][index]
    if not connected_group_support(name,members,contacts):raise ToolExecutionError('Restored members lack an actual same-group support chain to box')
    tolerance=float(policy.d.get('geometry_tolerance_m',.003))
    for member in members:
        actor=state[member];points=(world_vertices(policy.objects[member],actor)-center)@rotation
        if any(actor['grasp'])or np.any(points<np.asarray(region['lower'])-tolerance)or np.any(points>np.asarray(region['upper'])+tolerance):
            raise ToolExecutionError('Restored original group is not physically filled and released: '+member)
    return True


def remaining_group_instructions(design,index=2):
    region=design['local_regions'][index];names=sorted(design['unordered_expected_groups'][index],key=lambda n:('triangle'not in n,n))
    midpoint=(np.asarray(region['lower'])+region['upper'])/2
    return [dict(actor=n,container=region['actor'],slot_index=j,original_reference_local=[float(midpoint[0]+(j%2-.5)*.044),float(midpoint[1]+(j//2-.5)*.044),float(region['lower'][2])])for j,n in enumerate(names)]


def verify_local_stable(policy):
    names={r['actor']for r in policy.d['local_regions']}
    names.update(n for group in policy.d['unordered_expected_groups']for n in group)
    before=policy.snapshot()[0];start=policy.c.physics_ticks
    target=start+int(np.ceil(.5/float(policy.c.dt)))
    for _ in range(10):
        if policy.c.physics_ticks>=target:break
        policy.wait(1)
        for i in range(3):verify_open_group(policy,i)
    else:raise ToolExecutionError('Local-stage stability interval did not advance native physics')
    after=policy.snapshot()[0]
    for n in names:
        if np.linalg.norm(np.asarray(after[n]['pos'])-before[n]['pos'])>.002 or np.linalg.norm(np.asarray(after[n]['mat'])-before[n]['mat'])>.02:
            raise ToolExecutionError('Actual post-local group is not stable: '+n)


def run_packaging_phase(p,entry,parent,source_steps,save_checkpoint):
    from .execution_design_e09_reference import (stage_empty_crate,place_closed_group,
        close_original_lid,verify_container_member,verify_loaded_crate,deliver_loaded_crate,
        actual_supported_com,STAGE_XY)
    from .execution_design_thin_edge import table_bounds_task
    params=parent.get('branch_params',{});bounds=table_bounds_task(p.a.scene)
    crate,_=p.frame({'actor':'shipping_crate'})
    if entry!='stage_crate':
        if max(abs(np.asarray(crate[:2])-STAGE_XY))>.008:
            raise ToolExecutionError('Original carrier is not at its actual reviewed supported staging site')
        actual_supported_com(p,'shipping_crate',bounds);p._e09_crate_staged=True
    if entry=='stage_crate':stage_empty_crate(p)
    elif entry=='pack_group':
        index=params.get('index')
        if type(index)is not int or not 0<=index<=2:raise ToolExecutionError('Explicit original group index0..2 required')
        outer=next(x for x in p.d['packages']if x['container']=='shipping_crate')
        place_closed_group(p,'group_box'+str(index),[0,(index-1)*.12,outer['lower'][2]],closed=False)
    elif entry=='close_lid':
        index=params.get('index')
        if type(index)is not int or not 0<=index<=2:raise ToolExecutionError('Explicit original lid index0..2 required')
        for i in range(3):verify_container_member(p,'shipping_crate','group_box'+str(i))
        package=next(x for x in p.d['packages']if x['container']=='group_box'+str(index))
        close_original_lid(p,package)
    else:
        verify_loaded_crate(p);deliver_loaded_crate(p)
    context=dict(e09_entry=entry,created_by='physical_e09_packaging_branch',
        local_stage_native_completed=True,source_cumulative_steps=p.c.steps,
        assignment_identity_sha256=p.d['assignment_identity_sha256'],
        parent_checkpoint=deepcopy(parent['parent_checkpoint']),
        branch_source_cumulative_steps=source_steps,policy_start_step=0,policy_action_budget=p.limit,
        whole_chain_accepted=False)
    for key in('engineering_reference_budget_extension','parent_policy_action_budget'):
        if key in parent:context[key]=deepcopy(parent[key])
    if save_checkpoint is not None:save_checkpoint(p.c,author=p.a,context=context)
    return dict(schema='e09-partial-engineering-branch-v1',entry=entry,
        source_cumulative_steps=source_steps,final_cumulative_steps=p.c.steps,
        branch_actions=p.c.steps-source_steps,completed_boundary=entry,
        native_branch_route_completed=True,whole_chain_accepted=False,eligible_for_primary39=False)


def run_branch(author,entry,branch_name=None,*,checkpoint_context=None,save_checkpoint=None,stop_after_local=False):
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_e09_reference import log
    # The common native branch runner dispatches (author, context, name).
    # Keep the direct keyword interface available for isolated helper callers.
    if isinstance(entry,dict):
        checkpoint_context=entry;entry=branch_name or checkpoint_context.get('e09_entry')
        stop_after_local=bool(checkpoint_context.get('stop_after_local',False)or
            checkpoint_context.get('branch_params',{}).get('stop_after_local',False))
    if save_checkpoint is None and hasattr(author,'_branch_monitor'):
        def save_checkpoint(controller,author,context):
            monitor=author._branch_monitor;monitor.context.update(context)
            monitor.save('new-design-fixture-boundary'if context.get('new_design_fixture')else'post-local-all')
    if not author.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E09 checkpoint dispatch is engineering-only')
    monitor=getattr(author,'_branch_monitor',None)
    restored_steps=int(monitor.start)if monitor is not None else author.c.steps
    # Public STILL reconstruction is real work after the restored source.
    # Validate checkpoint lineage against that original boundary while keeping
    # every reconstruction action in the live cumulative counter and budget.
    if monitor is not None and author.c.steps-restored_steps!=len(monitor.receipts):
        raise ToolExecutionError('Native reconstructed actions and cumulative counter differ')
    if isinstance(checkpoint_context,dict)and checkpoint_context.get('new_design_fixture')is True:
        from .execution_design_e09_operable import run_design_fixture
        phases=dict(close_lid='lid_close',pack_group='closed_box_load',
                    stage_crate='crate_stage',deliver_crate='crate_deliver')
        if entry not in phases:raise ToolExecutionError('New E09 design fixture needs an explicit packaging phase')
        return run_design_fixture(author,phases[entry],
            params=checkpoint_context.get('branch_params',{}),save_checkpoint=save_checkpoint)
    validate_context(author.scene.spec,entry,restored_steps,checkpoint_context)
    policy=ExecutionDesignAuthor(author);source_steps=restored_steps;source_physics_ticks=author.c.physics_ticks
    if monitor is not None:
        source_physics_ticks-=sum(r['shared_tick_after']-r['shared_tick_before']for r in monitor.receipts)
    policy.start=int(checkpoint_context.get('policy_start_step',0));policy.limit=int(checkpoint_context.get('policy_action_budget',6000));author._branch_policy=policy
    extension=checkpoint_context.get('engineering_reference_budget_extension')
    explicit_extension=dict(parent_budget=6000,new_budget=12000,scope='independent_engineering_only',formal_action_cap_unchanged=True)
    extended=(policy.limit==12000 and extension==explicit_extension
        and checkpoint_context.get('parent_policy_action_budget')==6000
        and author.scene.spec.get('expert_action_budget')==12000)
    if policy.start!=0 or not(policy.limit==6000 or extended):
        raise ToolExecutionError('Original cumulative6000 or explicit independent engineering12000 budget required')
    if entry=='blue_grip':
        state,_=policy.snapshot();body=state['blue_triangle']
        source=policy.objects['blue_triangle'];original=np.r_[source['xy'],source['bottom']+source['size'][2]]
        if (any(any(x['grasp'])for x in state.values())or np.linalg.norm(np.asarray(body['pos'])-original)>.001
                or np.linalg.norm(np.asarray(body['mat'])-np.eye(3))>.002):
            raise ToolExecutionError('Native blue triangle must remain untouched on its original source rail')
        # Exact material-frame pose from the original successful native v8
        # pre-grasp3917, not a solved or teleported object/robot state.
        policy.stage('e09-original-native-blue-pregrip-public-correction')
        point=policy.point(dict(actor='blue_triangle',local=NATIVE_TRIANGLE_PREGRIP_LOCAL.tolist()))
        policy.move('left',point,tolerance=.0003)
    elif entry=='park_blue':
        state,_=policy.snapshot()
        if any(any(x['grasp'])for x in state.values()):raise ToolExecutionError('Park-blue checkpoint requires two actual empty hands')
        # Native contact caches are not serialized. The first counted public
        # retreat both separates the arms and rebuilds real object contacts;
        # a STILL would continue the old pending inward translation instead.
        policy.stage('e09-local-separate-empty-left-before-parking')
        policy.move('left',policy.tip('left')+[0,.010,0])
    elif entry in('pre_blue','blue_local',*PACK_PHASES):
        state,contacts=policy.snapshot()
        from .execution_design_e09_reference import connected_group_support
        if any(not connected_group_support(policy.d['local_regions'][i]['actor'],policy.d['unordered_expected_groups'][i],contacts)for i in range(3 if entry in PACK_PHASES else 2)):
            # Native contact warm-start caches are explicitly absent from the
            # legacy static fixture. One counted public hold obtains new real
            # forces before validating the saved physical group state.
            policy.stage('e09-checkpoint-native-contact-refresh');policy.wait(1)
    # The common restore already checked every saved object/robot native state.
    # Check physical group membership independently before issuing new actions.
    if entry in PACK_PHASES:
        from .execution_design_e09_reference import verify_group_members
        for i in range(3):verify_group_members(policy,'group_box'+str(i),released=True)
    else:
        for i in range(2 if entry in('pre_blue','park_blue','blue_local','blue_grip','blue_transport')else 3):verify_open_group(policy,i)
    if entry in PACK_PHASES:
        return run_packaging_phase(policy,entry,checkpoint_context,source_steps,save_checkpoint)
    if entry=='blue_grip':
        from .execution_design_e09_liftoff import lift_piece
        ref=policy.ref('blue_triangle');policy.stage('e09-native-blue-triangle-grip-and-lift')
        for _ in range(3):
            policy.act('left','GRASP')
            if policy.held(ref,'left'):break
        else:raise ToolExecutionError('Original blue triangle lacks actual bilateral native grip')
        lift_piece(policy,ref,'left')
        for i in range(2):verify_open_group(policy,i)
        context=dict(e09_entry='blue_lifted',created_by='physical_e09_blue_grip_branch',
            actual_held_actor='blue_triangle',actual_held_side='left',source_cumulative_steps=author.c.steps,
            assignment_identity_sha256=policy.d['assignment_identity_sha256'],
            parent_checkpoint=deepcopy(checkpoint_context['parent_checkpoint']),
            branch_source_cumulative_steps=source_steps,policy_start_step=0,policy_action_budget=6000,
            whole_chain_accepted=False)
        if save_checkpoint is not None:save_checkpoint(author.c,author=author,context=context)
        return dict(schema='e09-partial-engineering-branch-v1',entry=entry,
            source_cumulative_steps=source_steps,final_cumulative_steps=author.c.steps,
            branch_actions=author.c.steps-source_steps,completed_boundary='blue_triangle_native_lifted',
            native_branch_route_completed=True,whole_chain_accepted=False,eligible_for_primary39=False)
    if entry=='park_blue':
        from .execution_design_e09_reference import park_empty_other,measured_approach_height
        state,_=policy.snapshot()
        if any(any(x['grasp'])for x in state.values()):raise ToolExecutionError('Park-blue checkpoint requires two actual empty hands')
        blue={n:np.asarray(state[n]['pos']).copy()for n in policy.d['unordered_expected_groups'][2]}
        policy.stage('e09-local-park-right-before-blue');park_empty_other(policy,'left',empty_step_mm=20.,lateral_first=True)
        policy.stage('e09-local-blue-source-above');point=policy.point(policy.ref('blue_triangle'));height=measured_approach_height(policy,'left')
        policy.move('left',[*policy.tip('left')[:2],height]);policy.move('left',[*point[:2],height])
        state,_=policy.snapshot()
        for n,pos in blue.items():
            if np.linalg.norm(np.asarray(state[n]['pos'])-pos)>.002 or any(state[n]['grasp']):
                raise ToolExecutionError('Actual blue source changed during empty parking/approach')
        for i in range(2):verify_open_group(policy,i)
        context=dict(e09_entry='blue_local',created_by='physical_e09_park_blue_branch',
            actual_empty_arm_parked=True,source_cumulative_steps=author.c.steps,
            assignment_identity_sha256=policy.d['assignment_identity_sha256'],
            parent_checkpoint=deepcopy(checkpoint_context['parent_checkpoint']),
            branch_source_cumulative_steps=source_steps,policy_start_step=0,policy_action_budget=6000,
            whole_chain_accepted=False)
        if save_checkpoint is not None:save_checkpoint(author.c,author=author,context=context)
        return dict(schema='e09-partial-engineering-branch-v1',entry=entry,
            source_cumulative_steps=source_steps,final_cumulative_steps=author.c.steps,
            branch_actions=author.c.steps-source_steps,completed_boundary='blue_source_above',
            native_branch_route_completed=True,whole_chain_accepted=False,eligible_for_primary39=False)
    if entry in('pre_blue','blue_local','blue_transport'):
        if entry in('blue_local','blue_transport'):
            if np.linalg.norm(policy.tip('right')-[-.2,-.3,1.02])>.004:
                raise ToolExecutionError('Actual parked right hand differs from native blue prefix')
            policy._e09_active_side='left'
        state,_=policy.snapshot()
        if entry=='blue_transport':
            ref=policy.ref('blue_triangle');policy.require_held(ref,'left')
            original=policy.objects['blue_triangle'];initial_z=float(original['bottom']+original['size'][2])
            if (float(state['blue_triangle']['pos'][2])-initial_z<.068
                    or any(policy.contact('blue_triangle','fixture'+str(i))for i in range(len(policy.spec['fixtures'])))):
                raise ToolExecutionError('Native blue payload has not actually cleared its original source support')
            if any(any(x['grasp'])for n,x in state.items()if n!='blue_triangle'):
                raise ToolExecutionError('Native blue suffix may carry only its actual restored triangle')
            original_pickup=policy.pickup;pending={'blue_triangle'}
            def resume_pickup(name):
                if name in pending:
                    policy.require_held(ref,'left');pending.remove(name)
                    return ref,'left'
                return original_pickup(name)
            # Resume the real payload, without releasing/regrasping it or
            # replaying any source action before this captured boundary.
            policy.pickup=resume_pickup
        elif any(any(x['grasp'])for x in state.values()):raise ToolExecutionError('Pre-blue boundary requires both actual hands empty')
        for step in remaining_group_instructions(policy.d):
            region=next(x for x in policy.d['local_regions']if x['actor']==step['container'])
            policy.place(step['actor'],step['container'],policy.region_local(region,step['actor'],step['slot_index']))
        for i in range(3):verify_open_group(policy,i)
        context=dict(e09_entry='post_local_all',local_stage_native_completed=True,
            created_by='physical_e09_pre_blue_branch',source_cumulative_steps=author.c.steps,
            assignment_identity_sha256=policy.d['assignment_identity_sha256'],
            parent_checkpoint=deepcopy(checkpoint_context['parent_checkpoint']),
            branch_source_cumulative_steps=source_steps,whole_chain_accepted=False)
        if save_checkpoint is not None:
            save_checkpoint(author.c,author=author,context=context)
        log(policy,'actual-post-local-all-checkpoint-boundary',context=context)
        if stop_after_local or entry=='blue_transport':
            return dict(schema='e09-partial-engineering-branch-v1',entry=entry,
                source_cumulative_steps=source_steps,final_cumulative_steps=author.c.steps,
                branch_actions=author.c.steps-source_steps,completed_boundary='post_local_all',
                native_branch_route_completed=True,remaining_packaging_not_run=True,
                whole_chain_accepted=False,eligible_for_primary39=False,
                model_launch_enabled=False,public_actions_only=True)
    elif stop_after_local:
        raise ToolExecutionError('stop_after_local only bootstraps the existing pre-blue source')
    policy.package_stage();policy.deliver()
    return dict(schema='e09-partial-engineering-branch-v1',entry=entry,
        source_cumulative_steps=source_steps,final_cumulative_steps=author.c.steps,
        branch_actions=author.c.steps-source_steps,source_physics_ticks=source_physics_ticks,
        final_physics_ticks=author.c.physics_ticks,checkpoint_lineage=deepcopy(checkpoint_context),
        native_branch_route_completed=True,whole_chain_accepted=False,
        final_native_rubric_requires_common_runner=True,eligible_for_primary39=False,
        model_launch_enabled=False,public_actions_only=True)
