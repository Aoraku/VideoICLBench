"""E25B public-action engineering candidates; native validation remains required.

The source geometry, task goals and scoring stay unchanged. Only explicit engineering callers can request real public actions; production
task loading never invokes this reference.
"""
from copy import deepcopy
import math
import numpy as np
from .execution_design import REVISION_V3,source_sha256

# Reviewed actual source-mesh cross sections, after the source's baked rotation
# and normalisation used by spawn_source_asset. The point is a pinch centre,
# not a claim that a hollow spoon or fork has solid material at its centre.
SECTIONS={
 'spoon':dict(sha256='57eca21e894ebd2ef3a091127be5a51d4baf04e3da9bf06f90454a1f01040c4e',
  lower=[.054002492747695634,-.019095407038908337,-.005099136434408397],
  upper=[.0659873886630058,.019095407038908337,.009604323691639039]),
 'knife':dict(sha256='8d7e874a9fa51024264e6a9afb1b5c03cff586fc26f5b1eb417de57445dac18d',
  lower=[.05401666433924498,-.009336219336219337,-.01008518363357073],
  upper=[.06596750919331565,.008120374249406507,.0006200251361541683]),
 'fork':dict(sha256='134d334cc03851a697ada7cd31bfec4218ba3917a9dae084fcda4c6b62c918d6',
  lower=[.05400221610186871,-.012419615343638415,-.005929783455409649],
  upper=[.0659628271852078,.01242646033786,.00008549582049737993]),
}


def require_scope(author):
    spec=author.scene.spec;design=spec.get('execution_design',{})
    if not(spec.get('id')=='E25' and spec.get('variant')=='B'
            and design.get('revision')==REVISION_V3 and design.get('source_sha256')==source_sha256(REVISION_V3)
            and getattr(author,'_execution_design_reference_authorized',False)
            and getattr(author,'control_report',{}).get('engineering_reference_only') and not getattr(author,'smooth',False)
            and getattr(getattr(author.scene,'embodiment',None),'name',None)=='franka'):
        raise ValueError('E25B v3 private Panda engineering candidate required')


def candidate_grasp(author,obj):
    """Return a private geometric candidate, never edit a scene object."""
    require_scope(author)
    if obj['id']not in SECTIONS:raise ValueError('E25B reviewed utensil required')
    row=SECTIONS[obj['id']]
    if obj.get('source_asset',{}).get('sha256')!=row['sha256']:
        raise ValueError('E25B reviewed source mesh identity differs')
    low,high=np.array(row['lower']),np.array(row['upper'])
    if not(.015<high[1]-low[1]<.05 and .004<high[2]-low[2]<.02):
        raise ValueError('E25B pinch section dimensions invalid')
    result=deepcopy(obj);result['grasp_point_local']=((low+high)/2).tolist()
    return result


def rotation_candidates(author,side,name,goal,ik_probe):
    """Reject-only winding screen using actual held pose and native Jacobian.

    Every accepted future action must still use the public local IK and actual
    joint/contact guards. These coarse screens do not certify a continuous path.
    This function writes no poses, joints, controller targets or scores.
    """
    require_scope(author)
    if '_e07_after_relay'not in goal or goal.get('object')!=name:
        raise ValueError('E25B actual receiving stage required')
    original=next(g for g in author.scene.spec['goals']if g['object']==name)
    if (goal.get('target')!=original['target'] or any(k in goal for k in ('roll','pitch'))
            or abs(float(goal['yaw'])-float(original['yaw']))>1e-8):
        raise ValueError('E25B original absolute goal must be preserved')
    state,contacts=author.c.snapshot();body=state[name]
    hand_index=('left','right').index(side)
    if not body.get('grasp',[False,False])[hand_index] or not all(
        frozenset((name,side+'_finger'+str(i)))in contacts for i in (1,2)):
        raise RuntimeError('E25B rotation requires actual bilateral held contact')
    from .realworld_tool_expert import _axis_rotation
    from .author_orientation import _axis_angle
    actual=np.asarray(body['mat'],float);desired=_axis_rotation([0,0,1],float(goal['yaw']))
    axis,angle=_axis_angle(desired@actual.T)
    if angle<math.radians(150):raise ValueError('E25B half-turn candidate expected')
    tip=np.asarray(author.tip(side),float);tcp=np.asarray(author.tcp_rotation_task(side),float)
    paths=[]
    for winding in (angle,angle-2*math.pi):
        samples=[dict(position=tip.tolist(),rotation=(_axis_rotation(axis,t)@tcp).tolist())
                 for t in np.linspace(0,winding,9)]
        result=ik_probe(author,author.c,side,samples)
        accepted=len(result)==len(samples)and all(
            row.get('kinematically_reachable') and row.get('minimum_joint_margin_rad',0)>.05 for row in result)
        # Avoid treating unrelated redundancy solutions as a continuous arc.
        if accepted:
            joints=[np.asarray(row['candidate_joints_rad'],float)for row in result]
            accepted=all(q.shape==(7,)and np.isfinite(q).all()for q in joints)
            if accepted:accepted=all(np.max(np.abs(b-a))<.65 for a,b in zip(joints,joints[1:]))
        paths.append(dict(angle_rad=float(winding),axis_task=axis.tolist(),samples=result,
            coarse_ik_screen_passed=bool(accepted),continuous_path_verified=False,native_passed=False))
    return paths


def receiver_candidate(author,side,targets,pitch_deg):
    """Measured downward empty-palm candidate with conservative real mesh floor."""
    import itertools
    from .author_orientation import panda_downward_grasp_delta
    from .realworld_tool_expert import _axis_rotation
    require_scope(author)
    if pitch_deg not in (20,24):raise ValueError('E25B reviewed receiver pitch candidate required')
    base=np.asarray(author.tcp_rotation_task(side),float);tip=np.asarray(author.tip(side),float)
    g=author.finger_geometry(side)
    if g.get('source')!='actual_collision_mesh_current_body_pose' or len(g.get('fingers',[]))!=2:
        raise ValueError('E25B actual bilateral collision meshes required')
    fingers=g['fingers'];jaw=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m'])
    level=panda_downward_grasp_delta(base,jaw,[0,1,0])@base
    chosen=_axis_rotation(level[:,1],-math.radians(pitch_deg))@level
    delta=chosen@base.T;corners=[]
    for f in fingers:
        lo,hi=np.asarray(f['aabb_min_task_m']),np.asarray(f['aabb_max_task_m'])
        corners.extend(np.where(sign,hi,lo)-tip for sign in itertools.product((False,True),repeat=3))
    floor=.8003-float((np.asarray(corners)@delta.T)[:,2].min())
    proposals=[]
    for target in targets:
        row=deepcopy(target);row['rotation']=(np.asarray(target['rotation'])@base.T@chosen).tolist()
        row['position']=list(target['position']);row['position'][2]=max(float(row['position'][2]),floor);proposals.append(row)
    return chosen,proposals


def _joints(author,side):
    robot=author.scene.robots[side];ids,names=robot.find_joints('panda_joint[1-7]')
    if len(ids)!=7:raise RuntimeError('E25B actual seven arm joints required')
    def values(x):
        if hasattr(x,'detach'):x=x.detach()
        if hasattr(x,'cpu'):x=x.cpu()
        return np.asarray(x,float)
    return values(robot.data.joint_pos)[0,ids],values(robot.data.soft_joint_pos_limits)[0,ids],names


def rotate_payload(author,name,side,goal,ik_probe=None):
    """Follow a screened winding using public rotations and actual body poses."""
    import json
    from .realworld_tool_expert import _axis_rotation
    from .author_orientation import _axis_angle
    require_scope(author)
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    state,contacts=author.c.snapshot();initial=np.asarray(state[name]['mat'],float).copy()
    desired=_axis_rotation([0,0,1],float(goal['yaw']))
    paths=rotation_candidates(author,side,name,goal,ik_probe)
    q,limits,names=_joints(author,side)
    choices=[p for p in paths if p['coarse_ik_screen_passed']and
             np.max(np.abs(np.asarray(p['samples'][0]['candidate_joints_rad'])-q))<.2]
    evidence=dict(object=name,side=side,candidates=paths,native_passed=False,collision_verified=False)
    log=author.out/'e25-b-public-winding.private.jsonl'
    def record(row):
        with log.open('a')as f:f.write(json.dumps(row)+'\n')
    if not choices:record(dict(phase='screen_rejected',**evidence));raise RuntimeError('E25B no connected measured wrist winding')
    selected=max(choices,key=lambda p:min(x['minimum_joint_margin_rad']for x in p['samples']))
    evidence['chosen_angle_rad']=selected['angle_rad'];record(dict(phase='screen_selected',**evidence))
    tip0=np.asarray(author.tip(side),float);obj=next(o for o in author.scene.spec['objects']if o['id']==name)
    half=np.asarray(obj.get('bounds_half_extent',obj['size']));center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
    hand=('left','right').index(side);labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    previous_stage=author.stage;author.stage='e25-b-public-winding-'+name
    def guard():
        state,contacts=author.c.snapshot();body=state[name]
        if not body['grasp'][hand] or not all(frozenset((name,f'{side}_finger{i}'))in contacts for i in (1,2)):
            raise RuntimeError('E25B actual bilateral grip lost during public winding')
        allowed={frozenset((name,f'{side}_finger{i}'))for i in (1,2)}
        if any((name in pair or any(f'{side}_finger{i}'in pair for i in (1,2))) and pair not in allowed for pair in contacts):
            raise RuntimeError('E25B unexpected actual payload or finger collision during winding')
        q,limits,names=_joints(author,side)
        if not np.isfinite(q).all()or np.any(q<=limits[:,0]+.015)or np.any(q>=limits[:,1]-.015):
            raise RuntimeError('E25B actual intermediate joint limit approached')
        if np.linalg.norm(np.asarray(author.tip(side))-tip0)>.025:raise RuntimeError('E25B winding left actual TCP envelope')
        geometry=author.finger_geometry(side)
        bottom=float((np.asarray(body['pos'])+np.asarray(body['mat'])@center)[2]-(np.abs(body['mat'])@half)[2])
        if geometry.get('source')!='actual_collision_mesh_current_body_pose'or geometry['lowest_z_task_m']<.815 or bottom<.815:
            raise RuntimeError('E25B winding lacks actual table clearance')
        return body,q,limits,names
    # Consecutive subgoals differ by <=22.5deg, removing the pi-log ambiguity.
    # Each accepted public action still invokes the unchanged controller's local
    # IK at each physics tick and is checked against actual state afterwards.
    for fraction in np.linspace(0,1,9)[1:]:
        orientation=_axis_rotation(selected['axis_task'],selected['angle_rad']*fraction)@initial
        for _ in range(40):
            body,q,limits,names=guard();axis,angle=_axis_angle(orientation@np.asarray(body['mat']).T)
            if angle<math.radians(1.2):break
            k=int(np.argmax(np.abs(axis)));token=labels[k][int(axis[k]<0)]
            degrees=min(4.,max(.5,abs(math.degrees(angle*axis[k]))))
            author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
            body,q,limits,names=guard();feedback=author.c.action_feedback()['control_feedback'][side]
            record(dict(phase='public_step',object=name,side=side,fraction=float(fraction),token=token,degrees=degrees,
                measured_joint_names=list(names),measured_joints_rad=q.tolist(),limits_rad=limits.tolist(),public_local_ik_feedback=feedback))
            if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
                raise RuntimeError('E25B public local IK rejected intermediate winding')
        else:raise RuntimeError('E25B actual public winding subgoal did not converge')
    body,_,_,_=guard();error=_axis_angle(desired@np.asarray(body['mat']).T)[1]
    if error>math.radians(1.5):raise RuntimeError('E25B original absolute orientation not reached')
    record(dict(phase='rotation_complete',object=name,side=side,actual_original_goal_error_rad=error,native_passed=False))
    author.control_report.setdefault('e25_b_windings',[]).append(dict(object=name,side=side,selected_angle_rad=selected['angle_rad'],actual_goal_error_rad=error,public_actions_only=True,native_passed=False))
    author.stage=previous_stage
