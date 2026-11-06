"""Legacy real-load diagnostic: clear the empty hand, then lift and carry.

Source pose/q are explicitly approximate legacy reconstruction. This checks
real actuator/contact feasibility only; no native scoop history is supplied.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


from .execution_design_e28_contact_guard import support_geometry as supported_footprint,ensure_contact


def run(policy,tool,grip,side,food,context=None):
    context=dict(context or {})
    other='left'if side=='right'else'right';actor=tool['actor'];start=np.asarray(context.get('original_food_task',policy.snapshot()[0][food]['pos']),float).copy()
    obj=next(o for o in policy.spec['objects']if o['id']==food)
    def bottom():
        b=policy.snapshot()[0][food]
        return float(b['pos'][2]-(np.abs(b['mat'])@np.asarray(obj['size']))[2])
    initial_bottom=float(context.get('original_food_bottom_task',bottom()))
    (policy.a.out/'E28-loaded-author-goals.private.json').write_text(json.dumps(dict(
        source_steps=policy.c.steps,initial_food_task=start.tolist(),initial_food_bottom=initial_bottom,
        empty_hand_retreat_height_task=context.get('empty_hand_retreat_height_task'),
        loaded_lift_work_target_task=context.get('loaded_lift_work_target_task'),
        resumed_carry=context.get('legacy_resume_carry')is True,
        native_acceptance_or_evaluator_history_restored=False),indent=2)+'\n')
    from .execution_design_robot_contact_readback import install
    probe=install(policy.a,('table',actor,food),stem='E28-loaded-all-link-contacts',max_samples=3500)
    if context.get('record_native_contact_points')is True:
        from .execution_design_e28_contact_points import install as install_points
        install_points(policy,food,tool)
    def guard():
        policy.require_held(grip,side);body=policy.snapshot()[0][food]
        if any(body['grasp'])or any(policy.contact(food,f'{hand}_finger{i}')for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('Legacy blade load touched a robot hand')
        ensure_contact(policy,food,tool,lambda:policy.require_held(grip,side))
        body=policy.snapshot()[0][food]
        supported,local,gap=supported_footprint(policy,tool,food)
        if not supported:raise ToolExecutionError('Legacy food lost actual supported footprint')
        if probe['samples'][0]:
            report=json.loads((policy.a.out/'E28-loaded-all-link-contacts.private.json').read_text())
            if report['read_errors']:raise ToolExecutionError('Legacy loaded native robot-contact readback incomplete')
            contact={key:force for key,force in report['peak_force_n'].items()if key.endswith('|'+food)and force>.02}
            if contact:raise ToolExecutionError('Legacy loaded path touched a robot link: '+str(contact))
        with(policy.a.out/'E28-loaded-clearance-lift-carry.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(actions=policy.c.steps,stage=policy.a.stage,
                food_task=np.asarray(body['pos']).tolist(),food_center_tool_local=local.tolist(),
                blade_plane_gap_m=gap,actual_tool_food_contact=True,actual_food_grasp=body['grasp'],
                food_finger_contact=False,actual_supported_footprint=True,
                table_contact=policy.contact(food,'table'),robot_contact_samples=probe['samples'][0]))+'\n')
    guard()
    work=dict(actor=actor,local=tool['working_local'])
    if context.get('legacy_resume_carry')is not True:
        # The old hand was already detached, but its low fingertips hovered above
        # the food and blocked the later lift. Move it sideways before any UP.
        policy.stage('e28-legacy-loaded-empty-hand-clear-column')
        policy._e28_backstop_park=policy.tip(other).copy()
        direction=np.asarray(policy.snapshot()[0][actor]['mat'])[:,0].copy();direction[2]=0.;direction/=np.linalg.norm(direction)
        from .execution_design_e28_proven_entry import withdraw
        from .execution_design_e28_backstop import clear_loaded_column
        try:clear_loaded_column(policy,food,other)
        except ToolExecutionError:
            withdraw(policy,food,other,direction,guard)
        else:
            # This exact resumed state may already have completed the lateral
            # part. Do not reset a relative100mm goal and repeat the same retreat.
            policy.stage('e28-resumed-empty-hand-already-outside-column')
            target=policy.tip(other).copy();target[2]=float(context.get('empty_hand_retreat_height_task',target[2]+.04))
            if not np.isfinite(target[2]):raise ValueError('Finite original empty-hand retreat goal required')
            if target[2]>policy.tip(other)[2]+.002:policy.move(other,target,guard)
        state=policy.snapshot()[0];body=state[food];half=np.abs(body['mat'])@np.asarray(obj['size'])
        lo=np.asarray(body['pos'])-half;hi=np.asarray(body['pos'])+half
        for finger in policy.a.finger_geometry(other)['fingers']:
            low=np.asarray(finger['aabb_min_task_m']);high=np.asarray(finger['aabb_max_task_m'])
            if np.all(high[:2]>=lo[:2]-.010)and np.all(low[:2]<=hi[:2]+.010):
                raise ToolExecutionError('Legacy empty finger remains in loaded vertical column')
        policy.stage('e28-legacy-hand-free-lift60mm')
        lift_target=np.asarray(context.get('loaded_lift_work_target_task',policy.point(work)+[0.,0.,.060]),float)
        if lift_target.shape!=(3,)or not np.isfinite(lift_target).all():raise ValueError('Finite original material lift goal required')
        goal_path=policy.a.out/'E28-loaded-author-goals.private.json';goals=json.loads(goal_path.read_text());goals['loaded_lift_work_target_task']=lift_target.tolist();goal_path.write_text(json.dumps(goals,indent=2)+'\n')
        policy.move_point(side,work,lift_target,guard,tolerance=.0015);guard()
    else:
        from .execution_design_e28_backstop import clear_loaded_column
        clear_loaded_column(policy,food,other)
    if policy.contact(food,'table')or bottom()-initial_bottom<.006:
        raise ToolExecutionError('Legacy reconstructed load did not physically produce native6mm independent lift')
    lifted=bottom()-initial_bottom
    policy.stage('e28-legacy-hand-free-carry-to-plate')
    dest=policy.destination(food,0);high=max(float(dest[2])+.08,.92)
    policy.move_point(side,work,[*policy.point(work)[:2],high],guard)
    policy.move_point(side,work,[*dest[:2],high],guard);guard()
    carried=np.asarray(policy.snapshot()[0][food]['pos']);distance=float(np.linalg.norm(carried[:2]-start[:2]))
    container=policy.s['containers']['plate'];floor_axis=int(container.get('floor_axis',2))
    def in_plate():
        state=policy.snapshot()[0];body=state[food];plate=state[container['object']]
        local=np.asarray(plate['mat']).T@(np.asarray(body['pos'])-plate['pos'])
        radius=np.abs(np.asarray(plate['mat']).T@np.asarray(body['mat']))@np.asarray(obj['size'])
        lo=np.asarray(container['lower']);hi=np.asarray(container['upper']);axes=[i for i in range(3)if i!=floor_axis]
        return bool(np.all((local-radius)[axes]>=lo[axes]-.001)and np.all((local+radius)[axes]<=hi[axes]+.001))
    def plate_handoff_guard():
        policy.require_held(grip,side);body=policy.snapshot()[0][food]
        if any(body['grasp'])or any(policy.contact(food,f'{hand}_finger{i}')for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('Legacy offload touched a robot hand')
        if policy.contact(food,actor):guard()
        elif not(policy.contact(food,container['object'])and in_plate()):
            raise ToolExecutionError('Legacy offload lost support before actual plate handoff')
    policy.stage('e28-legacy-actual-plate-handoff')
    policy.move_point(side,work,np.asarray(dest)+[0.,0.,.003],plate_handoff_guard)
    policy.stage('e28-legacy-withdraw-blade-release')
    withdraw=np.asarray(policy.frame(work)[1])@np.asarray(tool['withdraw_local'])
    policy.move_point(side,work,policy.point(work)+withdraw*.10,plate_handoff_guard)
    policy.wait(3);policy.move(side,policy.tip(side)+[0.,0.,.07],lambda:policy.require_held(grip,side))
    body=policy.snapshot()[0][food];plate=policy.snapshot()[0][container['object']]
    if any(body['grasp'])or policy.contact(food,actor)or not policy.contact(food,container['object'])or not in_plate():
        raise ToolExecutionError('Legacy offload did not leave a real released plate-supported food')
    final=np.asarray(body['pos']);error=float(np.linalg.norm(final[:2]-np.asarray(plate['pos'])[:2]))
    result=dict(diagnostic_only=True,source_initial_episode=False,native_task_acceptance=False,
        segment='legacy-v11-supported-footprint-clear-lift-carry-offload',segment_passed=True,segment_finished=True,
        actual_food_lift_m=lifted,actual_food_xy_transport_m=distance,actual_plate_xy_error_m=error,
        actual_food_hand_contact=False,actual_supported_footprint=True,actual_food_released_from_blade=True,
        actual_food_plate_contact=True,actual_full_food_footprint_in_plate=True,actions=policy.c.steps-policy.start)
    (policy.a.out/'E28-loaded-tail-result.private.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
