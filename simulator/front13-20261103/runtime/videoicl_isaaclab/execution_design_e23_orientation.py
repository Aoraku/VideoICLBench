"""E23 engineering-only axial symmetry choices from measured read-only IK.

A cup can turn around its own axis without changing the required branch
insertion. Choose a real wrist endpoint with margin instead of imposing an
arbitrary extra twist. Candidate IK is not collision/path acceptance; actual
motion still uses the public controller and unchanged two-finger guards.
"""
import math
import numpy as np
from .realworld_tool_evidence import _unit
from .realworld_tool_expert import _axis_rotation,ToolExecutionError
from .realworld_mechanism_evidence import _rotation


def axial_rotations(current,source_axis,target_axis):
    current=_rotation(current);source=_unit(source_axis);target=_unit(target_axis)
    a=current@source;cos=float(np.clip(a@target,-1,1))
    if cos>1-1e-10:base=current
    else:
        if cos<-1+1e-8:
            seed=np.eye(3)[int(np.argmin(np.abs(a)))];axis=_unit(np.cross(a,seed))
        else:axis=_unit(np.cross(a,target))
        base=_axis_rotation(axis,math.acos(cos))@current
    return [(degrees,_axis_rotation(target,math.radians(degrees))@base)
            for degrees in (0,60,-60,120,-120,180)]


def align_cup_axis(policy,name,side,source_axis,target_axis,ik_probe=None):
    if policy.task!='E23':raise ToolExecutionError('E23 axial symmetry reference only')
    policy.require_held({'actor':name},side)
    state,_=policy.snapshot();current=_rotation(state[name]['mat'])
    target=_unit(target_axis)
    if float((current@_unit(source_axis))@target)>math.cos(math.radians(4)):return
    tcp=_rotation(policy.a.tcp_rotation_task(side));point=np.asarray(policy.tip(side),float)
    choices=axial_rotations(current,source_axis,target)
    targets=[dict(position=point.tolist(),rotation=(desired@current.T@tcp).tolist())for _,desired in choices]
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    candidates=ik_probe(policy.a,policy.c,side,targets)
    if len(candidates)!=len(choices):raise ToolExecutionError('Incomplete E23 measured IK candidates')
    valid=[]
    for index,row in enumerate(candidates):
        values=np.asarray([row.get('position_error_m',float('inf')),row.get('orientation_error_rad',float('inf')),
                           row.get('minimum_joint_margin_rad',-1),row.get('joint_distance_rad',float('inf'))],float)
        if (row.get('kinematically_reachable') and np.isfinite(values).all()
                and values[0]<.001 and values[1]<math.radians(1.5) and values[2]>.05):
            valid.append(index)
    evidence=dict(stage='E23-measured-axial-symmetry-IK',actor=name,side=side,
                  candidate_twists_deg=[degrees for degrees,_ in choices],candidates=candidates,
                  collision_verified=False,native_success_asserted=False)
    if not valid:
        policy.operations.append(dict(**evidence,chosen_index=None))
        raise ToolExecutionError('No measured E23 cup-axis wrist endpoint with joint margin')
    # Keep away from all actual joint limits, then prefer shorter joint travel.
    chosen=min(valid,key=lambda i:(-min(float(candidates[i]['minimum_joint_margin_rad']),.25),
                                   float(candidates[i]['joint_distance_rad'])))
    policy.operations.append(dict(**evidence,chosen_index=chosen,chosen_twist_deg=choices[chosen][0]))
    policy.stage('align-measured-cup-axis-'+name)
    policy.rotate_actor(name,side,choices[chosen][1])
    policy.require_held({'actor':name},side)
    measured=policy.snapshot()[0][name]['mat']@_unit(source_axis)
    if float(measured@target)<math.cos(math.radians(4)):
        raise ToolExecutionError('E23 cup axis does not match real branch after public rotation')


def align_cup_axis_incremental(policy,name,side,source_axis,target_axis,ik_probe=None,clearance_guard=None,maintain_position=None):
    """Align only the physically relevant cup axis, checking each public step.

    Endpoint IK may select a disconnected wrist path. Here candidate rotations
    start from the actual current TCP each iteration; large nullspace changes
    and near-limit endpoints are rejected before any public action is sent.
    Actual collision, tracking, and grasp guards still decide physical motion.
    """
    import json
    from pathlib import Path
    if policy.task!='E23':raise ToolExecutionError('E23 axial reference only')
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    source=_unit(source_axis);target=_unit(target_axis)
    degrees=min(5.,float(policy.max_deg))
    if not float(policy.min_deg)<=degrees:raise ToolExecutionError('E23 requires public rotations of at most five degrees')
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    history=[]
    def record(row):
        policy.operations.append(row)
        directory=getattr(policy.a,'out',None)
        if directory is not None:
            with (Path(directory)/'e23-axis-steps.private.jsonl').open('a')as f:
                f.write(json.dumps(row,allow_nan=False)+'\n')
    for iteration in range(120):
        if maintain_position is not None:maintain_position()
        if clearance_guard is not None:clearance_guard('before-axis-increment')
        policy.require_held({'actor':name},side)
        current=_rotation(policy.snapshot()[0][name]['mat']);axis=current@source
        error=math.acos(float(np.clip(axis@target,-1,1)))
        if error<math.radians(4):return
        tcp=_rotation(policy.a.tcp_rotation_task(side));point=np.asarray(policy.tip(side),float)
        choices=[]
        for i in range(3):
            for sign in (1,-1):
                delta=_axis_rotation(np.eye(3)[i],sign*math.radians(degrees))
                predicted=math.acos(float(np.clip((delta@axis)@target,-1,1)))
                if predicted<error-math.radians(.02):
                    choices.append(dict(token=tokens[i][int(sign<0)],error_rad=predicted,
                        rotation=(delta@tcp).tolist(),position=point.tolist()))
        if not choices:raise ToolExecutionError('No improving E23 public axis increment')
        rows=ik_probe(policy.a,policy.c,side,[dict(position=x['position'],rotation=x['rotation'])for x in choices])
        if len(rows)!=len(choices):raise ToolExecutionError('Incomplete E23 incremental IK diagnostics')
        accepted=[]
        for i,row in enumerate(rows):
            values=np.asarray([row.get('position_error_m',float('inf')),row.get('orientation_error_rad',float('inf')),
                               row.get('minimum_joint_margin_rad',-1),row.get('joint_distance_rad',float('inf'))],float)
            if (row.get('kinematically_reachable') and np.isfinite(values).all() and values[0]<.001
                    and values[1]<math.radians(1.5) and values[2]>.05 and values[3]<.35):accepted.append(i)
        evidence=dict(stage='E23-public-axis-increment',iteration=iteration,actor=name,side=side,
            axis_task=axis.tolist(),target_axis_task=target.tolist(),axis_error_rad=error,
            degrees=degrees,candidates=[dict(public_token=x['token'],predicted_axis_error_rad=x['error_rad'],ik=row)for x,row in zip(choices,rows)],
            collision_verified=False,native_success_asserted=False)
        if not accepted:
            record(dict(**evidence,chosen_index=None))
            raise ToolExecutionError('No near-neighbor E23 public rotation with joint margin')
        chosen=min(accepted,key=lambda i:(choices[i]['error_rad'],rows[i]['joint_distance_rad']))
        record(dict(**evidence,chosen_index=chosen,token=choices[chosen]['token']))
        policy.stage('align-measured-cup-axis-incremental-'+name)
        policy.act(side,choices[chosen]['token'],degrees=degrees)
        if clearance_guard is not None:clearance_guard('after-axis-increment')
        policy.require_held({'actor':name},side)
        after=_rotation(policy.snapshot()[0][name]['mat'])@source
        measured=math.acos(float(np.clip(after@target,-1,1)))
        record(dict(stage='E23-public-axis-increment-result',iteration=iteration,actor=name,
            axis_after_task=after.tolist(),axis_error_after_rad=measured,actual_native_state=True))
        history.append(measured)
        if measured>error+math.radians(2):raise ToolExecutionError('Actual E23 axis moved opposite to predicted public increment')
        if len(history)>=5 and min(history[-4:])>=history[-5]-math.radians(.2):
            raise ToolExecutionError('Actual E23 axis stopped improving during guarded increments')
    raise ToolExecutionError('E23 guarded cup-axis increments exhausted')
