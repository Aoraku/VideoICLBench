"""Offline legacy-evidence adapter for the shared native debug checkpoint.

No simulator state writer lives here. Fresh-world restoration exclusively uses
engineering_checkpoint.restore_startup. Missing velocities/drive targets are
explicit assumptions; these fixtures never certify a full primary episode.
"""
from copy import deepcopy
import numpy as np
from .layout import Layout,rotation_matrix,multiply_quaternions
from .engineering_checkpoint import SCHEMA,PHYSICAL_KEYS,_hash,reseal


def _array(value,shape,label):
    a=np.asarray(value,float)
    if a.shape!=shape or not np.isfinite(a).all():raise ValueError('Finite '+label+' with shape '+str(shape)+' required')
    return a


def matrix_quaternion(matrix):
    from scipy.spatial.transform import Rotation
    r=_array(matrix,(3,3),'rotation')
    if not np.allclose(r.T@r,np.eye(3),atol=2e-4)or not np.isclose(np.linalg.det(r),1.,atol=2e-4):raise ValueError('Proper recorded rotation required')
    return Rotation.from_matrix(r).as_quat()[[3,0,1,2]].tolist()


def tcp_pose_from_fingers(tip,left_origin,right_origin):
    """Measured Panda TCP/actual finger origins define its physical hand frame."""
    p=_array(tip,(3,),'TCP');a=_array(left_origin,(3,),'left finger origin');b=_array(right_origin,(3,),'right finger origin')
    y=a-b
    if np.linalg.norm(y)<1e-5:raise ValueError('Separated actual finger origins required')
    y/=np.linalg.norm(y);z=p-.5*(a+b);z-=y*float(z@y)
    if np.linalg.norm(z)<1e-5:raise ValueError('Actual TCP-to-finger-midpoint offset required')
    z/=np.linalg.norm(z);x=np.cross(y,z);x/=np.linalg.norm(x);z=np.cross(x,y)
    return dict(position=p.tolist(),quaternion=matrix_quaternion(np.column_stack((x,y,z))))


def build_measured_pose_fixture(spec,profile_config,*,object_states,robot_states,source,stage,context=None,object_velocities=None,mechanisms=None,assumptions=None):
    """Build shared SCHEMA JSON from actual task-frame legacy evidence.

    robot_states[side]: joint_names, q/qd (or joint_pos/joint_vel), grip,
    tcp_position_task and tcp_quaternion_task (or tcp_rotation_task). Optional
    root_state_task and drive_targets preserve explicitly measured values.
    object_velocities[name]: linvel/angvel in task frame; absent values become
    declared zero-velocity approximations. Bodies retain their recorded poses.
    """
    ed=spec['execution_design'];layout=Layout(profile_config['layout']);notes=list(assumptions or [])
    identity=dict(task=spec['id'],variant=spec['variant'],seed=spec['seed'],assignment_identity_sha256=ed['assignment_identity_sha256'],source_sha256=ed['source_sha256'],embodiment_config_sha256=spec['embodiment_config_sha256'],physical_geometry_sha256=_hash({k:spec.get(k)for k in PHYSICAL_KEYS}))
    required={o['id']for o in spec['objects']}
    if set(object_states)!=required:raise ValueError('Complete recorded rigid object states required')
    if set(robot_states)!=set(profile_config['robots']):raise ValueError('Complete recorded robot states required')
    objects={};velocities=object_velocities or {}
    for name,row in object_states.items():
        p=_array(row['pos'],(3,),name+' pos');q=matrix_quaternion(row['mat']);velocity=velocities.get(name)
        if velocity is None:
            v=w=np.zeros(3);notes.append(name+': object linear/angular velocity not recorded; zero-velocity approximate fixture')
        else:
            v=_array(velocity['linvel'],(3,),name+' linear velocity');w=_array(velocity['angvel'],(3,),name+' angular velocity')
        objects[name]=dict(root_state_task=np.r_[p,q,v,w].tolist())
    robots={};grips={};tcp={}
    inverse=np.asarray(layout.task_quat)*np.array([1.,-1.,-1.,-1.])
    for side,row in robot_states.items():
        names=list(row['joint_names']);n=len(names)
        if len(set(names))!=n or not n:raise ValueError('Unique full native joint names required')
        q=_array(row.get('q',row.get('joint_pos')),(n,),side+' q')
        raw_qd=row.get('qd',row.get('joint_vel'))
        if raw_qd is None:
            qd=np.zeros(n);notes.append(side+': joint velocity unavailable; explicit zero approximation')
        else:qd=_array(raw_qd,(n,),side+' qd')
        root=row.get('root_state_task')
        if root is None:
            mount=profile_config['robots'][side];root=np.r_[layout.world_to_task(mount['position']),multiply_quaternions(inverse,mount['rotation']),np.zeros(6)].tolist()
            notes.append(side+': fixed-base root from pinned source mount; root velocity zero')
        root=_array(root,(13,),side+' root')
        drives=row.get('drive_targets')
        if drives is None:
            drives=dict(position=None,velocity=None,effort=None);notes.append(side+': original drive targets unavailable; shared restore holds measured q and zero velocity/effort targets')
        else:
            if set(drives)!={'position','velocity','effort'}:raise ValueError('Complete recorded drive-target schema required')
            drives={k:None if v is None else _array(v,(n,),side+' '+k+' target').tolist()for k,v in drives.items()}
        robots[side]=dict(root_state_task=root.tolist(),joint_names=names,joint_pos=q.tolist(),joint_vel=qd.tolist(),drive_targets=drives)
        grip=float(row['grip'])
        if not np.isfinite(grip):raise ValueError('Finite recorded grip required')
        grips[side]=grip
        if 'tcp_targets_base'in row:
            pose=deepcopy(row['tcp_targets_base'])
        else:
            p=_array(row['tcp_position_task'],(3,),side+' measured TCP')
            tq=row.get('tcp_quaternion_task')
            if tq is None:tq=matrix_quaternion(row['tcp_rotation_task'])
            tq=_array(tq,(4,),side+' TCP quaternion')
            if not np.isclose(np.linalg.norm(tq),1.,atol=1e-4):raise ValueError('Unit recorded TCP quaternion required')
            br=rotation_matrix(root[3:7]);bq=root[3:7]*np.array([1.,-1.,-1.,-1.])
            pose=dict(position=(br.T@(p-root[:3])).tolist(),quaternion=list(multiply_quaternions(bq,tq)))
            notes.append(side+': original Cartesian target absent; use achieved measured TCP pose for diagnostic hold')
        tcp[side]=pose
    if not notes:notes.append('Legacy evidence fixture; PhysX contact/solver caches unavailable')
    src=deepcopy(source)
    if not all(k in src for k in ('steps','physics_ticks','dt')):raise ValueError('Recorded source action/tick/dt required')
    return reseal(dict(schema=SCHEMA,diagnostic_only=True,state_quality='measured_pose_fixture',stage=stage,context=deepcopy(context or {}),identity=identity,source=src,objects=objects,robots=robots,mechanisms=deepcopy(mechanisms or {}),controller=dict(grips=grips,tcp_targets_base=tcp,rolling_reference={},rolling_reference_velocity={}),passive_material={},assumptions=notes,limitations=['Old source lacked a complete native checkpoint','PhysX contact/solver caches and evaluator/history/success labels are not restored','Local debugging only; never a source-initial primary witness']))
