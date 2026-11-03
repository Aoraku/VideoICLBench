"""Front13 adapter: native checkpoints and honest legacy-pose debug fixtures.

The native core is frozen separately to avoid changing another session's API.
These are partial engineering experiments, never full-trajectory acceptance.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from . import _front13_checkpoint_native as native

FIELDS=('_public_action','_public_blocked','_public_blocked_before','_public_hold_q',
        '_public_limit_seen','_public_failures','_public_acceleration_override',
        '_public_superseded_orientation','_public_tolerances','_public_start',
        '_public_rotation_intent')
DTYPES={k:getattr(torch,k)for k in ('float32','float64','int32','int64','bool')}


def _encode(x):
    if isinstance(x,torch.Tensor):
        key=str(x.dtype).split('.')[-1]
        if key not in DTYPES:raise ValueError('Unsupported servo tensor dtype')
        return {'tensor':key,'value':x.detach().cpu().tolist()}
    if isinstance(x,tuple):return {'tuple':[_encode(v)for v in x]}
    if isinstance(x,np.ndarray):return _encode(x.tolist())
    if isinstance(x,np.generic):return _encode(x.item())
    if isinstance(x,list):return [_encode(v)for v in x]
    if isinstance(x,dict):return {k:_encode(v)for k,v in x.items()}
    return native._plain(x)


def _decode(x,device):
    if isinstance(x,list):return [_decode(v,device)for v in x]
    if isinstance(x,dict):
        if set(x)=={'tensor','value'}:
            if x['tensor']not in DTYPES:raise ValueError('Unsupported servo tensor dtype')
            value=torch.tensor(x['value'],device=device,dtype=DTYPES[x['tensor']])
            if not bool(torch.isfinite(value).all()):raise ValueError('Nonfinite servo tensor')
            return value
        if set(x)=={'tuple'}:return tuple(_decode(v,device)for v in x['tuple'])
        return {k:_decode(v,device)for k,v in x.items()}
    return native._plain(x)


def _allow(c):
    if getattr(c,'_engineering_branch_authorized',False)is not True:
        raise ValueError('Explicit independent engineering branch authorization required')
    pool=getattr(c,'_room_pool',None)
    if pool is not None and len(pool.controllers)!=1:raise ValueError('An isolated engineering room is required')
    if c.scene.spec['id']not in {f'E{i:02}'for i in range(1,14)}:raise ValueError('Outside front13 engineering scope')


def capture(controller,author=None,context=None):
    _allow(controller)
    p=native.capture(controller,getattr(author,'stage','public-boundary'),context)
    p.update(debug_only=True,eligible_full_acceptance=False,
             front13_servo={k:_encode(getattr(controller,k))for k in FIELDS if hasattr(controller,k)},
             author_state={k:_encode(getattr(author,k))for k in ('stage','carried_payload','control_report','_execution_design_reference_authorized')if author is not None and hasattr(author,k)})
    if callable(getattr(controller,'public_feedback',None)):
        p['tcp_task_positions']={k:v['tcp_position']for k,v in controller.public_feedback()['arms'].items()}
    return native.reseal(p)


def save(payload,path):
    path=Path(path);value=native.reseal(payload)
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');temp.chmod(0o600);temp.replace(path)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checkpoint_sha256=value['checkpoint_sha256'])


def load(path):
    p=json.loads(Path(path).read_text());expected=p.get('checkpoint_sha256')
    if expected!=native.reseal(p)['checkpoint_sha256']:raise ValueError('Checkpoint SHA mismatch')
    return p


def from_new_design_fixture(controller,description,author=None):
    """Author an explicit E09 unit-test start under the current new geometry.

    This does not import an old checkpoint, history, held flag or terminal score.
    Optional object poses are declared fixture initial conditions, at reset only.
    """
    _allow(controller);native._startup(controller)
    if description.get('schema')!='videoicl-engineering-new-design-fixture-v1':
        raise ValueError('Explicit new-design fixture schema required')
    if set(description)&{'evaluator','success','history','strict_success','task_score_100','initial_sealed'}:
        raise ValueError('New-design fixture cannot import evaluator labels')
    spec=controller.scene.spec;design=spec['execution_design'];case=description['identity']
    if spec['id']!='E09'or any(case.get(k)!=spec.get(k)for k in('id','variant','seed')):
        raise ValueError('New-design fixture requires matching E09 identity')
    if case.get('assignment_identity_sha256')!=design.get('assignment_identity_sha256')or case.get('source_sha256')!=design.get('source_sha256'):
        raise ValueError('New-design assignment/source differs')
    revision=design.get('operable_packaging',{})
    if revision.get('revision')not in {'e09-operable-packaging-v1-20261103','e09-operable-packaging-v2-20261103','e09-operable-packaging-v3-20261103'}or description.get('geometry_sha256')!=revision.get('geometry_sha256'):
        raise ValueError('Explicit current E09 packaging geometry fingerprint required')
    objects={o['id']:o for o in spec['objects']};members=design.get('target_members',[])
    if len(members)!=9 or len(set(members))!=9:
        raise ValueError('Nine original rule CAD actors required')
    expected={name:objects[name]['source_asset']['sha256']for name in members}
    if description.get('source_asset_sha256')!=expected:
        raise ValueError('Original nine CAD fingerprints differ')
    context=deepcopy(description.get('context',{}))
    if not isinstance(context,dict)or context.get('policy_start_step',0)!=0:
        raise ValueError('Fresh diagnostic fixture context required')
    context.update(new_design_fixture=True,new_design_geometry_sha256=revision['geometry_sha256'],
        not_old_checkpoint_continuation=True,debug_only=True,eligible_full_acceptance=False)
    p=capture(controller,author,context)
    p.update(state_quality='measured_pose_fixture',reset_servo_to_measured=True,
        source_evidence=dict(new_design_fixture=True,parent_evidence=deepcopy(description.get('parent_evidence',{}))))
    p['assumptions']+=['Explicit new-design engineering fixture; not an old native checkpoint continuation.',
        'No old evaluator history, success or held labels imported; actual contacts must develop in native physics.']
    overrides=description.get('object_root_overrides',{})
    if not isinstance(overrides,dict)or set(overrides)-set(p['objects']):
        raise ValueError('New-design fixture contains unknown actors')
    for name,row in overrides.items():
        if isinstance(row,dict):
            if set(row)!={'root_state_task'}:raise ValueError('Only explicit physical root state may be authored')
            value=native._array(row['root_state_task'],(13,),'fixture root state')
        else:
            value=np.r_[native._array(row,(7,),'fixture root pose'),np.zeros(6)]
        native._quat(value[3:7],'fixture root quaternion')
        p['objects'][name]['root_state_task']=value.tolist()
    if overrides:p['assumptions'].append('Explicit reset-time object-pose fixture overrides: '+','.join(sorted(overrides)))
    robots=description.get('robot_joint_overrides',{})
    if not isinstance(robots,dict):raise ValueError('Explicit native robot joint fixture mapping required')
    if robots:
        if (description.get('robot_source_embodiment_sha256')!=spec.get('embodiment_config_sha256')
                or set(robots)!=set(p['robots'])):
            raise ValueError('Robot fixture requires identical original embodiment and inventory')
        for side,values in robots.items():
            record=p['robots'][side];names=record['joint_names'];n=len(names)
            if (not isinstance(values,dict)or set(values)!={'joint_names','joint_pos','joint_vel','drive_targets'}
                    or values['joint_names']!=names):raise ValueError('Only matching native joint state/drive fixture allowed')
            record['joint_pos']=native._array(values['joint_pos'],(n,),'fixture robot q').tolist()
            record['joint_vel']=native._array(values['joint_vel'],(n,),'fixture robot qd').tolist()
            targets=values['drive_targets']
            if not isinstance(targets,dict)or set(targets)!=set(native.DRIVES):raise ValueError('Explicit native drive target fields required')
            record['drive_targets']={key:None if value is None else native._array(value,(n,),'fixture robot drive').tolist()for key,value in targets.items()}
        widths=description.get('gripper_initial_widths')
        if not isinstance(widths,dict)or set(widths)!=set(p['controller']['grips']):raise ValueError('Explicit original gripper command inventory required')
        if any(type(value)not in(int,float)or not np.isfinite(value)or not 0<=value<=.04 for value in widths.values()):raise ValueError('Original gripper command range required')
        p['controller']['grips']=deepcopy(widths)
        tcp=description.get('robot_source_tcp_task_positions')
        if not isinstance(tcp,dict)or set(tcp)!=set(p['robots']):raise ValueError('Matching measured native robot TCP readback required')
        p['tcp_task_positions']={side:native._array(point,(3,),'fixture native TCP').tolist()for side,point in tcp.items()}
        p['assumptions'].append('Explicit reset-time robot joint/drive and gripper-command fixture; original robot roots/profile retained, no held flag or evaluator history imported.')
    elif 'gripper_initial_widths'in description:raise ValueError('Gripper fixture requires matching original robot joint state')
    p['front13_servo']={}
    return native.reseal(p)


def restore(controller,payload,author=None):
    _allow(controller)
    if payload.get('debug_only')is not True or payload.get('eligible_full_acceptance')is not False:
        raise ValueError('Explicit front13 diagnostic payload required')
    forward=getattr(controller.sim,'forward',None)
    if not callable(forward):raise ValueError('Native FK refresh API unavailable')
    servo={k:_decode(v,controller.device)for k,v in payload.get('front13_servo',{}).items()}
    if set(servo)-set(FIELDS):raise ValueError('Unknown controller state fields')
    author_state={k:_decode(v,controller.device)for k,v in payload.get('author_state',{}).items()}
    if set(author_state)-{'stage','carried_payload','control_report','_execution_design_reference_authorized'}:
        raise ValueError('Unknown author state fields')
    receipt=native.restore_startup(controller,payload)
    for group in ('robots','mechanisms'):
        for asset in getattr(controller.scene,group,{}).values():
            if callable(getattr(asset,'write_data_to_sim',None)):asset.write_data_to_sim()
    for key,value in servo.items():setattr(controller,key,value)
    controller.steps=payload['source']['steps'];controller.physics_ticks=payload['source']['physics_ticks']
    if author is not None:
        for key,value in author_state.items():setattr(author,key,value)
    before=float(controller.sim.current_time);forward();controller.scene.update_physics(0.)
    if float(controller.sim.current_time)!=before:raise RuntimeError('FK refresh advanced physics')
    if payload.get('reset_servo_to_measured'):
        controller.targets={side:tuple(v.clone()if hasattr(v,'clone')else v.copy()for v in controller.pose(side))for side in controller.scene.robots}
        controller._public_action=None
        for key in FIELDS:
            if key!='_public_action':setattr(controller,key,{})
        controller._public_reference={};controller._public_reference_velocity={}
    verified=[]
    for group in ('objects','robots','mechanisms'):
        for name,asset in getattr(controller.scene,group,{}).items():
            expected=payload[group][name]
            root=np.asarray(native._root_to_task(controller.scene,asset.data.root_state_w))
            wanted=np.asarray(expected['root_state_task'])
            if np.max(abs(root[:3]-wanted[:3]))>2e-5 or abs(abs(root[3:7]@wanted[3:7])-1)>2e-6 or np.max(abs(root[7:]-wanted[7:]))>1e-4:
                raise RuntimeError('Native checkpoint root readback mismatch: '+name)
            if group!='objects'and np.max(abs(np.asarray(native._plain(asset.data.joint_pos))[0]-expected['joint_pos']))>2e-5:
                raise RuntimeError('Native checkpoint joint readback mismatch: '+name)
            if group!='objects'and np.max(abs(np.asarray(native._plain(asset.data.joint_vel))[0]-expected['joint_vel']))>1e-4:
                raise RuntimeError('Native checkpoint joint velocity readback mismatch: '+name)
            verified.append(group+'/'+name)
    if payload.get('tcp_task_positions'):
        feedback=controller.public_feedback()['arms']
        for side,target in payload['tcp_task_positions'].items():
            if np.linalg.norm(np.asarray(feedback[side]['tcp_position'])-target)>1e-4:
                raise RuntimeError('Restored native TCP FK mismatch: '+side)
    return dict(**receipt,restored=True,debug_only=True,eligible_full_acceptance=False,
                source_actions=controller.steps,native_readback_verified=True,verified_assets=verified)


def from_legacy(controller,legacy,author=None):
    """Create a static diagnostic fixture from a matching original action/tick.

    This explicitly resets unknown velocities/drive history. It is not a
    lossless PhysX continuation and carries no evaluator completion history.
    """
    _allow(controller)
    if legacy.get('schema')!='videoicl-engineering-legacy-boundary-v1':raise ValueError('Legacy boundary schema required')
    spec=controller.scene.spec;case=legacy['identity']
    if any(case.get(k)!=spec.get(k)for k in ('id','variant','seed')):raise ValueError('Legacy task identity mismatch')
    design=spec['execution_design']
    if case.get('assignment_identity_sha256')!=design.get('assignment_identity_sha256')or case.get('source_sha256')!=design.get('source_sha256'):
        raise ValueError('Legacy assignment or source identity mismatch')
    action=legacy['action_receipt'];row=legacy['native_state']
    if action['step_after']!=row['actions']+1 or action['shared_tick_after']!=row['native_physics_tick']+1:
        raise ValueError('Action receipt and native trajectory are not the same boundary')
    p=capture(controller,author,legacy.get('context',{}))
    p.update(state_quality='measured_pose_fixture',reset_servo_to_measured=True,
             stage=action.get('stage','legacy-debug-boundary'),source_evidence=deepcopy(legacy.get('source_evidence',{})))
    p['source'].update(steps=int(action['step_after']),physics_ticks=int(action['shared_tick_after']))
    p['assumptions']+=['Historical root and arm velocities unavailable: zero-velocity fixture; measured finger velocities retained when available.',
        'Historical controller drive targets unavailable: measured arm q hold and inferred native gripper command.',
        'Historical PhysX warm-start/contact caches and evaluator history are not restored.']
    from scipy.spatial.transform import Rotation
    if set(row['state'])!=set(p['objects']):raise ValueError('Legacy object inventory mismatch')
    for name,state in row['state'].items():
        pos=native._array(state['pos'],(3,),'legacy object position');matrix=native._array(state['mat'],(3,3),'legacy object rotation')
        if not np.allclose(matrix.T@matrix,np.eye(3),atol=2e-5)or np.linalg.det(matrix)<.999:raise ValueError('Invalid legacy object rotation')
        q=Rotation.from_matrix(matrix).as_quat();q=np.r_[q[3],q[:3]]
        p['objects'][name]['root_state_task']=np.r_[pos,q,np.zeros(6)].tolist()
    for name,record in p['mechanisms'].items():
        measured=row.get('mechanisms',{}).get(name)
        if measured is None or measured['joint_names']!=record['joint_names']:raise ValueError('Missing legacy mechanism joint state')
        record['joint_pos']=measured['joint_pos'];record['joint_vel']=measured.get('joint_vel',[0.]*len(record['joint_names']))
        record['drive_targets']={'position':record['joint_pos'],'velocity':None,'effort':None}
        p['assumptions'].append('Mechanism '+name+': original fixed root pose retained; actual source joint readback restored.')
    if not set(p['robots']).issubset(action['robot_diagnostics']):raise ValueError('Legacy robot inventory mismatch')
    grips={}
    for side,record in p['robots'].items():
        d=action['robot_diagnostics'][side];values={}
        for section,field in (('arm_joints','positions_rad'),('finger_joints','positions_m')):
            values.update(zip(d[section]['names'],d[section][field]))
        if set(values)!=set(record['joint_names']):raise ValueError('Legacy joint identity mismatch')
        q=[values[k]for k in record['joint_names']];record['joint_pos']=q;record['joint_vel']=[0.]*len(q)
        fingers=d['finger_joints'];measured=fingers.get('velocities_m_s')
        if measured is not None:
            velocity=native._array(measured,(len(fingers['names']),),'legacy finger joint velocity')
            for joint,value in zip(fingers['names'],velocity):record['joint_vel'][record['joint_names'].index(joint)]=float(value)
            p['assumptions'].append('Robot '+side+': measured original finger joint velocities restored; arm velocities remain unknown/zero.')
        held=any(state['grasp'][0 if side=='left'else 1]for state in row['state'].values())
        grips[side]=0. if held or np.mean(d['finger_joints']['positions_m'])<.02 else .04
        target=q.copy();finger_ids=controller.ids[side][1]
        requested=controller.scene.embodiment.gripper_values(grips[side]/.04)
        for index,value in zip(finger_ids,requested):target[index]=float(value)
        record['drive_targets']={'position':target,'velocity':None,'effort':None}
    p['controller'].update(grips=grips,rolling_reference={},rolling_reference_velocity={})
    p['front13_servo']={};p['tcp_task_positions']=deepcopy(action['tips'])
    p['author_state']['stage']=action.get('stage','legacy-debug-boundary')
    return native.reseal(p)
