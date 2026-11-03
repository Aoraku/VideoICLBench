"""Private engineering-only native state checkpoints and startup fixtures.

Restoration is restricted to a fresh unsealed controller. It is a diagnostic
initial condition, never a replay or a source-initial full-task acceptance.
PhysX contact/solver caches are not serialized; caller must settle and verify
actual pose, grip and support before issuing the resumed stage's public action.
"""
import copy
import hashlib
import json
import math
import numpy as np
from .layout import multiply_quaternions

SCHEMA='engineering-native-checkpoint-v1'
PHYSICAL_KEYS=('objects','mechanisms','fixtures','joints','zones','semantic','goals','table_surface')
DRIVES={'position':('joint_pos_target','set_joint_position_target'),
        'velocity':('joint_vel_target','set_joint_velocity_target'),
        'effort':('joint_effort_target','set_joint_effort_target')}
MATERIAL_PARAMETERS=('stiffness_nm_per_rad','yield_moment_nm','damping_nm_s_per_rad')


def _plain(value):
    if hasattr(value,'detach'):value=value.detach().cpu().numpy()
    if isinstance(value,np.ndarray):return _plain(value.tolist())
    if isinstance(value,np.generic):return _plain(value.item())
    if isinstance(value,dict):
        if any(not isinstance(k,str)for k in value):raise ValueError('Checkpoint keys must be strings')
        return {k:_plain(v)for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_plain(v)for v in value]
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,float)and math.isfinite(value):return value
    raise ValueError('Checkpoint requires finite JSON values: '+type(value).__name__)


def _hash(value):
    return hashlib.sha256(json.dumps(_plain(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def reseal(checkpoint):
    """Return a finite plain-JSON copy with a new integrity hash.

    This does not grant restore admission: identity/startup/schema validation
    still occurs in restore_startup. Fixture authors must declare assumptions.
    """
    result=_plain(checkpoint);result.pop('checkpoint_sha256',None)
    result['checkpoint_sha256']=_hash(result)
    return result


def identity(controller):
    spec=controller.scene.spec;design=spec.get('execution_design',{})
    row=dict(task=spec['id'],variant=spec['variant'],seed=spec['seed'],
        assignment_identity_sha256=design.get('assignment_identity_sha256'),
        source_sha256=design.get('source_sha256'),
        embodiment_config_sha256=spec.get('embodiment_config_sha256'),
        physical_geometry_sha256=_hash({k:spec.get(k)for k in PHYSICAL_KEYS}))
    if any(not isinstance(row[k],str)or not row[k]for k in ('assignment_identity_sha256','source_sha256','embodiment_config_sha256')):
        raise ValueError('Native assignment/source/profile fingerprints required')
    return row


def _array(value,shape,label):
    array=np.asarray(_plain(value),float)
    if array.shape!=shape or not np.isfinite(array).all():raise ValueError('Invalid finite shape for '+label)
    return array


def _single(value,size,label):
    array=np.asarray(_plain(value),float)
    if array.shape==(1,size):array=array[0]
    return _array(array,(size,),label)


def _quat(value,label):
    q=_array(value,(4,),label)
    if abs(float(np.linalg.norm(q))-1.)>1e-4:raise ValueError('Unit quaternion required: '+label)
    return q/np.linalg.norm(q)


def _frame(scene):
    rotation=_array(scene.layout.task_rotation,(3,3),'task rotation')
    if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-6)or np.linalg.det(rotation)<.999:
        raise ValueError('Proper task rotation required')
    quat=_quat(scene.layout.task_quat,'task quaternion')
    return rotation,quat


def _root_to_task(scene,value):
    root=_single(value,13,'native root state');rotation,quat=_frame(scene)
    root[3:7]=_quat(root[3:7],'native root')
    inverse=quat*np.array([1.,-1.,-1.,-1.])
    return np.r_[scene.world_to_task(root[:3]),multiply_quaternions(inverse,root[3:7]),
                  root[7:10]@rotation,root[10:13]@rotation].tolist()


def _root_to_world(scene,value):
    root=_array(value,(13,),'task root state');rotation,quat=_frame(scene)
    q=_quat(root[3:7],'task root')
    return np.r_[scene.task_to_world(root[:3]),multiply_quaternions(quat,q),
                  root[7:10]@rotation.T,root[10:13]@rotation.T]


def _asset_state(scene,asset,articulated,assumptions,label):
    row=dict(root_state_task=_root_to_task(scene,asset.data.root_state_w))
    if articulated:
        names=list(asset.joint_names);n=len(names)
        if not names or len(set(names))!=n or any(not isinstance(s,str)for s in names):raise ValueError('Unique native joint names required')
        row.update(joint_names=names,joint_pos=_single(asset.data.joint_pos,n,label+' q').tolist(),
                   joint_vel=_single(asset.data.joint_vel,n,label+' qd').tolist(),drive_targets={})
        for key,(field,_)in DRIVES.items():
            raw=getattr(asset.data,field,None)
            row['drive_targets'][key]=_single(raw,n,label+' '+field).tolist()if raw is not None else None
            if raw is None:assumptions.append(label+': unavailable '+field+'; startup will hold measured q / zero velocity or effort target')
    return row


def capture(controller,stage,context=None):
    """Read one completed native action boundary; returns finite plain JSON."""
    if not isinstance(stage,str)or not stage:raise ValueError('Explicit engineering stage required')
    if getattr(controller,'_engineering_action_in_flight',False)or getattr(controller,'_public_action_in_flight',False):
        raise ValueError('Cannot capture an in-flight action')
    if context is not None and not isinstance(context,dict):raise ValueError('Engineering checkpoint context must be a dictionary')
    if getattr(controller,'_author_joint_override',{})or getattr(controller,'_author_ff_twists',{}):
        raise ValueError('Private in-motion overrides cannot be captured as a public-action boundary')
    scene=controller.scene;assumptions=[]
    objects={name:_asset_state(scene,asset,False,assumptions,'object/'+name)for name,asset in scene.objects.items()}
    robots={name:_asset_state(scene,asset,True,assumptions,'robot/'+name)for name,asset in scene.robots.items()}
    mechanisms={name:_asset_state(scene,asset,True,assumptions,'mechanism/'+name)for name,asset in getattr(scene,'mechanisms',{}).items()}
    tcp={side:dict(position=_single(p,3,'TCP target position').tolist(),quaternion=_quat(_single(q,4,'TCP target quaternion'),'TCP target').tolist())for side,(p,q)in controller.targets.items()}
    passive={}
    for name,entry in getattr(scene,'passive_efforts',{}).items():
        model=entry['model']
        if type(model).__name__!='ElastoPlasticHinge':raise ValueError('Unreviewed passive checkpoint material')
        passive[name]=dict(joint=entry['joint'],parameters={k:float(getattr(model,k))for k in MATERIAL_PARAMETERS},
                           plastic_rest_angle_rad=float(model.plastic_rest_angle_rad))
    readback=dict(available=False)
    if callable(getattr(controller,'snapshot',None)):
        state,contacts=controller.snapshot();forces=getattr(controller,'contact_forces',{})
        readback=dict(available=True,object_grasps={name:list(row['grasp'])for name,row in state.items()},
            contacts=sorted(sorted(pair)for pair in contacts),
            contact_forces_n=[dict(bodies=sorted(pair),force_n=float(forces[pair]))for pair in contacts if pair in forces])
    result=dict(schema=SCHEMA,diagnostic_only=True,state_quality='measured_native_state',stage=stage,
        context=_plain(context or {}),identity=identity(controller),
        source=dict(steps=int(controller.steps),physics_ticks=int(controller.physics_ticks),dt=float(controller.dt)),
        objects=objects,robots=robots,mechanisms=mechanisms,
        controller=dict(grips=_plain(controller.grips),tcp_targets_base=tcp,
            rolling_reference=_plain(getattr(controller,'_public_reference',{})),
            rolling_reference_velocity=_plain(getattr(controller,'_public_reference_velocity',{}))),
        passive_material=passive,readback=_plain(readback),assumptions=assumptions,
        limitations=['PhysX contact/solver/sensor caches are not serialized','No evaluator/history/success flags are restored','Caller must capture only at a completed public-action boundary'])
    if getattr(controller,'_public_gripper_limits',None)is not None:
        result['controller']['gripper_reference']=_plain(getattr(controller,'_public_gripper_reference',{}))
        result['controller']['gripper_reference_velocity']=_plain(getattr(controller,'_public_gripper_reference_velocity',{}))
    if getattr(controller,'_public_gripper_contact_preload',None)is not None:
        result['controller']['gripper_contact_anchor']=_plain(getattr(controller,'_public_gripper_contact_anchor',{}))
        result['controller']['gripper_contact_active']=_plain(getattr(controller,'_public_gripper_contact_active',{}))
    return reseal(result)


def _startup(controller):
    if getattr(controller,'_engineering_restore_attempted',False):raise ValueError('Engineering startup restore is single-use')
    if controller.steps!=0 or getattr(controller,'started',False)or getattr(controller,'_public_action',None)is not None:
        raise ValueError('Engineering restore requires a fresh controller before any action')
    evaluator=controller.evaluator
    if any(getattr(evaluator,k,False)for k in ('initial_sealed','progress_initial_sealed')):
        raise ValueError('Cannot restore after native initial state was sealed')
    if getattr(controller,'_engineering_action_in_flight',False):raise ValueError('Cannot restore an in-flight action')


def _tensor_like(reference,value):
    # Native tensor constructors preserve the simulator device and float type;
    # numpy adapters keep CPU-only tests independent from Isaac/PyTorch imports.
    if callable(getattr(reference,'new_tensor',None)):return reference.new_tensor(value)
    return np.asarray(value,dtype=getattr(reference,'dtype',float))


def _native_kinematic_rigid(asset):
    """Read the actual USD rigid-body root, not a guessed semantic role."""
    view=getattr(asset,'root_physx_view',None);paths=getattr(view,'prim_paths',None)
    if paths is None:return False  # CPU adapters without native PhysX views.
    if len(paths)!=1:raise ValueError('One native rigid-body root required for checkpoint restore')
    from pxr import UsdPhysics
    import omni.usd
    stage=omni.usd.get_context().get_stage();prim=stage.GetPrimAtPath(paths[0])
    if not prim or not prim.HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError('Cannot validate native checkpoint rigid-body root: '+str(paths[0]))
    return bool(UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Get())


def _validate_asset(scene,asset,row,articulated,label,q_tolerance=1e-5):
    root=_root_to_world(scene,row['root_state_task'])
    kinematic=not articulated and _native_kinematic_rigid(asset)
    if kinematic:
        if np.any(np.abs(root[7:])>1e-8):raise ValueError('Nonzero kinematic velocity cannot be restored: '+label)
        if not callable(getattr(asset,'write_root_pose_to_sim',None)):
            raise ValueError('Native kinematic root pose write unavailable: '+label)
    root_writer=getattr(asset,'write_root_state_to_sim',None)
    if not callable(root_writer):
        if not all(callable(getattr(asset,k,None))for k in ('write_root_pose_to_sim','write_root_velocity_to_sim')):
            raise ValueError('Native root write API unavailable: '+label)
    plan=dict(asset=asset,root=root,articulated=articulated,kinematic=kinematic,label=label)
    if articulated:
        names=list(asset.joint_names);n=len(names)
        if row.get('joint_names')!=names:raise ValueError('Native joint name/order mismatch: '+label)
        q=_array(row['joint_pos'],(n,),label+' q');qd=_array(row['joint_vel'],(n,),label+' qd')
        limits=getattr(asset.data,'joint_pos_limits',getattr(asset.data,'soft_joint_pos_limits',None))
        if limits is None:raise ValueError('Native joint limits unavailable: '+label)
        limits=np.asarray(_plain(limits),float)
        if limits.shape==(1,n,2):limits=limits[0]
        limits=_array(limits,(n,2),label+' limits')
        if not 1e-5<=q_tolerance<=.05:raise ValueError('Invalid measured joint readback tolerance')
        if np.any(q<limits[:,0]-q_tolerance)or np.any(q>limits[:,1]+q_tolerance):raise ValueError('Checkpoint joint position exceeds native limit: '+label)
        if not callable(getattr(asset,'write_joint_state_to_sim',None)):raise ValueError('Native joint state API unavailable: '+label)
        targets=row.get('drive_targets')
        if not isinstance(targets,dict)or set(targets)!=set(DRIVES):raise ValueError('Complete drive target schema required: '+label)
        values={}
        for key,(field,method)in DRIVES.items():
            raw=targets[key];value=(q.copy()if key=='position'else np.zeros(n))if raw is None else _array(raw,(n,),label+' '+key+' target')
            if not callable(getattr(asset,method,None)):raise ValueError('Native drive target API unavailable: '+label+'/'+method)
            if key=='position'and (np.any(value<limits[:,0]-1e-5)or np.any(value>limits[:,1]+1e-5)):
                raise ValueError('Drive position target exceeds native joint limit: '+label)
            values[key]=value
        plan.update(q=q,qd=qd,drives=values)
    return plan


def restore_startup(controller,checkpoint):
    """Validate everything before writes, then restore a new diagnostic world.

    Does not advance physics or copy evaluator completion labels/counters. A
    failed native write consumes admission, so a partially restored world must
    be discarded rather than retrying it. No existing episode is restarted.
    """
    _startup(controller);value=_plain(copy.deepcopy(checkpoint));signature=value.pop('checkpoint_sha256',None)
    if signature!=_hash(value):raise ValueError('Engineering checkpoint integrity hash mismatch')
    if any(k in value for k in ('evaluator','success','strict_success','task_score_100','initial_sealed')):raise ValueError('Evaluator/success labels must not be restored')
    if value.get('schema')!=SCHEMA or value.get('diagnostic_only')is not True:raise ValueError('Explicit diagnostic-only engineering checkpoint required')
    if value.get('state_quality')not in ('measured_native_state','measured_pose_fixture'):raise ValueError('Unknown engineering checkpoint state quality')
    if value.get('state_quality')=='measured_pose_fixture'and not value.get('assumptions'):
        raise ValueError('Measured-pose fixtures require explicit velocity/hold assumptions')
    if not isinstance(value.get('stage'),str)or not value['stage']:raise ValueError('Engineering stage missing')
    if value.get('identity')!=identity(controller):raise ValueError('Checkpoint assignment/source/profile/physical geometry mismatch')
    if not isinstance(value.get('context'),dict)or not isinstance(value.get('assumptions'),list)or any(not isinstance(x,str)for x in value['assumptions']):raise ValueError('Explicit JSON context and textual assumptions required')
    source=value.get('source',{})
    if type(source.get('steps'))is not int or source['steps']<0 or type(source.get('physics_ticks'))is not int or source['physics_ticks']<0 or not float(source.get('dt',0))>0 or not math.isclose(float(source.get('dt',0)),float(controller.dt),rel_tol=0,abs_tol=1e-12):
        raise ValueError('Invalid native checkpoint time metadata')
    scene=controller.scene;plans=[]
    from .engineering_e40_native_readback import measured_tolerances
    measured_q_tolerances=measured_tolerances(scene,signature)
    # E44's known revolute Crease may retain tiny compliant solver overshoot.
    # The sealed measured native q is restored unchanged; prismatic fingers,
    # drive targets, limits, measured-pose fixtures and scoring stay unchanged.
    if (value.get('state_quality')=='measured_native_state' and scene.spec.get('id')=='E44'
            and value.get('mechanisms',{}).get('cardboard',{}).get('joint_names')==['Crease']):
        measured_q_tolerances['mechanisms/cardboard']=1e-4
    for group,assets,articulated in (('objects',scene.objects,False),('robots',scene.robots,True),('mechanisms',getattr(scene,'mechanisms',{}),True)):
        rows=value.get(group)
        if not isinstance(rows,dict)or set(rows)!=set(assets):raise ValueError('Checkpoint actor identity mismatch: '+group)
        if articulated and any(v is None for row in rows.values()for v in row.get('drive_targets',{}).values())and not value['assumptions']:
            raise ValueError('Missing drive targets require explicit hold/zero assumptions')
        plans.extend(_validate_asset(scene,asset,rows[name],articulated,group+'/'+name,
            measured_q_tolerances.get(group+'/'+name,1e-5))for name,asset in assets.items())
    controls=value.get('controller',{});grips=controls.get('grips');tcp=controls.get('tcp_targets_base')
    grip_config=scene.embodiment.config.get('gripper',{});grip_values=[*grip_config.get('open',[.04]),*grip_config.get('closed',[0.])]
    grip_low,grip_high=min(grip_values),max(grip_values)
    if not isinstance(grips,dict)or set(grips)!=set(scene.robots)or any(type(x)not in(int,float)or not grip_low<=x<=grip_high for x in grips.values()):raise ValueError('Invalid engineering gripper commands')
    if not isinstance(tcp,dict)or set(tcp)!=set(scene.robots):raise ValueError('Checkpoint TCP target identity mismatch')
    for side,pose in tcp.items():_array(pose['position'],(3,),side+' target');_quat(pose['quaternion'],side+' target')
    for key in ('rolling_reference','rolling_reference_velocity'):
        rows=controls.get(key)
        if not isinstance(rows,dict)or set(rows)-set(scene.robots):raise ValueError('Invalid rolling-cache actor identity')
        for side,row in rows.items():
            count=len(controller.ids[side][0]);_array(row,(1,count),key+'/'+side)
    gripper_reference_keys=('gripper_reference','gripper_reference_velocity')
    has_gripper_reference=any(key in controls for key in gripper_reference_keys)
    if has_gripper_reference:
        if not all(key in controls for key in gripper_reference_keys):raise ValueError('Complete gripper reference state required')
        from .public_gripper_reference import parameters
        reference_limits=parameters(scene.embodiment.config.get('control',{}))
        if reference_limits is None:raise ValueError('Gripper reference checkpoint requires the configured public profile')
        if any(not isinstance(controls[key],dict)for key in gripper_reference_keys):raise ValueError('Invalid gripper reference dictionaries')
        if set(controls[gripper_reference_keys[0]])!=set(controls[gripper_reference_keys[1]]):raise ValueError('Gripper reference/velocity actor mismatch')
        for key in gripper_reference_keys:
            rows=controls[key]
            if not isinstance(rows,dict)or set(rows)-set(scene.robots):raise ValueError('Invalid gripper reference actor identity')
            for side,row in rows.items():
                count=len(controller.ids[side][1]);value_array=_array(row,(1,count),key+'/'+side)
                if key=='gripper_reference_velocity':
                    if np.any(np.abs(value_array)>reference_limits[0]+1e-8):raise ValueError('Gripper reference velocity exceeds profile')
                elif np.any(value_array<grip_low-1e-8)or np.any(value_array>grip_high+1e-8):raise ValueError('Gripper reference outside source opening bounds')
    contact_keys=('gripper_contact_anchor','gripper_contact_active')
    if any(key in controls for key in contact_keys):
        if not all(key in controls for key in contact_keys)or getattr(controller,'_public_gripper_contact_preload',None)is None:raise ValueError('Complete configured contact-hold checkpoint required')
        if set(controls[contact_keys[0]])!=set(controls[contact_keys[1]]):raise ValueError('Contact-hold actor mismatch')
        for key in contact_keys:
            rows=controls[key]
            if not isinstance(rows,dict)or set(rows)-set(scene.robots):raise ValueError('Contact-hold actor identity mismatch')
            for side,row in rows.items():
                values=_array(row,(1,len(controller.ids[side][1])),key+'/'+side)
                if key=='gripper_contact_active':
                    if not np.isin(values,[0,1]).all():raise ValueError('Binary contact mask required')
                elif np.any(values<0)or np.any(values>.04+1e-8):raise ValueError('Contact anchor outside physical gripper range')
    materials=value.get('passive_material');entries=getattr(scene,'passive_efforts',{})
    if not isinstance(materials,dict)or set(materials)!=set(entries):raise ValueError('Passive material identity mismatch')
    for name,record in materials.items():
        entry=entries[name];model=entry['model']
        if type(model).__name__!='ElastoPlasticHinge'or record.get('joint')!=entry['joint']or record.get('parameters')!={k:float(getattr(model,k))for k in MATERIAL_PARAMETERS}:
            raise ValueError('Passive material or constitutive parameters changed')
        _array([record['plastic_rest_angle_rad']],(1,),'plastic rest angle')
        asset=scene.mechanisms[name];index=list(asset.joint_names).index(entry['joint'])
        raw_limits=getattr(asset.data,'joint_pos_limits',None)
        if raw_limits is None:raw_limits=getattr(asset.data,'soft_joint_pos_limits',None)
        limits=np.asarray(_plain(raw_limits),float).reshape(-1,len(asset.joint_names),2)[0,index]
        envelope=float(model.yield_moment_nm/model.stiffness_nm_per_rad)+1e-5
        if not limits[0]-envelope<=record['plastic_rest_angle_rad']<=limits[1]+envelope:
            raise ValueError('Plastic rest state lies outside reachable material history')
    # All validation above is pure. Consume startup admission before the first
    # irreversible simulator write; exceptions cannot be retried on this world.
    controller._engineering_restore_attempted=True
    for plan in plans:
        asset=plan['asset'];root=_tensor_like(asset.data.root_state_w,[plan['root'].tolist()])
        if plan['kinematic']:asset.write_root_pose_to_sim(root[:,:7])
        elif callable(getattr(asset,'write_root_state_to_sim',None)):asset.write_root_state_to_sim(root)
        else:
            asset.write_root_pose_to_sim(root[:,:7]);asset.write_root_velocity_to_sim(root[:,7:])
        if plan['articulated']:
            q=_tensor_like(asset.data.joint_pos,[plan['q'].tolist()]);qd=_tensor_like(asset.data.joint_vel,[plan['qd'].tolist()])
            asset.write_joint_state_to_sim(q,qd)
            for key,(field,method)in DRIVES.items():getattr(asset,method)(_tensor_like(asset.data.joint_pos,[plan['drives'][key].tolist()]))
    controller.grips=dict(grips)
    for side,pose in tcp.items():
        old=controller.targets[side];controller.targets[side]=(_tensor_like(old[0],[pose['position']]),_tensor_like(old[1],[pose['quaternion']]))
    for key,attribute in (('rolling_reference','_public_reference'),('rolling_reference_velocity','_public_reference_velocity')):
        setattr(controller,attribute,{side:_tensor_like(scene.robots[side].data.joint_pos,[row[0]])for side,row in controls[key].items()})
    for key,attribute in (('gripper_reference','_public_gripper_reference'),('gripper_reference_velocity','_public_gripper_reference_velocity')):
        # Old checkpoints contain no ramp cache: discard fresh-world caches so
        # the first restored tick seeds once from actual restored joint q.
        setattr(controller,attribute,{side:_tensor_like(scene.robots[side].data.joint_pos,[row[0]])for side,row in controls.get(key,{}).items()})
    for key,attribute in (('gripper_contact_anchor','_public_gripper_contact_anchor'),('gripper_contact_active','_public_gripper_contact_active')):
        setattr(controller,attribute,{side:_tensor_like(scene.robots[side].data.joint_pos,[row[0]])for side,row in controls.get(key,{}).items()})
    for name,record in materials.items():entries[name]['model'].plastic_rest_angle_rad=record['plastic_rest_angle_rad']
    controller._engineering_diagnostic_only=True
    return dict(schema=SCHEMA,diagnostic_only=True,checkpoint_sha256=signature,stage=value['stage'],context=value.get('context',{}),
        state_quality=value['state_quality'],source=source,assumptions=value.get('assumptions',[]),
        source_readback=value.get('readback',dict(available=False)),
        physics_advanced=False,evaluator_history_restored=False,source_initial_full_positive=False,
        requires_settle_and_contact_validation=True,restore_consumed=True,
        measured_native_joint_readback_tolerances_rad=measured_q_tolerances,
        pose_only_native_kinematic_roots=[plan['label']for plan in plans if plan['kinematic']])
