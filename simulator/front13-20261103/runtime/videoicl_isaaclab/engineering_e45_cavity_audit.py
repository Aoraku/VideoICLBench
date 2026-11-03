"""Read native cup/ball contact geometry at one tilted engineering checkpoint."""
import json
import numpy as np


def audit(policy,side='right',geometry_only=False):
    import carb,omni.physx,omni.usd
    from pxr import Usd,UsdPhysics,PhysxSchema,PhysicsSchemaTools
    from .engineering_tool_geometry_audit import _write
    from .engineering_cooked_geometry_audit import cooking_metadata
    from .source_reviewed_collisions import ray_hit_value
    from .engineering_checkpoint import capture
    if policy.task!='E45'or not getattr(policy.c,'_engineering_diagnostic_only',False):
        raise ValueError('Restored single-room E45 native cavity diagnostic only')
    scene=policy.a.scene;name=policy.s['containers']['cup']['object'];balls=policy.s['groups']['balls']
    ref=dict(actor=name,local=policy.s['containers']['cup']['grasp_local'])
    state,contacts=policy.snapshot();cup=state[name]
    if geometry_only:
        if any(cup['grasp'])or not policy.contact(name,'table'):
            raise ValueError('Geometry-only audit requires the actual source cup supported and released')
    else:
        policy.require_held(ref,side)
        if cup['mat'][2,2]>-.7:raise ValueError('Actual substantially inverted held cup required')
    def guard():
        policy.require_held(ref,side)
        if any(policy.contact(b,f'{s}_finger{i}')for b in balls for s in('left','right')for i in(1,2)):
            raise ValueError('Actual hand/ball interaction in passive cavity diagnostic')
    stage=omni.usd.get_context().get_stage();query=omni.physx.get_physx_scene_query_interface()
    def rays(actor,origin,direction,distance):
        expected=scene.root_path+'/Props/'+actor;hits=[]
        def receive(hit):
            path=ray_hit_value(hit,'rigidBody','rigid_body')
            path=str(path if isinstance(path,str)else PhysicsSchemaTools.intToSdfPath(path))
            if path==expected:
                point=scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float))
                normal=np.asarray(scene.layout.task_rotation).T@np.asarray(ray_hit_value(hit,'normal'),float)
                hits.append(dict(position_task=point.tolist(),normal_task=normal.tolist(),collision=str(ray_hit_value(hit,'collision'))))
            return True
        world=scene.task_to_world(origin);wd=np.asarray(scene.layout.task_rotation)@direction
        query.raycast_all(carb.Float3(*map(float,world)),carb.Float3(*map(float,wd)),distance,receive)
        return hits
    p=np.asarray(cup['pos']);r=np.asarray(cup['mat']);cup_rows=[]
    for x in np.linspace(-.020,.020,7):
        for y in np.linspace(-.020,.020,7):
            origin=p+r@np.array([x,y,.12]);hits=rays(name,origin,-r[:,2],.23)
            for h in hits:h['cup_local']=(r.T@(np.asarray(h['position_task'])-p)).tolist()
            cup_rows.append(dict(cup_local_xy=[float(x),float(y)],native_cup_hits=hits,
                first_hit_local_z=max((h['cup_local'][2]for h in hits),default=None)))
    ball_rows={}
    for ball in balls:
        center=np.asarray(state[ball]['pos']);rows=[]
        for x in np.linspace(-.009,.009,9):
            for y in np.linspace(-.009,.009,9):
                origin=center+np.array([x,y,-.04]);hits=rays(ball,origin,np.array([0.,0.,1.]),.08)
                hit=min(hits,key=lambda z:z['position_task'][2])if hits else None
                rows.append(dict(gravity_transverse_xy_m=[float(x),float(y)],native=hit))
        ball_rows[ball]=rows
    flags={};masses={};metadata={}
    for actor in[name,*balls]:
        root=stage.GetPrimAtPath(scene.root_path+'/Props/'+actor)
        rigid=PhysxSchema.PhysxRigidBodyAPI(root)
        flags[actor]=dict(disable_gravity_usd=rigid.GetDisableGravityAttr().Get(),
            rigid_body_enabled=UsdPhysics.RigidBodyAPI(root).GetRigidBodyEnabledAttr().Get(),colliders=[])
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                collision=PhysxSchema.PhysxCollisionAPI(prim)
                flags[actor]['colliders'].append(dict(path=str(prim.GetPath()),contact_offset_m=collision.GetContactOffsetAttr().Get(),rest_offset_m=collision.GetRestOffsetAttr().Get(),
                    approximation=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()if prim.HasAPI(UsdPhysics.MeshCollisionAPI)else str(prim.GetTypeName())))
        view=scene.objects[actor].root_physx_view
        masses[actor]=dict(masses_kg=view.get_masses().cpu().tolist(),inertias_kg_m2=view.get_inertias().cpu().tolist(),centres_of_mass=view.get_coms().cpu().tolist())
        for method in('get_disable_gravities',):
            if hasattr(view,method):
                try:flags[actor][method]=getattr(view,method)().cpu().tolist()
                except Exception as exc:flags[actor][method+'_read_error']=str(exc)
        metadata[actor]=cooking_metadata(scene,actor,side)
    before=capture(policy.c,'e45-before-passive-cavity-readback')
    tick_receipt=(dict(actual_physics_ticks=0,public_actions_issued=0,geometry_only=True)
        if geometry_only else policy.a.engineering_passive_ticks(250,guard))
    after=capture(policy.c,'e45-after-passive-cavity-readback')
    result=dict(schema='e45-native-cavity-gravity-diagnostic-v1',geometry_only=geometry_only,native_shape_flags=flags,native_mass_properties=masses,
        cooking_metadata=metadata,cup_exit_rays=cup_rows,ball_bottom_native_rays=ball_rows,
        before_native_state=before,after_native_state=after,passive_tick_receipt=tick_receipt,
        actual_contacts_before=[sorted(x)for x in contacts],source_objects=policy.spec['objects'])
    return _write(policy,'native-cup-cavity-audit.private.json',result)
