"""Engineering-only E29 grasp height from actual source and finger collisions."""
import json
from pathlib import Path
import numpy as np
from .execution_design import REVISION_V3,source_sha256

MALLET_SHA='b1d37e3d1e8bc55b4d81e39b4640ea0eafa1e2a5850eef49a3487ab31363d2ac'


def safe_height(point,tip,finger_geometry,shaft_world,floor=.8):
    """Keep the measured finger toes off the table, inside the real shaft band.

    Geometric overlap is only a prerequisite. The caller must subsequently
    establish the normal native two-finger grip; this does not assert grasp.
    """
    point=np.asarray(point,float);tip=np.asarray(tip,float);shaft=np.asarray(shaft_world,float)
    if point.shape!=(3,)or tip.shape!=(3,)or shaft.ndim!=2 or shaft.shape[1]!=3 or len(shaft)<4:
        raise ValueError('Actual shaft and TCP geometry required')
    lowest=float(finger_geometry['lowest_z_task_m'])
    if not np.isfinite(np.r_[point,tip,shaft.ravel(),lowest,floor]).all():raise ValueError('Nonfinite grasp geometry')
    safe=float(floor-(lowest-tip[2])+.0003)
    result=point.copy();result[2]=max(float(point[2]),safe)
    upper=float(shaft[:,2].max());lower=float(shaft[:,2].min())
    if result[2]>upper-.0005 or result[2]<lower-.0005:
        raise RuntimeError('Table-clear grasp has no verified shaft height overlap')
    if result[2]-point[2]>.012:raise RuntimeError('Unexpected large mallet grasp height correction')
    return result,dict(source_point_task_m=point.tolist(),safe_point_task_m=result.tolist(),
        measured_tcp_task_m=tip.tolist(),finger_lowest_z_task_m=lowest,table_z_task_m=float(floor),
        shaft_min_z_task_m=lower,shaft_max_z_task_m=upper,grasp_success_asserted=False)


def actual_shaft_points(policy,ref):
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    a=policy.a;actor=ref['actor'];stage=omni.usd.get_context().get_stage()
    body=stage.GetPrimAtPath(f'{a.scene.root_path}/Props/{actor}')
    if not body:raise RuntimeError('Actual mallet root missing')
    cache=UsdGeom.XformCache();inverse=cache.GetLocalToWorldTransform(body).GetInverse();vertices=[]
    for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh):continue
        ancestor=prim;collidable=False;enabled=True
        while ancestor and ancestor!=body:
            if ancestor.HasAPI(UsdPhysics.CollisionAPI):
                collidable=True;enabled=enabled and bool(UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get())
            ancestor=ancestor.GetParent()
        if not collidable or not enabled:continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
        matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
        vertices.append(points@matrix[:3,:3]+matrix[3,:3])
    if not vertices:raise RuntimeError('Actual mallet collision geometry missing')
    local=np.concatenate(vertices);grasp=np.asarray(ref['local'],float)
    # Source-reviewed long shaft lies along actor X. A short section around
    # the original grasp excludes the broad hammer head from overlap checks.
    section=local[np.abs(local[:,0]-grasp[0])<.008]
    if len(section)<4:raise RuntimeError('Reviewed mallet shaft section missing')
    state,_=policy.snapshot();value=state[actor]
    return section@np.asarray(value['mat'],float).T+np.asarray(value['pos'],float)


def table_clear_mallet_grasp(policy,ref,side,point):
    spec=policy.spec;d=spec.get('execution_design',{})
    if (spec['id']!='E29'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not policy.a.control_report.get('engineering_reference_only')):
        raise ValueError('Source-checked isolated E29 engineering reference required')
    obj=next(o for o in spec['objects']if o['id']==ref.get('actor'))
    if obj.get('source_asset',{}).get('sha256')!=MALLET_SHA:raise ValueError('Unreviewed mallet source')
    geometry=policy.a.finger_geometry(side);shaft=actual_shaft_points(policy,ref)
    # Layout.top is in rig world coordinates; convert the actual table center
    # into this room's task frame, including the pooled room origin.
    scene=policy.a.scene;table=scene.embodiment.config['layout']['table']
    world=np.asarray(table['position'],float)+np.asarray(getattr(scene,'origin',(0.,0.,0.)))
    world[2]=float(table['top'])+float(getattr(scene,'origin',(0.,0.,0.))[2])
    floor=float(scene.world_to_task(world)[2])
    target,receipt=safe_height(point,policy.tip(side),geometry,shaft,floor)
    receipt.update(task='E29',stage=policy.a.stage,side=side,source_asset_sha256=MALLET_SHA,
        source='actual_collision_mesh_and_current_native_body_pose',original_rule_unchanged=True,
        collision_vertex_count=len(shaft),action_step=policy.c.steps)
    with (Path(policy.a.out)/'mallet-grasp-geometry.private.jsonl').open('a')as f:f.write(json.dumps(receipt)+'\n')
    return target
