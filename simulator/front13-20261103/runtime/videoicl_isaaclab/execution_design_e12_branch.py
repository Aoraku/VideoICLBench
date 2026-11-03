"""E12 local engineering: empty-hand side entry at the original charger rim."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .author_orientation import _axis_angle


def make_plan(policy):
    if policy.task!='E12'or policy.variant not in('A','B','C')or policy.spec['execution_design']['condition']!='R':
        raise ToolExecutionError('Reviewed E12 ABC/R branch required')
    if policy.objects['charger_2'].get('source_asset',{}).get('sha256')!='e5843b3b6f1829b5a251030b7204eb5988b412a4f648138e7eb0a870f703b043':
        raise ToolExecutionError('Original reviewed charger collision source required')
    history=policy.a.control_report.get('e12_actual_acquired_hand_frames',[])
    if not history or history[0]['actor']!='charger_1'or history[0]['side']!='right':
        raise ToolExecutionError('Original first charger grasp frame required')
    source_pos,source_r=policy.frame(dict(actor='charger_2'))
    first_pos,first_r=policy.frame(dict(actor='charger_1'))
    return dict(phase='warm',side='right',actor='charger_2',grip_local=[0.,.012,.036],
        staging_tcp=[-.1,-.15,.98],source_pos=np.asarray(source_pos).tolist(),
        source_rotation=np.asarray(source_r).tolist(),first_pos=np.asarray(first_pos).tolist(),
        first_rotation=np.asarray(first_r).tolist(),
        restore_rotation=(source_r@np.asarray(history[0]['relative_hand_rotation'])).tolist(),
        toe_rotation=(source_r@np.array([[0,1,0],[1,0,0],[0,0,-1]])).tolist(),
        rotation_commands={'restore':0,'side':0},pending_rotation=False,pending_holds=0)


class ToeGeometry:
    """Full actual hand sweeps; source finger contact allowed only when grasping."""
    def __init__(self,policy,state):self.p=policy;self.state=state;self.side='right'
    def __call__(self):return self.check()
    def rotate(self,axis,angle):return self.check(rotation=_axis_rotation(axis,angle))
    def check(self,target=None,rotation=None):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
        from .execution_design_thin_edge import table_bounds_task
        snapshot,contacts=self.p.snapshot();tip=self.p.tip('right')
        if getattr(self.p,'_e12_functional_workflow',False):
            if snapshot['charger_1']['pos'][2]<.8 or snapshot['charger_2']['pos'][2]<.8:
                raise ToolExecutionError('E12 functional charger actually fell below table')
            return []
        if any(row['grasp'][1]for name,row in snapshot.items()if name!='charger_2'):
            raise ToolExecutionError('E12 toe branch requires empty hand before source grasp')
        gripping=self.state['phase']in('retry_release','grasp','complete')
        if not gripping and any(row['grasp'][1]for row in snapshot.values()):
            raise ToolExecutionError('E12 empty toe approach unexpectedly holds an object')
        if not self.p.contact('charger_1','strip'):
            raise ToolExecutionError('E12 first inserted charger lost actual socket support')
        for name,key in (('charger_1','first'),('charger_2','source')):
            pos,r=self.p.frame(dict(actor=name));angle=_axis_angle(r@np.asarray(self.state[key+'_rotation']).T)[1]
            if name=='charger_2'and gripping:continue
            if np.linalg.norm(pos-np.asarray(self.state[key+'_pos']))>.005 or angle>math.radians(3):
                raise ToolExecutionError('E12 restored charger pose no longer reproduces boundary')
        for name in snapshot:
            for i in (1,2):
                if frozenset((name,'right_finger'+str(i)))in contacts and not(name=='charger_2'and gripping):
                    raise ToolExecutionError('E12 toe approach has unexpected actual finger contact')
        obstacles={name:collision_parts_task(self.p,name)for name in snapshot}
        bodies={n:actual_mesh(self.p.a,'right',n)for n in('panda_hand',*self.p.a.scene.embodiment.fingers)}
        payload=bool(self.state.get('insertion_started'))
        if payload:
            from .execution_design_thin_edge import material_collision_points_task
            self.p.require_held(dict(actor='charger_2'),'right')
            bodies['payload']=material_collision_points_task(self.p,dict(actor='charger_2'))
        margin=.0003 if self.state.get('replanned_source_toe28')else .001
        results=[]
        for body,points in bodies.items():
            allowed=body!='panda_hand'and gripping
            pieces={name:parts for name,parts in obstacles.items()if not(allowed and name=='charger_2')
                and not(body=='payload'and name=='strip')}
            results.append(swept_pose_clearance({body:points},tip,tip if target is None else target,
                np.eye(3)if rotation is None else rotation,pieces,table_bounds_task(self.p.a.scene)['top'],margin=margin))
        self.p.a.control_report['e12_toe_actual_geometry']=dict(
            actual_collision_bodies=len(bodies),minimum_table_clearance_m=min(r['minimum_table_clearance_m']for r in results),
            source_finger_contact_allowed=gripping,obstacle_convex_piece_counts={k:len(v)for k,v in obstacles.items()})
        return results


def complete_second_from_source(policy):
    """Source-initial author hook; first insertion must already be physical."""
    if hasattr(policy,'_e12_toe_preparation'):
        raise ToolExecutionError('Source-initial second charger reference cannot reset an existing continuation')
    state=make_plan(policy)
    relative=_axis_rotation([1,0,0],-math.radians(10))@np.array([[0,1,0],[1,0,0],[0,0,-1]])
    state.update(replanned_source_toe28=True,grip_local=[0.,.012,.028],toe_tilt_degrees=10.,
        toe_rotation=(np.asarray(state['source_rotation'])@relative).tolist(),
        pre_restore_empty_waypoint=[-.1,-.15,.98])
    policy._e12_toe_preparation=state
    return run_branch(policy,{},'complete_second_toe28')


def resume_second_pin(policy):
    """Continue at the measured free-air pins, with no acquisition prefix."""
    from .execution_design_branch_geometry import install_public_guard
    from .execution_design_e12_reference import insert_charger_precisely
    from .realworld_structural_evidence import _basis
    state=getattr(policy,'_e12_toe_preparation',{})
    if not state.get('replanned_source_toe28')or not state.get('insertion_started'):
        raise ToolExecutionError('E12 actual toe pin continuation context required')
    policy.require_held(dict(actor='charger_2'),'right')
    slot_id=((1,2),(3,4),(1,4))[policy.index][1];slot=policy.s['slots'][str(slot_id)]
    pin=policy.s['pins']['charger_2'][0];hole=slot['holes'][0]
    ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);matrix=policy.frame(slot['ref'])[1]
    ha,hu,hv=(matrix@value for value in(ha,hu,hv));pa,pu,pv=_basis(pin['axis_local'],pin['u_local'])
    rotation=np.stack([hu,-hv,-ha],axis=1)@np.stack([pu,pv,pa],axis=1).T
    if not getattr(policy,'_e12_functional_workflow',False):install_public_guard(policy,ToeGeometry(policy,state))
    ref=dict(actor='charger_2',local=state['grip_local'],jaw_axis_local=[1,0,0])
    from .execution_design_e12_reference import pin_aperture_diagnostics
    near=min(row['axial_m']for row in pin_aperture_diagnostics(policy,'charger_2',slot_id))<.003
    insert_charger_precisely(policy,'charger_2',ref,'right',slot_id,rotation,
        state['physical_insertion_depth_m'],resume='precision'if near else True)
    native=list(getattr(policy.c.evaluator,'current_conditions',[]))
    if getattr(policy,'_e12_functional_workflow',False):
        from .execution_design_e12_functional import record_result
        result=record_result(policy)
        if not result['functional_pass']:raise ToolExecutionError('E12 coarse continuation lacks two real released insertions')
        return dict(local_completed=True,functional_pass=True,functional_acceptance=result,whole_task_score=None)
    if not native or not all(row.get('passed')is True for row in native):
        raise ToolExecutionError('E12 released continuation lacks original native conditions')
    return dict(local_completed=True,native_current_conditions=native,whole_task_score=None)


def complete_first_pin(policy):
    """Continue the measured first pin pair directly, without its free-air prefix."""
    from .execution_design_e12_reference import insert_charger_precisely,pin_aperture_diagnostics
    from .realworld_structural_evidence import _basis
    name=policy.s['groups']['chargers'][0];slot_id=((1,2),(3,4),(1,4))[policy.index][0]
    slot=policy.s['slots'][str(slot_id)];pin=policy.s['pins'][name][0];hole=slot['holes'][0]
    ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);matrix=policy.frame(slot['ref'])[1]
    ha,hu,hv=(matrix@value for value in(ha,hu,hv));pa,pu,pv=_basis(pin['axis_local'],pin['u_local'])
    rotation=np.stack([hu,-hv,-ha],axis=1)@np.stack([pu,pv,pa],axis=1).T
    ref=policy.ref(name);held=policy.snapshot()[0][name]['grasp']
    sides=[side for index,side in enumerate(('left','right'))if held[index]]
    if len(sides)!=1:raise ToolExecutionError('E12 first continuation requires one actual holding hand')
    side=sides[0];policy.require_held(ref,side)
    depth=min(float(pin['length'])*.85,float(hole['depth'])-.001)
    from .execution_design_e12_reference import pin_aperture_diagnostics
    near=min(row['axial_m']for row in pin_aperture_diagnostics(policy,name,slot_id))<.003
    insert_charger_precisely(policy,name,ref,side,slot_id,rotation,depth,resume='precision'if near else True)
    return dict(local_completed=True,first_actual_socket_contact=policy.contact(name,'strip'),
        actual_pin_diagnostics=pin_aperture_diagnostics(policy,name,slot_id),whole_task_score=None)


def release_second_pin(policy):
    """Release the measured guided charger; let real gravity seat its pins."""
    from .execution_design_branch_geometry import install_public_guard
    from .execution_design_e12_reference import release_toe_charger,occupied_pin_channel_diagnostics
    state=getattr(policy,'_e12_toe_preparation',{})
    if not state.get('replanned_source_toe28')or not state.get('insertion_started'):
        raise ToolExecutionError('E12 actual guided toe continuation required')
    ref=dict(actor='charger_2',local=state['grip_local'],jaw_axis_local=[1,0,0]);policy.require_held(ref,'right')
    slot_id=((1,2),(3,4),(1,4))[policy.index][1]
    channels=occupied_pin_channel_diagnostics(policy,'charger_2',slot_id)
    if not all(row['fits_actual_channel']and row['actual_depth_m']>0. for row in channels):
        raise ToolExecutionError('E12 release requires actual material inside both original channels')
    install_public_guard(policy,ToeGeometry(policy,state))
    release_toe_charger(policy,'charger_2',ref,'right',slot_id)
    native=list(getattr(policy.c.evaluator,'current_conditions',[]))
    if not native or not all(row.get('passed')is True for row in native):
        raise ToolExecutionError('E12 guided release lacks original native depth/contact conditions')
    return dict(local_completed=True,occupied_channels_before_release=channels,
        native_current_conditions=native,whole_task_score=None)


def _settle(policy,state,geometry):
    if not state['pending_rotation']:return
    feedback=policy.c.action_feedback()['control_feedback']['right']
    tolerance=float(feedback.get('orientation_tolerance_rad',.05))
    while float(policy.c.action_feedback()['control_feedback']['right']['orientation_error_rad'])>tolerance:
        before=float(policy.c.action_feedback()['control_feedback']['right']['orientation_error_rad'])
        state['pending_holds']+=1;policy.act('right','STILL')
        after=float(policy.c.action_feedback()['control_feedback']['right']['orientation_error_rad'])
        state['pending_no_progress']=state.get('pending_no_progress',0)+1 if after>=before-.0005 else 0
        if state['pending_no_progress']>=3:raise ToolExecutionError('E12 accepted empty rotation has no actual progress')
    geometry.check();state['pending_rotation']=False


def _rotate(policy,state,geometry,key,maximum):
    target=np.asarray(state[key+'_rotation']);count_key='restore'if key=='restore'else'side'
    while True:
        _settle(policy,state,geometry)
        axis,angle=_axis_angle(target@np.asarray(policy.a.tcp_rotation_task('right')).T)
        if angle<math.radians(1):return
        if state['rotation_commands'][count_key]>=100:raise ToolExecutionError('E12 toe empty rotation exceeded original finite round bound')
        i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
        state['rotation_commands'][count_key]+=1;state['pending_rotation']=True;state['pending_holds']=0;state['pending_no_progress']=0
        policy.act('right',token,degrees=min(maximum,max(.5,abs(math.degrees(angle*axis[i])))))


def run_branch(policy,context,branch_name):
    if branch_name not in ('prepare_second_toe','grasp_second_toe','complete_second_toe','complete_second_tilted_toe','complete_second_toe28'):
        raise ToolExecutionError('Unregistered E12 toe branch')
    state=getattr(policy,'_e12_toe_preparation',None)
    if state is None:state=make_plan(policy);policy._e12_toe_preparation=state
    if branch_name=='complete_second_toe28'and not state.get('replanned_source_toe28'):
        if state['phase']!='grasp'or policy.held(dict(actor='charger_2'),'right'):
            raise ToolExecutionError('Toe28 retry requires the actual failed empty source grip')
        pos,rotation=policy.frame(dict(actor='charger_2'))
        relative=_axis_rotation([1,0,0],-math.radians(10))@np.array([[0,1,0],[1,0,0],[0,0,-1]])
        state.update(replanned_source_toe28=True,previous_source_pos=state['source_pos'],
            previous_source_rotation=state['source_rotation'],source_pos=pos.tolist(),source_rotation=rotation.tolist(),
            grip_local=[0.,.012,.028],toe_rotation=(rotation@relative).tolist(),
            phase='retry_release',pending_rotation=False,pending_holds=0,staging_tcp=[-.1,-.15,.92])
    if branch_name=='complete_second_tilted_toe'and 'toe_tilt_degrees'not in state:
        if state['phase']!='lower'or policy.held(dict(actor='charger_2'),'right'):
            raise ToolExecutionError('Tilted toe retry requires the measured empty source-lower boundary')
        # The1044 wrist collider rests on the table although the fingers clear
        # it. Raise with the accepted hand frame before deliberately replacing
        # its side-entry orientation through public rotation commands.
        relative=_axis_rotation([1,0,0],-math.radians(10))@np.array([[0,1,0],[1,0,0],[0,0,-1]])
        state.update(toe_tilt_degrees=10.,toe_rotation=(np.asarray(state['source_rotation'])@relative).tolist(),
            phase='recover_raise',pending_rotation=False,pending_holds=0,staging_tcp=[-.1,-.15,.92])
    geometry=ToeGeometry(policy,state);original=policy.act
    translations={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    rotations={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
    def act(side=None,token='STILL',mm=1.,degrees=5.,follower=None):
        geometry.check()
        if side!='right'or follower is not None:raise ToolExecutionError('E12 toe branch permits only original right working hand')
        if token in translations:
            axis,sign=translations[token];target=policy.tip(side).copy();target[axis]+=sign*max(policy.min_mm,min(policy.max_mm,mm))/1000;geometry.check(target=target)
        elif token in rotations:
            axis,sign=rotations[token];geometry.check(rotation=_axis_rotation(np.eye(3)[axis],sign*math.radians(degrees)))
        original(side,token,mm=mm,degrees=degrees,follower=follower);geometry.check()
    policy.act=act
    if state['phase']=='warm':state['phase']='verify'
    if not policy.contact('charger_1','strip'):
        policy.stage('toe-source-public-contact-rebuild')
        # Native checkpoint restore also needs a physical contact update. Count
        # this public action inside the existing pending bound when applicable.
        pending=float(policy.c.action_feedback()['control_feedback']['right']['orientation_error_rad'])
        tolerance=float(policy.c.action_feedback()['control_feedback']['right'].get('orientation_tolerance_rad',.05))
        if state['pending_rotation']and pending>tolerance:
            state['pending_holds']+=1
        original('right','STILL');geometry.check()
    if state['phase']=='verify':
        geometry.check();state['phase']='pre_restore'if state.get('pre_restore_empty_waypoint')else'restore'
    ref=dict(actor='charger_2',local=state['grip_local'],jaw_axis_local=[1,0,0])
    while state['phase']not in('ready','grasp','complete'):
        phase=state['phase'];policy.stage('toe-source-'+phase)
        if phase=='pre_restore':
            policy.move('right',state['pre_restore_empty_waypoint'],guard=geometry.check)
            state['phase']='restore'
        elif phase=='retry_release':
            policy.act('right','RELEASE')
            pos,rotation=policy.frame(dict(actor='charger_2'))
            relative=_axis_rotation([1,0,0],-math.radians(10))@np.array([[0,1,0],[1,0,0],[0,0,-1]])
            state.update(source_pos=pos.tolist(),source_rotation=rotation.tolist(),
                toe_rotation=(rotation@relative).tolist(),phase='recover_raise')
        elif phase=='recover_raise':
            policy.move('right',np.r_[policy.tip('right')[:2],state['staging_tcp'][2]],guard=geometry.check)
            state['phase']='side'
        elif phase=='restore':_rotate(policy,state,geometry,'restore',10.);state['phase']='stage'
        elif phase=='stage':policy.move('right',state['staging_tcp'],guard=geometry.check);state['phase']='side'
        elif phase=='side':_rotate(policy,state,geometry,'toe',10.);state['phase']='over'
        elif phase=='over':
            policy.move('right',np.r_[policy.point(ref)[:2],state['staging_tcp'][2]],guard=geometry.check);state['phase']='lower'
        elif phase=='lower':policy.move('right',policy.point(ref),tolerance=.001,guard=geometry.check);state['phase']='ready'
        else:raise ToolExecutionError('Invalid restored E12 toe acquisition phase')
    if branch_name=='prepare_second_toe':
        if state['phase']!='ready':raise ToolExecutionError('E12 toe preparation already entered grasp stage')
        geometry.check();return dict(local_completed=True,ready_for_real_grasp=True,whole_task_score=None)
    if state['phase']=='ready':state.update(phase='grasp',attempts=0,stable=0)
    if state['phase']=='grasp'and policy.held(ref,'right'):
        pos,r=policy.frame(ref);state.update(phase='complete',actual_grip_local=(r.T@(policy.tip('right')-pos)).tolist())
    while state['phase']=='grasp':
        if state['attempts']>=5:raise ToolExecutionError('E12 shallow toe pinch lacks an actual hold')
        state['attempts']+=1;policy.stage('toe-source-real-grasp');policy.act('right','GRASP')
        state['stable']=state['stable']+1 if policy.held(ref,'right')else 0
        if state['stable']>=1:
            policy.require_held(ref,'right');state['phase']='complete'
            pos,r=policy.frame(ref);state['actual_grip_local']=(r.T@(policy.tip('right')-pos)).tolist()
    geometry.check();policy.require_held(ref,'right')
    if branch_name in('complete_second_toe','complete_second_tilted_toe','complete_second_toe28'):
        from .realworld_structural_evidence import _basis
        from .execution_design_e12_reference import insert_charger_precisely
        from .execution_design_branch_geometry import HeldGeometry,install_public_guard
        slot_id=((1,2),(3,4),(1,4))[policy.index][1];slot=policy.s['slots'][str(slot_id)]
        if state.get('replanned_source_toe28')and not state.get('source_lifted_before_payload_guard'):
            from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
            top=table_bounds_task(policy.a.scene)['top'];policy.stage('toe-source-actual-held-liftoff')
            # The real source rests on the table. Guard the complete hand and
            # original first charger while lifting, then require payload-floor
            # clearance before installing the free-air payload sweep guard.
            for _ in range(8):
                geometry.check();policy.require_held(ref,'right')
                if float(material_collision_points_task(policy,dict(actor='charger_2'))[:,2].min())>top+.001:break
                policy.act('right','UP',mm=10.)
            else:raise ToolExecutionError('E12 actual source did not lift clear while held')
            geometry.check();policy.require_held(ref,'right');state['source_lifted_before_payload_guard']=True
        policy.act=original
        held_geometry=geometry if state.get('replanned_source_toe28')else HeldGeometry(policy,'charger_2','right',allowed_payload=('strip',))
        if not getattr(policy,'_e12_functional_workflow',False):install_public_guard(policy,held_geometry)
        pin=policy.s['pins']['charger_2'][0];hole=slot['holes'][0]
        ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);matrix=policy.frame(slot['ref'])[1]
        ha,hu,hv=(matrix@value for value in(ha,hu,hv));pa,pu,pv=_basis(pin['axis_local'],pin['u_local'])
        rotation=np.stack([hu,-hv,-ha],axis=1)@np.stack([pu,pv,pa],axis=1).T
        depth=min(float(pin['length'])*.85,float(hole['depth'])-.001)
        if state.get('replanned_source_toe28'):
            state['recipe_depth_before_toe_clearance_m']=depth
            # Eight mm more plastic inside the pads reaches the real flat face.
            # Enter the original holes shallowly while keeping the hand above
            # the first body. Gravity must then seat the released charger;
            # original native depth is checked only after physical release.
            depth-=.008
            if depth<.003:
                raise ToolExecutionError('Toe28 clearance leaves insufficient real pin engagement')
            state['physical_insertion_depth_m']=depth
        state['insertion_started']=True
        # Original first body top is below0.89m. A0.99m pin transit clears
        # it and avoids the unnecessary1.15m high far-forward hand posture.
        previous=policy.clearance;policy.clearance=.99
        try:insert_charger_precisely(policy,'charger_2',ref,'right',slot_id,rotation,depth)
        finally:policy.clearance=previous
        native=list(getattr(policy.c.evaluator,'current_conditions',[]))
        if getattr(policy,'_e12_functional_workflow',False):
            from .execution_design_e12_functional import record_result
            result=record_result(policy)
            if not result['functional_pass']:raise ToolExecutionError('E12 coarse workflow lacks two real released insertions')
            return dict(local_completed=True,functional_pass=True,functional_acceptance=result,whole_task_score=None)
        if not native or not all(item.get('passed')is True for item in native):
            raise ToolExecutionError('E12 completed second insertion lacks original native task conditions')
        state['original_native_conditions_reached']=True
        return dict(local_completed=True,actual_grip_local=state['actual_grip_local'],
            native_current_conditions=native,whole_task_score=None)
    return dict(local_completed=True,actual_grip_local=state['actual_grip_local'],whole_task_score=None)
