"""C591: lift and return the truly empty released-knife hand."""
import hashlib,json,re
from pathlib import Path
import numpy as np
from .execution_design_segments_e19_e25 import _scope,_empty


def source_home_context(a,reference):
    """Read only the pinned old controller's policy targets, server locally."""
    from .engineering_checkpoint import identity
    from .layout import rotation_matrix
    if not isinstance(reference,dict)or set(reference)!={'path','sha256'}:
        raise ValueError('Pinned source-initial home checkpoint reference required')
    path=reference['path']
    if not re.fullmatch(r'/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering/execution-design-v3-20261102-e25c-full-positive-slot10-v5-s4201/result/room-00-E25-C-s4201/engineering-reference/checkpoints/stage-0001-initial.private.json',path):
        raise ValueError('Exact original C initial policy context required')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('Original C initial policy context SHA mismatch')
    cp=json.loads(raw)
    if (cp.get('schema')!='engineering-native-checkpoint-v1'or cp.get('identity')!=identity(a.c)
            or cp.get('source',{}).get('steps')!=0 or cp['source'].get('physics_ticks')!=840):
        raise ValueError('Matching original C native initial identity required')
    xy={};rotations={}
    for side in ('left','right'):
        root=np.asarray(cp['robots'][side]['root_state_task'],float)
        target=cp['controller']['tcp_targets_base'][side];rotation=rotation_matrix(root[3:7])
        xy[side]=(root[:3]+rotation@np.asarray(target['position']))[:2].tolist()
        rotations[side]=rotation@rotation_matrix(np.asarray(target['quaternion']))
    return xy,rotations


def run_segment(a,segment,parameters):
    _scope(a,'E25','C');cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (segment!='e25_c_empty_return_from591'or not isinstance(parameters,dict)
            or set(parameters)!={'initial_checkpoint'}or a.scene.spec.get('seed')!=4201
            or cp.get('diagnostic_only')is not True
            or source.get('steps')!=591 or source.get('physics_ticks')!=59940
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered C591 admitted native checkpoint required')
    state,contacts=_empty(a)
    if frozenset(('knife','table'))not in contacts:
        raise RuntimeError('C591 real released knife table support required')
    home,rotations=source_home_context(a,parameters['initial_checkpoint'])
    a._e25_home_rotations=rotations
    from .execution_design_generated_route import measured_generated_clearance,park_before_hand_switch
    clearance=measured_generated_clearance(a)['clearance_z_m'];before=a.c.steps
    park_before_hand_switch(a,'left','right',home,clearance)
    _empty(a)
    from .execution_design_e25_functional import distance_from_objects
    if distance_from_objects(a,'left')<.030:raise RuntimeError('Actual C released hand has not cleared objects')
    if frozenset(('knife','table'))not in a.c.snapshot()[1]:
        raise RuntimeError('C591 original released knife support changed')
    return dict(local_completed=True,actions=a.c.steps-before,operations=[dict(
        operation='actual_lift_empty_rotation_then_original_home',side='left',
        home_reference='pinned_source_initial_native_controller_target',clearance_m=clearance)])
