"""Continue an actual held drawer to its unchanged 95mm engineering target."""
import numpy as np
from .realworld_mechanism_expert import MechanismExecutionError
from .execution_design_e18_regrasp import REFERENCE_AXIAL_M,release_reseat


def prepare(worker,role,side):
    before=worker._public_pull_observation(role,side,0);worker._require_public_pull_grip(before,side)
    start=worker.c.steps;reseat=None
    def issue(token,mm=1.):
        if worker.c.steps-start>=4:raise MechanismExecutionError('E18 one real pad reseat exhausted four public actions')
        worker.act(side,token,mm=mm)
        feedback=worker.c.action_feedback().get('control_feedback',{}).get(side,{})
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
            raise MechanismExecutionError('E18 real pad reseat public controller refused')
    if before['tcp_axial_offset_m']-REFERENCE_AXIAL_M>.0005:
        reseat=release_reseat(worker,side,issue)
    follow=worker.follow_drawer_pad_z_once(role,side)
    after=worker._public_pull_observation(role,side,7);worker._require_public_pull_grip(after,side)
    return dict(before=before,reseat=reseat,z_follow=follow,after=after,
                actual_public_preparation_actions=worker.c.steps-start)


def run(worker,parameters):
    a=worker.a;spec=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{})
    if (parameters!={}or spec.get('variant')!='A'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('condition')!='I'
            or cp.get('diagnostic_only')is not True
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(4,402)
            or not getattr(worker.c,'_engineering_diagnostic_only',False)
            or not getattr(worker.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted E18 A/I4201 actual held native4/402 opening boundary required')
    role='drawer';side='left';target=worker.motion[role]['open_distance']
    tolerance=min(.001,target-worker.roles[role]['open_threshold'])
    start=worker.c.steps;initial=worker.displacement(role);history=[];pulls=[]
    worker.stage('local-E18-continue-original95mm-open-from-held4')
    for _ in range(80):
        current=worker.displacement(role)
        if abs(target-current)<=tolerance:break
        if worker.c.steps-start>=600:raise MechanismExecutionError('E18 continuous opening exhausted bounded public actions')
        prep=prepare(worker,role,side);current=worker.displacement(role)
        if abs(target-current)<=tolerance:break
        direction=worker.axis(role)*(1 if target>current else-1);axis=int(np.argmax(np.abs(direction)))
        if abs(direction[axis])<.95:raise MechanismExecutionError('Original E18 drawer axis is not public-translation aligned')
        amount=min(.002,max(.0005,abs(target-current)))
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(direction[axis]<0)]
        worker.act(side,token,mm=amount*1000.)
        after=worker.record_drawer_public_pull(role,side);worker._require_public_pull_grip(after,side)
        actual=worker.displacement(role);history.append(actual)
        pulls.append(dict(preparation=prep,requested_mm=amount*1000.,readback=after,
            displacement_before_m=current,displacement_after_m=actual,actual_increase_m=actual-current))
        if len(history)>=8 and max(history[-8:])-min(history[-8:])<.0002:
            raise MechanismExecutionError('Drawer joint stalled despite handle contact: '+role)
    else:raise MechanismExecutionError('Drawer did not reach measured target: '+role)
    final=worker.displacement(role)
    if abs(final-target)>tolerance:raise MechanismExecutionError('Original E18 full opening target/tolerance not reached')
    return dict(local_completed=True,actions=worker.c.steps-start,operations=worker.operations,pulls=pulls,
        measured_initial_drawer_m=initial,measured_final_drawer_m=final,
        original_full_open_target_m=target,original_open_tolerance_m=tolerance,
        full_drawer_open_completed=True,balls_or_full_task_completed=False)
