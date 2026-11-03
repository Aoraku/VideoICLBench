"""E10 engineering-only thin-piece acquisition, using actual finger geometry."""
import numpy as np

from .realworld_tool_expert import ToolExecutionError


def near_side_piece_ref(author,ref):
    """Center the opposing jaws; keep a near-board tangent offset where broad."""
    from copy import deepcopy
    if author.task!='E10' or not author.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    obj=author.objects[ref['actor']]
    reviewed={'square':'fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb',
              'triangle':'caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b',
              'circle':'043034c6aad20115868b17db73066c112e089da589acaf38de3d06c1aaf2c179'}
    if obj.get('source_asset',{}).get('sha256')!=reviewed.get(obj.get('shape')):
        raise ToolExecutionError('E10 near-side pinch requires pinned source plate')
    if not np.allclose(ref['jaw_axis_local'],[1,0,0]) or len(ref['local'])!=3:
        raise ToolExecutionError('E10 near-side pinch requires original source jaw axis')
    result=deepcopy(ref);result['local'][0]=0.;result['local'][1]=0. if obj['shape']=='triangle'else .010;result['e10_reviewed_near_side']=True
    return result


def contact_band_target(point, bottom, top, tcp_z, finger_lowest):
    """Keep toes inside the real six-millimetre side band, clear of its support."""
    values=np.asarray([*point,bottom,top,tcp_z,finger_lowest],float)
    if not np.isfinite(values).all() or not .005 <= top-bottom <= .007:
        raise ToolExecutionError('E10 reference requires measured thin-piece side band')
    offset=float(tcp_z-finger_lowest)
    if not 0 <= offset <= .03:
        raise ToolExecutionError('E10 actual finger-to-TCP geometry out of reviewed range')
    target=np.asarray(point,float).copy()
    # Original Panda pads bevel toward their toes. On a6mm source plate,
    # a2.5mm toe height leaves only the upper pad edge touching and closure
    # cams the open hand above the material. Keep the open toes0.8mm clear
    # of the measured support before closing; never descend closed fingers.
    target[2]=bottom+.0008+offset
    return target


def lift_thin_piece(author,ref,side,height=.07):
    """Clear the support with small public steps before ordinary transport."""
    if author.task!='E10'or not author.a.control_report.get('engineering_reference_only')or not .002<=height<=.07:
        raise ToolExecutionError('Explicit E10 engineering liftoff required')
    start=float(author.tip(side)[2]);goal=start+height;low=0;count=0
    author.stage('small-step-thin-liftoff-'+ref['actor'])
    for _ in range(160):
        author.require_held(ref,side);before=float(author.tip(side)[2])
        if before>=goal-.002:break
        mm=min(2. if before<start+.020 else 5.,max(author.min_mm,(goal-before)*1000))
        author.act(side,'UP',mm=mm);count+=1;author.require_held(ref,side)
        progress=float(author.tip(side)[2])-before
        low=low+1 if progress<mm*.0001 else 0
        if low>=8:raise ToolExecutionError('E10 actual small-step liftoff stalled')
    else:raise ToolExecutionError('E10 actual small-step liftoff exceeded bound')
    if author.contact(ref['actor'],'table'):raise ToolExecutionError('E10 thin piece did not actually leave its support')
    row=dict(actor=ref['actor'],side=side,public_actions=count,height_m=float(author.tip(side)[2])-start,
        source_table_contact=False,first_twenty_mm_step_cap=2.,whole_task_score=None)
    author.a.control_report.setdefault('e10_small_step_liftoffs',[]).append(row)
    return dict(row,local_completed=True)


def seat_supported_contact_band(author,ref,side):
    """Verify side contact; never push closed fingers through a plate's top."""
    if not author.contact(ref['actor'],'table'):return
    author.require_held(ref,side)
    value=author.snapshot()[0][ref['actor']];obj=author.objects[ref['actor']]
    rotation=np.asarray(value['mat']);center=np.asarray(value['pos'])+rotation@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    half=float(np.abs(rotation[2])@np.asarray(obj['size']));top=float(center[2]+half)
    geometry=author.a.finger_geometry(side);toe=float(geometry['lowest_z_task_m'])
    toes=[float(f['lowest_point_task_m'][2])for f in geometry.get('fingers',[])]or[toe]
    if min(toes)<.8003:raise ToolExecutionError('E10 closed fingertip would contact table')
    if max(toes)>top-.0005:raise ToolExecutionError('E10 closed pads missed the real side material; top pressure is not a lifting pinch')


def level_open_panda_pinch(author,ref,side):
    """Keep both toes level: a five-degree jaw tilt consumes a six-mm plate."""
    if author.a.scene.embodiment.name!='franka':
        author.a.align_gripper_axis(side,author.frame(ref)[1]@np.asarray(ref['jaw_axis_local']));return
    from .author_orientation import panda_downward_grasp_delta
    from .execution_design_branch_geometry import HeldGeometry,install_public_guard
    from .execution_design_branch_rotation import turn_to_fixed_goal
    robot=author.a.scene.robots[side];ids=[robot.find_bodies(name)[0][0]for name in author.a.scene.embodiment.fingers]
    jaw=robot.data.body_pos_w[0,ids[0]]-robot.data.body_pos_w[0,ids[1]]
    jaw=author.a.scene.layout.task_rotation.T@jaw.detach().cpu().numpy()
    current=np.asarray(author.a.tcp_rotation_task(side));desired=author.frame(ref)[1]@np.asarray(ref['jaw_axis_local'])
    joints,_=robot.find_joints('panda_joint7')
    if len(joints)!=1:raise ToolExecutionError('Unique original Panda wrist joint required')
    joint=int(joints[0]);joint7=[float(robot.data.joint_pos[0,joint]),*robot.data.soft_joint_pos_limits[0,joint].detach().cpu().tolist()]
    delta=panda_downward_grasp_delta(current,jaw,desired,joint7_state=joint7);target=delta@current
    guard=HeldGeometry(author,ref['actor'],side,require_hold=False);original=author.act
    had_original=hasattr(author,'_branch_public_original_act')
    install_public_guard(author,guard);author.stage('level-open-thin-pinch-'+ref['actor'])
    try:result=turn_to_fixed_goal(author,side,target,guard,1.,lambda:None)
    finally:
        author.act=original
        if not had_original:del author._branch_public_original_act
    author.a.control_report.setdefault('e10_level_open_pinch',[]).append(dict(actor=ref['actor'],side=side,**result))


def acquire_thin_piece(author,ref,side,*,local_reacquire=False):
    """Public movements and real two-finger holding; no object/robot pose writes."""
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    author.stage('acquire-thin-'+ref['actor'])
    if not local_reacquire:prepare_thin_hand(author,side)
    author.act(side,'RELEASE')
    obj=author.objects[ref['actor']]
    state=author.snapshot()[0][ref['actor']];mat=np.asarray(state['mat'])
    if mat[2,2]<.98:raise ToolExecutionError('E10 thin acquisition requires upright source piece')
    center=np.asarray(state['pos'])+mat@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    extent=np.abs(mat[2])@np.asarray(obj['size']);bottom=float(center[2]-extent);top=float(center[2]+extent)
    point=author.point(ref);height=max(.94,float(point[2])+.07)
    author.move(side,[*author.tip(side)[:2],height]);level_open_panda_pinch(author,ref,side)
    author.stage('acquire-thin-'+ref['actor']);author.move(side,[*point[:2],height])
    return close_prepared_thin_piece(author,ref,side)


def prepare_thin_hand(author,active):
    """Retract an empty far-post arm before raising it toward a stow."""
    for side,robot in author.a.scene.robots.items():
        index=0 if side=='left'else 1
        def empty():
            state,contacts=author.snapshot()
            if any(v['grasp'][index]for v in state.values())or any(frozenset((n,f'{side}_finger{i}'))in contacts for n in state for i in(1,2)):
                raise ToolExecutionError('E10 empty-arm transit still contacts a physical object')
        empty();tip=author.tip(side)
        if tip[2]<.90:author.move(side,[*tip[:2],.94],empty)
        tip=author.tip(side)
        # The prior generic macro raised at x≈+.13 to1.15m, exactly at
        # Panda's extension boundary. Retract at achieved clearance first.
        if tip[0]>-.15:author.move(side,[-.20,tip[1],tip[2]],empty,tolerance=.006)
        tip=author.tip(side)
        if tip[2]>1.02:author.move(side,[*tip[:2],.98],empty,tolerance=.006)
        if side!=active:
            value=robot.data.root_pos_w[0]
            if hasattr(value,'detach'):value=value.detach().cpu().numpy()
            base=author.a.scene.world_to_task(value);tip=author.tip(side)
            if abs(float(tip[1]-base[1]))>.02:author.move(side,[tip[0],float(base[1]),tip[2]],empty,tolerance=.006)
    author.a._single_hand_active=None


def close_prepared_thin_piece(author,ref,side,*,warm_support=False):
    """Finish an already aligned open-hand approach without replaying it."""
    if author.task!='E10'or not author.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    if warm_support:
        author.act(side,'STILL')
        if not author.contact(ref['actor'],'table'):raise ToolExecutionError('Prepared source lacks actual table support')
    author.stage('open-thin-side-band-'+ref['actor'])
    obj=author.objects[ref['actor']];state=author.snapshot()[0][ref['actor']];mat=np.asarray(state['mat'])
    if mat[2,2]<.98:raise ToolExecutionError('Prepared E10 thin source must be nearly level')
    center=np.asarray(state['pos'])+mat@np.asarray(obj.get('local_bounds_center',[0,0,0]));extent=float(np.abs(mat[2])@np.asarray(obj['size']))
    bottom=float(center[2]-extent);top=float(center[2]+extent)
    target=contact_band_target(author.point(ref),bottom,top,author.tip(side)[2],author.a.finger_geometry(side)['lowest_z_task_m'])
    # A generic2mm waypoint tolerance consumes most of this6mm side band.
    # Reach the measured open-toe height before closing, not by trying to push
    # an already closed/top-clamped gripper down through the supported plate.
    author.move(side,target,tolerance=.0004)
    # A target alone is not clearance evidence. Refuse closing if actual toes
    # have either penetrated the support or passed completely above the piece.
    lowest=float(author.a.finger_geometry(side)['lowest_z_task_m'])
    if not bottom+.0003<=lowest<=top-.0005:
        raise ToolExecutionError('Actual E10 fingertips outside supported side contact band')
    author.a.control_report.setdefault('e10_open_contact_band',[]).append(dict(actor=ref['actor'],side=side,actual_toe_z_m=lowest,bottom_m=bottom,top_m=top))
    stable=0
    for _ in range(5):
        author.act(side,'GRASP');stable=stable+1 if author.held(ref,side) else 0
        if stable>=3:
            if ref.get('e10_reviewed_near_side'):
                pos,rotation=author.frame(ref)
                local=np.asarray(rotation).T@(author.tip(side)-np.asarray(pos))
                author.a.control_report.setdefault('e10_actual_near_side_grips',[]).append(dict(
                    actor=ref['actor'],side=side,tcp_body_local_m=local.tolist()))
                if not np.isfinite(local).all():raise ToolExecutionError('E10 actual pinch is nonfinite')
                author.a.control_report['e10_actual_near_side_grips'][-1]['preferred_offset_band']=bool(.007<=local[1]<=.016)
                # The preferred reachability offset is a recipe diagnostic.
                # Actual dual-pad grip, public IK and native threading/support
                # decide whether this grasp can finish the task.
            seat_supported_contact_band(author,ref,side)
            return
    raise ToolExecutionError('E10 thin side-band reference did not establish actual hold')


def post_transport_height(author,name,side,local_point,target,rotation):
    """Measured swept cargo and finger clearance; no hard maximum height."""
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    if float(np.asarray(rotation)[2,2])<.99:
        raise ToolExecutionError('E10 post route requires the reviewed level insertion orientation')
    state=author.snapshot()[0];value=state[name];obj=author.objects[name]
    matrix=np.asarray(value['mat']);center=np.asarray(value['pos'])+matrix@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    half=np.abs(matrix)@np.asarray(obj['size']);point=author.point(dict(actor=name,local=local_point))
    local_point=np.asarray(local_point,float);destination_rotation=np.asarray(rotation,float)
    destination_half=np.abs(destination_rotation)@np.asarray(obj['size'])
    destination_center_offset=destination_rotation@(np.asarray(obj.get('local_bounds_center',[0,0,0]))-local_point)
    cargo_depth=max(float(point[2]-center[2]+half[2]),float(destination_half[2]-destination_center_offset[2]))
    extent=np.maximum(half[:2]+np.abs(center[:2]-point[:2]),destination_half[:2]+np.abs(destination_center_offset[:2]))+.010
    lo=np.minimum(point[:2],np.asarray(target)[:2])-extent
    hi=np.maximum(point[:2],np.asarray(target)[:2])+extent
    top=.8
    def include(c,h):
        nonlocal top
        if np.all(c[:2]+h[:2]>=lo)and np.all(c[:2]-h[:2]<=hi):top=max(top,float(c[2]+h[2]))
    for actor,v in state.items():
        if actor==name:continue
        o=author.objects[actor];r=np.asarray(v['mat'])
        include(np.asarray(v['pos'])+r@np.asarray(o.get('local_bounds_center',[0,0,0])),np.abs(r)@np.asarray(o['size']))
    for f in author.spec.get('fixtures',[]):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E10 route fixture shape')
        include(np.array([*f['xy'],f['z']],float),np.asarray(f['size'],float))
    tcp_offset=float(point[2]-author.tip(side)[2])
    height=max(.94,top+.030+cargo_depth,author.a.floor_clear_tcp(side,floor=top+.030)+tcp_offset)
    author.a.control_report.setdefault('e10_measured_post_routes',[]).append(dict(actor=name,obstacle_top_m=top,cargo_depth_below_point_m=cargo_depth,transport_point_z_m=height,corridor_lower_xy=lo.tolist(),corridor_upper_xy=hi.tolist()))
    return height


def relay_table_site(author,name):
    """Choose an empty actual on-table patch near the two arm bases."""
    import itertools
    scene=author.a.scene;table=scene.layout.config['table'];origin=np.asarray(getattr(scene,'origin',(0,0,0)))
    center=np.asarray(table['position'])+origin;half=np.asarray(table['size'])/2
    corners=np.array([scene.world_to_task(center+half*np.array(sign))for sign in itertools.product((-1,1),repeat=3)])
    low,high=corners.min(axis=0),corners.max(axis=0);state=author.snapshot()[0]
    obj=author.objects[name];extent=float(np.linalg.norm(obj['size'][:2]))+.025
    obstacles=[]
    for n,value in state.items():
        if n==name:continue
        o=author.objects[n];r=np.asarray(value['mat']);c=np.asarray(value['pos'])+r@np.asarray(o.get('local_bounds_center',[0,0,0]));h=np.abs(r)@np.asarray(o['size']);obstacles.append((c[:2],h[:2]))
    for f in author.spec.get('fixtures',[]):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E10 relay fixture')
        obstacles.append((np.asarray(f['xy']),np.asarray(f['size'][:2])))
    middle=(low[1]+high[1])/2
    for dx,dy in itertools.product((extent+.015,extent+.065,extent+.115),(0.,-.08,.08,-.16,.16)):
        xy=np.array([low[0]+dx,middle+dy])
        if np.any(xy-extent<low[:2])or np.any(xy+extent>high[:2]):continue
        if any(np.all(np.abs(xy-p)<h+extent)for p,h in obstacles):continue
        return np.array([*xy,float(high[2])+.004])
    raise ToolExecutionError('No empty actual table patch for E10 physical regrasp')


def relay_to_destination_hand(author,name,ref,side,target):
    """Real table support/release followed by the other hand's real thin grip."""
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    scene=author.a.scene;bases={}
    for hand,robot in scene.robots.items():
        v=robot.data.root_pos_w[0]
        if hasattr(v,'detach'):v=v.detach().cpu().numpy()
        bases[hand]=np.asarray(scene.world_to_task(v))
    receiver=min(bases,key=lambda hand:float(np.linalg.norm(np.asarray(target)[:2]-bases[hand][:2])))
    if receiver==side:return ref,side
    stage=relay_table_site(author,name);author.stage('real-table-relay-'+name)
    rotation=author.frame(ref)[1]
    if rotation[2,2]<.99:raise ToolExecutionError('E10 relay requires a nearly level held source')
    previous=author.clearance
    author.clearance=post_transport_height(author,name,side,author.bottom_local(name),stage,rotation)
    try:author.lower_place(name,ref,side,author.bottom_local(name),stage,rotation,support='table')
    finally:author.clearance=previous
    state,contacts=author.snapshot()
    if any(state[name]['grasp'])or frozenset((name,'table'))not in contacts:
        raise ToolExecutionError('E10 regrasp requires actual released table support')
    if np.linalg.norm(np.asarray(state[name]['pos'])[:2]-stage[:2])>.015:
        raise ToolExecutionError('E10 released piece left physical relay site')
    author.a.control_report.setdefault('e10_physical_relays',[]).append(dict(actor=name,from_side=side,to_side=receiver,actual_released_position=np.asarray(state[name]['pos']).tolist(),actual_table_contact=True))
    park_released_donor(author,side,bases[side])
    acquire_thin_piece(author,ref,receiver)
    lift_thin_piece(author,ref,receiver)
    return ref,receiver


def park_released_donor(author,side,base):
    """Withdraw the empty donor using public actions before receiver approach."""
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    index=0 if side=='left'else 1
    def empty():
        state,contacts=author.snapshot()
        if any(v['grasp'][index] for v in state.values())or any(
                frozenset((name,f'{side}_finger{i}'))in contacts
                for name in state for i in (1,2)):
            raise ToolExecutionError('E10 donor retreat requires actually empty fingers')
    empty();author.stage('park-released-donor-'+side)
    base=np.asarray(base,float);height=max(.98,float(author.tip(side)[2]))
    if base.shape!=(3,)or not np.isfinite(base).all():raise ToolExecutionError('E10 actual donor base is invalid')
    author.move(side,[*author.tip(side)[:2],height],empty)
    author.move(side,[author.tip(side)[0],float(base[1]),height],empty)
    # Once the empty donor has left the central transfer column, preserve
    # its achieved X. Pulling farther toward its base caused native433 BACK
    # failure despite already being safely on the donor side.
    empty()
