"""B792: retract the genuinely empty extended arm before lifting home."""
import hashlib,json
from pathlib import Path
import numpy as np
from .execution_design_segments_e19_e25 import _scope,_empty
from .execution_design_e25_b_reference import _joints


def retract_empty(a,side,home_xy):
    _scope(a,'E25','B');_empty(a)
    if side!='left':return []
    q,limits,_=_joints(a,side);margin=float(limits[3,1]-q[3]);tip=np.asarray(a.tip(side),float)
    delta=np.asarray(home_xy[side],float)-tip[:2];distance=float(np.linalg.norm(delta))
    if margin>=.4 or distance<.25:return []
    geometry=a.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose'or geometry['lowest_z_task_m']<.84:
        raise RuntimeError('B empty-arm retraction requires actual above-obstacle finger clearance')
    target=tip.copy();target[:2]+=.020*delta/distance
    a.stage='e25-B-empty-retract-before-lift';a.move_generated({side:target.tolist()});_empty(a)
    q,limits,_=_joints(a,side)
    if float(limits[3,1]-q[3])<.02:
        raise RuntimeError('B actual empty retraction did not leave the elbow stop')
    return [dict(operation='actual_empty_retraction_before_vertical_home_return',requested_translation_m=.020)]


def run_segment(a,segment,parameters):
    _scope(a,'E25','B');cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    boundaries={'e25_b_empty_return_from792':(792,80040),'e25_b_empty_return_from636':(636,64440)}
    boundary=boundaries.get(segment)
    if (boundary is None or set(parameters)!={'initial_checkpoint'}
            or a.scene.spec.get('seed')!=4201 or cp.get('diagnostic_only')is not True
            or(source.get('steps'),source.get('physics_ticks'))!=boundary
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered B636/B792 actual empty native checkpoint required')
    _empty(a);reference=parameters['initial_checkpoint'];path=reference['path']
    expected='/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering/execution-design-v3-20261102-e25b-full-positive-slot10-v7-s4201/result/room-00-E25-B-s4201/engineering-reference/checkpoints/stage-0001-initial.private.json'
    if path!=expected:raise ValueError('Exact original B source-initial home context required')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('B initial policy context SHA mismatch')
    initial=json.loads(raw)
    from .engineering_checkpoint import identity
    from .layout import rotation_matrix
    if initial['identity']!=identity(a.c)or initial['source']['steps']!=0 or initial['source']['physics_ticks']!=840:
        raise ValueError('Original B initial source identity required')
    home={};rotations={}
    for side in('left','right'):
        root=np.asarray(initial['robots'][side]['root_state_task']);r=rotation_matrix(root[3:7]);target=initial['controller']['tcp_targets_base'][side]
        home[side]=(root[:3]+r@np.asarray(target['position']))[:2].tolist();rotations[side]=r@rotation_matrix(np.asarray(target['quaternion']))
    a._e25_home_rotations=rotations
    from .execution_design_generated_route import measured_generated_clearance,park_before_hand_switch
    clearance=measured_generated_clearance(a)['clearance_z_m'];before=a.c.steps
    park_before_hand_switch(a,'left','right',home,clearance);_empty(a)
    from .execution_design_e25_functional import distance_from_objects
    if distance_from_objects(a,'left')<.030:raise RuntimeError('Actual B released hand has not cleared objects')
    return dict(local_completed=True,actions=a.c.steps-before,operations=[dict(operation='actual_empty_hand_object_clearance')])
