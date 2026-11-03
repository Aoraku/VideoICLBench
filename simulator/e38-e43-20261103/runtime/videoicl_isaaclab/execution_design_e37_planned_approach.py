"""Full-world verified private E37 head approach through native motor targets."""
import json
import math
import numpy as np


def run(policy,ref,side,entry,axis,head, *, slot_sign=1,engage=False):
    from .realworld_tool_expert import ToolExecutionError
    from .author_mplib_planner import plan,_quat
    from .engineering_native_tick import diagnostic_tick_scope
    from .engineering_robot_table_contacts import install
    a=policy.a
    diagnostic=bool(getattr(policy.c,'_engineering_diagnostic_only',False))
    source_author=getattr(a,'_engineering_e37_source_author',False)is True
    if not (a.control_report.get('engineering_reference_only') is True
            and policy.task=='E37' and policy.spec['seed']==4201
            and policy.spec['execution_design']['condition']=='R'
            and policy.spec['execution_design']['revision']=='embodied50-execution-v3-20261102'
            and (diagnostic or source_author)):
        raise ValueError('Explicit checkpoint E37 planning diagnostic required')
    if slot_sign not in (-1,1):raise ValueError('The original slot has two equivalent plane signs')
    driver=entry['driver'];actor=driver['actor'];tip=dict(actor=actor,local=driver['tip_local'])
    a.carried_payload=(actor,side)
    observer=install(a,stem='E37-planned-native-all-link-table')

    def guard():
        policy.require_held(ref,side)
        report=observer['snapshot']()
        if report['read_errors']:
            raise ToolExecutionError('E37 planned robot/table readback incomplete')
        hits={name:force for name,force in report['all_link_table_peak_force_n'].items()
              if force is not None and force>1.}
        if hits:
            report['unexpected_robot_table_contacts_n']=hits
            (a.out/'E37-planned-table-contact-stop.private.json').write_text(json.dumps(report,indent=2)+'\n')
            raise ToolExecutionError('E37 planned motion touched the real table: '+str(hits))

    def execute(phase,offset):
        guard();state=policy.snapshot()[0]
        current=np.asarray(state[actor]['mat'],float)
        actual_axis=np.asarray(axis,float);actual_axis/=np.linalg.norm(actual_axis)
        slot=np.asarray(state[entry['screw']]['mat'],float)@np.asarray(entry['radial_local'],float)
        slot-=actual_axis*float(slot@actual_axis);slot/=np.linalg.norm(slot)
        x=-actual_axis;z=slot_sign*slot;y=np.cross(z,x);y/=np.linalg.norm(y)
        desired=np.column_stack((x,y,np.cross(x,y)))
        delta=desired@current.T
        hand=np.asarray(a.tcp_rotation_task(side),float)
        target_rotation=delta@hand
        target=np.asarray(head(),float)+actual_axis*offset+delta@(
            np.asarray(policy.tip(side),float)-np.asarray(policy.point(tip),float))
        policy.stage('e37-verified-fullworld-'+phase)
        proposed=plan(a.scene,policy.c,side,target.tolist(),
                      task_tcp_quaternion=_quat(target_rotation).tolist())
        (a.out/('E37-fullworld-'+phase+'-plan.private.json')).write_text(
            json.dumps(proposed,default=lambda value:value.tolist(),indent=2)+'\n')
        if proposed.get('status')!='Success' or proposed.get('verified') is not True:
            raise ToolExecutionError('E37 full-world verified head path unavailable: '+str(proposed.get('status')))
        previous=getattr(a,'_engineering_e37_verified_path',False)
        a._engineering_e37_verified_path=True
        try:
            with diagnostic_tick_scope(a,reference_authorization=not diagnostic):
                receipt=a.execute_joint_path(side,proposed,guard=guard)
        finally:a._engineering_e37_verified_path=previous
        guard()
        actual=np.asarray(policy.point(tip),float)-np.asarray(head(),float)
        state=policy.snapshot()[0];current=np.asarray(state[actor]['mat'],float)
        shaft=current@np.asarray(driver['axis_local'],float);shaft/=np.linalg.norm(shaft)
        axis_error=math.degrees(math.acos(float(np.clip(shaft@(-actual_axis),-1,1))))
        plane_error=math.degrees(math.acos(float(np.clip(abs(slot@current[:,2]),-1,1))))
        error=float(np.linalg.norm(actual-actual_axis*offset))
        report=dict(phase=phase,side=side,slot_sign=slot_sign,
            actual_tip_minus_head_m=actual.tolist(),tip_error_m=error,
            actual_axis_error_degrees=axis_error,actual_slot_plane_error_degrees=plane_error,
            native_motor_receipt=receipt,diagnostic_only=diagnostic,native_task_acceptance=False)
        (a.out/('E37-fullworld-'+phase+'-actual.private.json')).write_text(
            json.dumps(report,default=lambda value:value.tolist(),indent=2)+'\n')
        if error>(.0005 if phase=='slot'else .003) or max(axis_error,plane_error)>.5:
            raise ToolExecutionError('E37 physically tracked tool missed unchanged head/slot tolerance')
        return report

    try:
        reports=[execute('above-head',.03)]
        if engage:reports.append(execute('slot',-min(.002,float(entry['socket_depth'])*.6)))
        return dict(task='E37',variant=policy.variant,diagnostic_only=diagnostic,
            source_initial_episode=not diagnostic,native_task_acceptance=False,
            segment='verified-native-motor-head-approach',segment_finished=True,
            segment_passed=True,phases=reports,actions=policy.c.steps-policy.start)
    finally:observer['close']()
