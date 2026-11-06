"""Cooked-blade centering, protected straight contact entry, native pilot."""
import json
from pathlib import Path
import numpy as np


def run(p,ref,side,entry,axis,head, *, torque_degrees=5.):
    from .realworld_tool_expert import ToolExecutionError
    from .execution_design_e37_blade import Blade
    from .execution_design_e37_slot import run as pilot
    from .engineering_native_tick import diagnostic_tick_scope
    from .author_mplib_planner import capture_scene,plan_snapshot,_quat
    from .author_mplib_cartesian import run_screw_candidate
    a=p.a;c=p.c;actor=entry['driver']['actor'];tip=dict(actor=actor,local=entry['driver']['tip_local'])
    diagnostic=bool(getattr(c,'_engineering_diagnostic_only',False))
    if not (a.control_report.get('engineering_reference_only') is True
            and p.task=='E37' and p.spec['seed']==4201
            and p.spec['execution_design']['condition']=='R'
            and p.spec['execution_design']['revision']=='embodied50-execution-v3-20261102'
            and (diagnostic or getattr(a,'_engineering_e37_source_author',False)is True)):
        raise ValueError('Explicit E37 checkpoint motor seating required')
    axis=np.asarray(axis,float);axis/=np.linalg.norm(axis)
    a.carried_payload=(actor,side)
    # A shallow physical engagement is enough for the initial torque pilot.
    # The evaluator keeps the original groove, pitch and history criteria.
    depth=min(.0004,float(entry['socket_depth'])*.6)
    blade=Blade(p,entry,axis,head,depth)
    log=a.out/'E37-planned-slot-phases.private.jsonl'
    def record(value):
        with log.open('a')as stream:stream.write(json.dumps(value,default=lambda v:v.tolist())+'\n')
    def measure():return c.evaluator.screw_measure(entry)
    def guard():
        p.require_held(ref,side)
        table=p._e37_table_readback()
        if table['read_errors']:raise ToolExecutionError('E37 table force observation incomplete')
        hits={n:f for n,f in table['all_link_table_peak_force_n'].items()if f is not None and f>1.}
        if hits:raise ToolExecutionError('E37 real robot/table contact: '+str(hits))
    initial=blade.measurement();record(dict(phase='actual-cooked-entry-preflight',blade=initial))

    def move(phase,offset,contact=False,center=False):
        guard();state=p.snapshot()[0];body=state[actor]
        initial_hand=np.asarray(a.tcp_rotation_task(side));initial_body=np.asarray(body['mat'])
        hand_to_body=initial_hand.T@initial_body
        initial_tip=np.asarray(p.point(tip));delta=initial_tip-np.asarray(head())
        lateral=delta-axis*float(delta@axis)
        goal_tip=np.asarray(head())+lateral+axis*offset
        if center:goal_tip+=blade.centering_translation()
        goal_tcp=np.asarray(p.tip(side))+goal_tip-initial_tip
        request=dict(position=goal_tcp.tolist(),quaternion=_quat(initial_hand).tolist())
        existing_contact=(measure()['driver_force']>0
            or blade.physical_groove_measurement()['actual_source_blade_minimum_z_m']<0)
        if contact or existing_contact:request['allowed_contact_pairs']=[[actor,entry['screw']]]
        snapshot=capture_scene(a.scene,c,side,request)
        driver_shapes=[shape for shape in snapshot['shapes']if shape['actor']==actor]
        if len(driver_shapes)!=1:raise ToolExecutionError('Reviewed single driver collision root required')
        # The guarded planner contains the actual native cooked parts as well
        # as original source vertices, while keeping every collision root.
        driver_shapes[0]['vertices']=np.concatenate([
            np.asarray(driver_shapes[0]['vertices']),*blade.local]).tolist()
        driver_shapes[0]['proxy']='original_source_and_actual_native_cooked_convex_union_hull'
        profile=json.loads(Path(snapshot['profile']).read_text())
        p.stage('e37-official-straight-'+phase)
        proposed=run_screw_candidate(lambda:plan_snapshot(snapshot,profile),qpos_step=.002)
        if (proposed.get('status')!='Success'or proposed.get('verified')is not True)and not contact:
            # A Cartesian interpolation failure is not a physical collision
            # proof. In clear space the existing complete-world planner is
            # allowed to choose a different collision-verified joint path.
            straight_failure=proposed
            proposed=plan_snapshot(snapshot,profile)
            proposed.setdefault('diagnostics',{})['straight_candidate_failure']={
                'status':straight_failure.get('status'),
                'attempts':straight_failure.get('diagnostics',{}).get('attempts',[])}
        (a.out/('E37-'+phase+'-actual-snapshot.private.json')).write_text(json.dumps(snapshot,indent=2)+'\n')
        (a.out/('E37-'+phase+'-straight-plan.private.json')).write_text(json.dumps(proposed,default=lambda v:v.tolist(),indent=2)+'\n')
        if proposed.get('status')!='Success'or proposed.get('verified')is not True:
            raise ToolExecutionError('No verified straight real-blade '+phase+' path: '+str(proposed.get('status')))
        def path_guard():
            guard();actual=p.snapshot()[0][actor]
            expected=np.asarray(a.tcp_rotation_task(side))@hand_to_body
            error=np.degrees(np.arccos(np.clip((np.trace(expected@np.asarray(actual['mat']).T)-1)/2,-1,1)))
            # Record small contact compliance without requiring an extra
            # author precision threshold. Original socket alignment governs
            # whether a real torque attempt can begin.
            if error>20.:
                record(dict(phase=phase,real_tool_slip_degrees=float(error)))
                raise ToolExecutionError('Real blade slipped outside the certified rigid attachment')
        def seated_contact():
            return blade.physical_groove_measurement()['physical_tip_inside_original_groove']
        previous=getattr(a,'_engineering_e37_verified_path',False);a._engineering_e37_verified_path=True
        try:
            with diagnostic_tick_scope(a,reference_authorization=not diagnostic):
                receipt=a.execute_joint_path(side,proposed,guard=path_guard,
                    done=seated_contact if contact else None)
        finally:a._engineering_e37_verified_path=previous
        record(dict(phase=phase,native_motor_receipt=receipt,actual_blade=blade.measurement(),
            native_socket_measurement={k:v.item()if isinstance(v,np.generic)else v for k,v in measure().items()},
            stop_on_source_groove_entry=bool(contact),planned_slot_maximum_depth_m=depth))
        if contact and not seated_contact():raise ToolExecutionError('Actual blade never entered the original source groove')
    move('above-original-slot',.003,center=True)
    move('original-slot-contact',-depth,contact=True)
    return pilot(p,ref,side,entry,axis,head,torque_degrees=torque_degrees,already_seated=True,
        physical_socket=blade.physical_groove_measurement)
