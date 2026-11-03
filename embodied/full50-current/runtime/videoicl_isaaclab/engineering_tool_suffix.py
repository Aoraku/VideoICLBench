"""Allowlisted checkpoint suffixes for E42/E43/E45/E46 engineering only.

A suffix proves a local physical stage. It is never assembled into a source-
initial positive or a model evaluation. Existing native contact guards remain.
"""
import copy
import json
import os
from pathlib import Path
import numpy as np
from .execution_design import REVISION_V3
from .engineering_checkpoint import capture,identity
from .realworld_tool_expert import ToolAuthor,ToolExecutionError

ENTRIES={'E42':{'e42-push-remaining'},'E43':{'e43-open-gate','e43-cooked-ball-audit','e43-passive-roll','e43-guide-from-source-hold','e43-reposition-held-guide'},
         'E45':{'e45-receive-and-pour','e45-tilt-held','e45-sweep-audit','e45-cavity-audit','e45-incremental-tilt'},
         'E46':{'e46-scoop-from-held','e46-relative-insert','e46-cooked-blade-audit'}}


def _save(policy,stage,context):
    row=capture(policy.c,stage,context)
    path=Path(policy.a.out)/('suffix-'+stage+'.checkpoint.private.json')
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
    temporary.chmod(0o600);os.replace(temporary,path)
    return str(path)


def _held_source(policy,context):
    t=policy.s['tools']['main'];side=context.get('tool_side',t.get('hand','right'))
    if side not in ('left','right'):raise ToolExecutionError('Invalid explicit source-tool hand')
    grip=dict(actor=t['actor'],local=t['grasp_local'],jaw_axis_local=t['jaw_axis_local'])
    policy.require_held(grip,side)
    return t,grip,side


def _remaining(policy,context,group):
    names=context.get('remaining_'+group)
    all_names=policy.s['groups'][group]
    if not isinstance(names,list)or not names or len(set(names))!=len(names)or not set(names)<=set(all_names):
        raise ToolExecutionError('Explicit remaining source '+group+' identities required')
    return names


def _pour(policy,context,entry):
    hooks=getattr(policy.c,'tick_hooks',None)
    def ball_channel_guard(*_):
        for ball in policy.s['groups']['balls']:
            if any(policy.contact(ball,f'{s}_finger{i}')for s in('left','right')for i in(1,2)):
                raise ToolExecutionError('Actual cup hand obstructed or struck the source ball channel')
    enabled=context.get('exterior_body_grip')is True and hooks is not None
    if enabled:hooks.append(ball_channel_guard)
    try:return _pour_impl(policy,context,entry)
    finally:
        if enabled:hooks.remove(ball_channel_guard)


def _pour_impl(policy,context,entry):
    from .execution_design_pour_handoff import orient_empty_pour_hand,choose_pour_hand
    cup=policy.s['containers']['cup'];name=cup['object'];side=context.get('cup_side','right')
    migration=getattr(policy.a,'_engineering_resume_checkpoint',{}).get('context',{}).get('e45_ball_migration')
    if migration:
        inside,supported=policy.c.evaluator.container_members('cup',policy.s['groups']['balls'])
        _save(policy,'e45-new-ball-geometry-after-startup',dict(context,changed_contact_geometry=True,
            initial_actual_inside=list(inside),initial_actual_supported=list(supported),
            old_settled_ball_state_preserved=False))
        if set(inside)!=set(policy.s['groups']['balls']):
            raise ToolExecutionError('New contact geometry did not retain all actual initial cup contents')
    if side not in ('left','right'):raise ToolExecutionError('Invalid checkpoint cup hand')
    ref=dict(actor=name,local=cup['grasp_local'],jaw_axis_local=cup['jaw_axis_local'])
    if context.get('exterior_body_grip')is True:
        from .execution_design_pour_clearance import body_grip_reference,pour_token
        selected=context.get('selected_exterior_grip_local',[0.,0.,-.024])
        if len(selected)!=3:
            raise ToolExecutionError('Explicit source cup exterior-grip frame required')
        ref=body_grip_reference(policy,ref,selected[2],selected[:2])
        if context.get('engineering_pour_token')is not None:
            policy._engineering_pour_token=context['engineering_pour_token'];pour_token(policy)
        if context.get('exterior_search_mode')is not None:
            if context['exterior_search_mode']!='measured_lateral_body_v1':
                raise ToolExecutionError('Unreviewed exterior-grasp search mode')
            policy._engineering_exterior_search_mode=context['exterior_search_mode']
    elif entry=='e45-receive-and-pour' or context.get('grip_lowering_m')is not None:
        from .execution_design_pour_clearance import wall_grip_reference
        lowering=float(context.get('grip_lowering_m',.012))
        if not .008<=lowering<=.015:raise ToolExecutionError('Reviewed source side-wall grasp offset required')
        ref=wall_grip_reference(policy,ref,lowering)
    policy._engineering_pour_grip_reference=ref
    if context.get('ballistic_aim_offset_task_xy_m')is not None:
        offset=np.asarray(context['ballistic_aim_offset_task_xy_m'],float)
        if offset.shape!=(2,)or not np.isfinite(offset).all()or np.linalg.norm(offset)>.18:raise ToolExecutionError('Bounded measured E45 flight offset required')
        policy._engineering_pour_aim_offset_xy=offset
    if 'return_point_task'in context:
        point=np.asarray(context['return_point_task'],float);rotation=np.asarray(context['return_rotation_task'],float)
        if point.shape!=(3,)or not np.isfinite(point).all()or not .83<point[2]<.90 or rotation.shape!=(3,3)or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5):
            raise ToolExecutionError('Measured supported source-cup return frame required')
        policy._engineering_pour_return_point_task=point
        policy._engineering_pour_return_rotation_task=rotation
    prefix=getattr(policy.a,'_engineering_resume_checkpoint',{}).get('context',{}).get('e45_public_prefix_variant')
    if prefix and context.get('shared_public_prefix')is True:
        policy._engineering_preserve_held_pour_hand=True
    if (not getattr(policy,'_engineering_preserve_held_pour_hand',False)and choose_pour_hand({s:policy.tip(s)for s in ('left','right')},policy.destination(name))!=side):
        raise ToolExecutionError('Checkpoint cup hand would repeat an unrequested table handoff')
    if entry=='e45-receive-and-pour':
        state,_=policy.snapshot();body=state[name]
        if any(body['grasp'])or not policy.contact(name,'table')or body['mat'][2,2]<.98:
            raise ToolExecutionError('Receiving suffix requires actual released upright supported cup')
        tops=[float(v['pos'][2]+(np.abs(v['mat'])@np.asarray(next(o['size']for o in policy.spec['objects']if o['id']==n)))[2])for n,v in state.items()]
        previous=policy.clearance;policy.clearance=min(previous,max(tops)+.06)
        try:
            orient_empty_pour_hand(policy,ref,side,transport_clearance=previous)
            policy.acquire(ref,side)
        finally:policy.clearance=previous
    policy.require_held(ref,side)
    if ref.get('engineering_exterior_body_grip')is True:
        context['selected_exterior_grip_local']=list(ref['local'])
    _save(policy,'e45-before-first-tilt',dict(context,cup_side=side))
    # The public pour routine retains all native rim/ball/grip/return checks.
    # Its initial acquisition becomes a read-only held check; choose_pour_hand
    # above proves that its table-handoff branch cannot repeat the old stage.
    acquire=policy.acquire
    def already_acquired(requested,requested_side):
        if requested.get('actor')==name and requested_side==side:
            policy.require_held(requested,side);return
        return acquire(requested,requested_side)
    policy.acquire=already_acquired
    policy.s['tool_expert']['hand']=side
    try:policy.pour()
    finally:policy.acquire=acquire


def _relative_scoop(policy,context):
    from .execution_design_e46_backstop import insert
    from .execution_design_spatula_clearance import blade_edge_floor_height
    t,grip,side=_held_source(policy,context);names=_remaining(policy,context,'cargo')
    if len(names)!=1:raise ToolExecutionError('Relative insertion suffix accepts one real block')
    name=names[0];edge=dict(actor=t['actor'],local=np.mean(t['edge_segment'],axis=0));work=dict(actor=t['actor'],local=t['working_local'])
    state,_=policy.snapshot();body=state[name];obj=next(o for o in policy.spec['objects']if o['id']==name)
    half=np.abs(body['mat'])@np.asarray(obj['size']);bottom=float(body['pos'][2]-half[2])
    direction=np.asarray(context.get('direction_task',state[t['actor']]['mat']@np.array([1.,0.,0.])),float)
    if direction.shape!=(3,)or not np.isfinite(direction).all()or np.linalg.norm(direction[:2])<.1:
        raise ToolExecutionError('Measured horizontal source blade direction required')
    direction[2]=0.;direction/=np.linalg.norm(direction)
    height=float(context.get('edge_height_m',policy.point(edge)[2]));tool_obj=next(o for o in policy.spec['objects']if o['id']==t['actor'])
    minimum=blade_edge_floor_height(tool_obj,state[t['actor']]['mat'],edge['local'],bottom)
    if not np.isfinite(height)or height<minimum-.0003 or height>bottom+min(.004,1.5*half[2]):
        raise ToolExecutionError('Checkpoint blade height lies outside actual table-clear entry band')
    guard=lambda:policy.require_held(grip,side)
    if context.get('finite_open_backstop')is True:
        from .execution_design_e46_finite_backstop import prepare
        prepare(policy,name,side,direction,guard,already_oriented=context.get('finite_backstop_already_oriented')is True)
    if context.get('pitched_open_backstop')is True:
        from .execution_design_e46_backstop_pose import prepare
        prepare(policy,name,side,direction,guard,contact_face=context.get('backstop_contact_face'))
    if context.get('blade_down_pitch_degrees')is not None:
        from .execution_design_cutlery_grasp import orient
        from .realworld_tool_expert import _axis_rotation
        if float(context['blade_down_pitch_degrees'])!=3.:raise ToolExecutionError('Only the one reviewed3degree blade entry is enabled')
        policy.stage('e46-unload-blade-before-down3');policy.move(side,policy.tip(side)+[0,0,.020],guard)
        rotation=np.asarray(policy.a.tcp_rotation_task(side));axis=np.cross([0.,0.,1.],direction)
        policy.stage('e46-blade-down3');orient(policy.a,side,_axis_rotation(axis,np.deg2rad(3.))@rotation)
        st=policy.snapshot()[0];food_bottom=float(st[name]['pos'][2]-(np.abs(st[name]['mat'])@np.asarray(obj['size']))[2])
        height=blade_edge_floor_height(tool_obj,st[t['actor']]['mat'],edge['local'],food_bottom)+.0002
        policy.stage('e46-lower-real-tip-to-source-floor');policy.move_point(side,edge,np.r_[policy.point(edge)[:2],height],guard,tolerance=.0005)
        _save(policy,'e46-actual-tip-down3-ready',dict(context,actual_edge_height_m=float(policy.point(edge)[2]),source_minimum_edge_height_m=height-.0002))
    insert(policy,name,edge,side,direction,height,guard,
        resume_backstop=context.get('backstop_already_placed')is True,
        park_task=context.get('backstop_park_task'),entry_step_m=float(context.get('entry_step_m',.003)),
        entry_tolerance_m=float(context.get('entry_tolerance_m',.001)))
    _save(policy,'e46-after-relative-entry',dict(context,direction_task=direction.tolist(),edge_height_m=height))
    if not policy.contact(name,t['actor']):raise ToolExecutionError('Restored relative entry has no actual blade support')
    def loaded():
        guard()
        if not policy.contact(name,t['actor']):raise ToolExecutionError('Restored block lost actual blade support')
    policy.stage('suffix-independent-blade-lift')
    policy.move_point(side,work,policy.point(work)+[0,0,.065],loaded)
    body=policy.snapshot()[0][name];actual_bottom=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
    if any(body['grasp'])or policy.contact(name,'table')or actual_bottom-bottom<.006:
        raise ToolExecutionError('Restored relative entry did not yield a real independent blade lift')
    _save(policy,'e46-after-independent-lift',context)
    destination=policy.destination(name)
    policy.stage('suffix-carry-scooped-food')
    height=max(destination[2]+.08,.92)
    policy.move_point(side,work,[*policy.point(work)[:2],height],loaded)
    policy.move_point(side,work,[*destination[:2],height],loaded)
    policy.move_point(side,work,destination+[0,0,.003],loaded)
    policy.stage('suffix-withdraw-blade-release')
    withdraw=policy.frame(work)[1]@np.asarray(t['withdraw_local'],float)
    policy.move_point(side,work,policy.point(work)+withdraw*.10,guard)
    policy.wait(3);policy.move(side,policy.tip(side)+[0,0,.07],guard)
    body=policy.snapshot()[0][name]
    if any(body['grasp'])or policy.contact(name,t['actor'])or not policy.contact(name,'table'):
        raise ToolExecutionError('Transported scoop did not release to actual destination support')
    _save(policy,'e46-after-delivery-and-withdrawal',context)


def solve(author,checkpoint,request):
    spec=author.scene.spec;task=spec.get('id');entry=request.get('entry')
    if (task not in ENTRIES or entry not in ENTRIES[task]or
            spec.get('execution_design',{}).get('revision')!=REVISION_V3 or
            not getattr(author,'control_report',{}).get('engineering_reference_only')or
            checkpoint.get('diagnostic_only')is not True or
            checkpoint.get('identity')!=identity(author.c)or
            not getattr(author.c,'_engineering_diagnostic_only',False)):
        raise ToolExecutionError('Explicit validated tool engineering checkpoint suffix required')
    context=dict(checkpoint.get('context',{}));context.update(request.get('context',{}))
    policy=ToolAuthor(author);policy.s=copy.deepcopy(policy.s);start=policy.c.steps
    _save(policy,'restored-'+entry,context)
    if task=='E42':
        if context.get('forward_handle_regrasp') is True:
            from .engineering_e42_regrasp import regrasp
            t=policy.s['tools']['main'];side=context.get('tool_side','right')
            grip=dict(actor=t['actor'],local=t['grasp_local'],jaw_axis_local=t['jaw_axis_local'])
            t,grip,side=regrasp(policy,t,grip,side)
            policy.tool=lambda:(t,grip,side)
        else:
            t,grip,side=_held_source(policy,context)
            policy.tool=lambda:(_held_source(policy,context))
        names=_remaining(policy,context,'balls');policy.s['groups']['balls']=list(names)
        policy.push()
    elif task=='E43' and entry=='e43-cooked-ball-audit':
        from .engineering_tool_geometry_audit import ball_support_audit
        ball_support_audit(policy)
    elif task=='E43' and entry=='e43-passive-roll':
        from .engineering_tool_geometry_audit import passive_ball_roll
        passive_ball_roll(policy)
    elif task=='E43' and entry=='e43-guide-from-source-hold':
        if not checkpoint.get('context',{}).get('rail_audit') or any(any(v['grasp'])for v in policy.snapshot()[0].values()):
            raise ToolExecutionError('Measured source rail-hold checkpoint with empty hands required')
        if not policy.contact('ball','launcher') or not policy.contact('ball','gate'):
            raise ToolExecutionError('Restored source gate must still retain the actual ball')
        policy.guide()
    elif task=='E43' and entry=='e43-reposition-held-guide':
        from .execution_design_e43_guide_plan import NATIVE_RESPONSE
        if context.get('guide_response')!=NATIVE_RESPONSE:
            raise ToolExecutionError('Measured source guide response calibration required')
        if not policy.contact('ball','launcher')or not policy.contact('ball','gate'):
            raise ToolExecutionError('Held-guide suffix requires the source ball still behind its gate')
        _held_source(policy,context);policy.tool=lambda:_held_source(policy,context)
        policy._engineering_guide_response=NATIVE_RESPONSE
        policy.guide()
    elif task=='E43':
        from .execution_design_e43_trigger import open_upper_gate
        t,grip,side=_held_source(policy,context)
        open_upper_gate(policy,grip,side)
    elif task=='E45' and entry=='e45-cavity-audit':
        from .engineering_e45_cavity_audit import audit
        audit(policy,context.get('cup_side','right'),geometry_only=context.get('geometry_only')is True)
    elif task=='E45' and entry=='e45-sweep-audit':
        from .engineering_tool_geometry_audit import pour_sweep_audit
        pour_sweep_audit(policy,context.get('cup_side','right'))
    elif task=='E45' and entry=='e45-incremental-tilt':
        cup=policy.s['containers']['cup'];name=cup['object'];side=context.get('cup_side','right')
        ref=dict(actor=name,local=cup['grasp_local']);degrees=float(context.get('step_degrees',2.))
        if side not in('left','right')or not .5<=degrees<=2.:
            raise ToolExecutionError('Bounded actual held-cup tilt diagnostic required')
        policy.require_held(ref,side);before=policy.snapshot()[0][name]['mat'].copy()
        policy.stage('one-small-held-cup-tilt')
        policy.act(side,policy.s['tool_expert']['pour_rotation_token'],degrees=degrees)
        policy.require_held(ref,side);after=policy.snapshot()[0][name]['mat']
        measured=float(np.rad2deg(np.arccos(np.clip((np.trace(after@before.T)-1)/2,-1,1))))
        (author.out/'incremental-cup-tilt.private.json').write_text(json.dumps(dict(
            public_actions=1,requested_degrees=degrees,actual_cup_rotation_degrees=measured,
            real_bilateral_grip_retained=True,diagnostic_only=True,whole_task_positive=False)))
    elif task=='E45':_pour(policy,context,entry)
    elif entry=='e46-cooked-blade-audit':
        from .engineering_tool_geometry_audit import blade_front_audit
        _held_source(policy,context);blade_front_audit(policy)
    elif entry=='e46-relative-insert':_relative_scoop(policy,context)
    else:
        t,grip,side=_held_source(policy,context);names=_remaining(policy,context,'cargo')
        policy.s['groups']['cargo']=list(names);policy.tool=lambda:(_held_source(policy,context))
        policy.spatula()
    _save(policy,'completed-'+entry,context)
    return dict(task=task,variant=spec['variant'],entry=entry,actions=policy.c.steps-start,
        checkpoint_sha256=checkpoint['checkpoint_sha256'],diagnostic_only=True,
        source_initial_full_positive=False,execution_finished=True,suffix_completed=True,
        physics_success_not_asserted=True,native_validation_required=True,
        operations=policy.operations)
