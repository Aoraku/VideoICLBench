"""Private E24 candidate: real tabletop push, then pinch a supported overhang.

The original lid/box geometry and scoring remain untouched. Every displacement
uses public actions. The measured table edge permits the lower open finger to
pass below the tabletop only while its actual collider is outside the table.
"""
import math
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .author_orientation import _axis_angle

LID_SHA='180837493663657fecabc2cbfb1f3ffeedfc96c700ae4ae4a1c82eae5c412fde'
# The source plate is centred at X=Y=0. The offset point is a side-pinch
# site near its edge, not the body's centre used to measure the push distance.
LID_PLATE_CENTER_LOCAL=np.array([0.,0.,.0200153])
LID_EDGE_GRASP_LOCAL=np.array([0.,.098,.0200153])
LID_CENTER_LOCAL=LID_EDGE_GRASP_LOCAL  # Existing private candidate imports.


def table_bounds(policy):
    layout=policy.a.scene.layout;table=layout.config['table']
    center=layout.world_to_task(table['position']);half=np.abs(layout.task_rotation.T)@(np.asarray(table['size'])/2)
    return center-half,center+half


def side_grasp_rotation(lid_rotation):
    r=np.asarray(lid_rotation,float);jaw=r[:,2];forward=-r[:,1]
    return np.column_stack((np.cross(jaw,forward),jaw,forward))


def empty_rotation(policy,side,target):
    from .realworld_tool_expert import _axis_rotation
    from .execution_design_drawer_ik_probe import inspect
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(120):
        state,_=policy.snapshot()
        if any(x['grasp'][0 if side=='left'else 1]for x in state.values()):
            raise ToolExecutionError('E24 empty orientation cannot rotate a held object')
        current=policy.a.tcp_rotation_task(side);axis,error=_axis_angle(target@current.T)
        if error<math.radians(2):return
        if policy.tip(side)[2]<.94:raise ToolExecutionError('E24 empty hand rotation requires real high clearance')
        choices=[];accepted=[]
        for degree in (5.,2.5,1.25,.625,.5):
            if degree<policy.min_deg or degree>policy.max_deg:continue
            for i in range(3):
                for sign in (1,-1):
                    candidate=_axis_rotation(np.eye(3)[i],sign*math.radians(degree))@current
                    remaining=_axis_angle(target@candidate.T)[1]
                    if remaining<error-math.radians(.01):choices.append(dict(token=labels[i][int(sign<0)],degrees=degree,rotation=candidate.tolist(),position=policy.tip(side).tolist(),error=remaining))
            rows=inspect(policy.a,policy.c,side,[dict(rotation=x['rotation'],position=x['position'])for x in choices])
            if len(rows)!=len(choices):raise ToolExecutionError('Missing E24 empty wrist IK diagnostics')
            accepted=[i for i,r in enumerate(rows)if r.get('kinematically_reachable') and r.get('position_error_m',1)<.001 and r.get('orientation_error_rad',1)<math.radians(1.5) and r.get('minimum_joint_margin_rad',0)>.05 and r.get('joint_distance_rad',9)<.35]
            if accepted:break
            choices=[]
        if not choices or not accepted:raise ToolExecutionError('No safe nearby public E24 empty wrist rotation')
        i=min(accepted,key=lambda j:choices[j]['error']);choice=choices[i]
        policy.act(side,choice['token'],degrees=choice['degrees'])
    raise ToolExecutionError('E24 empty wrist rotation exhausted')


def finger_table_clearance(policy,side,lo,hi):
    measured=policy.a.finger_geometry(side)
    if measured.get('source')!='actual_collision_mesh_current_body_pose':raise ToolExecutionError('Actual E24 finger collision geometry required')
    rows=measured.get('fingers',[])
    if len(rows)!=2 or {r.get('name')for r in rows}!={'panda_leftfinger','panda_rightfinger'}:
        raise ToolExecutionError('Both actual E24 finger colliders required')
    for row in rows:
        low=np.asarray(row['aabb_min_task_m'],float);high=np.asarray(row['aabb_max_task_m'],float)
        if low.shape!=(3,)or high.shape!=(3,)or not np.isfinite([low,high]).all()or(low>high).any():
            raise ToolExecutionError('Invalid actual E24 finger bounds')
        above=float(low[2])>=float(hi[2])+.001
        outside=any(high[i]<lo[i]-.003 or low[i]>hi[i]+.003 for i in (0,1))
        if not above and not outside:raise ToolExecutionError('E24 actual lower finger overlaps tabletop envelope')
    return measured


def _push_plane_target(policy,side,body):
    """Keep the original contact height from the current measured plate pose."""
    center=np.asarray(body['pos'],float)+np.asarray(body['mat'],float)@LID_PLATE_CENTER_LOCAL
    target=np.asarray(policy.tip(side),float).copy()
    target[1]=center[1]
    target[2]=center[2]-.0100153
    return target


def _push_public_increment(policy,side,token,lo,hi,*,mm,budget_start=None,maximum_actions=12):
    if budget_start is not None and policy.c.steps-budget_start>=maximum_actions:
        raise ToolExecutionError('E24 short contact push exhausted its public-action bound')
    finger_table_clearance(policy,side,lo,hi)
    policy.act(side,token,mm=mm)
    feedback=policy.c.action_feedback().get('control_feedback',{}).get(side,{})
    if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names')
            or feedback.get('consecutive_ik_refusals',0)>0):
        raise ToolExecutionError('E24 public contact push controller rejected the action')
    finger_table_clearance(policy,side,lo,hi)


def _coarse_push_plane(policy,side,lo,hi,*,budget_start=None):
    """Correct a coarse contact band at most twice; never chase a loaded point."""
    for _ in range(2):
        state,_=policy.snapshot();target=_push_plane_target(policy,side,state['lid'])
        error=target-policy.tip(side);error[0]=0.
        if np.max(np.abs(error))<=.004:return
        axis=int(np.argmax(np.abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        _push_public_increment(policy,side,token,lo,hi,mm=min(3.,abs(float(error[axis]))*1000),budget_start=budget_start)
    state,_=policy.snapshot();error=_push_plane_target(policy,side,state['lid'])-policy.tip(side)
    if np.max(np.abs(error[1:]))>.006:
        raise ToolExecutionError('E24 actual pusher remains outside coarse contact band after bounded correction')


def _push_contact_observation(policy,side):
    state,contacts=policy.snapshot();forces=getattr(policy.c,'contact_forces',{})
    pairs=[frozenset(('lid',f'{side}_finger{i}'))for i in (1,2)]
    force=[]
    for pair in pairs:
        value=forces.get(pair)
        force.append(float(value)if isinstance(value,(int,float))and math.isfinite(value)else None)
    return dict(lid_position_task_m=np.asarray(state['lid']['pos']).tolist(),
        finger_contact=[pair in contacts for pair in pairs],contact_force_n=force,
        lid_table_contact=frozenset(('lid','table'))in contacts)


def _lid_push_context(policy):
    from .execution_design import REVISION_V3
    if (policy.task!='E24' or policy.spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or not policy.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('E24 v3 independent engineering only')
    obj=policy.objects['lid']
    if obj.get('source_asset',{}).get('sha256')!=LID_SHA:raise ToolExecutionError('Unreviewed physical lid')
    state,contacts=policy.snapshot();body=state['lid'];rotation=np.asarray(body['mat'])
    if rotation[2,2]<.98 or abs(rotation[0,1])<.98:
        raise ToolExecutionError('E24 overhang candidate requires actual near-flat sideways lid')
    lo,hi=table_bounds(policy);side='left';origin=np.asarray(body['pos']).copy()
    target_center=float(lo[0])+.050
    if origin[0]<=target_center or origin[0]-target_center>.45:
        raise ToolExecutionError('Unreviewed E24 lid push distance')
    return obj,lo,hi,side,origin,target_center


def pickup_lid_overhang(policy):
    context=_lid_push_context(policy)
    obj,lo,hi,side,origin,target_center=context
    # Close the empty fingers high above the table, then use their actual
    # negative-X face to push the positive-X side of the original lid.
    policy.stage('E24-lid-public-push-setup')
    policy.act(side,'RELEASE');policy.move(side,[*policy.tip(side)[:2],max(.98,float(policy.tip(side)[2]))])
    from .realworld_tool_expert import _axis_rotation
    # A ten-degree forward pitch keeps the wrist behind the leading fingers.
    # The original straight-down pose reaches its extension boundary before
    # the measured positive-X lid edge. All actual collision guards remain.
    empty_rotation(policy,side,_axis_rotation([0,1,0],math.radians(-10))@np.diag([-1.,1.,-1.]))
    policy.act(side,'GRASP')
    state,_=policy.snapshot()
    if any(x['grasp'][0]for x in state.values()):raise ToolExecutionError('E24 push hand unexpectedly holds an object')
    return continue_lid_from_transit(policy,_push_context=context)


def _empty_pusher_state(policy,side):
    state,_=policy.snapshot()
    if any(any(body['grasp'])for body in state.values()):
        raise ToolExecutionError('E24 transit continuation requires both actual hands empty')
    from .realworld_tool_expert import _axis_rotation
    expected=_axis_rotation([0,1,0],math.radians(-10))@np.diag([-1.,1.,-1.])
    if _axis_angle(expected@np.asarray(policy.a.tcp_rotation_task(side)).T)[1]>math.radians(4):
        raise ToolExecutionError('E24 transit continuation requires the measured ten-degree pusher')
    if not isinstance(getattr(policy.c,'grips',None),dict)or policy.c.grips.get(side)!=0.:
        raise ToolExecutionError('E24 transit continuation requires the existing closed empty pusher command')
    return state


def _pusher_approach(policy,side,obj,state):
    # Recompute from the restored actual lid/finger poses. Earlier transit
    # waypoints and their stale joint model are deliberately not reused.
    geom=policy.a.finger_geometry(side);leading=min(x['aabb_min_task_m'][0]for x in geom['fingers'])-policy.tip(side)[0]
    extent=np.abs(np.asarray(state['lid']['mat']))@np.asarray(obj['size']);center=np.asarray(state['lid']['pos'])
    return np.array([center[0]+extent[0]+.004-leading,center[1],center[2]+.010])


def continue_lid_from_transit(policy,*,_push_context=None):
    """Resume the already closed ten-degree pusher; never repeat its setup."""
    context=_lid_push_context(policy)if _push_context is None else _push_context
    obj,lo,hi,side,origin,target_center=context
    state=_empty_pusher_state(policy,side)
    approach=_pusher_approach(policy,side,obj,state)
    from .execution_design_e24_transit import empty_pusher_transfer
    empty_pusher_transfer(policy,side,approach)
    policy.move(side,approach,lambda:finger_table_clearance(policy,side,lo,hi))
    return push_from_contact_band(policy,_push_context=context)


def push_from_contact_band(policy,*,_push_context=None):
    """Continue an actual pusher already at the completed approach boundary."""
    context=_lid_push_context(policy)if _push_context is None else _push_context
    obj,lo,hi,side,origin,target_center=context
    state=_empty_pusher_state(policy,side)
    approach=_pusher_approach(policy,side,obj,state)
    if np.max(np.abs(policy.tip(side)-approach))>.003:
        raise ToolExecutionError('E24 pusher is outside the measured original approach contact band')
    finger_table_clearance(policy,side,lo,hi)
    policy.stage('E24-lid-public-supported-edge-push')
    for _ in range(160):
        state,contacts=policy.snapshot();position=np.asarray(state['lid']['pos'])
        finger_table_clearance(policy,side,lo,hi)
        if position[0]<=target_center:break
        if abs(position[1]-origin[1])>.035 or state['lid']['mat'][2,2]<.98:
            raise ToolExecutionError('E24 actual lid departed supported push corridor')
        if position[0]<lo[0]+.035:raise ToolExecutionError('E24 lid center crossed supported edge margin')
        # Repeated public X actions leave small actual Y/Z residuals. Without
        # feedback correction these accumulated until the closed fingers
        # passed above the source plate while the lid remained on the table.
        # Correct only the original contact plane, using actual public moves.
        _coarse_push_plane(policy,side,lo,hi)
        _push_public_increment(policy,side,'BACK',lo,hi,mm=3.)
    else:raise ToolExecutionError('E24 actual lid did not reach measured supported overhang')
    policy.move(side,policy.tip(side)+[.03,0,.08]);policy.act(side,'RELEASE')
    policy.wait(3);state,contacts=policy.snapshot();body=state['lid'];rotation=np.asarray(body['mat'])
    if (frozenset(('lid','table'))not in contacts or any(body['grasp']) or body['pos'][0]<lo[0]+.035 or rotation[2,2]<.98):
        raise ToolExecutionError('E24 overhang has no measured stable table support')
    policy.stage('E24-lid-side-pinch-outside-table')
    policy.move(side,[*policy.tip(side)[:2],.98]);empty_rotation(policy,side,side_grasp_rotation(rotation))
    ref=dict(actor='lid',local=LID_EDGE_GRASP_LOCAL.tolist(),jaw_axis_local=[0,0,1])
    point=policy.point(ref);outside=point+rotation[:,1]*.10
    policy.move(side,[outside[0],outside[1],.98]);policy.move(side,outside,lambda:finger_table_clearance(policy,side,lo,hi))
    finger_table_clearance(policy,side,lo,hi)
    policy.move(side,point,lambda:finger_table_clearance(policy,side,lo,hi))
    stable=0
    for _ in range(5):
        policy.act(side,'GRASP');finger_table_clearance(policy,side,lo,hi)
        stable=stable+1 if policy.held(ref,side)else 0
        if stable>=3:break
    else:raise ToolExecutionError('E24 real lid edge lacks settled bilateral grip')
    policy.move(side,policy.tip(side)+[0,0,.10],lambda:policy.require_held(ref,side))
    policy.operations.append(dict(stage='E24-physical-overhang-side-grasp',source_sha256=LID_SHA,
        table_bounds_task_m=[lo.tolist(),hi.tolist()],target_lid_center_x=target_center,
        measured_lid_pose_after_push=body,grasp_local=ref['local'],public_actions_only=True))
    return ref,side


def push_contact_short(policy):
    """From a real existing lid contact, test only bounded public3mm pushes."""
    obj,lo,hi,side,origin,target_center=_lid_push_context(policy)
    state=_empty_pusher_state(policy,side);position=np.asarray(state['lid']['pos']);tip=policy.tip(side)
    extent=np.abs(np.asarray(state['lid']['mat']))@np.asarray(obj['size'])
    if (tip[0]<=position[0] or tip[0]>position[0]+extent[0]+.04
            or np.max(np.abs((_push_plane_target(policy,side,state['lid'])-tip)[1:]))>.006):
        raise ToolExecutionError('E24 short push requires the actual positive-edge coarse contact band')
    finger_table_clearance(policy,side,lo,hi)
    before=_push_contact_observation(policy,side)
    start=policy.c.steps;observations=[before]
    if not any(before['finger_contact']):
        # Native state restoration does not preserve the PhysX contact cache.
        # Inside the already checked contact band, reacquire by real public
        # motion only; an old checkpoint's force is never replayed as contact.
        policy.stage('local-E24-rebuild-real-contact-at-most-two-one-mm-steps')
        for _ in range(2):
            prior_tip=policy.tip(side).copy()
            _push_public_increment(policy,side,'BACK',lo,hi,mm=1.,budget_start=start)
            state=_empty_pusher_state(policy,side);actual=np.asarray(state['lid']['pos'])
            if (abs(actual[1]-origin[1])>.035 or state['lid']['mat'][2,2]<.98
                    or actual[0]<lo[0]+.035):
                raise ToolExecutionError('E24 public contact approach left original measured contact band')
            if float(prior_tip[0]-policy.tip(side)[0])<.0001:
                raise ToolExecutionError('E24 public one-mm contact approach failed to advance BACK')
            observations.append(_push_contact_observation(policy,side))
            if any(observations[-1]['finger_contact']):break
        else:raise ToolExecutionError('E24 failed to rebuild actual lid-finger contact within two public1mm steps')
    # A restored lid may settle down and slide while contact is reacquired.
    # Only displacement after the real new contact counts as short-push travel.
    contact_origin_x=float(policy.snapshot()[0]['lid']['pos'][0])
    policy.stage('local-E24-bounded-real-contact-three-mm-push')
    for _ in range(4):
        if not any(_push_contact_observation(policy,side)['finger_contact']):
            _coarse_push_plane(policy,side,lo,hi,budget_start=start)
        _push_public_increment(policy,side,'BACK',lo,hi,mm=3.,budget_start=start)
        state,_=policy.snapshot();body=state['lid'];actual=np.asarray(body['pos'])
        if (any(any(item['grasp'])for item in state.values()) or abs(actual[1]-origin[1])>.035
                or body['mat'][2,2]<.98 or actual[0]<lo[0]+.035):
            raise ToolExecutionError('E24 actual lid departed original empty supported-push corridor')
        observations.append(_push_contact_observation(policy,side))
        travel=float(contact_origin_x-actual[0])
        if travel>=.0005:
            return dict(local_completed=True,actions=policy.c.steps-start,operations=policy.operations,
                measured_lid_travel_x_m=travel,observations=observations,
                measured_lid_x_slide_before_rebuilt_contact_m=float(origin[0]-contact_origin_x),
                maximum_public_actions=12,maximum_back_pushes=4,requested_public_push_mm=3.,
                maximum_contact_approach_actions=2,requested_contact_approach_mm=1.,
                full_supported_overhang_or_side_grasp_completed=False)
    raise ToolExecutionError('E24 bounded short contact push made less than0.5mm measured lid travel')


def _lid_table_support_during(policy,action):
    """Observe native force ticks without altering the evaluator or commands."""
    evaluator=policy.c.evaluator;original=evaluator.update;rows=[];all_lid=[]
    def observed(state,contacts,dt):
        for pair in contacts:
            force=policy.c.contact_forces.get(pair)
            if 'lid'in pair and isinstance(force,(int,float))and math.isfinite(force)and force>0:
                all_lid.append(dict(physics_tick=int(policy.c.physics_ticks),bodies=sorted(pair),force_n=float(force),dt_s=float(dt)))
        force=policy.c.contact_forces.get(frozenset(('lid','table')))
        if (frozenset(('lid','table'))in contacts and isinstance(force,(int,float))
                and math.isfinite(force)and force>0):
            rows.append(dict(physics_tick=int(policy.c.physics_ticks),force_n=float(force),dt_s=float(dt)))
        return original(state,contacts,dt)
    evaluator.update=observed
    try:action()
    finally:evaluator.update=original
    return dict(positive_force_ticks=rows,positive_tick_count=len(rows),
        positive_duration_s=sum(row['dt_s']for row in rows),
        maximum_measured_force_n=max((row['force_n']for row in rows),default=0.),
        all_actual_lid_contact_force_ticks=all_lid)


def _lid_source_vertical_table_gap(policy,lo,hi):
    from .execution_design_e24_collision import actual_object_parts
    points=[part['points']for part in actual_object_parts(policy)
            if part['name'].startswith('object:lid:')]
    if not points:raise ToolExecutionError('E24 actual source lid collider vertices required for support band')
    points=np.concatenate(points);inside=np.all((points[:,:2]>=lo[:2])&(points[:,:2]<=hi[:2]),axis=1)
    if not np.any(inside):raise ToolExecutionError('E24 source lid has no measured collider vertices above tabletop')
    return float(np.min(points[inside,2])-hi[2])


def approach_settled_lid1_and_push(policy,parameters,*,source_boundary=(1,102)):
    """The admitted native1/102 lid is already on the actual table."""
    author=policy.a;spec=author.scene.spec;checkpoint=getattr(author,'_engineering_resume_checkpoint',{})
    source=checkpoint.get('source',{})
    if (parameters!={}or spec.get('variant')!='A'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('condition')!='I'
            or checkpoint.get('diagnostic_only')is not True
            or(source.get('steps'),source.get('physics_ticks'))!=source_boundary
            or not getattr(policy.c,'_engineering_diagnostic_only',False)
            or not getattr(policy.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E24 A/I4201 native1/102 settled checkpoint required')
    obj,lo,hi,side,origin,target_center=_lid_push_context(policy)
    state=_empty_pusher_state(policy,side);finger_table_clearance(policy,side,lo,hi)
    position=np.asarray(state['lid']['pos']);extent=np.abs(np.asarray(state['lid']['mat']))@np.asarray(obj['size'])
    tip=policy.tip(side)
    if tip[0]<=position[0]or tip[0]>position[0]+extent[0]+.04:
        raise ToolExecutionError('E24 settled approach must start at the measured positive-X lid side')
    def observation(action_support=None):
        state=_empty_pusher_state(policy,side);actual=np.asarray(state['lid']['pos'])
        row=_push_contact_observation(policy,side)
        force=policy.c.contact_forces.get(frozenset(('lid','table')))
        endpoint_support=bool(row['lid_table_contact']and isinstance(force,(int,float))and math.isfinite(force)and force>0)
        # A resting lid can report no table pair and can be supported by an
        # actual box/rim instead. Preserve those observations without adding
        # a table-name or force-stability requirement to the original task.
        gap=_lid_source_vertical_table_gap(policy,lo,hi)
        actual_state,actual_contacts=policy.snapshot()
        if any(any(actual_state[name]['grasp'])or frozenset((name,'box'))not in actual_contacts
               for name in policy.s['cups']):
            raise ToolExecutionError('E24 lid approach disturbed a real released cup/box contact')
        if (abs(actual[1]-origin[1])>.035 or state['lid']['mat'][2,2]<.98 or actual[0]<lo[0]+.035):
            raise ToolExecutionError('E24 settled lid lost actual supported push corridor')
        finger_table_clearance(policy,side,lo,hi)
        row['lid_table_force_n']=float(force)if isinstance(force,(int,float))and math.isfinite(force)else None
        row['endpoint_lid_table_support']=endpoint_support
        row['source_vertex_vertical_table_gap_m']=gap
        row['actual_action_support']=action_support
        return row
    start=policy.c.steps;rows=[observation()]
    policy.stage('local-E24-native1-settled-rim-approach')
    for _ in range(4):
        if any(rows[-1]['finger_contact']):break
        before=policy.tip(side).copy()
        support=_lid_table_support_during(policy,lambda:_push_public_increment(policy,side,'BACK',lo,hi,mm=3.,budget_start=start,maximum_actions=6))
        if float(before[0]-policy.tip(side)[0])<.0001:
            raise ToolExecutionError('E24 settled BACK approach failed to advance')
        rows.append(observation(support))
    if not any(rows[-1]['finger_contact']):
        raise ToolExecutionError('E24 measured settled rim lacks real contact after four public3mm approaches')
    contact_origin=float(policy.snapshot()[0]['lid']['pos'][0])
    policy.stage('local-E24-native1-one-real-contact-three-mm-push')
    before=policy.tip(side).copy()
    support=_lid_table_support_during(policy,lambda:_push_public_increment(policy,side,'BACK',lo,hi,mm=3.,budget_start=start,maximum_actions=6))
    if float(before[0]-policy.tip(side)[0])<.0001:
        raise ToolExecutionError('E24 real-contact BACK push failed to advance')
    rows.append(observation(support));after=float(policy.snapshot()[0]['lid']['pos'][0]);travel=contact_origin-after
    if travel<.0005:raise ToolExecutionError('E24 real-contact3mm push made less than0.5mm actual lid travel')
    return dict(local_completed=True,actions=policy.c.steps-start,operations=policy.operations,
        observations=rows,source_actions=source_boundary[0],source_physics_ticks=source_boundary[1],
        measured_lid_travel_after_contact_m=travel,measured_lid_slide_during_approach_m=float(origin[0]-contact_origin),
        maximum_approach_actions=4,approach_public_mm=3.,maximum_total_public_actions=6,
        full_supported_overhang_or_side_grasp_completed=False)
