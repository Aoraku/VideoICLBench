"""An isolated engineering motor hold with real native contact readback.

This is a separate private primitive, never a shortened GUI action. The prior
public receipt must already be complete. Only actuator goals are rebased;
robot/object state, contacts and evaluator history are never assigned.
"""
import json
from .realworld_tool_expert import ToolExecutionError
from .engineering_native_tick import diagnostic_tick_scope
from .recording_trajectory import frame_due


def _last_receipt(path):
    if not path.exists():return None
    with path.open('rb')as stream:
        stream.seek(max(0,path.stat().st_size-100000));lines=stream.read().decode().splitlines()
    for line in reversed(lines):
        try:return json.loads(line)
        except ValueError:continue
    return None


def hold(policy,food,tool,base_guard,measure,maximum_ticks=10):
    from .execution_design_e28_source import _scope
    _scope(policy)
    a=policy.a;c=policy.c;pool=getattr(c,'_room_pool',None)
    if getattr(a,'_engineering_e28_contact_hold',False)is not True:
        raise ValueError('Explicit E28 engineering native-contact hold opt-in required')
    if maximum_ticks!=10:raise ValueError('Only the reviewed ten-tick maximum is admitted')
    if c.steps-policy.start>=policy.limit:raise ToolExecutionError('E28 author action budget exhausted before native hold')
    receipt_path=a.out/'demo-actions.private.jsonl';last=_last_receipt(receipt_path)
    if last is None or last.get('step_after')!=c.steps:
        raise ValueError('Native contact hold requires the last completed action receipt')
    clock=pool.physics_ticks if pool is not None else c.physics_ticks
    if last.get('shared_tick_after',last.get('physics_tick_after'))!=clock:
        raise ValueError('Native contact hold requires the completed receipt physics clock')
    if last.get('control')=='private_native_contact_hold':
        raise ValueError('At most one contact hold per completed non-hold action')
    before=c.steps;tick_before=c.physics_ticks;shared_before=clock;time_before=float(c.sim.current_time)
    previous_public=getattr(c,'_public_action',None);old_stage=a.stage;samples=[];recovered=False;error=None;intent_cleared=False;targets_rebased=False
    from .engineering_checkpoint import capture
    directory=a.out/'checkpoints';directory.mkdir(exist_ok=True)
    (directory/f'native-contact-hold-before-action-{before:04d}.private.json').write_text(json.dumps(capture(c,'before-native-contact-hold'),indent=2)+'\n')
    try:
        # Admission occurs before changing any command intent. The bridge keeps
        # the room attached and uses its original write/step/read/hook path.
        with diagnostic_tick_scope(a,reference_authorization=True):
            c._public_action=None;intent_cleared=True
            c.targets={side:tuple(value.clone()for value in c.pose(side))for side in c.scene.robots};targets_rebased=True
            a.stage='e28-private-native-contact-readback-hold'
            for _ in range(maximum_ticks):
                base_guard()
                next_tick=pool.physics_ticks+1 if pool is not None else c.physics_ticks+1
                c.tick(render=frame_due(next_tick,c.dt,c.scene.embodiment.config['physics']['render_hz']))
                base_guard();state=measure();valid=bool(state['supported']and abs(state['plane_gap_m'])<=.001
                    and not state['hand_contact']and not state['table_contact'])
                samples.append(dict(physics_tick=c.physics_ticks,actual_contact=state['actual_blade_contact'],
                    actual_native_contact_force_n=c.contact_forces.get(frozenset((food,tool['actor']))),
                    native_supported_footprint=state['supported'],plane_gap_m=state['plane_gap_m'],
                    food_tool_local=state['local'].tolist(),hand_contact=state['hand_contact'],table_contact=state['table_contact']))
                if not valid:raise ToolExecutionError('E28 native contact hold lost original physical support geometry')
                if state['actual_blade_contact']:
                    recovered=True;break
    except Exception as exc:
        error=exc
    finally:
        executed=c.physics_ticks-tick_before
        if executed:c.steps+=1
        a.stage=old_stage
        row=dict(stage='e28-private-native-contact-readback-hold',control='private_native_contact_hold',
            is_gui_action=False,step_before=before,step_after=c.steps,physics_tick_before=tick_before,
            physics_tick_after=c.physics_ticks,shared_tick_before=shared_before,
            shared_tick_after=pool.physics_ticks if pool is not None else c.physics_ticks,
            physics_ticks=executed,maximum_native_ticks=maximum_ticks,simulation_seconds=float(c.sim.current_time)-time_before,
            previous_completed_public_intent=previous_public,public_intent_cleared=intent_cleared,
            measured_tcp_motor_targets=targets_rebased,robot_or_object_states_written=False,contact_or_history_written=False,
            actual_contact_recovered=recovered,tick_samples=samples,error=None if error is None else repr(error))
        with receipt_path.open('a')as stream:stream.write(json.dumps(row)+'\n')
        with(a.out/'E28-native-contact-holds.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        (directory/f'native-contact-hold-after-action-{c.steps:04d}.private.json').write_text(json.dumps(capture(c,'after-native-contact-hold'),indent=2)+'\n')
    if error is not None:raise error
    if not recovered:raise ToolExecutionError('E28 native contact did not recover within ten real hold ticks')
    return dict(actual_contact=True,recovered=True,private_primitive='native_contact_hold',
        private_actions=c.steps-before,physics_ticks=c.physics_ticks-tick_before)
