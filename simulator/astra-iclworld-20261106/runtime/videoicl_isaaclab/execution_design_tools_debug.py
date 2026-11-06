"""Short, diagnostic-only E28/E37 suffixes after startup reconstruction.

No acquisition, initial-episode history, scoring labels or native acceptance are
restored here. The caller must first validate actual restored grip/contact.
"""
import math
import json
import numpy as np
from .realworld_tool_expert import ToolAuthor,ToolExecutionError
from .realworld_structural_expert import StructuralAuthor


def _context(author,payload,task):
    if payload.get('schema')!='engineering-native-checkpoint-v1' or payload.get('diagnostic_only')is not True:
        raise ValueError('Tools suffix requires an explicit diagnostic engineering checkpoint')
    spec=author.scene.spec;identity=payload.get('identity',{})
    if spec['id']!=task or any(identity.get(k)!=spec[k]for k in ('variant','seed'))or identity.get('task')!=task:
        raise ValueError('Tools checkpoint task/variant/seed mismatch')
    if not author.control_report.get('engineering_reference_only'):
        raise ValueError('Tools checkpoint suffix cannot run in model evaluation')
    for key in ('assignment_identity_sha256','source_sha256'):
        if identity.get(key)!=spec['execution_design'][key]:raise ValueError('Tools checkpoint source identity mismatch')
    return payload.get('context',{})


def _budget(policy,context,default):
    limit=context.get('maximum_actions',default)
    if type(limit)is not int or not 1<=limit<=3000:raise ValueError('Bounded integer diagnostic action budget required')
    policy.limit=min(policy.limit,limit)


def _e28_achieved_contact_hold(policy,guard,mode='private'):
    if mode=='public':
        policy.stage('checkpoint-e28-public-achieved-pose-rebase')
        guard();policy.a.act('ROTATE_CCW','ROTATE_CCW',mm=1.,rotation_deg=.5);guard()
        return
    if mode!='private':raise ValueError('Reviewed actual contact hold mode required')
    from .engineering_native_tick import diagnostic_tick_scope
    policy.stage('checkpoint-e28-actual-contact-hold-before-withdrawal')
    with diagnostic_tick_scope(policy.a):
        receipt=policy.c.author_move({s:policy.tip(s)for s in ('left','right')},
            max_speed=.03,max_acceleration=.1,guard=guard,tracking_tolerance=.001)
    with(policy.a.out/'demo-actions.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(stage=policy.a.stage,control='private_continuous_actual_contact_hold',
            tips={s:policy.tip(s).tolist()for s in ('left','right')},**receipt))+'\n')



def _near_blade_ref(policy,tool):
    from .execution_design_e28_reference import actual_leading_surfaces
    actor=tool['actor'];actual_leading_surfaces(policy,actor)
    vertices=np.asarray(policy._e28_local_collision_vertices,float)
    rear=float(tool['support_bounds']['lower'][0]);candidates=[]
    for distance in (.012,.020,.030,.045,.060,.080,.100,.130):
        station=rear-distance;band=vertices[np.abs(vertices[:,0]-station)<=.004]
        if len(band)<4:continue
        lower=band.min(0);upper=band.max(0);width=float(upper[1]-lower[1]);thickness=float(upper[2]-lower[2])
        if not .002<=width<=.070 or not .001<=thickness<=.030:continue
        local=np.array([station,(lower[1]+upper[1])/2,(lower[2]+upper[2])/2])
        candidates.append(dict(local=local.tolist(),collision_vertices=len(band),actual_band_lower=lower.tolist(),actual_band_upper=upper.tolist(),jaw_width_m=width,thickness_m=thickness))
    if not candidates:raise ToolExecutionError('No actual finite source neck cross-section fits the open Panda jaws')
    # Prefer a thick neck section over a broad, thin blade shoulder. The
    # latter can briefly touch both fingertips yet slide out as lifting starts.
    thick=[row for row in candidates if row['thickness_m']>=.012 and row['jaw_width_m']<=.04]
    requested=getattr(policy,'_e28_grasp_station',None)
    if requested is not None:
        if not math.isfinite(float(requested)):raise ValueError('Finite actual source grasp station required')
        chosen=min(candidates,key=lambda row:abs(row['local'][0]-float(requested)))
        if abs(chosen['local'][0]-float(requested))>.002:raise ToolExecutionError('Requested grasp station lacks a measured finite material section')
    else:chosen=max(thick,key=lambda row:row['local'][0])if thick else min(candidates,key=lambda row:row['jaw_width_m']/row['thickness_m'])
    (policy.a.out/'E28-neck-grasp-geometry.private.json').write_text(json.dumps(dict(actual_source_collision_mesh=True,candidates=candidates,chosen=chosen,native_grasp_not_yet_verified=True),indent=2)+'\n')
    return dict(actor=actor,local=chosen['local'],jaw_axis_local=tool['jaw_axis_local'])


def _regrip_neck(policy,tool,side,edge,food):
    actor=tool['actor'];before=policy.point(edge).copy();neck=_near_blade_ref(policy,tool)
    if not policy.contact(actor,'table'):
        if not getattr(policy,'_e28_level_entry_retract',False):
            raise ToolExecutionError('Neck regrip requires real table-supported tool')
        from .execution_design_e28_reference import actual_leading_surfaces
        obj=next(o for o in policy.spec['objects']if o['id']==food);body=policy.snapshot()[0][food]
        floor=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
        surface=actual_leading_surfaces(policy,actor)
        if not floor-.002<=surface['bottom_z']<=floor+.002:
            raise ToolExecutionError('Neck regrip requires real table-supported tool')
        policy.stage('e28-measured-table-contact-before-real-release')
        for _ in range(3):
            policy.require_held(neck,side);policy.act(side,'DOWN',mm=1.)
            if policy.contact(actor,'table'):break
        else:raise ToolExecutionError('Actual held tool did not regain table contact before regrip')
    policy.stage('checkpoint-e28-table-supported-neck-regrip');policy.act(side,'RELEASE')
    def resting():
        if not policy.contact(actor,'table'):raise ToolExecutionError('Released spatula lost actual table support during neck regrip')
        if any(policy.snapshot()[0][food]['grasp']):raise ToolExecutionError('Neck regrip touched the selected food with a hand grasp')
    resting();height=max(.96,float(policy.tip(side)[2])+.06)
    policy.move(side,[*policy.tip(side)[:2],height],resting)
    target=policy.point(neck);policy.move(side,[*target[:2],height],resting)
    target=policy.point(neck).copy();target[2]=max(float(target[2]),policy.a.floor_clear_tcp(side))
    policy.move(side,target,resting,tolerance=.002)
    settled=0
    for _ in range(8):
        policy.act(side,'GRASP')
        sensor,labels=policy.a.scene.contacts[actor]
        matrix=sensor.data.force_matrix_w[0].sum(axis=0).cpu().numpy()
        forces=[matrix[labels.index(f'{side}_finger{i}')]for i in (1,2)]
        magnitudes=[float(np.linalg.norm(force))for force in forces]
        opposition=float(-forces[0]@forces[1]/max(magnitudes[0]*magnitudes[1],1e-12))
        verified=policy.held(neck,side)and min(magnitudes)>.7 and opposition>.7
        with (policy.a.out/'E28-real-neck-grasp-forces.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(step=policy.c.steps,point_local=neck['local'],forces_world_n=[force.tolist()for force in forces],opposition=opposition,real_opposed_grip=bool(verified)))+'\n')
        settled=settled+1 if verified else 0
        if settled>=3:break
    else:raise ToolExecutionError('Actual opposed near-neck spatula grip was not acquired')
    if getattr(policy,'_e28_level_entry_retract',False):
        guard=lambda:policy.require_held(neck,side)
        direction=np.asarray(policy.snapshot()[0][actor]['mat'])[:,0].copy();direction[2]=0;direction/=np.linalg.norm(direction)
        policy.stage('e28-near-com-retract-before-level-entry')
        policy.move(side,policy.tip(side)-direction*.035,guard)
        policy.move(side,policy.tip(side)+[0.,0.,.06],guard)
        from .execution_design_e28_reference import level_handle
        level_handle(policy,actor,side,guard,tolerance_degrees=1.,minimum_rotation_degrees=5.)
        _descend_neck_blade(policy,tool,side,food,neck,reject_food_contact=True)
    else:_stage_neck_blade(policy,tool,side,edge,food,neck,before)
    (policy.a.out/'E28-real-neck-regrip.private.json').write_text(json.dumps(dict(physical_grip_verified=True,grasp=neck,actual_edge=policy.point(edge).tolist(),no_object_pose_written=True),indent=2)+'\n')
    return neck


def _stage_neck_blade(policy,tool,side,edge,food,neck,before=None):
    """Lift first, then descend in 1mm pulses, stopping on actual support.

    A coarse material waypoint can push a sloped source shoulder through the
    table before the blade-edge target arrives. It must never precede this
    real-contact descent.
    """
    actor=tool['actor'];guard=lambda:policy.require_held(neck,side)
    before=policy.point(edge).copy()if before is None else np.asarray(before).copy()
    policy.stage('checkpoint-e28-neck-lift-clearance')
    for _ in range(16):
        guard()
        if not policy.contact(actor,'table')and policy.point(edge)[2]>=before[2]+.025:break
        policy.act(side,'UP',mm=3.);guard()
    else:raise ToolExecutionError('Actual neck grip could not lift spatula clear')
    from .execution_design_e28_reference import level_handle,actual_leading_surfaces
    level_handle(policy,actor,side,guard,tolerance_degrees=1.,minimum_rotation_degrees=5.)
    target=before.copy();target[2]=policy.point(edge)[2]
    policy.move_point(side,edge,target,guard)
    _descend_neck_blade(policy,tool,side,food,neck)


def _descend_neck_blade(policy,tool,side,food,neck,*,reject_food_contact=False):
    from .execution_design_e28_reference import actual_leading_surfaces
    actor=tool['actor'];guard=lambda:policy.require_held(neck,side)
    obj=next(o for o in policy.spec['objects']if o['id']==food);body=policy.snapshot()[0][food]
    bottom=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
    policy.stage('checkpoint-e28-neck-contact-descent')
    for _ in range(80):
        guard();surfaces=actual_leading_surfaces(policy,actor)
        if reject_food_contact and policy.contact(actor,food):
            raise ToolExecutionError('Entry descent contacted food before table-level insertion')
        with (policy.a.out/'E28-neck-contact-descent.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(step=policy.c.steps,food_bottom_z=bottom,
                actual_table_contact=policy.contact(actor,'table'),**surfaces))+'\n')
        if policy.contact(actor,'table'):
            if not(bottom-.006<=surfaces['bottom_z']<=bottom+.002 and surfaces['top_z']<=bottom+.004):
                raise ToolExecutionError('Neck-held actual blade tip cannot enter food underside at first table contact')
            return
        if surfaces['bottom_z']<bottom-.006:raise ToolExecutionError('Actual neck-held blade descended below source underside band')
        policy.act(side,'DOWN',mm=1.)
    raise ToolExecutionError('Actual neck-held blade failed to reach table support')


def _prepare_tip_entry(policy,tool,side,edge,food,grip):
    """Use the actual thin source tip, rather than pushing its curved lip."""
    actor=tool['actor'];guard=lambda:policy.require_held(grip,side)
    state=policy.snapshot()[0][actor];original=policy.point(edge).copy()
    direction=np.asarray(state['mat'])[:,0].copy();direction[2]=0.;direction/=np.linalg.norm(direction)
    policy.stage('checkpoint-e28-retract-blunt-lip-and-lift')
    policy.move(side,policy.tip(side)-direction*.035,guard)
    policy.move(side,policy.tip(side)+[0.,0.,.08],guard)
    current=np.asarray(policy.snapshot()[0][actor]['mat']);yaw=math.atan2(current[1,0],current[0,0])
    c,s=math.cos(yaw),math.sin(yaw);t=math.radians(17.);ct,st=math.cos(t),math.sin(t)
    desired=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])@np.array([[ct,0.,st],[0.,1.,0.],[-st,0.,ct]])
    policy.stage('checkpoint-e28-real-tip-down-entry-angle');history=[]
    for _ in range(40):
        guard();current=np.asarray(policy.snapshot()[0][actor]['mat']);delta=desired@current.T
        angle=math.acos(float(np.clip((np.trace(delta)-1)/2,-1.,1.)));history.append(angle)
        if angle<=math.radians(1.):break
        if policy.contact(actor,'table'):raise ToolExecutionError('Spatula touched table during clear-space entry-angle rotation')
        if len(history)>=12 and history[-12]-min(history[-11:])<math.radians(.5):raise ToolExecutionError('Actual source entry-angle rotation stalled')
        axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle));component=int(np.argmax(abs(axis)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(axis[component]<0)]
        policy.act(side,token,degrees=max(5.,min(8.,abs(math.degrees(angle*axis[component]))+2.8)))
    else:raise ToolExecutionError('Actual source entry-angle rotation exhausted bounded actions')
    guard();normal=np.asarray(policy.snapshot()[0][actor]['mat'])@np.asarray(tool['support_normal_local'])
    if normal[2]<=.805:raise ToolExecutionError('Actual entry tilt left original upward blade-support geometry')
    target=original.copy();target[2]=policy.point(edge)[2]
    policy.move_point(side,edge,target,guard)
    _descend_neck_blade(policy,tool,side,food,grip)


def run_e28(author,payload):
    context=_context(author,payload,'E28');policy=ToolAuthor(author);_budget(policy,context,300)
    policy._e28_grasp_station=context.get('grasp_station_x')
    tool=policy.s['tools']['main'];side=tool.get('hand','right');actor=tool['actor']
    grip=dict(actor=actor,local=tool['grasp_local'],jaw_axis_local=tool['jaw_axis_local'])
    if context.get('rebuild_source_fidelity_grasp')is True:
        migration=context.get('e28_source_cooking_migration')
        if not migration or migration.get('changed_objects')!=['spatula']:
            raise ValueError('Explicit migrated E28 source collider required for grasp rebuild')
        import omni.usd
        from pxr import Usd,UsdPhysics
        root=omni.usd.get_context().get_stage().GetPrimAtPath(author.scene.root_path+'/Props/spatula')
        colliders=[]
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI)or not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():continue
            if not prim.HasAPI(UsdPhysics.MeshCollisionAPI):continue
            approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())
            resolution=prim.GetAttribute('physxSDFMeshCollision:sdfResolution').Get()
            if approximation!='sdf'or resolution!=384:raise ValueError('Actual spatula SDF384 collider readback mismatch')
            colliders.append(dict(path=str(prim.GetPath()),approximation=approximation,sdf_resolution=resolution))
        if not colliders:raise ValueError('Actual source SDF spatula collider missing')
        policy.stage('e28-source-sdf-three-real-public-grasps');evidence=[]
        for _ in range(3):
            policy.act(side,'GRASP');policy.require_held(grip,side)
            sensor,labels=author.scene.contacts[actor]
            forces=sensor.data.force_matrix_w[0].sum(axis=0).cpu().numpy()
            evidence.append(dict(step=policy.c.steps,actual_grasp=True,
                forces_world_n=[np.asarray(forces[labels.index(f'{side}_finger{i}')]).tolist()for i in(1,2)]))
        (author.out/'E28-source-sdf-real-grasp-rebuild.private.json').write_text(json.dumps(
            dict(source_initial_episode=False,old_contact_not_assumed=True,actual_colliders=colliders,evidence=evidence),indent=2)+'\n')
    if context.get('empty_hand_table_regrip')is not True:policy.require_held(grip,side)
    elif not(context.get('regrip_neck')is True and policy.contact(actor,'table')):
        raise ToolExecutionError('Empty-hand suffix requires explicit table-supported real regrip')
    if context.get('grip_patch_probe')is True:
        from .execution_design_grip_readback import install
        movements=context.get('grip_probe_down_steps',0)
        if type(movements)is not int or not 0<=movements<=12:raise ValueError('At most twelve measured 1mm grip-probe steps are allowed')
        probe=install(author,actor,side,max_samples=200+100*movements,stem='E28-native-grip')
        policy.stage('checkpoint-e28-passive-native-grip-hold')
        policy.act(side,'STILL');policy.act(side,'STILL')
        if movements:
            policy.stage('checkpoint-e28-measured-public-down1mm')
            for _ in range(movements):
                policy.require_held(grip,side);policy.act(side,'DOWN',mm=1.);policy.require_held(grip,side)
        return dict(diagnostic_only=True,segment_finished=True,segment_passed=False,
            measurement_completed=probe['samples'][0]>0,measurement_samples=probe['samples'][0],
            segment='passive-native-grip-properties-and-contact-buffers',native_task_acceptance=False)
    food=context.get('food')
    if food not in policy.s['groups']['active']:raise ValueError('Explicit selected E28 food required')
    if context.get('practical_far_top_brace_and_deliver')is True:
        author._engineering_e28_contact_hold=True
        from .execution_design_e28_brace import practical
        return practical(policy,tool,grip,side,food)
    if context.get('coarse_insert_then_deliver')is True:
        author._engineering_e28_contact_hold=True
        from .execution_design_e28_coarse_offload import resume_insert_and_deliver
        return resume_insert_and_deliver(policy,tool,grip,side,food,
            insertion_pulse_already_completed=context.get('insertion_pulse_already_completed')is True,
            additional_insertion_pulses=context.get('additional_insertion_pulses',0),
            tip_down_entry_degrees=context.get('tip_down_entry_degrees',0.),
            retract_and_reseat_source_blade=context.get('retract_and_reseat_source_blade')is True,
            entry_already_retracted_high=context.get('entry_already_retracted_high')is True)
    if context.get('coarse_plate_offload')is True:
        author._engineering_e28_contact_hold=True
        from .execution_design_e28_coarse_offload import run
        return run(policy,tool,grip,side,food,destination=context.get('coarse_plate_target_task'))
    if context.get('legacy_loaded_carry_probe')is True:
        if context.get('native_contact_hold')is True:
            author._engineering_e28_contact_hold=True
        from .execution_design_e28_loaded_debug import run
        return run(policy,tool,grip,side,food,context=context)
    if context.get('contact_geometry_probe')is True:
        from .execution_design_grip_readback import install
        probe=install(author,actor,side,max_samples=250,stem='E28-food-contact',additional_targets=(food,'table'))
        policy.stage('e28-passive-real-food-contact-hold');policy.act(side,'STILL')
        direction=np.asarray(policy.snapshot()[0][actor]['mat'])[:,0];component=int(np.argmax(abs(direction[:2])))
        token=(('FWD','BACK'),('LEFT','RIGHT'))[component][int(direction[component]<0)]
        policy.stage('e28-measured-real-food-contact-forward3mm');policy.act(side,token,mm=3.)
        return dict(diagnostic_only=True,native_task_acceptance=False,segment_finished=True,
            segment_passed=False,measurement_completed=probe['samples'][0]>=200,
            measurement_samples=probe['samples'][0],segment='actual-tool-food-contact-geometry-readback')
    if context.get('far_top_brace_probe')is True:
        from .execution_design_e28_brace import run
        return run(policy,tool,grip,side,food)
    if context.get('record_food_loading_contacts')is True:
        from .execution_design_grip_readback import install
        install(author,food,'left',max_samples=2000,stem='E28-loading-food',additional_targets=(actor,'table'))
    if context.get('record_robot_table_contacts')is True:
        from .execution_design_robot_contact_readback import install
        install(author,('table',actor,food),stem='E28-native-all-link-contacts')
    body=policy.snapshot()[0][food]
    if any(body['grasp']):raise ToolExecutionError('Restored E28 food is hand-grasped')
    edge=dict(actor=actor,local=np.asarray(tool['edge_segment'],float).mean(axis=0))
    work=dict(actor=actor,local=tool['working_local'])
    if context.get('regrip_neck')is True:
        policy._e28_grasp_station=context.get('grasp_station_x')
        policy._e28_level_entry_retract=context.get('level_entry_retract')is True
        grip=_regrip_neck(policy,tool,side,edge,food)
        body=policy.snapshot()[0][food]
    elif context.get('neck_already_gripped')is True:
        grip=_near_blade_ref(policy,tool);policy.require_held(grip,side)
        if context.get('insertion_already_staged')is True:
            if context.get('withdraw_backstop_before_insertion')is not True:
                if not policy.contact(food,'table'):
                    if context.get('hold_before_backstop_withdrawal')is True:
                        _e28_achieved_contact_hold(policy,lambda:policy.require_held(grip,side))
                    if not policy.contact(food,'table'):
                        raise ToolExecutionError('Insertion continuation requires actual food table support')
                from .execution_design_e28_reference import actual_leading_surfaces
                obj=next(o for o in policy.spec['objects']if o['id']==food)
                body=policy.snapshot()[0][food];bottom=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
                surface=actual_leading_surfaces(policy,actor)
                upper=bottom+.004
                if context.get('public_rock_before_entry')is True or context.get('support_plane_feed')is True:
                    # A resumed upper-edge contact attempt deliberately starts
                    # above the underside. This only admits its measured source
                    # pose; actual table/hand/grip guards and insertion scoring
                    # are unchanged. It cannot certify an inserted blade.
                    upper=float(body['pos'][2]+(np.abs(body['mat'])@np.asarray(obj['size']))[2])+.002
                if not bottom-.006<=surface['bottom_z']<=upper:
                    raise ToolExecutionError('Restored actual blade is outside the admitted measured contact band')
        elif context.get('tip_already_oriented')is True:
            state=policy.snapshot()[0][actor];normal=np.asarray(state['mat'])@np.asarray(tool['support_normal_local'])
            if normal[2]<=.805:raise ToolExecutionError('Restored source blade lost upward support orientation')
            direction=np.asarray(state['mat'])[:,0].copy();direction[2]=0.;direction/=np.linalg.norm(direction)
            policy.stage('checkpoint-e28-retract-clear-before-contact-descent')
            policy.move(side,policy.tip(side)-direction*.035,lambda:policy.require_held(grip,side))
            _descend_neck_blade(policy,tool,side,food,grip,reject_food_contact=True)
        elif context.get('tip_entry')is True:
            _prepare_tip_entry(policy,tool,side,edge,food,grip)
        elif context.get('neck_contact_descent_only')is True:
            _descend_neck_blade(policy,tool,side,food,grip)
        else:_stage_neck_blade(policy,tool,side,edge,food,grip)
        body=policy.snapshot()[0][food]
    actual=policy.snapshot()[0][actor];direction=np.asarray(actual['mat'])[:,0].copy();direction[2]=0
    direction/=np.linalg.norm(direction);height=float(policy.point(edge)[2])
    park=np.asarray(context['backstop_park_task'],float)
    if park.shape!=(3,)or not np.isfinite(park).all():raise ValueError('Explicit finite original backstop parking pose required')
    policy._e28_backstop_park=park.copy()
    guard=lambda:policy.require_held(grip,side)
    if context.get('hold_before_backstop_withdrawal')is True:
        policy._e28_contact_hold=lambda:_e28_achieved_contact_hold(policy,guard,context.get('contact_hold_mode','private'))
        policy._e28_short_backstop_retreat=True
    obj=next(o for o in policy.spec['objects']if o['id']==food)
    initial_bottom=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size']))[2])
    from .execution_design_e28_backstop import insert,center_over_blade
    kwargs={}
    if 'insertion_pulse_mm'in context:kwargs['pulse_mm']=float(context['insertion_pulse_mm'])
    if context.get('backstop_already_withdrawn')is True:
        from .execution_design_e28_backstop import clear_loaded_column
        clear_loaded_column(policy,food,context.get('backstop_side','left'))
        if any(policy.contact(food,f'{s}_finger{i}')for s in ('left','right')for i in (1,2)):
            raise ToolExecutionError('Restored hand-free insertion still touches food with a finger')
        kwargs['backstop_already_withdrawn']=True
        kwargs['backstop_side']=context.get('backstop_side','left')
    if context.get('backstop_already_placed')is True:
        kwargs['backstop_side']=context.get('backstop_side','left')
        if context.get('withdraw_backstop_before_insertion')is True:
            policy._e28_short_backstop_retreat=context.get('short_backstop_retreat')is True
            if context.get('contact_hold_before_withdrawal')is True:
                _e28_achieved_contact_hold(policy,guard)
            from .execution_design_e28_backstop import withdraw
            withdraw(policy,food,kwargs['backstop_side'],direction,guard)
            kwargs['backstop_already_withdrawn']=True
            if context.get('withdraw_backstop_only')is True:
                return dict(task='E28',diagnostic_only=True,source_initial_episode=False,
                    native_task_acceptance=False,segment='actual-side-contact-detachment',
                    segment_finished=True,segment_passed=True,actions=policy.c.steps-policy.start,
                    final_food_task=np.asarray(policy.snapshot()[0][food]['pos']).tolist(),
                    food_hand_contact=False)
        elif not policy.contact(food,'table'):raise ToolExecutionError('Restored insertion food lacks actual table support')
    policy.stage('checkpoint-e28-actual-blade-insertion')
    if context.get('public_rock_before_entry')is True:
        from .execution_design_e28_rock import prepare
        prepare(policy,tool,grip,side,food,edge,direction,
            raise_mm=context.get('public_rock_raise_mm',8.),entry_height_task=context.get('public_rock_entry_height_task'),
            feed_only=context.get('public_rock_feed_only')is True)
        height=float(policy.point(edge)[2])
    if context.get('support_plane_feed')is True:
        from .execution_design_e28_plane_feed import run
        run(policy,tool,grip,side,food,edge,direction)
        height=float(policy.point(edge)[2])
    insert(policy,food,edge,side,direction,height,guard,**kwargs)
    def loaded():
        guard()
        if not policy.contact(food,actor):raise ToolExecutionError('Checkpoint scoop lost actual blade support')
        state,contacts=policy.snapshot()
        if any(state[food]['grasp'])or any(frozenset((food,f'{s}_finger{i}'))in contacts for s in ('left','right')for i in (1,2)):
            raise ToolExecutionError('Checkpoint independent blade lift touched a hand')
    loaded();policy.stage('checkpoint-e28-independent-lift20mm')
    policy.move_point(side,work,policy.point(work)+[0.,0.,.020],loaded,tolerance=.001)
    loaded();state=policy.snapshot()[0];food_bottom=float(state[food]['pos'][2]-(np.abs(state[food]['mat'])@np.asarray(obj['size']))[2])
    if policy.contact(food,'table')or food_bottom-initial_bottom<.006:
        raise ToolExecutionError('Checkpoint scoop did not produce real table-free blade lift')
    on_patch,local=center_over_blade(tool,state[actor],state[food]['pos'])
    if not on_patch:raise ToolExecutionError('Checkpoint food left the real blade load patch')
    return dict(task='E28',variant=policy.variant,diagnostic_only=True,source_initial_episode=False,
        native_task_acceptance=False,segment='actual-insertion-and-independent-lift',actions=policy.c.steps-policy.start,
        segment_finished=True,segment_passed=True,food=food,actual_food_lift_m=food_bottom-initial_bottom,
        actual_food_center_tool_local=local.tolist(),actual_table_contact=False,actual_food_hand_contact=False)


def run_e37(author,payload):
    context=_context(author,payload,'E37');policy=StructuralAuthor(author);_budget(policy,context,400)
    if context.get('table_link_force_probe')is True:
        # The explicit one-STILL measurement records an existing contact;
        # it does not attempt to move through that contact.
        return _run_e37_segment(policy,context)
    from .execution_design_e37_table_guard import guard_actions
    with guard_actions(policy)as observer:
        policy._e37_table_readback=observer['snapshot']
        try:return _run_e37_segment(policy,context)
        finally:del policy._e37_table_readback


def _run_e37_segment(policy,context):
    author=policy.a
    role=context.get('role','left');allowed=(['left'],['right'],['left','right'])[policy.index]
    if role not in allowed:raise ValueError('E37 suffix role is outside selected rule')
    entry=policy.s['screw_roles'][role];driver=entry['driver'];actor=driver['actor'];side=context.get('side','right')
    if side not in ('left','right'):raise ValueError('Explicit native driver hand required')
    ref=dict(actor=actor,**policy.geometry['driver_grasp'])
    if context.get('rebuild_source_fidelity_grasp')is True:
        migrated=getattr(author,'_engineering_resume_checkpoint',{}).get('context',{}).get('e37_source_cooking_migration')
        if not migrated:raise ValueError('Explicit source-fidelity fixture required for physical grasp rebuild')
        policy.stage('e37-source-sdf-real-grasp-rebuild')
        for _ in range(3):policy.act(side,'GRASP')
    policy.require_held(ref,side)
    if context.get('table_link_force_probe')is True:
        from .execution_design_e37_contact_probe import run
        return run(author,policy)
    fixture=entry['fixture'];axis=policy.frame(fixture['ref'])[1]@np.asarray(fixture['axis_local'],float);axis/=np.linalg.norm(axis)
    head=lambda:policy.body_point({'actor':entry['screw']},entry['head_socket_local'])
    if context.get('unscrew_from_current')is True:
        from .execution_design_e37_unscrew import finish_role
        return finish_role(policy,ref,side,entry,axis,head)
    if context.get('physical_slot_pilot_from_current')is True:
        from .execution_design_e37_blade import Blade
        from .execution_design_e37_slot import run
        blade=Blade(policy,entry,axis,head,.0004)
        return run(policy,ref,side,entry,axis,head,
            torque_degrees=context.get('torque_degrees',10.),already_seated=True,
            physical_socket=blade.physical_groove_measurement)
    if context.get('planned_slot_from_head')is True:
        from .execution_design_e37_planned_slot import run
        return run(policy,ref,side,entry,axis,head,
            torque_degrees=context.get('torque_degrees',5.))
    if context.get('slot_from_head')is True:
        from .execution_design_e37_slot import run
        return run(policy,ref,side,entry,axis,head,
            torque_degrees=context.get('torque_degrees',5.))
    if context.get('planned_head_approach')is True:
        from .execution_design_e37_planned_approach import run
        return run(policy,ref,side,entry,axis,head,
            slot_sign=context.get('slot_sign',1),engage=context.get('engage_slot')is True)
    from .execution_design_e37_approach import above_head
    if context.get('handoff_to_left')is True:
        from .execution_design_e37_handoff import handoff
        if side!='right':raise ValueError('A completed left handoff must resume directly with side=left')
        if context.get('native_handoff_motion')is True:
            from .engineering_native_tick import diagnostic_tick_scope
            with diagnostic_tick_scope(author):
                ref,side=handoff(policy,ref,native_motion=True,
                    flip_empty_wrist=context.get('flip_empty_wrist')is True,
                    side_approach=context.get('side_handoff_approach')is True,
                    side_approach_jaw_sign=context.get('side_approach_jaw_sign'),
                    incoming_already_at_safe_wrist=context.get('incoming_already_at_safe_wrist')is True,
                    section=context.get('handoff_material_section','shaft'))
        else:ref,side=handoff(policy,ref)
        policy.stage('checkpoint-e37-incoming-driver-clearance-lift')
        policy.move(side,policy.tip(side)+[0.,0.,.04],lambda:policy.require_held(ref,side))
    above_head(policy,ref,side,driver,entry,axis,head,resume_at_current_pose=True)
    state=policy.snapshot()[0];current=np.asarray(state[actor]['mat']);slot=np.asarray(state[entry['screw']]['mat'])@np.asarray(entry['radial_local'])
    slot-=axis*float(slot@axis);slot/=np.linalg.norm(slot)
    shaft=current@np.asarray(driver['axis_local']);shaft/=np.linalg.norm(shaft)
    axis_error=math.acos(float(np.clip(shaft@(-axis),-1.,1.)))
    plane_error=math.acos(float(np.clip(abs(slot@current[:,2]),-1.,1.)))
    if max(axis_error,plane_error)>math.radians(.5)+1e-5:
        raise ToolExecutionError('Checkpoint driver did not reach actual source axis/slot alignment')
    if context.get('engage_slot')is True:
        tip=dict(actor=actor,local=driver['tip_local']);guard=lambda:policy.require_held(ref,side)
        from .execution_design_e37_handoff import move_tip
        policy.stage('checkpoint-e37-working-tip-approach')
        move_tip(policy,side,tip,head()+axis*.03,guard)
        if context.get('realign_at_head')is True:
            above_head(policy,ref,side,driver,entry,axis,head,resume_at_current_pose=True)
            move_tip(policy,side,tip,head()+axis*.03,guard)
        policy.stage('checkpoint-e37-real-slot-engagement')
        move_tip(policy,side,tip,head()-axis*min(.002,entry['socket_depth']*.6),guard,tolerance=.0005)
    return dict(task='E37',variant=policy.variant,diagnostic_only=True,source_initial_episode=False,
        native_task_acceptance=False,segment='actual-driver-orientation',actions=policy.c.steps-policy.start,
        segment_finished=True,segment_passed=True,actual_shaft_error_degrees=math.degrees(axis_error),actual_slot_plane_error_degrees=math.degrees(plane_error),role=role,actual_driver_hand=side)
