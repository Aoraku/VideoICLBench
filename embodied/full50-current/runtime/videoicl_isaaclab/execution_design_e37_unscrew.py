"""Continuous real E37 turns with actual two-hand wrist resets."""
import json
import math
import numpy as np


def finish_role(p,ref,side,entry,axis,head):
    from .execution_design_e37_blade import Blade
    from .execution_design_e37_regrip import helical_turn,regrip,measured_turn_room,_scope,_plan,_execute,_hand
    from .realworld_tool_expert import ToolExecutionError
    _scope(p)
    a=p.a;c=p.c;axis=np.asarray(axis,float);axis/=np.linalg.norm(axis)
    blade=Blade(p,entry,axis,head,.0004)
    a.carried_payload=(ref['actor'],side)
    log=a.out/'E37-real-unscrew-progress.private.jsonl'
    def record(row):
        with log.open('a')as stream:stream.write(json.dumps(row,default=lambda x:x.tolist())+'\n')
    def measure():
        return {k:v.item()if isinstance(v,np.generic)else v for k,v in c.evaluator.screw_measure(entry).items()}
    def free():
        m=measure();return m['overlap']<=1e-6 and m['fixture_contact']==0
    def slot():return blade.physical_groove_measurement()['physical_tip_inside_original_groove']
    def reset_neighborhood():
        # Resetting the empty hand does not rotate the screw. The genuinely
        # supported tool may leave the groove and is reseated afterwards.
        tip=np.asarray(p.point(dict(actor=ref['actor'],local=entry['driver']['tip_local'])))
        reach=float(max(p.objects[entry['screw']]['size'][:2]))
        return bool(np.linalg.norm(tip-np.asarray(head()))<=reach and measure()['cos']>=.9)
    def table_guard():
        row=p._e37_table_readback()
        if row['read_errors']:raise ToolExecutionError('E37 native table-force readback incomplete')
        hits={k:v for k,v in row['all_link_table_peak_force_n'].items()if v is not None and v>1.}
        if hits:raise ToolExecutionError('E37 real robot/table contact: '+str(hits))
    def base_guard():
        p.require_held(ref,side);table_guard()
        if c.steps-p.start>=p.limit:raise ToolExecutionError('E37 bounded author-action budget exhausted')
    def working_region():
        return slot()or(reset_neighborhood()and measure()['driver_force']>0)
    def guard():
        base_guard()
        # Real head contact can continue while the semantic tip crosses a
        # millimetre bookkeeping boundary. Keep the original score exactly,
        # and judge this author continuation by physical tool/head contact.
        if not free()and not working_region():raise ToolExecutionError('E37 real tool left the source screw working region')
    baseline=measure();previous=baseline;angle=0.;stalled=0;resets=0
    resume_stage=getattr(a,'_engineering_resume_checkpoint',{}).get('context',{}).get('resume_regrip_stage')
    for index in range(600):
        base_guard()
        if free():break
        room=measured_turn_room(p,side,head(),axis,float(entry['pitch_m']),entry['unscrew_direction'])
        degrees=min(30.,math.degrees(.7*float(room['safe_angle_rad'])))
        if resume_stage=='main_release'or float(room['safe_angle_rad'])<math.radians(45.)or degrees<5.:
            p.stage('e37-held-driver-to-clearspace-reset')
            if resume_stage is None:
                from .realworld_tool_expert import _axis_rotation
                free_heading=_axis_rotation(axis,-math.pi/2)@_hand(p,side)
                proposal=_plan(p,side,[-.30,0.,1.20],free_heading,
                    driver=ref['actor'],screw=entry['screw'])
                _execute(p,side,proposal,base_guard)
            from .execution_design_thin_edge import table_bounds_task
            table_top=float(table_bounds_task(a.scene)['top'])
            local_material=np.concatenate(blade.local)
            def clear_space():
                body=p.snapshot()[0][ref['actor']]
                material=local_material@np.asarray(body['mat']).T+np.asarray(body['pos'])
                return bool(material[:,2].min()>table_top+.01)
            if not clear_space():raise ToolExecutionError('Held driver did not actually clear the original table')
            p.stage('e37-real-wrist-reserve-reset')
            checkpointing=getattr(a,'_engineering_stage_checkpoints',False)
            # The regrip contains explicit motor-hold overrides. They are
            # not public-action boundaries; defer that automatic capture,
            # while all real native ticks/actions/receipts remain recorded.
            a._engineering_stage_checkpoints=False
            try:
                regrip(p,ref,dict(actor=entry['driver']['actor'],local=entry['driver']['tip_local']),
                    axis,clear_space,main_side=side,screw=entry['screw'],
                    unscrew_direction=entry['unscrew_direction'],extra_guard=table_guard,resume_stage=resume_stage)
            finally:a._engineering_stage_checkpoints=checkpointing
            resume_stage=None
            if checkpointing:
                from .engineering_checkpoint import capture
                checkpoint=capture(c,'e37-real-regrip-completed',context=dict(
                    carried_payload=[ref['actor'],side],active_side=side,
                    diagnostic_only=bool(getattr(c,'_engineering_diagnostic_only',False))))
                folder=a.out/'checkpoints';folder.mkdir(exist_ok=True)
                (folder/('e37-regrip-%03d.private.json'%(resets+1))).write_text(json.dumps(checkpoint,indent=2)+'\n')
            resets+=1;p.require_held(ref,side);table_guard()
            from .execution_design_e37_planned_approach import run as approach
            p.stage('e37-real-return-to-original-screw-after-reset')
            approach(p,ref,side,entry,axis,head,slot_sign=-1,engage=False)
            from .execution_design_e37_planned_slot import run as reseat
            p.stage('e37-real-source-groove-reentry-after-reset')
            reseat(p,ref,side,entry,axis,head,torque_degrees=0.)
            guard()
            room=measured_turn_room(p,side,head(),axis,float(entry['pitch_m']),entry['unscrew_direction'])
            degrees=min(30.,math.degrees(.7*float(room['safe_angle_rad'])))
            if degrees<5.:raise ToolExecutionError('Real wrist reset did not regain useful original-limit reserve')
        elif not working_region():
            from .execution_design_e37_planned_slot import run as reseat
            p.stage('e37-real-source-groove-reentry')
            reseat(p,ref,side,entry,axis,head,torque_degrees=0.)
            guard()
            continue
        p.stage('e37-real-original-thread-turn-'+str(index))
        receipt=helical_turn(p,ref,head,axis,degrees,float(entry['pitch_m']),
            entry['unscrew_direction'],side=side,extra_guard=guard)
        now=measure();delta=(now['angle']-previous['angle']+math.pi)%(2*math.pi)-math.pi
        delta*=entry['unscrew_direction'];angle+=delta
        stalled=stalled+1 if delta<math.radians(.1)else 0
        row=dict(index=index,source_initial_episode=not bool(getattr(c,'_engineering_diagnostic_only',False)),
            diagnostic_only=bool(getattr(c,'_engineering_diagnostic_only',False)),
            requested_driver_degrees=degrees,actual_screw_increment_degrees=math.degrees(delta),
            actual_screw_total_degrees=math.degrees(angle),actual_axial_travel_m=now['axial']-baseline['axial'],
            native_measurement=now,native_thread_history_valid=bool(c.evaluator.thread_history_valid),
            original_pitch_m=entry['pitch_m'],physical_groove=blade.physical_groove_measurement(),
            wrist_resets=resets,native_motor_receipt=receipt)
        record(row);previous=now
        if stalled>=3:raise ToolExecutionError('Three real tool turns did not rotate the actual screw')
    if not free():raise ToolExecutionError('Original thread remains engaged after bounded real turns')
    result=dict(task='E37',role=entry['screw'],diagnostic_only=bool(getattr(c,'_engineering_diagnostic_only',False)),
        source_initial_episode=not bool(getattr(c,'_engineering_diagnostic_only',False)),
        segment='actual-original-thread-removal',segment_passed=True,
        actual_screw_total_degrees=math.degrees(angle),actual_axial_travel_m=measure()['axial']-baseline['axial'],
        native_thread_history_valid=bool(c.evaluator.thread_history_valid),native_task_acceptance=False,
        actual_original_thread_separated=True,wrist_resets=resets,actions=c.steps-p.start)
    (a.out/'E37-real-unscrew-result.private.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
