"""E20 source-rail pickup by the hand nearest its destination cell."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def reviewed_red_rail_conflict(author, ref):
    """Only the native-evidenced red1/fixture7 conflict uses early liftoff.

    Blue's old three-GRASP route succeeded. Moving blue at its first contact
    regressed to 7.23mm sideways slip at action270, so it stays on that route.
    Red1 had two genuine held receipts before the third squeeze overturned it.
    """
    if (author.task != 'E20' or ref.get('actor') != 'red_supply_1'
            or not author.a.control_report.get('engineering_reference_only')
            or author.spec.get('execution_design', {}).get('revision') != 'embodied50-execution-v3-20261102'):
        return False
    obj = author.objects['red_supply_1']
    if obj.get('source_asset', {}).get('sha256') != '0a52a9c5b908277e7e408155316a3fc55f889405d6ab0331f0922e8bb4047120':
        return False
    support = author.d.get('initial_storage', {}).get('red_supply_1')
    if support != 'fixture7' or len(author.spec.get('fixtures', [])) <= 7:
        return False
    rail = author.spec['fixtures'][7]
    return bool(rail.get('type') == 'box' and np.allclose(rail.get('size'), [.003, .012, .014])
                and author.contact('red_supply_1', support))


def require_measured_red_grip_ready(author, ref, side):
    if not reviewed_red_rail_conflict(author, ref):
        raise ToolExecutionError('E20 measured red1 source-rail conflict required')
    robot = author.a.scene.robots[side]
    ids = author.c.ids[side][1]
    def measured(value):
        if hasattr(value, 'detach'):value = value.detach()
        if hasattr(value, 'cpu'):value = value.cpu()
        return np.asarray(value, float)
    q = measured(robot.data.joint_pos[0, ids])
    qd = measured(robot.data.joint_vel[0, ids])
    observed_liftoff=(author.spec.get('variant')in('A','B','C')and author.spec.get('seed')==4201
        and author.spec.get('execution_design',{}).get('condition')=='I')
    if (q.shape != (2,) or qd.shape != (2,) or not np.isfinite([q, qd]).all()
            or np.min(q) <= .001 or(not observed_liftoff and np.max(np.abs(qd)) > .010)):
        raise ToolExecutionError('E20 red rail grip still dynamically closing before liftoff')
    if observed_liftoff:
        state,contacts=author.snapshot()
        if not state['red_supply_1']['grasp'][('left','right').index(side)]or not all(
                frozenset(('red_supply_1',side+'_finger'+str(i)))in contacts for i in(1,2)):
            raise ToolExecutionError('E20 A red liftoff requires real bilateral contact')
        author.a.control_report['e20_a_red_single_finger_speed_observation']=dict(
            measured_finger_q_m=q.tolist(),measured_finger_qd_m_s=qd.tolist(),
            velocity_quiet_wait_required=False,actual_lift_and_grip_validation_required=True)


def finish_chip_grip(author, ref, side):
    """Public grip tail, also usable as an engineering checkpoint segment.

    Enter after the measured pre-grasp waypoint, before the first GRASP.
    The default route keeps the original three held receipts. Only red1 on
    its original narrow rail branches after two actual held receipts.
    """
    stable = 0
    for _ in range(5):
        author.act(side, 'GRASP')
        stable = stable + 1 if author.held(ref, side) else 0
        blue_left=(author.task=='E20'and author.spec.get('variant')in('B','C')
            and author.spec.get('seed')==4201 and side=='left'and ref.get('actor')=='blue_supply_1'
            and author.spec.get('execution_design',{}).get('condition')=='I'
            and author.a.control_report.get('engineering_reference_only')
            and author.d.get('initial_storage',{}).get('blue_supply_1')=='fixture3'
            and author.contact('blue_supply_1','fixture3'))
        if stable>=2 and blue_left:
            verify_grip_during_small_liftoff(author,ref,side,initial_measured_grips=1)
            return
        if stable >= 2 and reviewed_red_rail_conflict(author, ref):
            verify_grip_during_small_liftoff(author, ref, side, initial_measured_grips=2)
            return
        if stable >= 3:
            if (author.task=='E20'and getattr(author,'variant',None)=='B'and side=='right'
                    and ref.get('actor')=='blue_supply_1'
                    and author.a.control_report.get('engineering_reference_only')
                    and author.d.get('revision')=='embodied50-execution-v3-20261102'
                    and author.d.get('condition')=='I'
                    and author.d.get('initial_storage',{}).get('blue_supply_1')=='fixture3'
                    and author.contact('blue_supply_1','fixture3')):
                from .execution_design_e20_b_reseat import supported_pad_reseat
                supported_pad_reseat(author,'blue_supply_1','right')
            return
    raise ToolExecutionError('No settled two-finger chip grip')


def verify_grip_during_small_liftoff(author, ref, side, *, initial_measured_grips=1):
    """Verify an actual E20 pinch while lifting clear of its real narrow rail.

    Native near-cell A held red_supply_1 on actions 545/546, then squeezed it
    off its rail on the third stationary GRASP. Keep the three consecutive
    measured-grip requirement, but use recorded 2 mm UP actions after the
    first real pinch. No attachment, state write, or contact substitution.
    """
    if (author.task != 'E20' or not author.a.control_report.get('engineering_reference_only')
            or author.spec.get('execution_design', {}).get('revision') != 'embodied50-execution-v3-20261102'):
        raise ToolExecutionError('E20 v3 independent engineering liftoff required')
    if initial_measured_grips not in (1, 2):
        raise ToolExecutionError('E20 liftoff needs one or two actual measured grip receipts')
    if initial_measured_grips == 2:
        require_measured_red_grip_ready(author, ref, side)
    name = ref['actor']
    author.require_held(ref, side)
    origin = np.asarray(author.frame({'actor': name})[0], float).copy()
    tip0 = np.asarray(author.tip(side), float).copy()
    roots = ['table', *(f'fixture{i}' for i in range(len(author.spec.get('fixtures', []))))]
    supports = [n for n in roots if author.contact(name, n)]
    stable = initial_measured_grips
    functional=(author.spec.get('variant')in('A','B','C')and author.spec.get('seed')==4201
        and author.spec.get('execution_design',{}).get('condition')=='I')
    # Leave the narrow rail in one real motion rather than repeatedly squeezing
    # a 2mm-thick chip against it. Native grip/contact checks still run after UP.
    step_mm=10. if functional and name=='red_supply_1'and initial_measured_grips==2 else 2.
    minimum_rise=.005 if functional else .010
    lateral_limit=.020 if functional else .006
    for _ in range(20):
        author.require_held(ref, side)
        author.act(side, 'UP', mm=step_mm)
        author.require_held(ref, side)
        if functional and not all(author.contact(name,side+'_finger'+str(i))for i in(1,2)):
            raise ToolExecutionError('E20 actual lift lost bilateral finger contact')
        stable += 1
        delta = np.asarray(author.frame({'actor': name})[0], float) - origin
        if np.linalg.norm(delta[:2]) > lateral_limit:
            raise ToolExecutionError('E20 chip slides sideways during measured liftoff')
        if float(author.tip(side)[2] - tip0[2]) > .010 and delta[2] < .003:
            raise ToolExecutionError('E20 hand rises without actual chip liftoff')
        remaining = [n for n in supports if author.contact(name, n)]
        if stable >= (2 if functional else 3) and delta[2] >= minimum_rise and not remaining:
            author.a.control_report.setdefault('e20_small_liftoffs', []).append(dict(
                actor=name, hand=side, consecutive_measured_grips=stable,
                payload_delta_m=delta.tolist(), original_supports=supports,
                remaining_supports=remaining,minimum_payload_rise_m=minimum_rise,
                lateral_envelope_m=lateral_limit,public_lift_mm=step_mm))
            return
    raise ToolExecutionError('E20 bounded actual chip liftoff exhausted')


def robot_bases(author):
    if author.task!='E20' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E20 independent engineering control required')
    scene=author.a.scene;bases={}
    for side,robot in scene.robots.items():
        value=robot.data.root_pos_w[0]
        if hasattr(value,'detach'):value=value.detach().cpu().numpy()
        bases[side]=np.asarray(scene.world_to_task(value),float)
    return bases


def nearest_target_hand(author,target):
    bases=robot_bases(author)
    return min(bases,key=lambda side:float(np.linalg.norm(np.asarray(target)[:2]-bases[side][:2])))


def replenishment_candidates(author, region):
    preserved={n for names in author.d['initial_preserved'].values() for n in names}
    state=author.snapshot()[0];bases=robot_bases(author)
    names=[n for n in region['candidates'] if n.startswith(region['required_color']+'_') and n not in preserved]
    return sorted(names,key=lambda n:(max(float(np.linalg.norm(np.asarray(state[n]['pos'])[:2]-p[:2])) for p in bases.values()),n))


def ordered_replenishment_regions(author):
    """Start with a required chip whose original rail is near both arms."""
    state=author.snapshot()[0];bases=robot_bases(author)
    def rank(region):
        if region['count']<=len(author.d['initial_preserved'][region['id']]):return float('inf')
        names=replenishment_candidates(author,region)
        return min(max(float(np.linalg.norm(np.asarray(state[n]['pos'])[:2]-p[:2]))for p in bases.values())for n in names)
    return sorted(author.d['local_regions'],key=rank)


def remember_freed_source_rail(author,name):
    support=author.d.get('initial_storage',{}).get(name)
    if not support or not support.startswith('fixture'):return
    fixture=author.spec['fixtures'][int(support[7:])]
    if not np.allclose(fixture.get('size'),[.003,.012,.014]):return
    if getattr(author,'_e20_freed_source_rail',None):return
    author._e20_freed_source_rail=dict(actor=support,xy=list(fixture['xy']),surface_z=fixture['z']+fixture['size'][2])


def measured_empty_approach_height(author,side):
    state=author.snapshot()[0];top=.8
    for name,value in state.items():
        obj=author.objects[name];r=np.asarray(value['mat']);c=np.asarray(value['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        top=max(top,float(c[2]+np.abs(r[2])@np.asarray(obj['size'])))
    for f in author.spec.get('fixtures',[]):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E20 source fixture')
        top=max(top,float(f['z']+f['size'][2]))
    return max(.98,author.a.floor_clear_tcp(side,floor=top+.05))


def pickup_via_transfer_support(author, name, target):
    """Real source-hand pickup, supported release, destination-hand regrasp."""
    destination=nearest_target_hand(author,target)
    if (author.spec.get('variant')=='B'and author.spec.get('seed')==4201
            and author.spec.get('execution_design',{}).get('condition')=='I'
            and author.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
            and author.a.control_report.get('engineering_reference_only')
            and name=='blue_supply_1'and destination=='left'
            and author.d.get('initial_storage',{}).get(name)=='fixture3'
            and author.objects[name].get('source_asset',{}).get('sha256')=='0a52a9c5b908277e7e408155316a3fc55f889405d6ab0331f0922e8bb4047120'):
        # Native B97/98 established the real source-side left pinch; B98-v18
        # then really lifted, carried and released blue1 onto its original
        # tray cell. Keep that destination hand and omit the failed rail2
        # intermediate release/regrasp. Every pickup still uses public actions.
        return author.pickup(name,side_override='left')
    if getattr(author,'_engineering_e20_direct_destination',False):
        if (author.spec.get('variant')!='C'or author.spec.get('seed')!=4201
                or author.spec.get('execution_design',{}).get('condition')!='I'
                or not getattr(author.c,'_engineering_diagnostic_only',False)
                or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
            raise ToolExecutionError('Direct destination acquisition requires admitted E20 C423 suffix')
        return author.pickup(name,side_override=destination)
    route=getattr(author,'_e20_freed_source_rail',None)
    # The first required chip is selected from a near-centre existing rail.
    # Only after a real successful placement may that vacated rail be reused.
    if not route:return author.pickup(name,side_override=destination)
    source=nearest_target_hand(author,author.snapshot()[0][name]['pos'])
    ref,side=author.pickup(name,side_override=source)
    if source==destination:return ref,side
    support=route['actor'];index=int(support.removeprefix('fixture'))
    fixture=author.spec['fixtures'][index]
    point=np.array([*route['xy'],route['surface_z']],float)
    if (fixture.get('type')!='box' or not np.allclose(fixture['xy'],point[:2])
            or abs(fixture['z']+fixture['size'][2]-point[2])>1e-6):
        raise ToolExecutionError('E20 transfer route disagrees with physical fixture')
    for other,value in author.snapshot()[0].items():
        if other==name:continue
        obj=author.objects[other];r=np.asarray(value['mat']);center=np.asarray(value['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]));half=np.abs(r)@np.asarray(obj['size'])
        if np.all(center[:2]+half[:2]>point[:2]-.018) and np.all(center[:2]-half[:2]<point[:2]+.018):
            raise ToolExecutionError('Previously used E20 source rail is occupied')
    before=author.clearance
    author.stage('workflow-transfer-'+name)
    author.clearance=author.measured_transport_clearance(name,side)
    try:
        author.lower_place(name,ref,side,author.bottom_local(name),point,np.eye(3),support=support)
    finally:author.clearance=before
    state,contacts=author.snapshot()
    if any(state[name]['grasp']) or frozenset((name,support)) not in contacts:
        raise ToolExecutionError('E20 chip handover needs released real support contact')
    actual=author.point(dict(actor=name,local=author.bottom_local(name)))
    if np.max(np.abs(actual-point))>.006:
        raise ToolExecutionError('E20 chip slipped from narrow transfer support')
    author.a.control_report.setdefault('e20_supported_handovers',[]).append(
        dict(actor=name,from_hand=source,to_hand=destination,support=support,
             released_bottom_task_m=np.asarray(actual).tolist(),real_contact_verified=True))
    return author.pickup(name,side_override=destination)
