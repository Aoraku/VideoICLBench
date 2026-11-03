"""One real release/inward regrasp after measured handle-pad slip."""
import numpy as np
from .realworld_mechanism_expert import MechanismExecutionError


REFERENCE_AXIAL_M=.007781968128777326


def _closing(row):
    return (not row['bilateral_contact']and min(row['finger_q_m'])>.003
            and max(row.get('finger_qd_m_s',[0.,0.]))<-.001)


def _two_pulls(worker,side,start,issue):
    pulls=[]
    for index in range(2):
        worker.stage('local-E18-regrasp-Zfollow-two-mm-pull-'+str(index+1))
        if worker.c.steps-start>=8:raise MechanismExecutionError('E18 bounded regrasp has no remaining public action')
        follow=worker.follow_drawer_pad_z_once('drawer',side)
        initial=worker.displacement('drawer');issue('BACK',mm=2.)
        after=worker.record_drawer_public_pull('drawer',side);worker._require_public_pull_grip(after,side)
        increase=float(worker.displacement('drawer')-initial)
        if increase<.0005:raise MechanismExecutionError('E18 regrasp short pull increased drawer less than0.5mm')
        pulls.append(dict(index=index+1,z_follow=follow,readback=after,displacement_increase_m=increase))
    return pulls


def _hand_clearance(worker,side,*,released=False,movement=None):
    from .execution_design_e18_geometry import actual_hand_clouds
    geometry=actual_hand_clouds(worker.a,side)
    if geometry.get('source')!='actual_native_collision_mesh_current_body_pose' or len(geometry['clouds_tcp'])!=3:
        raise MechanismExecutionError('Native complete E18 hand geometry required for regrasp')
    clouds=[np.asarray(v,float).copy()for v in geometry['clouds_tcp']]
    if released:
        robot=worker.a.scene.robots[side];ids,_=robot.find_joints('panda_finger_joint[1-2]')
        value=robot.data.joint_pos
        if hasattr(value,'detach'):value=value.detach()
        if hasattr(value,'cpu'):value=value.cpu()
        q=np.asarray(value,float)[0,ids];jaw=np.asarray(geometry['jaw_axis_tcp'])
        for i,sign in ((0,1),(1,-1)):clouds[i]+=sign*(.04-float(q[i]))*jaw
    rotation=np.asarray(worker.a.tcp_rotation_task(side));tip=worker.tip(side)
    delta=np.zeros(3)if movement is None else np.asarray(movement,float)
    world=[v@rotation.T+tip+delta for v in clouds]
    floor=min(float(v[:,2].min()-geometry['table_top'])for v in world)
    palm=float(np.min((world[2]-worker.point('drawer'))@worker.axis('drawer')))
    if floor<=.002 or palm<=.003:
        raise MechanismExecutionError('E18 real release/regrasp violates original hand/table or palm/handle clearance')
    return dict(hand_table_clearance_m=floor,palm_handle_clearance_m=palm,predicted_release=bool(released))


def release_reseat(worker,side,issue):
    opening_clearance=_hand_clearance(worker,side,released=True)
    worker.stage('local-E18-one-real-release-inward-regrasp')
    issue('RELEASE');released=worker._public_pull_observation('drawer',side,5)
    if min(released['finger_q_m'])<=.003:
        raise MechanismExecutionError('E18 actual release did not open both pads beyond source handle width')
    _hand_clearance(worker,side)
    excess=float(released['tcp_axial_offset_m'])-REFERENCE_AXIAL_M
    if excess<-.0006 or excess>.002:
        raise MechanismExecutionError('E18 released handle is outside one bounded inward regrasp corridor')
    if excess>.0005:
        amount=min(1.2,max(worker.min_mm,excess*1000.));axis=worker.axis('drawer')
        component=int(np.argmax(np.abs(axis)))
        if abs(axis[component])<.95:raise MechanismExecutionError('E18 real inward regrasp requires original public axis')
        delta=-axis*amount/1000.;_hand_clearance(worker,side,movement=delta)
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(delta[component]<0)]
        tip=worker.tip(side).copy();issue(token,mm=amount)
        if float((worker.tip(side)-tip)@(-axis))<.0001:
            raise MechanismExecutionError('E18 empty inward regrasp failed to advance')
    positioned=worker._public_pull_observation('drawer',side,6);_hand_clearance(worker,side)
    if abs(float(positioned['tcp_axial_offset_m'])-REFERENCE_AXIAL_M)>.0006:
        raise MechanismExecutionError('E18 one inward regrasp did not recover original measured pad depth')
    issue('GRASP');gripped=worker._public_pull_observation('drawer',side,1)
    if _closing(gripped):
        issue('GRASP');gripped=worker._public_pull_observation('drawer',side,1)
    worker._require_public_pull_grip(gripped,side)
    return dict(opening_clearance=opening_clearance,released=released,positioned=positioned,gripped=gripped)


def run(worker,parameters):
    author=worker.a;spec=author.scene.spec;checkpoint=getattr(author,'_engineering_resume_checkpoint',{})
    source=checkpoint.get('source',{})
    if (parameters!={} or spec.get('variant')!='A' or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('condition')!='I'
            or checkpoint.get('diagnostic_only')is not True
            or(source.get('steps'),source.get('physics_ticks'))!=(2,202)
            or not getattr(worker.c,'_engineering_diagnostic_only',False)
            or not getattr(worker.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted E18 A/I4201 native2/202 inward regrasp boundary required')
    side='left';start=worker.c.steps
    before=worker._public_pull_observation('drawer',side,0);worker._require_public_pull_grip(before,side)
    def issue(token,mm=1.):
        if worker.c.steps-start>=8:raise MechanismExecutionError('E18 bounded real regrasp exhausted eight public actions')
        worker.act(side,token,mm=mm)
        feedback=worker.c.action_feedback().get('control_feedback',{}).get(side,{})
        if feedback.get('status')=='blocked' or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
            raise MechanismExecutionError('E18 real release/regrasp public controller refused')
    reseat=release_reseat(worker,side,issue)
    pulls=_two_pulls(worker,side,start,issue)
    return dict(local_completed=True,actions=worker.c.steps-start,operations=worker.operations,
        **reseat,before=before,pulls=pulls,maximum_public_actions=8,full_drawer_open_completed=False,
        original_full_open_target_m=worker.motion['drawer']['open_distance'])


def finish_closing(worker,parameters):
    author=worker.a;spec=author.scene.spec;cp=getattr(author,'_engineering_resume_checkpoint',{})
    if (parameters!={}or spec.get('variant')!='A'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('condition')!='I'
            or cp.get('diagnostic_only')is not True
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(3,302)
            or not getattr(worker.c,'_engineering_diagnostic_only',False)
            or not getattr(worker.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted E18 A/I4201 actual closing native3/302 boundary required')
    side='left';start=worker.c.steps;before=worker._public_pull_observation('drawer',side,0)
    if not(_closing(before)or before['bilateral_contact']):
        raise MechanismExecutionError('E18 native closing suffix has neither real closing pads nor bilateral contact')
    _hand_clearance(worker,side)
    def issue(token,mm=1.):
        if worker.c.steps-start>=6:raise MechanismExecutionError('E18 closing suffix exhausted six public actions')
        worker.act(side,token,mm=mm)
        feedback=worker.c.action_feedback().get('control_feedback',{}).get(side,{})
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
            raise MechanismExecutionError('E18 closing suffix public controller refused')
    worker.stage('local-E18-one-public-GRASP-to-finish-real-closing')
    issue('GRASP');gripped=worker._public_pull_observation('drawer',side,1)
    worker._require_public_pull_grip(gripped,side)
    pulls=_two_pulls(worker,side,start,issue)
    return dict(local_completed=True,actions=worker.c.steps-start,operations=worker.operations,
        before=before,gripped=gripped,pulls=pulls,maximum_public_actions=6,
        full_drawer_open_completed=False,original_full_open_target_m=worker.motion['drawer']['open_distance'])
