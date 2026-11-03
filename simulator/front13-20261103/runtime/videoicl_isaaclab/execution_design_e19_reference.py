"""Measured cap transport for isolated v3 engineering references."""
import json
import numpy as np
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def _scope(tool):
    if (tool.task != 'E19' or tool.spec.get('execution_design', {}).get('revision') != REVISION_V3
            or not getattr(tool.a, 'control_report', {}).get('engineering_reference_only')):
        raise ValueError('E19 v3 independent engineering reference required')


def choose_cap_hand(tool,name,target):
    """Select by both measured endpoints; public acquisition still proves reach."""
    _scope(tool)
    source=np.asarray(tool.point(tool.ref(name)),float);target=np.asarray(target,float)
    if source.shape!=(3,) or target.shape!=(3,) or not np.isfinite(np.r_[source,target]).all():
        raise ValueError('Finite measured E19 pickup and mouth points required')
    distances={}
    for side,robot in tool.a.scene.robots.items():
        p=robot.data.root_pos_w[0]
        if hasattr(p,'detach'):p=p.detach().cpu().numpy()
        base=np.asarray(tool.a.scene.world_to_task(p),float)
        if base.shape!=(3,) or not np.isfinite(base).all():raise ValueError('Finite native arm base required')
        distances[side]=[float(np.linalg.norm(point-base)) for point in (source,target)]
    if set(distances)!={'left','right'}:raise ValueError('Both native E19 arm bases required')
    chosen=min(distances,key=lambda side:(max(distances[side]),sum(distances[side]),side))
    tool.a.control_report.setdefault('e19_hand_choices',[]).append(dict(actor=name,source=source.tolist(),target=target.tolist(),distances_m=distances,chosen=chosen,native_reachability_verified=False))
    return chosen


def cap_transport_height(tool, name, side, local_point, target):
    _scope(tool)
    state, _ = tool.snapshot()
    tops = {}
    bottoms = {}
    for obj in tool.spec['objects']:
        body = state[obj['id']]
        pos = np.asarray(body['pos'], float)
        rotation = np.asarray(body['mat'], float)
        half = np.asarray(obj.get('bounds_half_extent', obj['size']), float)
        center = pos + rotation @ np.asarray(obj.get('local_bounds_center', [0, 0, 0]), float)
        extent = np.abs(rotation) @ half
        if not np.isfinite(np.r_[center, extent]).all() or np.any(half <= 0):
            raise ValueError('Finite actual bottle and cap collision bounds required')
        tops[obj['id']] = float(center[2] + extent[2])
        bottoms[obj['id']] = float(center[2] - extent[2])
    point = np.asarray(tool.point(dict(actor=name, local=local_point)), float)
    target = np.asarray(target, float)
    if point.shape != (3,) or target.shape != (3,) or not np.isfinite(np.r_[point, target]).all():
        raise ValueError('Finite measured cap point and target required')
    geometry = tool.a.finger_geometry(side)
    if geometry.get('source') != 'actual_collision_mesh_current_body_pose':
        raise ValueError('Actual finger mesh required for cap transport')
    depth = max(0., float(point[2]) - bottoms[name], float(point[2]) - float(geometry['lowest_z_task_m']))
    top = max([.8] + [z for obj, z in tops.items() if obj != name])
    height = max(top + depth + .025, float(target[2]) + .025)
    if not np.isfinite(height): raise ValueError('Finite cap transport height required')
    return dict(height_m=height, obstacle_top_m=top, depth_below_working_point_m=depth,
                margin_m=.025, native_reachability_verified=False)


def move_cap_point(tool, side, control, target, guard, tolerance=.002):
    """Close feedback on the material point, without a stale inner TCP target.

    The old reference oscillated around one 12 mm increment for 180 actions.
    Every new action now uses the achieved cap pose and the same public limits.
    """
    _scope(tool)
    target = np.asarray(target, float)
    if target.shape != (3,) or not np.isfinite(target).all() or not .0008 <= tolerance <= .002:
        raise ValueError('Finite measured cap target and reviewed tolerance required')
    history = []
    for _ in range(300):
        guard()
        point = np.asarray(tool.point(control), float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError('Finite actual cap point required')
        error = target - point
        if np.max(np.abs(error)) <= tolerance: return
        history.append(point.copy())
        if len(history) > 32 and max(np.linalg.norm(p - point) for p in history[-32:]) < .0003:
            raise ToolExecutionError('Actual cap material point stalled')
        axis = int(np.argmax(np.abs(error)))
        token = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))[axis][int(error[axis] < 0)]
        tool.act(side, token, mm=float(abs(error[axis]) * 1000))
    raise ToolExecutionError('Actual cap material point did not converge')


def retreat_empty_hand(tool, side, home_xy, clearance):
    """Vacate the bottle area through public motion after actual release.

    Keeping the first empty hand over its bottle leaves it beside the next
    loaded hand. Return to the measured starting XY above the bottle tops.
    """
    _scope(tool)
    home_xy = np.asarray(home_xy, float)
    if side not in ('left', 'right') or home_xy.shape != (2,) or not np.isfinite(home_xy).all():
        raise ValueError('Actual E19 starting hand XY required')
    if not np.isfinite(clearance): raise ValueError('Finite measured retreat clearance required')
    index = 0 if side == 'left' else 1
    def empty():
        state, _ = tool.snapshot()
        if any(bool(body.get('grasp', [False, False])[index]) for body in state.values()):
            raise ToolExecutionError('E19 retreat requires actual empty hand')
    empty()
    height = max(float(tool.tip(side)[2]), float(clearance) + .06)
    tool.stage('cap-empty-return-' + side)
    tool.move(side, [*tool.tip(side)[:2], height], guard=empty)
    tool.move(side, [*home_xy, height], guard=empty)
    empty()


def place_cap(tool, name, ref, side, local_point, target, bottle, home_xy):
    _scope(tool)
    control = dict(actor=name, local=list(local_point))
    target = np.asarray(target, float)
    guard = lambda: tool.require_held(ref, side)
    guard()
    route = cap_transport_height(tool, name, side, local_point, target)
    with (tool.a.out / 'measured-cap-transports.private.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(cap=name, bottle=bottle, **route)) + '\n')
    height = route['height_m']
    tool.stage('cap-measured-lift-' + bottle)
    move_cap_point(tool, side, control, [*tool.point(control)[:2], height], guard)
    tool.stage('cap-measured-transfer-' + bottle)
    move_cap_point(tool, side, control, [*target[:2], height], guard)
    if (tool.spec.get('variant')=='C' and tool.label(name)=='red'
            and tool.label(bottle)=='water_bottle'):
        # This pair's native failure showed a finger pressing the bottle and
        # stale-mouth chasing; keep all previously accepted pair routes intact.
        gravity_seat_red_water(tool,name,ref,side,control,bottle)
        retreat_empty_hand(tool,side,home_xy,height)
        return
    tool.stage('cap-real-mouth-' + bottle)
    move_cap_point(tool, side, control, target + [0, 0, .001], guard, tolerance=.001)
    tool.release(ref, side)
    tool.move(side, tool.tip(side) + [0, 0, .06])
    tool.wait(3)
    if not tool.contact(name, bottle):
        raise ToolExecutionError('Placed cap lacks actual bottle support: ' + name)
    retreat_empty_hand(tool, side, home_xy, height)


def _native_finger_velocities(tool,side):
    """Actual native Panda finger qd in m/s; no pose-derived substitute."""
    robot=tool.a.scene.robots[side];ids,names=robot.find_joints('panda_finger_joint[1-2]')
    if len(ids)!=2 or set(names)!={'panda_finger_joint1','panda_finger_joint2'}:
        raise ValueError('Measured bilateral native E19 finger velocities required')
    value=robot.data.joint_vel[0,ids]
    if hasattr(value,'detach'):value=value.detach()
    if hasattr(value,'cpu'):value=value.cpu()
    value=np.asarray(value,float)
    if value.shape!=(2,)or not np.isfinite(value).all():raise ValueError('Finite actual E19 finger qd required')
    return list(names),value


def gravity_seat_red_water(tool,name,ref,side,control,bottle,*,entry_phase='alignment'):
    """C red/water candidate: release above the real rim, never push through it.

    All changes are public robot actions. The original native support and
    geometric covering rule must still pass after the cap falls freely.
    """
    import math
    _scope(tool)
    if entry_phase not in ('alignment','rim_release'):raise ValueError('Reviewed measured cap entry phase required')
    if tool.spec.get('variant')!='C' or tool.label(name)!='red' or tool.label(bottle)!='water_bottle':
        raise ValueError('Reviewed E19 C red cap / water bottle pair required')
    semantic=tool.spec['semantic'];cover=semantic['caps'][name];mouth=semantic['mouths'][bottle]
    objects={o['id']:o for o in tool.spec['objects']}
    pins={name:'a8d1a023e305cc173e0bda92a4c52f7f2f20731a32894b4fbab2a2669f840c4a',bottle:'a1063067fb4ff0db03ba5436820756f9149f6eb45b5c9c5973ef5d6274eff71f'}
    if any(objects[n].get('source_asset',{}).get('sha256')!=pin for n,pin in pins.items()):
        raise ValueError('E19 C seating requires reviewed cap and bottle source meshes')
    initial=tool.snapshot()[0][bottle];anchor=np.asarray(initial['pos'],float).copy()
    log=tool.a.out/'e19-c-gravity-seating.private.jsonl'
    def record(phase,**data):
        with log.open('a')as f:f.write(json.dumps(dict(phase=phase,cap=name,bottle=bottle,**data))+'\n')
    def measure(held=True):
        state,contacts=tool.snapshot();cb,bb=state[name],state[bottle]
        cp=np.asarray(cb['pos'])+np.asarray(cb['mat'])@np.asarray(cover['center_local'])
        bp=np.asarray(bb['pos'])+np.asarray(bb['mat'])@np.asarray(mouth['center_local'])
        ca=np.asarray(cb['mat'])@np.asarray(cover['axis_local']);ca/=np.linalg.norm(ca)
        ba=np.asarray(bb['mat'])@np.asarray(mouth['axis_local']);ba/=np.linalg.norm(ba)
        geo=tool.a.finger_geometry(side)
        if (not np.isfinite(np.r_[cp,bp,ca,ba]).all()or geo.get('source')!='actual_collision_mesh_current_body_pose'):
            raise ValueError('Measured native cap / mouth / finger geometry required')
        if held:
            tool.require_held(ref,side)
            if np.linalg.norm(np.asarray(bb['pos'])-anchor)>.002:
                raise ToolExecutionError('E19 bottle moved during held cap alignment')
            if any(frozenset((bottle,side+'_finger'+str(i)))in contacts for i in (1,2)):
                raise ToolExecutionError('E19 held fingers contacted the real bottle')
            if ba[2]<math.cos(math.radians(5)):
                raise ToolExecutionError('E19 mouth tilted beyond reviewed gravity approach')
        return cp,bp,ca,ba,float(geo['lowest_z_task_m']),contacts
    if entry_phase=='alignment':
        tool.stage('cap-c-align-above-actual-mouth')
        for _ in range(80):
            cp,bp,ca,ba,low,contacts=measure()
            if cp[2]-bp[2]<.012 or low-bp[2]<.008:
                raise ToolExecutionError('E19 cap axis alignment lacks actual rim clearance')
            angle=math.acos(float(np.clip(ca@ba,-1,1)))
            if angle<math.radians(.25):break
            cross=np.cross(ca,ba);norm=np.linalg.norm(cross)
            if norm<1e-8:raise ToolExecutionError('E19 cap axis has no safe local rotation')
            axis=cross/norm;k=int(np.argmax(abs(axis)))
            token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[k][int(axis[k]<0)]
            tool.act(side,token,degrees=min(2.,max(.5,abs(math.degrees(angle*axis[k])))))
        else:raise ToolExecutionError('E19 actual cap axis did not converge')
    tool.stage('cap-c-measured-rim-release')
    history=[]
    for _ in range(220):
        cp,bp,ca,ba,low,contacts=measure()
        if float(ca@ba)<math.cos(math.radians(.25)):
            raise ToolExecutionError('E19 held cap axis drifted before rim release')
        depth=max(0.,float(cp[2]-low));gap=max(.003,depth+.002)
        if gap>.012:raise ToolExecutionError('E19 real fingers require excessive gravity drop')
        # The real source annulus has only .5mm radial clearance. The first
        # native drop started .395mm off-centre with .446deg axis error and
        # ended supported but tilted 23.27deg. Per-tick follow-up also exposed
        # a release impulse before bottle contact; centering alone did not fix it.
        # Aim along the measured bottle axis, observe the actual fingers once,
        # and let the real placement test the unchanged native covering rule.
        target=bp+ba*(gap/float(ba[2]));delta=target-cp
        xy=float(np.max(abs(delta[:2])));target_z=float(target[2])
        if xy<=.00025 and abs(cp[2]-target_z)<=.00025:
            if low<bp[2]+.0015:raise ToolExecutionError('E19 real fingers still below safe mouth clearance')
            names,qd=_native_finger_velocities(tool,side)
            # Latest engineering preference: one measured observation, no
            # extra settling sequence or velocity convergence requirement.
            record('before_real_release',cap_opening=cp.tolist(),mouth=bp.tolist(),cap_axis=ca.tolist(),mouth_axis=ba.tolist(),finger_lowest_z=low,radial_xy_error_m=xy,gap_m=float(cp[2]-bp[2]),finger_joint_names=names,finger_qd_m_s=qd.tolist(),finger_velocity_observation_only=True)
            break
        history.append(cp.copy())
        if len(history)>30 and max(np.linalg.norm(x-cp)for x in history[-30:])<.0002:
            raise ToolExecutionError('E19 measured rim approach stalled')
        if xy>.00025 and (cp[2]<bp[2]+.003 or low<bp[2]+.0015):
            token='UP';mm=min(1.,max(.5,(bp[2]+.015-cp[2])*1000))
        elif xy>.00025:
            axis=int(np.argmax(abs(delta[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(delta[axis]<0)];mm=min(1.,max(.5,abs(delta[axis])*1000))
        else:
            dz=target_z-cp[2];token='UP'if dz>0 else'DOWN';mm=min(1.,max(.5,abs(dz)*1000))
        tool.act(side,token,mm=float(mm))
    else:raise ToolExecutionError('E19 measured rim release point did not converge')
    tool.release(ref,side)
    tool.move(side,tool.tip(side)+[0,0,.06])
    tool.wait(3)
    cp,bp,ca,ba,low,contacts=measure(held=False);delta=bp-cp;depth=float(delta@ca);radial=float(np.linalg.norm(delta-depth*ca))
    state,_=tool.snapshot();released=not any(state[name].get('grasp',[]));supported=tool.contact(name,bottle)
    covering=(float(ba@ca)>.98 and 0<=depth<=cover['depth']+.001
        and radial+mouth['outer_radius']<=cover['inner_radius']+.001)
    record('after_real_release',released=bool(released),actual_support_contact=bool(supported),actual_covering=bool(covering),axial_depth_m=depth,radial_error_m=radial,native_accepted=False)
    if not released or not supported or not covering:
        raise ToolExecutionError('E19 gravity placement lacks actual released cap covering/support')
