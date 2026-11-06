"""E39 engineering-only reference tracking from measured payload positions.

This selects ordinary public Cartesian actions. It never changes native body
poses, joint state, grasp constraints, scoring, or the 2 mm waypoint tolerance.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def acquire_work_tray_down(author,ref,side):
    """Source-initial reference: align the full empty palm before gripping.

    Axis-only alignment left the real held wrist 7.48 degrees away from the
    downward orientation used by route IK. Do the complete public turn above
    the actual tab, then verify genuine bilateral acquisition as usual.
    Checkpoint suffixes never call this acquisition route.
    """
    from .execution_design_e39_package import _empty,orient_empty,_native_route,preflight_empty_orientation
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    from .author_orientation import _axis_angle
    if side!='left' or ref.get('actor')!='work_tray':raise ToolExecutionError('E39 source tray acquisition must use its reviewed left hand')
    author.stage('e39-empty-full-down-before-tray-grip')
    author.act(side,'RELEASE');_empty(author,side)
    point=author.point(ref);height=max(.95,float(point[2])+.10,float(author.tip(side)[2]))
    author.move(side,[*author.tip(side)[:2],height],lambda:_empty(author,side))
    author.move(side,[*point[:2],height],lambda:_empty(author,side))
    _empty(author,side,contact_free=True)
    _,body=author.frame(ref);jaw=body@np.asarray(ref['jaw_axis_local'],float);jaw[2]=0.;jaw/=np.linalg.norm(jaw)
    current=np.asarray(author.a.tcp_rotation_task(side));targets=physical_grasp_targets(author.a,author.c,side,[0,0,1],jaw)
    targets.sort(key=lambda r:_axis_angle(np.asarray(r)@current.T)[1])
    chosen=None
    for target in targets:
        try:
            _native_route(author,side,target,[author.tip(side),point],'full-down-tray-turn-and-descent')
            preflight_empty_orientation(author,side,target)
            chosen=target;break
        except ToolExecutionError:continue
    if chosen is None:raise ToolExecutionError('No full-down actual E39 tray acquisition route')
    orient_empty(author,side,chosen)
    author.stage('e39-full-down-actual-tray-grip')
    author.move(side,point,lambda:_empty(author,side))
    stable=0
    for _ in range(5):
        author.act(side,'GRASP')
        stable=stable+1 if author.held(ref,side)else 0
        if stable>=3:return
    raise ToolExecutionError('No actual bilateral E39 full-down tray grip')


def move_empty_waypoint(author,side,target,guard=None,tolerance=.002):
    """Public empty-hand moves compensate measured command/tracking offsets.

    Native v15 kept cycling around the same 2--4 mm approach residual: each
    accepted axis move lost about 1--1.5 mm and drifted in the other axes.
    Infer that loss from actual TCP readback without relaxing the target band.
    """
    target=np.asarray(target,float)
    if side not in ('left','right') or target.shape!=(3,) or not np.isfinite(target).all():
        raise ToolExecutionError('Invalid E39 empty-hand waypoint')
    if not np.isfinite(tolerance) or tolerance<=0:raise ToolExecutionError('Invalid E39 empty-hand tolerance')
    history=[];bias={};zero_motion=0
    initial_error=target-np.asarray(author.tip(side),float)
    horizontal=float(np.max(abs(initial_error[:2])))>.010 and abs(float(initial_error[2]))<.010
    for _ in range(200):
        if guard:guard()
        state=author.snapshot()[0]
        if any(v['grasp'][0 if side=='left' else 1]for v in state.values()):
            raise ToolExecutionError('E39 empty waypoint acquired an unexpected payload')
        before=np.asarray(author.tip(side),float);error=target-before
        if not np.isfinite(before).all():raise ToolExecutionError('Invalid actual E39 TCP')
        if np.max(np.abs(error))<=tolerance:return
        history.append(float(np.linalg.norm(error)))
        if len(history)>=49 and min(history[-49:-24])-min(history[-24:])<.0003:
            raise ToolExecutionError('E39 empty waypoint made no net progress')
        axis=2 if horizontal and abs(float(error[2]))>.003 else int(np.argmax(abs(error)));sign=1 if error[axis]>0 else -1
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(sign<0)]
        amount=min(author.max_mm,max(author.min_mm,abs(float(error[axis]))*1000+bias.get(token,0.)))
        author.act(side,token,mm=amount)
        after=np.asarray(author.tip(side),float)
        if after.shape!=(3,) or not np.isfinite(after).all():raise ToolExecutionError('Invalid actual E39 TCP')
        zero_motion=zero_motion+1 if amount>=4. and np.linalg.norm(after-before)<.00001 else 0
        if zero_motion>=2:raise ToolExecutionError('E39 empty public actions made no measured motion')
        loss=amount-sign*float(after[axis]-before[axis])*1000
        bias[token]=float(np.clip(loss,0.,min(6.,author.max_mm)))
    raise ToolExecutionError('E39 empty waypoint public action bound exhausted')


def move_payload_point(author,side,ref,target,guard=None,follower=None,tolerance=.002,done=None):
    target=np.asarray(target,dtype=float)
    if target.shape!=(3,) or not np.isfinite(target).all() or not np.isfinite(tolerance) or tolerance<=0:
        raise ToolExecutionError('Invalid measured E39 payload waypoint')
    if side not in ('left','right') or follower not in (None,'left','right'):
        raise ToolExecutionError('Unknown E39 physical robot hand')
    errors=[];bias={}
    for _ in range(600):
        if guard:guard()
        if done is not None and done():return
        position=np.asarray(author.point(ref),dtype=float)
        if position.shape!=(3,) or not np.isfinite(position).all():
            raise ToolExecutionError('Invalid actual E39 payload position')
        error=target-position;residual=float(np.max(np.abs(error)))
        if residual<=tolerance:return
        errors.append(residual)
        # Detect a repeating residual plateau even when the arm keeps moving
        # a few mm in a FWD/UP limit cycle. Legitimate slow progress remains
        # possible; the minimum required improvement is only 0.3 mm/24 actions.
        if len(errors)>=25 and errors[-25]-min(errors[-24:])<.0003:
            raise ToolExecutionError('E39 payload waypoint stalled: residual_m=%.6f, best_last_24_m=%.6f'%(errors[-25],min(errors[-24:])))
        axis=int(np.argmax(np.abs(error)))
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        amount=min(abs(float(error[axis]))*1000.+bias.get(token,0.),author.max_mm)
        author.act(side,token,mm=amount,follower=follower)
        measured=np.asarray(author.point(ref),float)
        along=float(np.sign(error[axis])*(measured[axis]-position[axis])*1000.)
        bias[token]=float(np.clip(amount-along,0.,min(8.,author.max_mm)))
    raise ToolExecutionError('E39 measured payload waypoint action bound exhausted')


def swept_height(start,end,relative_lower,relative_upper,obstacles,margin=.005,vertical_tracking_allowance=0.,horizontal_margin=None):
    """Actual translated assembly AABB sweep, with independent XY/Z margin."""
    start,end,lo,hi=map(lambda x:np.asarray(x,float),(start,end,relative_lower,relative_upper))
    if any(x.shape!=(3,) or not np.isfinite(x).all() for x in (start,end,lo,hi)) or np.any(lo>hi):
        raise ToolExecutionError('Invalid E39 assembly sweep')
    if not np.isfinite(vertical_tracking_allowance)or vertical_tracking_allowance<0:
        raise ToolExecutionError('Invalid E39 vertical tracking allowance')
    xy_margin=margin if horizontal_margin is None else float(horizontal_margin)
    if not np.isfinite(xy_margin)or xy_margin<0:raise ToolExecutionError('Invalid E39 horizontal tracking allowance')
    sweep_lo=np.minimum(start[:2],end[:2])+lo[:2]-xy_margin
    sweep_hi=np.maximum(start[:2],end[:2])+hi[:2]+xy_margin
    height=.8+margin-lo[2]+vertical_tracking_allowance
    for a,b in obstacles:
        a,b=np.asarray(a,float),np.asarray(b,float)
        if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite([a,b]).all() or np.any(a>b):
            raise ToolExecutionError('Invalid E39 obstacle bounds')
        if np.all(sweep_hi>=a[:2]) and np.all(sweep_lo<=b[:2]):
            height=max(height,float(b[2]+margin-lo[2]+vertical_tracking_allowance))
    return height


def place_work_tray(author,container,local):
    ref,side=author.pickup('work_tray')
    return carry_held_work_tray(author,container,local,ref,side,entry='y')


def assembly_contained_xy(author,container,*,tolerance=None):
    """Conservative full-body XY containment before any gravity release."""
    from itertools import product
    package=next(p for p in author.d['packages']if p['container']==container)
    box_p,box_r=author.frame(dict(actor=container))
    for name in ['work_tray',*author.d['target_members']]:
        p,r=author.frame(dict(actor=name));obj=author.objects[name]
        half=np.asarray(obj['size']);center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
        points=np.asarray(list(product(*zip(center-half,center+half))))@r.T+p
        local=(points-box_p)@box_r
        allowed=float(author.d.get('geometry_tolerance_m',.003))if tolerance is None else float(tolerance)
        if np.any(local[:,:2].min(0)<np.asarray(package['lower'])[:2]-allowed)or np.any(local[:,:2].max(0)>np.asarray(package['upper'])[:2]+allowed):return False
    return True


def carry_held_work_tray(author,container,local,ref,side,*,entry='x'):
    """Move Y then X around the real open lid; all moves remain public actions.

    Include actual carried pieces and finger collision bounds in each sweep.
    This is a payload corridor, not a whole-arm collision certificate; native
    motion/contact feedback still decides whether each public move succeeds.
    The scoring model and body/joint states are never written here.
    """
    name='work_tray'
    if ref.get('actor')!=name or side!='left' or entry not in ('y','x','align','seat'):
        raise ToolExecutionError('E39 held-stage route requires its actual left-held work tray')
    initial=author.snapshot()[0]
    references={n:(np.asarray(initial[n]['pos']).copy(),np.asarray(initial[n]['mat']).copy())
                for n in author.d['reference_objects']}
    point=dict(actor=name,local=author.bottom_local(name))
    base,rot=author.frame(dict(actor=container));target=base+rot@np.asarray(local,float)
    def guard():
        author.require_held(ref,side)
        state=author.snapshot()[0]
        if state[name]['mat'][2,2]<.995:raise ToolExecutionError('E39 tray tilted during low transport')
        for member in author.d['target_members']:
            if not author.contact(member,name):raise ToolExecutionError('E39 carried piece lost tray support')
        for n,(p,r)in references.items():
            if np.linalg.norm(np.asarray(state[n]['pos'])-p)>.002 or np.linalg.norm(np.asarray(state[n]['mat'])-r)>.02:
                raise ToolExecutionError('E39 carried tray disturbed protected reference')
    def plan(end,horizontal_margin=None):
        guard();origin=author.point(point);state=author.snapshot()[0]
        assembly={name,*author.d['target_members']};moving=[];obstacles=[]
        for actor,value in state.items():
            obj=author.objects[actor];matrix=np.asarray(value['mat']);center=np.asarray(value['pos'])+matrix@np.asarray(obj.get('local_bounds_center',[0,0,0]));extent=np.abs(matrix)@np.asarray(obj['size'])
            (moving if actor in assembly else obstacles).append((center-extent,center+extent))
        for finger in author.a.finger_geometry(side)['fingers']:
            moving.append((np.asarray(finger['aabb_min_task_m']),np.asarray(finger['aabb_max_task_m'])))
        for fixture in author.spec.get('fixtures',[]):
            if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed E39 fixture geometry')
            center=np.asarray([*fixture.get('xy',[0,0]),fixture['z']]);extent=np.asarray(fixture['size']);obstacles.append((center-extent,center+extent))
        lo=np.min([a for a,b in moving],axis=0)-origin;hi=np.max([b for a,b in moving],axis=0)-origin
        # Native v17 lateral actions sagged another 3.16 mm after entering the
        # 3 mm tracking band, creating a real tray/box-rim contact. Add 6 mm
        # vertically only; larger XY inflation would falsely reintroduce the
        # tall open-lid obstacle that the 10 mm Y detour already clears.
        height=swept_height(origin,end,lo,hi,obstacles,margin=.008,vertical_tracking_allowance=.006,
                            horizontal_margin=horizontal_margin)
        # A vertical lift may begin with existing supporting contacts. Once
        # the swept lowest point clears all intersected objects, translate.
        height=max(height,float(target[2])+.015)
        author.move_point(side,point,[*origin[:2],height],guard,tolerance=.003)
        def transit_guard():
            guard()
            if author.contact(name,container):
                raise ToolExecutionError('E39 elevated tray transport contacted the protective box')
            lid=next(p.get('lid')for p in author.d['packages']if p['container']==container)
            if lid and any(author.contact(moving,lid)for moving in [name,*author.d['target_members'],side+'_finger1',side+'_finger2']):
                raise ToolExecutionError('E39 elevated tray transport contacted the open lid')
        move_clearance_plane(author,side,point,[*end[:2],height],transit_guard,tolerance=.003)
    # Budget the actual 3mm tracking band before the X sweep: the nominal
    # lid gap is only 9mm. A 10mm Y detour prevents endpoint residue from
    # expanding the horizontal sweep across the vertical lid.
    detour=target.copy();detour[1]+=.010
    if entry=='y':
        author.stage('workflow-tray-lid-detour-y')
        origin=author.point(point);plan([origin[0],detour[1],origin[2]])
    if entry in ('y','x'):
        author.stage('workflow-tray-lid-detour-x');plan(detour)
    if entry!='seat':
        # Use the native 3mm horizontal boundary for the short final align.
        # Keep the measured 8mm vertical clearance plus 6mm sag allowance.
        # Source B had 7.45mm real lid separation; an extra 8mm XY inflation
        # selected an unnecessary, unreachable 1.33m lift.
        author.stage('workflow-tray-align-over-box')
        plan(target,horizontal_margin=float(author.d.get('geometry_tolerance_m',.003)))
    elif np.max(abs(author.point(point)[:2]-target[:2]))>.015:
        raise ToolExecutionError('E39 seat-stage fixture is outside the box alignment corridor')
    author.stage('workflow-tray-seat-in-box')
    # Real v4 fingers reached the 872mm box rim while the tray still hung
    # 23mm above its floor. The 4mm side gap cannot admit a whole Panda pad.
    # Stop at a measured finger-clear release plane, then let this same tray
    # settle under gravity. No object/support state is assigned here.
    from .execution_design_e39_package import body_bounds
    rim=float(body_bounds(author,container)[1][2])
    finger_lowest=float(author.a.finger_geometry(side)['lowest_z_task_m'])
    offset=finger_lowest-float(author.point(point)[2])
    release_height=max(float(target[2])+.001,rim+.006-offset)
    if release_height-float(target[2])>.035:
        raise ToolExecutionError('E39 finger-clear release would require more than 35mm gravity descent')
    def ready_to_release():
        bottom=float(author.point(point)[2])
        lowest=float(author.a.finger_geometry(side)['lowest_z_task_m'])
        return (assembly_contained_xy(author,container)and 0<=bottom-float(target[2])<=.035
            and rim-bottom>=.020 and lowest>=rim+.003)
    move_payload_point(author,side,point,[*target[:2],release_height],guard,done=ready_to_release)
    bottom=float(author.point(point)[2]);guard()
    if (not assembly_contained_xy(author,container)or not 0<=bottom-float(target[2])<=.035
            or rim-bottom<.020):
        raise ToolExecutionError('E39 gravity release lacks full XY containment and embedded tray depth')
    author.stage('workflow-finger-clear-gravity-seat')
    author.release(ref,side);author.wait(3)
    from .execution_design_e39_piece import require_local_piece_poses
    require_local_piece_poses(author)
    author.move(side,[*author.tip(side)[:2],.920],lambda:require_local_piece_poses(author));author.wait(1)
    require_local_piece_poses(author)
    if not author.contact(name,container):raise ToolExecutionError('E39 tray lacks actual protective-box support')
    if author.a.control_report.get('engineering_reference_only'):
        from .execution_design_e39_escape import escape_empty_for_lid
        old=getattr(author.a,'_execution_design_reference_authorized',False)
        author.a._execution_design_reference_authorized=True
        try:escape_empty_for_lid(author,rotation_degrees=3.)
        finally:author.a._execution_design_reference_authorized=old


def move_clearance_plane(author,side,ref,target,guard,tolerance=.003):
    """Horizontal transport keeps measured Z in band before advancing XY."""
    target=np.asarray(target,float);history=[];bias_by_token={}
    if target.shape!=(3,) or not np.isfinite(target).all():raise ToolExecutionError('Invalid E39 clearance plane')
    initial=np.asarray(author.point(ref),float)
    primary=int(np.argmax(np.abs((target-initial)[:2])));cross=1-primary
    for _ in range(600):
        guard();position=np.asarray(author.point(ref),float)
        if position.shape!=(3,) or not np.isfinite(position).all():raise ToolExecutionError('Invalid actual E39 clearance pose')
        error=target-position
        if np.max(np.abs(error))<=tolerance:return
        # Correct actual sag before any further horizontal move. Each bounded
        # public move remains subject to the native motion/contact feedback.
        axis=2 if abs(error[2])>tolerance else cross if abs(error[cross])>tolerance else primary
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        history.append(position.copy())
        if len(history)>=49:
            distances=np.linalg.norm(target-np.asarray(history[-49:]),axis=1)
            if float(np.min(distances[:25]))-float(np.min(distances[25:]))<.0003:
                raise ToolExecutionError('E39 clearance-plane best target distance made no net progress across 24-action windows')
        amount=min(author.max_mm,10.,abs(float(error[axis]))*1000+bias_by_token.get(token,0.))
        if axis==2 and error[2]>0:
            # Native loaded UP4.266mm advanced only .052mm (no IK refusal).
            # Start at 6mm, then estimate the actual command-minus-motion
            # offset. Keep every request inside the original 10mm bound;
            # any overshoot is remeasured and corrected before XY advances.
            amount=min(author.max_mm,10.,max(6.,abs(float(error[2]))*1000+bias_by_token.get(token,0.)))
        author.act(side,token,mm=amount)
        measured=np.asarray(author.point(ref),float)
        if measured.shape!=(3,) or not np.isfinite(measured).all():raise ToolExecutionError('Invalid E39 post-action payload measurement')
        actual_along=float(np.sign(error[axis])*(measured[axis]-position[axis])*1000)
        if axis in (0,1):
            downward=float(position[2]-measured[2])
            if downward>.004 and downward>2.*abs(float(measured[axis]-position[axis])):
                raise ToolExecutionError('E39 horizontal public action moved primarily downward; stop for checkpoint posture repair')
        bias_by_token[token]=float(np.clip(amount-actual_along,0.,8.))
    raise ToolExecutionError('E39 clearance-plane public action bound exhausted')
