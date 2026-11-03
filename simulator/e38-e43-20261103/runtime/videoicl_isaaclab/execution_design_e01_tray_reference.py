"""E01 independent engineering: measured two-hand tray transport candidate."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def acquire_tray_rim(author,side,other,*,rim_x=-.055):
    """Resume one real rim acquisition from its last saved public-action phase."""
    if author.task!='E01' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E01 independent engineering control required')
    if side not in ('left','right')or other not in ('left','right')or side==other:
        raise ToolExecutionError('E01 acquisition requires distinct working/supporting hands')
    refs=reviewed_forward_grips(author,rim_x);ref=refs[side]
    state=getattr(author,'_e01_rim_acquisition',None)
    if state is None or state.get('side')!=side or state.get('other')!=other:
        state=dict(side=side,other=other,rim_x=rim_x,planned_local=ref['local'],phase='release',stable=0,
            lift_before_align=bool(author.held({'actor':'tray'},side)))
        author._e01_rim_acquisition=state
    elif state.get('rim_x',-.055)!=rim_x:
        snapshot,contacts=author.snapshot();index=0 if side=='left'else 1
        if any(row['grasp'][index]for row in snapshot.values())or any(
                frozenset((name,side+'_finger'+str(i)))in contacts
                for name in snapshot for i in (1,2)):
            raise ToolExecutionError('E01 changed rim point requires actual empty clear working hand')
        state.update(rim_x=rim_x,phase='over',stable=0,attempts=0,height=float(author.tip(side)[2]))
    if state.get('phase')not in ('release','raise_before_align','align','raise','over','lower','grasp','complete'):
        raise ToolExecutionError('E01 saved rim acquisition phase is invalid')
    def guard():
        author.require_held({'actor':'tray'},other)
        pos,rotation=author.frame({'actor':'tray'})
        if rotation[2,2]<math.cos(math.radians(8)):
            raise ToolExecutionError('E01 supported rim acquisition exceeded original tilt envelope')
        baseline=getattr(author,'_e01_verified_rim_grips',{}).get(other)
        if baseline is None and other=='right':baseline=getattr(author,'_e01_support_grip_local',None)
        if baseline is not None and np.linalg.norm(pos+rotation@np.asarray(baseline)-author.tip(other))>.006:
            raise ToolExecutionError('E01 supporting hand lost original material-point grip band')
        require_finger_floor_clearance(author,side)
    author.a._engineering_action_guard=guard
    while state['phase']!='complete':
        guard();phase=state['phase'];author.stage('dual-tray-acquire-'+side+'-'+phase)
        if phase=='release':
            state['phase']='raise_before_align'if state.get('lift_before_align')else'align'
            author.act(side,'RELEASE')
        elif phase=='raise_before_align':
            point=author.point(ref);height=max(.98,float(author.tip(side)[2]),float(point[2])+.10)
            author.move(side,[*author.tip(side)[:2],height],guard);state['phase']='align'
        elif phase=='align':
            _,rotation=author.frame(ref)
            author.a.align_gripper_axis(side,rotation@np.array(ref['jaw_axis_local']))
            guard();state['phase']='raise'
        elif phase=='raise':
            point=author.point(ref);height=max(.98,float(author.tip(side)[2]),float(point[2])+.10)
            author.move(side,[*author.tip(side)[:2],height],guard)
            state['height']=height;state['phase']='over'
        elif phase=='over':
            point=author.point(ref);author.move(side,[*point[:2],state['height']],guard)
            state['phase']='lower'
        elif phase=='lower':
            author.move(side,author.point(ref),guard)
            require_finger_floor_clearance(author,side);state['phase']='grasp'
        else:
            require_finger_floor_clearance(author,side);author.act(side,'GRASP');guard()
            state['stable']=state.get('stable',0)+1 if author.held(ref,side)else 0
            state['attempts']=state.get('attempts',0)+1
            if state['stable']>=1:
                pos,rotation=author.frame({'actor':'tray'})
                grips=getattr(author,'_e01_verified_rim_grips',{})
                grips[side]=rotation.T@(author.tip(side)-pos)
                author._e01_verified_rim_grips=grips;state['phase']='complete'
            elif state['attempts']>=5:
                raise ToolExecutionError('E01 dual tray reference lacks actual '+side+' grip')
    guard();author.require_held(ref,side)
    del author.a._engineering_action_guard
    return dict(local_completed=True,acquired_side=side,supporting_side=other,
        phase=state['phase'],whole_task_score=None)


def settle_empty_tray_on_table(author,side,*,release_other=True):
    """Use the already extracted tray on its real table, without a prep detour."""
    from copy import deepcopy
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    if author.task!='E01'or side not in('left','right')or not author.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('Reviewed E01 empty tray settling required')
    reviewed_forward_grips(author,.055)
    if any(name in author.objects and author.contact(name,'tray')for name in('burger','fries','drink')):
        raise ToolExecutionError('In-place empty tray route cannot carry meal contents')
    other='right'if side=='left'else'left';state=getattr(author,'_e01_transport_state',None)
    if state is None or state.get('mode')!='settle_empty':
        prior=deepcopy(state);point=author.point(dict(actor='tray',local=author.bottom_local('tray').tolist()))
        state=dict(mode='settle_empty',phase='release_other'if release_other else'settle',side=side,
            support='table',target=[*point[:2],.8],prior_private_transport_plan=prior,lower_actions=0)
        author._e01_transport_state=state
    if state['side']!=side:raise ToolExecutionError('E01 empty support hand changed across restore')
    table=table_bounds_task(author.a.scene);table_top=table['top']
    def floor_clear():
        values={}
        for hand in('left','right'):
            lows=[float(actual_mesh(author.a,hand,name)[:,2].min())
                for name in('panda_hand',*author.a.scene.embodiment.fingers)]
            values[hand]=min(lows)-table_top
            if values[hand]<.0003:raise ToolExecutionError('E01 actual full hand lacks table clearance')
        author.a.control_report['e01_empty_settle_hand_clearance_m']=values
    def guarded_support():
        floor_clear()
        if not author.contact('tray','table'):author.require_held({'actor':'tray'},side)
    if state['phase']=='release_other':
        guarded_support();state['phase']='settle';author.stage('release-unneeded-empty-tray-hand')
        author.act(other,'RELEASE');guarded_support()
    if state['phase']=='settle':
        author.stage('settle-extracted-empty-tray-on-actual-table')
        for _ in range(12):
            guarded_support()
            if author.contact('tray','table'):break
            state['lower_actions']+=1;author.act(side,'DOWN',mm=3.)
        else:raise ToolExecutionError('E01 empty tray failed to find actual table support')
        guarded_support();state['phase']='retreat';state['retreat_goal']=(author.tip(side)+[0,0,.06]).tolist()
        author.act(side,'RELEASE')
        snapshot,_=author.snapshot()
        if any(snapshot['tray']['grasp']):raise ToolExecutionError('E01 empty tray did not actually release')
    if state['phase']=='retreat':
        author.stage('retreat-empty-after-in-place-tray-settle')
        def supported():
            floor_clear()
            pos,r=author.frame({'actor':'tray'});com=pos+r@np.asarray(getattr(author,'_e01_native_com_local',[0,0,0]))
            if np.any(com[:2]<table['lower'][:2])or np.any(com[:2]>table['upper'][:2]):
                raise ToolExecutionError('E01 released tray departed actual table support projection')
        author.move(side,state['retreat_goal'],guard=supported)
        state['phase']='complete'
    if not author.contact('tray','table'):raise ToolExecutionError('E01 empty tray lacks actual table support')
    pos,rotation=author.frame({'actor':'tray'})
    author.a.control_report['e01_actual_empty_prep_pose']=dict(position_task_m=pos.tolist(),
        rotation_task=rotation.tolist(),private_staging_coordinate_required=False)
    return dict(local_completed=True,actual_table_support=True,actual_prep_position=pos.tolist(),
        empty_tray_released=True,private_staging_detour_omitted=True,whole_task_score=None)


def transport_tray(author,target,support,existing_side=None,*,already_dual=False,single_side=None,settle_in_place=False):
    if settle_in_place:
        return settle_empty_tray_on_table(author,single_side or existing_side or'left')
    if author.task!='E01' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E01 independent engineering control required')
    from .execution_design_e01_contact_diagnostic import install
    if not hasattr(author,'_e01_native_bottom_local')or not hasattr(author,'_e01_native_com_local'):
        install(author)
    name='tray';refs=reviewed_forward_grips(author,.055)
    saved=getattr(author,'_e01_transport_state',None)
    if saved is not None and saved.get('phase')=='complete'and(
            saved.get('support')!=support or not np.allclose(saved.get('target'),target,atol=1e-9)):
        saved=None;del author._e01_transport_state
    obj=author.objects[name]
    if not np.allclose(obj['size'],[.11,.16,.014],atol=1e-7):
        raise ToolExecutionError('Dual tray grip requires reviewed source tray geometry')
    def held(side):author.require_held({'actor':name},side)
    def acquire(side,other=None):
        author.stage('dual-tray-acquire-'+side)
        if other:held(other)
        author.act(side,'RELEASE')
        ref=refs[side];_,rotation=author.frame(ref)
        author.a.align_gripper_axis(side,rotation@np.array(ref['jaw_axis_local']))
        point=author.point(ref);height=max(.98,float(author.tip(side)[2]),float(point[2])+.10)
        guard=(lambda:held(other))if other else None
        author.move(side,[*author.tip(side)[:2],height],guard)
        author.move(side,[*point[:2],height],guard)
        author.move(side,author.point(ref),guard)
        require_finger_floor_clearance(author,side)
        stable=0
        for _ in range(5):
            if other:held(other)
            author.act(side,'GRASP');stable=stable+1 if author.held(ref,side)else 0
            if stable>=1:
                pos,r=author.frame({'actor':name})
                grips=getattr(author,'_e01_verified_rim_grips',{})
                grips[side]=r.T@(author.tip(side)-pos);author._e01_verified_rim_grips=grips
                return
        raise ToolExecutionError('E01 dual tray reference lacks actual '+side+' grip')
    if saved is not None or already_dual:
        pass
    elif existing_side:
        extract_whole_tray_from_lower_shelf(author,existing_side)
        state=author.snapshot()[0][name];matrix=np.asarray(state['mat'])
        center=np.asarray(state['pos'])+matrix@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        upper=author.d['storage_surfaces']['rack_upper']
        if center[0]+np.abs(matrix[0])@np.asarray(obj['size'])>upper['xy'][0]-upper['half_size'][0]-.015:
            raise ToolExecutionError('Actual extracted tray remains below upper storage shelf')
        other='left'if existing_side=='right'else'right'
        held(existing_side);acquire_tray_rim(author,other,existing_side,rim_x=.055)
        acquire_tray_rim(author,existing_side,other,rim_x=.055)
    else:
        acquire('left');acquire('right','left')
    def guard():
        held('left');held('right')
        if author.frame({'actor':name})[1][2,2]<math.cos(math.radians(8)):
            raise ToolExecutionError('E01 real dual-held tray departed level transport envelope')
    control=dict(actor=name,local=author.bottom_local(name).tolist())
    target=np.asarray(target,float)
    if saved is None:
        guard()
        grip_pos,grip_rotation=author.frame({'actor':name})
        grip_locals=dict(getattr(author,'_e01_verified_rim_grips',{}))
        for side in('left','right'):
            if side not in grip_locals:grip_locals[side]=grip_rotation.T@(author.tip(side)-grip_pos)
        author._e01_verified_rim_grips=grip_locals
        validate_dual_grip_drift(author,grip_locals,guard)
        start=author.point(control);points=[start[:2],np.array([start[0],target[1]]),target[:2]]
        height=max(author.measured_staging_route_height(name,'left',points),
                   author.measured_staging_route_height(name,'right',points))
        saved=dict(phase='lift',target=target.tolist(),support=support,grip_locals=grip_locals,
            initial_heights={side:float(author.tip(side)[2])for side in ('left','right')},
            waypoints=[[*start[:2],height],*[list(xy)+[height]for xy in points[1:]],(target+[0,0,.001]).tolist()],waypoint=0)
        author._e01_transport_state=saved
    elif saved.get('support')!=support or not np.allclose(saved.get('target'),target,atol=1e-9):
        raise ToolExecutionError('E01 transport resume cannot replace original destination')
    grip_locals=saved['grip_locals'];initial_heights=saved['initial_heights']
    def move(goal):
        history=[]
        for _ in range(900):
            guard();point=author.point(control);error=np.asarray(goal)-point
            if np.max(np.abs(error))<=.002:return
            axis=int(np.argmax(np.abs(error)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            balanced_dual_step(author,token,min(2.,abs(float(error[axis]))*1000),initial_heights)
            validate_dual_grip_drift(author,grip_locals,guard)
            history.append(author.point(control))
            if len(history)>=15 and max(np.linalg.norm(p-history[-1])for p in history[-15:])<.0003:
                raise ToolExecutionError('E01 real dual-hand tray transport stalled')
        raise ToolExecutionError('E01 dual-hand tray waypoint exceeded public action bound')
    while saved['waypoint']<len(saved['waypoints']):
        index=saved['waypoint'];author.stage(('dual-tray-lift','dual-tray-transport-y','dual-tray-transport-x','dual-tray-lower')[index])
        move(saved['waypoints'][index]);saved['waypoint']+=1
    if saved['phase']=='lift':
        guard();saved.update(phase='retreat',retreat_goal=(author.tip('left')+[0,0,.06]).tolist())
        author.act('left','RELEASE',follower='right')
    def supported():
        if not author.contact(name,support):raise ToolExecutionError('Dual-hand placed tray lacks actual support')
    if saved['phase']=='retreat':
        supported();author.move('left',saved['retreat_goal'],guard=supported,follower='right');saved['phase']='complete'
    supported()
    return dict(local_completed=True,phase=saved['phase'],actual_support=True,whole_task_score=None)


def correct_dual_grip_drift(author,grip_locals,guard):
    """Keep actual TCP material points from separating while lifting the tray.

    Only public single-hand translations; the tray remains an unconstrained
    rigid body. Both real holds and the original tilt envelope stay mandatory.
    """
    for _ in range(24):
        guard();pos,rotation=author.frame({'actor':'tray'})
        errors={side:pos+rotation@np.asarray(local)-author.tip(side)
                for side,local in grip_locals.items()}
        if set(errors)!={'left','right'} or any(not np.isfinite(v).all()for v in errors.values()):
            raise ToolExecutionError('E01 measured bilateral TCP geometry is invalid')
        # Correct lateral spreading only. Vertical load deflection belongs to
        # the outer tray-bottom transport loop; forcing it back to the unloaded
        # grip height drove the supported tray DOWN (native693, fixture7.09N).
        # Actual bilateral holds and tilt remain required before every command.
        for error in errors.values():error[2]=0.
        side=max(errors,key=lambda side:np.max(abs(errors[side])))
        error=errors[side];axis=int(np.argmax(abs(error)))
        if abs(float(error[axis]))<=.0005:return
        if np.linalg.norm(error)>.006:
            raise ToolExecutionError('E01 actual tray grip drift exceeds recoverable side band')
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        author.act(side,token,mm=.5)
    raise ToolExecutionError('E01 bilateral material-point correction did not converge')


def balanced_dual_step(author,token,mm,initial_heights):
    """Let the lower lifted hand catch up without pushing the higher hand down."""
    if token in ('UP','DOWN'):
        displacement={side:float(author.tip(side)[2])-initial_heights[side]
                      for side in ('left','right')}
        if not all(math.isfinite(value)for value in displacement.values()):
            raise ToolExecutionError('E01 invalid actual bilateral lift response')
        if max(displacement.values())-min(displacement.values())>.0005:
            side=(min if token=='UP'else max)(displacement,key=displacement.get)
            author.act(side,token,mm=mm)
            return
    author.act('left',token,mm=mm,follower='right')


def validate_dual_grip_drift(author,grip_locals,guard):
    """Record material-point drift while requiring actual bilateral holding.

    The former6mm macro gate was not a task-native requirement. Native851
    retained all four original cooked-rim contacts at1.13degrees tilt despite
    TCP compliance exceeding that gate. Keep the displacement as evidence.
    """
    guard();pos,rotation=author.frame({'actor':'tray'})
    if set(grip_locals)!={'left','right'}:
        raise ToolExecutionError('E01 measured bilateral TCP geometry is invalid')
    measured={}
    for side,local in grip_locals.items():
        error=pos+rotation@np.asarray(local)-author.tip(side)
        if not np.isfinite(error).all():
            raise ToolExecutionError('E01 measured bilateral TCP geometry is invalid')
        measured[side]=dict(error_task_m=error.tolist(),lateral_m=float(np.linalg.norm(error[:2])),
            former_macro_gate_exceeded=bool(np.linalg.norm(error[:2])>.006))
    report=getattr(getattr(author,'a',None),'control_report',None)
    if report is not None:report['e01_dual_material_drift_diagnostic']=measured


def reviewed_forward_grips(author,rim_x=-.055):
    obj=author.objects['tray']
    if obj.get('source_asset',{}).get('sha256')!='f3de40e9b8aeabc426e1f7056d596d9e01baaf8cb961274d7405b459349fa56c':
        raise ToolExecutionError('E01 forward grip requires pinned source collision mesh')
    # At x=-55mm,z=+5mm the pinned source wall sections are
    # left y136.757..157.651mm and right -157.690..-131.691mm.
    # The prior z=-4mm TCP put the inner open finger on the tray floor
    # (57N normal contact); lift the pads nine mm while retaining forward x.
    if rim_x==-.055:ys=[('left',.147204),('right',-.144690)]
    elif rim_x==.055:
        # The opposite longitudinal location is on the same original walls.
        # SHA-verified triangle sections at x=+55,z=+5mm:
        # left136.932..157.654mm, right−157.681..−131.153mm.
        ys=[('left',.14729337078985683),('right',-.14441710679978337)]
    else:raise ToolExecutionError('E01 unreviewed source rim longitudinal point')
    return {side:dict(actor='tray',local=[rim_x,y,.005],jaw_axis_local=[0,1,0])for side,y in ys}



def require_finger_floor_clearance(author,side):
    geometry=author.a.finger_geometry(side)
    for finger in geometry['fingers']:
        low=np.asarray(finger['aabb_min_task_m']);high=np.asarray(finger['aabb_max_task_m'])
        if not np.isfinite(np.r_[low,high]).all():
            raise ToolExecutionError('E01 actual finger collision bounds invalid')
        floor=.8
        for fixture in author.spec.get('fixtures',[]):
            if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed E01 supporting fixture')
            xy=np.asarray(fixture['xy']);half=np.asarray(fixture['size'])
            if np.all(high[:2]>=xy-half[:2])and np.all(low[:2]<=xy+half[:2]):
                floor=max(floor,float(fixture['z'])+half[2])
        if low[2]<floor+.001:
            raise ToolExecutionError('E01 forward grip fingers lack actual support clearance')


def settle_current_dual_grips(author,refs,acquire,guard):
    """One bounded public regrasp after the second hand rotates the real tray.

    Native v8 left pads were 14mm above their current material point while the
    old held bit still remained true. Both current points must be checked
    before setting the transport baseline; never absorb that error as zero.
    """
    def errors():
        guard()
        values={side:author.tip(side)-author.point(refs[side])for side in ('left','right')}
        if any(not np.isfinite(error).all()for error in values.values()):
            raise ToolExecutionError('E01 current dual-grip material geometry invalid')
        return values
    values=errors()
    side=max(values,key=lambda name:np.linalg.norm(values[name]))
    if np.linalg.norm(values[side])>.006:
        author.stage('dual-tray-refresh-current-'+side)
        acquire(side,'right'if side=='left'else'left')
    values=errors()
    author.a.control_report['e01_pre_lift_grip_errors_m']={side:error.tolist()for side,error in values.items()}
    if any(np.linalg.norm(error)>.006 for error in values.values()):
        raise ToolExecutionError('E01 current bilateral rim alignment failed after bounded regrasp')


def supported_com_margin(vertices,com,table_low,table_high):
    """Actual bottom projection clipped to the actual tabletop; no full-AABB rule."""
    from scipy.spatial import ConvexHull
    polygon=np.asarray(vertices,float)[:,:2];com=np.asarray(com,float)[:2]
    if len(polygon)<3 or not np.isfinite(polygon).all() or not np.isfinite(com).all():
        raise ToolExecutionError('E01 actual native support polygon unavailable')
    polygon=polygon[ConvexHull(polygon).vertices]
    for axis in (0,1):
        for edge,sign in ((table_low[axis],1),(table_high[axis],-1)):
            clipped=[]
            for p,q in zip(polygon,np.roll(polygon,-1,axis=0)):
                dp=sign*(p[axis]-edge);dq=sign*(q[axis]-edge)
                if dp>=0:clipped.append(p)
                if (dp>=0)!=(dq>=0):clipped.append(p+(q-p)*dp/(dp-dq))
            if len(clipped)<3:return -float('inf'),[]
            polygon=np.asarray(clipped)
    hull=ConvexHull(polygon);distances=-(hull.equations[:,:2]@com+hull.equations[:,2])
    return float(distances.min()),polygon[hull.vertices].tolist()


def extract_whole_tray_from_lower_shelf(author,side):
    """Supported horizontal withdrawal, permitting stable physical overhang."""
    import itertools
    shelf=author.d['storage_surfaces']['rack_lower'];edge=float(shelf['xy'][0]-shelf['half_size'][0])
    obj=author.objects['tray'];history=[]
    def actual_bounds():
        pos,rot=author.frame({'actor':'tray'})
        center=np.asarray(pos)+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        half=np.abs(rot)@np.asarray(obj['size'])
        return center-half,center+half
    low,high=actual_bounds()
    if high[0]<edge-.015:return
    scene=author.a.scene;table=scene.layout.config['table'];origin=np.asarray(getattr(scene,'origin',(0,0,0)))
    center=np.asarray(table['position'])+origin;half=np.asarray(table['size'])/2
    corners=np.array([scene.world_to_task(center+half*np.array(sign))for sign in itertools.product((-1,1),repeat=3)])
    table_low,table_high=corners.min(0),corners.max(0)
    bottom=getattr(author,'_e01_native_bottom_local',None);com_local=getattr(author,'_e01_native_com_local',None)
    if bottom is None or com_local is None:raise ToolExecutionError('E01 native COM and actual bottom geometry required')
    if not hasattr(author,'_e01_support_grip_local'):
        p,r=author.frame({'actor':'tray'});author._e01_support_grip_local=np.asarray(r).T@(author.tip(side)-p)
    prior=author.a.control_report.get('e01_lower_shelf_support',{})
    table_verified=bool(author.a.control_report.get('e01_table_support_previously_verified')or prior.get('table_contact'))
    if not author.contact('tray','table')and not table_verified:
        # The rack is8mm above the table. The original front grip still holds
        # the pan while the back rests on the rack; settle its free front edge
        # onto the lower table before any further horizontal withdrawal.
        author.stage('settle-tray-front-onto-table')
        initial_tip=np.asarray(author.tip(side)).copy()
        initial_pos,initial_rotation=author.frame({'actor':'tray'})
        initial_hand=np.asarray(author.a.tcp_rotation_task(side)).copy()
        grip_local=np.asarray(initial_rotation).T@(initial_tip-np.asarray(initial_pos))
        points=np.asarray(bottom)@np.asarray(initial_rotation).T+np.asarray(initial_pos)
        front=points[(points[:,0]<edge-.015)&np.all(points[:,:2]>=table_low[:2],axis=1)&np.all(points[:,:2]<=table_high[:2],axis=1)]
        if not len(front):raise ToolExecutionError('E01 actual front bottom has no table projection')
        gap=max(0.,float(front[:,2].min()-table_high[2]))
        descent_limit=max(.014,gap+.006+.003)
        if not math.isfinite(descent_limit)or descent_limit>.04:
            raise ToolExecutionError('E01 measured front settling travel exceeds reviewed geometry')
        author.a.control_report['e01_front_settle_plan']=dict(actual_initial_front_gap_m=gap,
            actual_descent_limit_m=descent_limit,material_point_limit_m=.006,tilt_limit_degrees=8.)
        for _ in range(96):
            author.require_held({'actor':'tray'},side)
            pos,rotation=author.frame({'actor':'tray'})
            if rotation[2,2]<math.cos(math.radians(8)):
                raise ToolExecutionError('E01 supported front settling exceeded original tilt envelope')
            require_finger_floor_clearance(author,side)
            if np.linalg.norm(np.asarray(pos)+rotation@grip_local-author.tip(side))>.006:
                raise ToolExecutionError('E01 front settling lost original material-point grip band')
            if author.contact('tray','table'):break
            if not author.contact('tray',shelf['actor']):raise ToolExecutionError('E01 front settling lost actual rack support')
            if initial_tip[2]-author.tip(side)[2]>descent_limit:raise ToolExecutionError('E01 front settling exceeded measured actual descent envelope')
            # Follow the pan's measured pitch as it pivots on the rack. The
            # fixed original wrist plane let pads slide9mm while the pan's
            # front fell only3mm in native541. Only real public rotations are
            # used; the held body pose and original tilt band stay mandatory.
            if follow_supported_tray_orientation(author,side,rotation@np.asarray(initial_rotation).T@initial_hand):
                continue
            author.act(side,'DOWN',mm=.5)
        else:raise ToolExecutionError('E01 tray front did not establish actual table support')
    if author.contact('tray','table'):
        author.a.control_report['e01_table_support_previously_verified']=True
    author.stage('withdraw-entire-tray-beyond-lower-shelf')
    for _ in range(100):
        author.require_held({'actor':'tray'},side);low,high=actual_bounds()
        pos,rot=author.frame({'actor':'tray'})
        if rot[2,2]<math.cos(math.radians(8)):raise ToolExecutionError('E01 supported withdrawal exceeded original tilt envelope')
        material_error=np.asarray(pos)+rot@np.asarray(author._e01_support_grip_local)-author.tip(side)
        if np.linalg.norm(material_error)>.006:raise ToolExecutionError('E01 supported withdrawal lost original material-point grip band')
        table_contact=author.contact('tray','table');rack_contact=author.contact('tray',shelf['actor'])
        if not(table_contact or rack_contact):raise ToolExecutionError('E01 supported withdrawal lost actual table and original rack support')
        if table_contact:author.a.control_report['e01_table_support_previously_verified']=True
        require_finger_floor_clearance(author,side)
        error=float(high[0]-(edge-.016))
        com=np.asarray(pos)+rot@com_local;points=np.asarray(bottom)@rot.T+pos
        shift=np.array([-max(error,0.),0,0])
        margin,polygon=supported_com_margin(points+shift,com+shift,table_low,table_high)
        if margin<.008:raise ToolExecutionError('E01 projected native COM leaves actual table support polygon')
        author.a.control_report['e01_lower_shelf_support']=dict(native_com_task_m=com.tolist(),goal_com_task_m=(com+shift).tolist(),goal_support_polygon_xy_m=polygon,goal_com_margin_m=margin,table_contact=table_contact,original_rack_contact=rack_contact,material_point_error_m=material_error.tolist())
        if error<=0:
            author.a.control_report['e01_lower_shelf_clearance']=dict(actual_bounds=[low.tolist(),high.tolist()],lower_shelf_front_x=edge)
            return
        history.append(float(high[0]))
        if len(history)>=16 and history[-16]-history[-1]<.0005:
            raise ToolExecutionError('E01 supported full shelf withdrawal stalled')
        author.act(side,'BACK',mm=min(4.,max(.5,error*1000)))
    raise ToolExecutionError('E01 full shelf withdrawal exceeded public action bound')


def follow_supported_tray_orientation(author,side,target):
    from .author_orientation import _axis_angle
    current=np.asarray(author.a.tcp_rotation_task(side))
    axis,angle=_axis_angle(np.asarray(target)@current.T)
    if angle<=math.radians(.5):return False
    i=int(np.argmax(abs(axis)))
    token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
    author.act(side,token,degrees=.5)
    return True
