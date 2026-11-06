"""Short real E37 slot seating and original-pitch torque pilot."""
import json
import math
import numpy as np


def run(policy,ref,side,entry,axis,head, *, torque_degrees=5.,already_seated=False,physical_socket=None):
    from .realworld_tool_expert import ToolExecutionError
    from .execution_design_e37_handoff import move_tip
    from .engineering_checkpoint import capture
    from .execution_design_jacobian_reference import capture as capture_jacobian
    from .execution_design_e37_regrip import helical_turn
    a=policy.a;c=policy.c
    diagnostic=bool(getattr(c,'_engineering_diagnostic_only',False))
    if not (a.control_report.get('engineering_reference_only') is True
            and policy.task=='E37' and policy.spec['seed']==4201
            and policy.spec.get('execution_design',{}).get('condition')=='R'
            and policy.spec['execution_design'].get('revision')=='embodied50-execution-v3-20261102'
            and (diagnostic or getattr(a,'_engineering_e37_source_author',False)is True)):
        raise ValueError('Explicit E37 checkpoint seating diagnostic required')
    if not 0.<=float(torque_degrees)<=10.:
        raise ValueError('Initial physical screw pilot is bounded to ten degrees')
    tip=dict(actor=entry['driver']['actor'],local=entry['driver']['tip_local'])
    axis=np.asarray(axis,float);axis/=np.linalg.norm(axis)
    read_table=getattr(policy,'_e37_table_readback',None)
    if not callable(read_table):raise ValueError('Whole-robot native table observation required')
    def measure():
        return {name:value.item()if isinstance(value,np.generic)else value
                for name,value in c.evaluator.screw_measure(entry).items()}
    def guard():
        policy.require_held(ref,side)
        table=read_table()
        if table['read_errors']:raise ToolExecutionError('E37 slot table-force readback incomplete')
        hits={name:force for name,force in table['all_link_table_peak_force_n'].items()
              if force is not None and force>1.}
        if hits:raise ToolExecutionError('E37 real slot motion touched table: '+str(hits))
    def seated():
        if physical_socket is not None:
            return physical_socket()['physical_tip_inside_original_groove']
        m=measure()
        # Reuse the unchanged native socket geometry: its depth is already
        # gated by the source radial clearance, depth and actual part poses.
        return m['depth']>0. and m['cos']>=.9 and m['aligned']
    def turn_guard():
        guard()
        if not seated():raise ToolExecutionError('Real driver left the original socket')
    def save_checkpoint(stage):
        cp=capture(c,stage,context=dict(carried_payload=[tip['actor'],side],
            active_side=side,role='left'if entry['screw'].endswith('left')else'right'))
        p=a.out/'checkpoints'/(stage+'.private.json');p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(cp,indent=2)+'\n')
        return dict(path=str(p),source=cp['source'],checkpoint_sha256=cp['checkpoint_sha256'])

    guard()
    if not already_seated:
        policy.stage('e37-original-slot-horizontal-alignment')
        target=np.asarray(policy.point(tip),float);target[:2]=np.asarray(head(),float)[:2]
        move_tip(policy,side,tip,target,guard,tolerance=.0005)
        policy.stage('e37-original-slot-depth')
        target=np.asarray(head(),float)-axis*min(.002,float(entry['socket_depth'])*.6)
        move_tip(policy,side,tip,target,guard,tolerance=.0005)
    turn_guard();policy.stage('e37-original-slot-seated')
    checkpoint=save_checkpoint('e37-original-slot-seated')
    before=measure();before_jacobian=capture_jacobian(a,c,side)
    observations=dict(samples=0,engaged_driver_contact_samples=0,peak_driver_contact_force_n=0.)
    def observe(controller,render):
        m=measure();observations['samples']+=1
        observations['peak_driver_contact_force_n']=max(observations['peak_driver_contact_force_n'],float(m['driver_force']))
        if m['driver_force']>0 and seated() and m['cos']>=.9:
            observations['engaged_driver_contact_samples']+=1
    report=dict(task='E37',variant=policy.variant,diagnostic_only=diagnostic,
        source_initial_episode=not diagnostic,native_task_acceptance=False,
        insertion_skipped_for_existing_seating=bool(already_seated),
        already_seated_by_actual_native_contact=bool(already_seated and before['depth']>0 and before['driver_force']>0),
        original_socket_seated=bool(before['depth']>0 and before['cos']>=.9),
        physical_source_groove_measurement=physical_socket()if physical_socket is not None else None,
        engagement_observation_basis='source_original_rectangular_groove'if physical_socket is not None else'native_circular_tip_grade',
        seated_native_measurement=before,
        seated_checkpoint=checkpoint,seated_native_jacobian=before_jacobian,
        original_pitch_m=entry['pitch_m'],requested_turn_degrees=float(torque_degrees))
    path=a.out/'E37-original-slot-torque-pilot.private.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    if torque_degrees:
        policy.stage('e37-original-short-helical-pilot');c.tick_hooks.append(observe)
        try:
            receipt=helical_turn(policy,ref,head,axis,float(torque_degrees),
                float(entry['pitch_m']),entry['unscrew_direction'],side=side,extra_guard=turn_guard)
        finally:
            c.tick_hooks.remove(observe)
            after=measure();angle=(after['angle']-before['angle']+math.pi)%(2*math.pi)-math.pi
            angle*=entry['unscrew_direction'];travel=after['axial']-before['axial']
            report.update(after_native_measurement=after,actual_screw_turn_degrees=math.degrees(angle),
                actual_screw_axial_travel_m=travel,
                original_pitch_coupling_error_m=abs(travel-angle*entry['pitch_m']/(2*math.pi)),
                native_thread_history_valid=bool(c.evaluator.thread_history_valid),
                real_driver_contact_observations=observations,
                physical_motion_claim_uses_native_screw_not_requested_driver_rotation=True)
            path.write_text(json.dumps(report,indent=2)+'\n')
        report['native_motor_receipt']=receipt
        if (observations['engaged_driver_contact_samples']==0 or angle<=math.radians(.1)
                or travel<=0 or not c.evaluator.thread_history_valid):
            path.write_text(json.dumps(report,indent=2)+'\n')
            raise ToolExecutionError('Short pilot has no confirmed original-pitch screw motion')
    report.update(segment='original-slot-and-short-native-torque',segment_finished=True,
        segment_passed=True,actions=c.steps-policy.start)
    path.write_text(json.dumps(report,indent=2)+'\n')
    return report
