"""Private E31 opposite-rim handoff; no world creation or rule changes.

Requires the real right-held plate. Proposals never establish a physical grip.
Stops after genuine left grasp, actual right release and geometric withdrawal.
"""
import json,math
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def handover(a,params=None):
    params=params or {};spec=a.scene.spec
    if (spec.get('id')!='E31'or spec.get('variant')not in ('B','C')or spec.get('seed')!=4201 or a.scene.embodiment.name!='franka'or
        spec.get('execution_design',{}).get('condition')!='I'or
        not getattr(a,'_execution_design_reference_authorized',False)):
        raise ValueError('Private I E31B/C opposite-rim engineering handoff required')
    from .engineering_checkpoint import capture
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_cutlery_grasp import sectional_target
    from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
    from .execution_design_e34_debug import preview_clearance
    from .execution_design_thin_edge import table_bounds_task
    from .author_orientation import _axis_angle
    name='plate';left='left';right='right';s=spec['semantic'];floor=float(table_bounds_task(a.scene)['top'])
    local=np.asarray(params.get('rim_local',[.09178,.00079,.01094]),float)
    if local.shape!=(3,)or not np.isfinite(local).all():raise ValueError('Finite physical opposite rim point required')
    report=dict(local_debug_only=True,primary_witness=False,passed=False,trace=[],source_identity=getattr(a,'_engineering_resume_checkpoint',{}).get('identity'))
    path=Path(a.out)/'e31-left-opposite-handoff.private.json';original=a.act;right_released=False;left_acquired=False;releasing_right=False;released_escape_axis=[None]
    initial,contacts=a.c.snapshot();plate_start=initial[name];baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in initial.items()if n!=name}
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def both(side):
        b=a.c.snapshot()[0][name];ix=('left','right').index(side)
        return bool(b['grasp'][ix]and all(force(name,side+'_finger'+str(i))>.001 for i in (1,2)))
    if params.get('resume_stage')=='right_withdraw':
        if not both(left)or initial[name]['grasp'][1]:raise RuntimeError('Actual left-held, original right-released plate required')
        left_acquired=True;right_released=True;a.carried_payload=(name,left)
    elif params.get('resume_stage')=='dual_grasp':
        if not both(left)or not both(right):raise RuntimeError('Actual native dual grasp required at resumed handoff')
        left_acquired=True;a.carried_payload=(name,left)
    elif not both(right)or(any(initial[n]['grasp'][0]for n in initial)and not params.get('reopen_before_descend')):
        raise RuntimeError('Actual right-held plate and empty or explicitly reopening left hand required')
    def write():path.write_text(json.dumps(report,indent=2,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    policy=SimpleNamespace(a=a,frame=frame)
    def meshes(side):return {n:actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)}
    def robot_obstacles(side):
        result={}
        for n in a.scene.robots[side].body_names:
            try:result[side+'_'+n]=[actual_mesh(a,side,n)]
            except ValueError:continue
        if side+'_panda_hand'not in result:raise RuntimeError('Actual peer palm geometry missing')
        return result
    def props(exclude_plate=False):
        return {n:collision_parts_task(policy,n)for n in initial if not(exclude_plate and n==name)}
    def guard():
        state,contacts=a.c.snapshot()
        if not right_released and not releasing_right and not both(right):raise RuntimeError('Original right plate grip lost before handoff')
        if left_acquired and not both(left):raise RuntimeError('New actual left plate grip lost')
        for n,old in baseline.items():
            b=state[n]
            if any(b['grasp'])or np.linalg.norm(np.asarray(b['pos'])-old['pos'])>.003 or np.linalg.norm(np.asarray(b['mat'])-old['mat'])>.05:
                raise RuntimeError('Opposite-rim handoff moved unselected '+n)
            if any(force(n,side+'_finger'+str(i))>.001 for side in (left,right)for i in (1,2)):
                raise RuntimeError('Opposite-rim handoff contacted unselected '+n)
        b=state[name]
        if not left_acquired:
            report['plate_motion_during_empty_left_approach']=dict(
                translation_m=float(np.linalg.norm(np.asarray(b['pos'])-plate_start['pos'])),
                rotation_matrix_delta=float(np.linalg.norm(np.asarray(b['mat'])-plate_start['mat'])),
                diagnostic_only=True,plate_pose_fixed_not_a_native_task_predicate=True)
        if float(b['mat'][2,2])>-.20:raise RuntimeError('Handoff lost actual plate-down hemisphere')
    def geometry(side,target=None,delta=None,near_plate=False):
        own=meshes(side);tip=np.asarray(a.tip(side));target=tip if target is None else np.asarray(target);delta=np.eye(3)if delta is None else delta
        obstacles=props(exclude_plate=True);obstacles.update(robot_obstacles(right if side==left else left))
        swept_pose_clearance(own,tip,target,delta,obstacles,floor,margin=.001)
        # The palm must clear the selected plate; only the real fingers may
        # meet selected material while acquiring/releasing the rim.
        if side==right and right_released:
            displacement=target-tip
            if np.linalg.norm(displacement)>1e-8:
                outward=(tip-np.asarray(a.c.snapshot()[0][name]['pos'])
                    if released_escape_axis[0]is None else released_escape_axis[0])
                if float(displacement@outward)<=0:
                    raise RuntimeError('Released right hand must move away from the supported actual plate')
                # Starting contact cannot prohibit a separating motion. Its
                # proposed endpoint must clear the actual selected material;
                # the entire sweep still clears the bowl and the other robot.
                if released_escape_axis[0]is None:
                    swept_pose_clearance({'palm':own['panda_hand']+displacement},target,target,np.eye(3),
                        {name:collision_parts_task(policy,name)},floor,margin=.001)
                else:
                    report.setdefault('physical_selected_hand_separation',[]).append(dict(
                        step=a.c.steps,delta_task=displacement.tolist(),finger_back_axis=released_escape_axis[0].tolist(),
                        selected_plate_contact_allowed_during_bounded_pullback=True))
        else:
            swept_pose_clearance({'palm':own['panda_hand']},tip,target,delta,{name:collision_parts_task(policy,name)},floor,margin=.001)
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    def pulse(side,token,mm=5.,deg=5.,check=True):
        guard()
        if check:geometry(side)
        original(token if side==left else'STILL',token if side==right else'STILL',mm,rotation_deg=deg)
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names'):
            raise RuntimeError('Actual handoff public IK/limit rejected '+token+': '+str(feedback.get('reason')))
        guard()
        if check:geometry(side)
    def move(side,goal,tol=.002,done=None):
        errors=[]
        for _ in range(100):
            if done is not None and done():return
            target=np.asarray(goal()if callable(goal)else goal,float);tip=np.asarray(a.tip(side));error=target-tip
            if np.max(abs(error))<=tol:return
            errors.append(float(np.linalg.norm(error)))
            if len(errors)>=24 and min(errors[-24:-16])-min(errors[-8:])<.0005:raise RuntimeError('Opposite-rim measured waypoint stalled')
            i=int(np.argmax(abs(error)));direction=1 if error[i]>0 else-1;step=min(15.,max(3.,abs(error[i])*1000));proposed=tip.copy();proposed[i]+=direction*step/1000
            geometry(side,target=proposed);pulse(side,labels[i][0 if a.generated_axis_signs[side][i]==direction else 1],step)
        raise RuntimeError('Opposite-rim public motion bound exhausted')
    def rim():
        b=a.c.snapshot()[0][name];return np.asarray(b['pos'])+np.asarray(b['mat'])@local
    def section_goal(point,tip,current,target,hand,material_frame=False,approach_frame=False):
        fingers=[hand[n]for n in a.scene.embodiment.fingers]
        if not material_frame:
            return sectional_target(point,tip,current,target,hand['panda_hand'],fingers,float(point[2])-.0033)
        # A tilted plate has different world-Z heights at its two fingers.
        # Cut both real fingers at the same material-normal depth instead.
        plate=a.c.snapshot()[0][name]
        F=target@np.diag([-1.,1.,-1.])if approach_frame else np.asarray(plate['mat'])@np.diag([1.,-1.,-1.])
        point_f=np.asarray(point)@F
        goal=sectional_target(point_f,np.asarray(tip)@F,F.T@current,F.T@target,
            hand['panda_hand']@F,[m@F for m in fingers],float(point_f[2])-.0033)
        return F@goal
    def save(stage):
        cp=capture(a.c,stage,context=dict(local_debug_only=True,carried_payload=[name,left if left_acquired else right]));p=Path(a.out)/('e31-left-handoff-'+stage+'.checkpoint.private.json');p.write_text(json.dumps(cp,indent=2)+'\n');report['trace'].append(dict(stage=stage,step=a.c.steps,checkpoint=str(p)));write();return str(p)
    def finish_handoff():
        nonlocal right_released,releasing_right
        if not right_released:
            initial_open=float(a.scene.robots[right].data.joint_pos[0,a.c.ids[right][1]].detach().cpu().numpy().max())
            a.stage='e31-left-handoff-real-right-release';releasing_right=True
            for extra in (.001,.002,.003,.005,.008,.012):
                a.c.grips[right]=min(.04,initial_open+extra)
                for _ in range(2):original();guard()
                b=a.c.snapshot()[0][name]
                if not b['grasp'][1]and max(force(name,right+'_finger'+str(i))for i in(1,2))<=.001:right_released=True;break
            if not right_released:raise RuntimeError('Original right hand did not physically release plate')
            releasing_right=False
        save('actual-left-only-grasp')
        # The original palm can remain physically underneath the dish even
        # after its pinch releases. Lift the genuinely left-held dish away
        # first; a sideways palm sweep would otherwise catch its lower rim.
        physics=a.scene.contacts[name][0]._physics_sim_view
        contact_view=physics.create_rigid_contact_view(str(a.scene.objects[name].root_physx_view.prim_paths[0]),
            filter_patterns=[f'{a.scene.root_path}/{right}_robot/{n}'for n in(a.scene.embodiment.hand,*a.scene.embodiment.fingers)],
            max_contact_data_count=1024)
        def original_hand_forces():
            v=contact_view.get_contact_force_matrix(a.c.dt)
            array=np.asarray(v.detach().cpu().numpy()if hasattr(v,'detach')else v,float).reshape(3,3)
            if not np.isfinite(array).all():raise RuntimeError('Actual released-hand native force readback required')
            report['latest_released_right_force_vectors_task_n']=(array@a.scene.layout.task_rotation).tolist()
            return np.linalg.norm(array,axis=1).tolist()
        a.stage='e31-original-empty-gripper-full-opening';original('STILL','RELEASE');guard()
        a.stage='e31-original-empty-finger-axis-pullback'
        start=np.asarray(a.tip(right));axis=-np.asarray(a.tcp_rotation_task(right))[:,2]
        # This measured wrist branch refuses pure DOWN while translating
        # sideways. A horizontal pull along the same backward direction
        # clears the finite palm without chasing an unreachable Z target.
        axis[2]=0.
        if np.linalg.norm(axis)<.2:raise RuntimeError('Released original hand requires a measured horizontal escape axis')
        axis/=np.linalg.norm(axis)
        released_escape_axis[0]=axis
        report['native_right_pullback_reference']=dict(tcp=start.tolist(),backward_finger_axis=axis.tolist(),
            actual_hand_meshes=meshes(right),actual_plate_parts=collision_parts_task(policy,name));write()
        for fraction in(.25,.5,.75,1.):
            target=start+.06*fraction*axis
            for component in(0,1):
                for _ in range(6):
                    error=float(target[component]-a.tip(right)[component])
                    if abs(error)<.002:break
                    if error*axis[component]<=0:break
                    token=labels[component][0 if a.generated_axis_signs[right][component]==np.sign(error)else 1]
                    pulse(right,token,min(5.,abs(error)*1000))
                else:raise RuntimeError('Empty original hand actual local pullback component stalled')
            forces=original_hand_forces();report.setdefault('released_right_hand_force_trace',[]).append(dict(steps=a.c.steps,forces_n=forces));write()
        released_escape_axis[0]=None
        if max(original_hand_forces())>.001:raise RuntimeError('Original palm/fingers still physically touch after bounded local-axis pullback')
        save('plate-actually-clear-of-original-palm')
        a.stage='e31-left-handoff-right-withdraw';state,_=a.c.snapshot();direction=np.asarray(a.tip(right))-np.asarray(state[name]['pos']);direction/=np.linalg.norm(direction)
        if direction[2]<0:direction[2]=0.;direction/=np.linalg.norm(direction)
        move(right,np.asarray(a.tip(right))+.12*direction)
        if a.c.snapshot()[0][name]['grasp'][1]or max(force(name,right+'_finger'+str(i))for i in(1,2))>.001:raise RuntimeError('Right hand recontacted plate after withdrawal')
        right_hand=meshes(right);clear,_=preview_clearance(list(right_hand.values()),[0,0,0],{name:collision_parts_task(policy,name)},margin=.008)
        if not clear:raise RuntimeError('Right hand actual collision geometry still too close to plate after retreat')
        original('STILL','RELEASE',5.);guard();checkpoint=save('left-held-right-clear')
        report.update(passed=True,segment_passed=True,actual_left_plate_grasp=True,actual_right_plate_grasp=False,right_plate_forces_n=[force(name,right+'_finger'+str(i))for i in(1,2)],plate_normal=np.asarray(a.c.snapshot()[0][name]['mat'])[:,2].tolist(),checkpoint=checkpoint,final_step=a.c.steps);write();return report
    try:
        resume_stage=params.get('resume_stage','')
        if resume_stage not in ('','descend','grasp','dual_grasp','right_withdraw'):raise ValueError('Known actual E31 handoff resume stage required')
        if resume_stage in('dual_grasp','right_withdraw'):
            guard();save('restored-actual-dual-grasp');return finish_handoff()
        use_material_frame=bool(resume_stage)
        if resume_stage:
            guard();save('right-held-left-already-at-rim-approach')
            if resume_stage=='descend'and params.get('reopen_before_descend')is True:
                a.stage='e31-left-handoff-reopen-before-material-entry'
                original('RELEASE','STILL');guard()
        else:
            if params.get('pinch_mode')=='axial':
                a.stage='e31-left-handoff-axial-empty-stage'
                move(left,[*a.tip(left)[:2],1.10]);move(left,[0.,.24,1.10])
                original('RELEASE','STILL');guard()
            guard();save('right-held-before-proposal');tip=np.asarray(a.tip(left));current=np.asarray(a.tcp_rotation_task(left));own=meshes(left);state,_=a.c.snapshot();plate=state[name];point=rim();radial=np.asarray(plate['mat'])@np.array([1.,0.,0.]);flat=radial.copy();flat[2]=0.;flat/=np.linalg.norm(flat)
            tangent=np.array([-flat[1],flat[0],0.]);plate_tangent=np.asarray(plate['mat'])[:,1]
            radial_rotations=physical_grasp_targets(a,a.c,left,[0,0,1],pinch_axis=flat)
            radial_rotations+=physical_grasp_targets(a,a.c,left,-np.asarray(plate['mat'])[:,2],pinch_axis=radial)
            tangent_rotations=physical_grasp_targets(a,a.c,left,[0,0,1],pinch_axis=tangent)
            tangent_rotations+=physical_grasp_targets(a,a.c,left,-np.asarray(plate['mat'])[:,2],pinch_axis=plate_tangent)
            rotations=[('tangent',r)for r in tangent_rotations]+[('radial',r)for r in radial_rotations]
            preferred=params.get('pinch_mode','tangent')
            if preferred not in ('tangent','radial','axial','auto'):raise ValueError('Known physical pinch mode required')
            if preferred=='axial':
                radial=np.asarray(plate['mat'])@np.r_[local[:2]/np.linalg.norm(local[:2]),0.]
                z=-radial;y=np.asarray(plate['mat'])[:,2];x=np.cross(y,z)
                rotations=[('axial',np.column_stack((x,y,z))),('axial',np.column_stack((-x,-y,z)))]
            proposals=[];rejected=[];targets=[];obstacles=props(exclude_plate=True);obstacles.update(robot_obstacles(right));plate_parts=collision_parts_task(policy,name)
            geometry_path=Path(a.out)/'e31-left-handoff-native-proposal-geometry.private.json'
            native_geometry=dict(source_identity=report['source_identity'],left_actual_hand_meshes=own,
                actual_obstacle_collision_parts=obstacles,actual_selected_plate_parts=plate_parts,
                source_actual_tcp=tip,source_actual_rotation=current,source_actual_plate=plate,
                selected_material_rim=point,proposals=proposals,rejected_proposals=rejected)
            def write_geometry():
                geometry_path.write_text(json.dumps(native_geometry,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
            # Persist the real meshes before computing any proposal, so an empty
            # candidate set can be inspected without repeating the physical prefix.
            write_geometry();report['native_proposal_geometry']=str(geometry_path);write()
            for mode,rotation in rotations:
                try:
                    goal=section_goal(point,tip,current,rotation,own,material_frame=mode=='axial',approach_frame=mode=='axial')
                    material_frame=mode=='axial'
                except ValueError as exc:
                    if mode=='axial':
                        rejected.append(dict(pinch_mode=mode,rotation=rotation,error=type(exc).__name__+': '+str(exc)))
                        write_geometry();continue
                    try:
                        goal=section_goal(point,tip,current,rotation,own,material_frame=True)
                        material_frame=True
                    except ValueError as material_exc:
                        rejected.append(dict(pinch_mode=mode,rotation=rotation,error=type(exc).__name__+': '+str(exc),
                            material_frame_error=type(material_exc).__name__+': '+str(material_exc)))
                        write_geometry();continue
                transformed={n:(m-tip)@(rotation@current.T).T+goal for n,m in own.items()}
                clear1,_=preview_clearance(list(transformed.values()),[0,0,0],obstacles)
                clear2,_=preview_clearance([transformed['panda_hand']],[0,0,0],{name:plate_parts})
                proposals.append(dict(pinch_mode=mode,rotation=rotation,goal=goal,palm_and_peer_clear=clear1 and clear2,
                    section_frame='approach_normal'if mode=='axial'else'plate_normal'if material_frame else'world_z'));targets.extend([dict(position=tip,rotation=rotation),dict(position=[tip[0],tip[1],1.10],rotation=rotation),dict(position=[point[0],point[1],1.10],rotation=rotation),dict(position=goal,rotation=rotation)])
            write_geometry();report['rejected_proposals']=rejected
            rows=inspect(a,a.c,left,targets)if targets else [];choices=[]
            from .execution_design_jacobian_reference import capture as capture_jacobian
            from .execution_design_e31_continuation import screen as screen_continuation
            measured=capture_jacobian(a,a.c,left)if proposals else None
            report['native_continuation_reference']=measured
            for i,p in enumerate(proposals):
                pair=rows[4*i:4*i+4];margin=min(v['minimum_joint_margin_rad']for v in pair)
                if p['palm_and_peer_clear']and all(v['kinematically_reachable']and v['position_error_m']<.001 and v['orientation_error_rad']<math.radians(1.5)for v in pair)and margin>=.08:
                    continuation=screen_continuation(measured,targets[4*i:4*i+4],margin=.08)
                    p['native_continuation']=continuation
                    if continuation['passed']:
                        margin=min(margin,continuation['minimum_joint_margin_rad'])
                        choices.append((int(preferred=='auto'or p['pinch_mode']==preferred),margin,i))
            report['proposals']=[dict(**p,native_ik=rows[4*i:4*i+4])for i,p in enumerate(proposals)];write()
            if not choices:raise RuntimeError('No actual-palm-clear opposite-rim left orientation with measured joint margin')
            _,_,index=max(choices);use_material_frame=proposals[index]['section_frame']!='world_z';wanted=proposals[index]['rotation'];a.stage='e31-left-handoff-orient-empty'
            for _ in range(100):
                axis,angle=_axis_angle(wanted@np.asarray(a.tcp_rotation_task(left)).T)
                if angle<math.radians(.8):break
                v=axis*angle;i=int(np.argmax(abs(v)));d=1 if v[i]>0 else-1;turn=min(8.,max(.5,abs(math.degrees(v[i]))));delta_axis=np.eye(3)[i]
                from .realworld_tool_expert import _axis_rotation
                geometry(left,delta=_axis_rotation(delta_axis,d*math.radians(turn)))
                pulse(left,(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][0 if d>0 else 1],deg=turn)
            else:raise RuntimeError('Actual empty-left orientation did not converge')
            a.stage='e31-left-handoff-high-approach';move(left,[*a.tip(left)[:2],1.10]);move(left,[*rim()[:2],1.10]);save('left-over-opposite-rim')
        def actual_goal():
            tip=np.asarray(a.tip(left));r=np.asarray(a.tcp_rotation_task(left));ms=meshes(left);p=rim()
            return section_goal(p,tip,r,r,ms,material_frame=use_material_frame,
                approach_frame=params.get('pinch_mode')=='axial')
        if resume_stage=='grasp':
            # Native contact, rather than another thin-section target, marks
            # the moment to close on an already reached rim. This branch is
            # only for an exact completed-action checkpoint at that contact.
            if max(force(name,left+'_finger'+str(i))for i in(1,2))<=.001:
                raise RuntimeError('Actual left rim contact required before resumed real grasp')
            geometry(left);save('left-already-contacting-actual-rim')
        else:
            a.stage='e31-left-handoff-rim-descend'
            move(left,actual_goal,tol=.0015,
                done=None if params.get('pinch_mode')=='axial'else lambda:max(force(name,left+'_finger'+str(i))for i in(1,2))>.001)
            save('left-at-actual-rim')
        a.stage='e31-left-handoff-real-left-grasp'
        for _ in range(3):pulse(left,'GRASP',check=False)
        if not both(left)or not both(right):raise RuntimeError('Opposite rim did not establish genuine simultaneous two-hand plate grip')
        left_acquired=True;a.carried_payload=(name,left);save('actual-dual-grasp')
        return finish_handoff()
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps);write();raise
    finally:a.act=original
