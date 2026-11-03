"""Single-source E43 rail hold then real hand-pull diagnostic, no model/API."""
import json
import os
import numpy as np
from .engineering_checkpoint import capture
from .execution_design_e43_rail import validated_settings,native_readback_matches
from .realworld_tool_expert import ToolExecutionError


def _idle_source_ticks(policy,count,guard=None):
    c=policy.c;pool=getattr(c,'_room_pool',None)
    controllers=getattr(pool,'controllers',{})
    if (type(count)is not int or not 1<=count<=250 or policy.task!='E43'
            or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or os.environ.get('VIC_ENGINEERING_E43_RAIL_AUDIT')!='1'
            or not policy.a.control_report.get('engineering_reference_only')
            or len(controllers)!=1 or next(iter(controllers.values()),None)is not c
            or getattr(pool,'terminal',{}) or c.steps!=0
            or getattr(c,'_engineering_action_in_flight',False)
            or getattr(c,'_public_action_in_flight',False)
            or getattr(policy.a,'_engineering_failure_latched',False)):
        raise ToolExecutionError('Idle single-source E43 rail audit required')
    before=c.physics_ticks;shared=pool.physics_ticks
    for _ in range(count):
        if guard:guard()
        pool.tick()
        if c.steps!=0:raise ToolExecutionError('Passive source rail audit issued an action')
        if guard:guard()
    return dict(public_actions_issued=0,native_ticks=c.physics_ticks-before,shared_ticks=pool.physics_ticks-shared)


def solve(policy):
    import omni.usd
    from pxr import UsdPhysics
    from .execution_design_e43_trigger import select_gate_hand_frame
    spec=policy.spec;joints=spec.get('joints',[])
    index=next(i for i,j in enumerate(joints)if j.get('child')=='gate')
    record=joints[index];settings=validated_settings(spec,record)
    path=policy.a.scene.root_path+'/Constraints/joint'+str(index)
    drive=UsdPhysics.DriveAPI(omni.usd.get_context().get_stage().GetPrimAtPath(path),'linear')
    values=dict(stiffness_n_per_m=drive.GetStiffnessAttr().Get(),
        target_velocity_m_s=drive.GetTargetVelocityAttr().Get(),damping_n_s_per_m=drive.GetDampingAttr().Get(),
        maximum_resistance_n=drive.GetMaxForceAttr().Get(),
        position_target_authored=drive.GetTargetPositionAttr().HasAuthoredValueOpinion())
    (policy.a.out/'source-passive-rail-drive-readback.private.json').write_text(json.dumps(values,indent=2)+'\n')
    if not native_readback_matches(values):
        raise ToolExecutionError('Actual source rail drive is not the reviewed passive resistance')
    policy.stage('source-passive-gate-rail-hold')
    state,_=policy.snapshot();start=state['gate']['pos'].copy();rows=[]
    def log():
        state,contacts=policy.snapshot()
        row=dict(actions=policy.c.steps,native_physics_tick=policy.c.physics_ticks,
            gate_position=state['gate']['pos'].tolist(),ball_position=state['ball']['pos'].tolist(),
            gate_drift_m=float(np.linalg.norm(state['gate']['pos']-start)),
            ball_launcher_contact=policy.contact('ball','launcher'),
            ball_gate_contact=policy.contact('ball','gate'),
            actual_contact_forces_n=[dict(bodies=sorted(pair),force_n=float(force))
                for pair,force in policy.c.contact_forces.items()if 'ball'in pair or'gate'in pair])
        if any(any('finger'in body for body in pair)and ('ball'in pair or'gate'in pair)for pair in contacts):
            raise ToolExecutionError('No-hand source rail audit has hand contact')
        rows.append(row)
        with(policy.a.out/'source-passive-rail-hold.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        if row['gate_drift_m']>.005 or not row['ball_launcher_contact']:
            raise ToolExecutionError('Passive source gate failed to retain the ball during preparation')
    def hold_guard():
        state,contacts=policy.snapshot()
        if (np.linalg.norm(state['gate']['pos']-start)>.005
                or not policy.contact('ball','launcher')
                or any(any('finger'in body for body in pair)and ('ball'in pair or'gate'in pair)for pair in contacts)):
            raise ToolExecutionError('Passive source gate first failed native retention/contact check')
    log()
    for _ in range(24):_idle_source_ticks(policy,250,hold_guard);log()
    checkpoint=capture(policy.c,'e43-after-source-rail-hold',dict(rail_audit=True))
    (policy.a.out/'source-after-rail-hold.checkpoint.private.json').write_text(json.dumps(checkpoint))
    gate=next(o for o in spec['objects']if o['id']=='gate')
    ref=dict(actor='gate',local=[0.,0.,gate['size'][2]-.005],jaw_axis_local=[1.,0.,0.])
    direction=np.asarray(policy.s['launcher']['trigger']['press_direction_task'],float);direction/=np.linalg.norm(direction)
    side='left';select_gate_hand_frame(policy,ref,side,direction)
    policy.stage('source-rail-real-upper-grasp');policy.acquire(ref,side)
    policy.require_held(ref,side);before=policy.snapshot()[0]['gate']['pos'].copy()
    def guard():
        policy.require_held(ref,side)
        if any(policy.contact('ball',f'{s}_finger{i}')for s in('left','right')for i in(1,2)):
            raise ToolExecutionError('Source rail pull hand touched the ball')
    policy.stage('source-rail-real-pull');policy.move(side,policy.tip(side)+direction*.065,guard,tolerance=.003)
    travel=float((policy.snapshot()[0]['gate']['pos']-before)@direction)
    if travel<.055:raise ToolExecutionError('Passive rail prevented actual hand gate withdrawal')
    policy.stage('source-rail-release-and-retreat');policy.act(side,'RELEASE');policy.move(side,policy.tip(side)+[0,0,.08])
    result=dict(schema='e43-source-passive-rail-diagnostic-v1',diagnostic_only=True,
        source_initial_full_positive=False,whole_task_success=False,
        passive_hold_native_ticks=6000,passive_hold_public_actions=0,
        maximum_observed_hold_drift_m=max(r['gate_drift_m']for r in rows),
        actual_drive_readback=values,actual_hand_pull_travel_m=travel,
        diagnostic_passed=True,viscous_approximation_not_static_lock=True)
    (policy.a.out/'source-passive-rail-result.private.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
