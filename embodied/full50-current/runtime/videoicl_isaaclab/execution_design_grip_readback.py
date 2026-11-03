"""Passive room-aware native contact/torque readback for engineering grips.

Creates independent Tensor read views only. Does not author USD schemas,
materials, contact geometry, robot targets, object states or evaluator history.
Friction-point count is not asserted to be an independent PhysX patch/anchor ID.
"""
import json
import numpy as np
from .author_native_grip_probe import cpu_copy,decode_patch
from .author_mplib_planner import _matrix


def install(author,actor,side,*,max_samples=250,stem='native-grip',additional_targets=()):
    if not author.control_report.get('engineering_reference_only'):
        raise ValueError('Passive grip readback is engineering-only')
    scene=author.scene;c=author.c
    if scene.spec['id']not in tuple(f'E{i:02d}'for i in range(26,38)):
        raise ValueError('Passive grip readback outside explicit task scope')
    if side not in scene.robots or actor not in scene.objects:raise ValueError('Unknown actual grip pair')
    from pxr import Usd,UsdGeom,UsdPhysics,PhysxSchema
    stage=c.sim.stage;cache=UsdGeom.XformCache();sensor=scene.contacts[actor][0]
    physics=sensor._physics_sim_view;tool=scene.objects[actor];tool_path=str(tool.root_physx_view.prim_paths[0])
    finger_paths=[f'{scene.root_path}/{side}_robot/{body}'for body in scene.embodiment.fingers]
    extra={}
    for name in additional_targets:
        if name=='table':extra[name]=scene.rig_root+'/Table'
        elif name in scene.objects and name!=actor:extra[name]=str(scene.objects[name].root_physx_view.prim_paths[0])
        else:raise ValueError('Additional passive pair must name an actual scene body')
    views={path:physics.create_rigid_contact_view(tool_path,filter_patterns=[path],max_contact_data_count=1024)for path in [*finger_paths,*extra.values()]}
    if any(v.sensor_count!=1 or v.filter_count!=1 for v in views.values()):raise ValueError('Exact tool/finger view required')
    def props(view):
        result={}
        for name in ('get_material_properties','get_contact_offsets','get_rest_offsets','get_coms','get_masses','get_inertias'):
            try:result[name]=cpu_copy(getattr(view,name)()).tolist()
            except Exception as exc:result[name]={'error':type(exc).__name__+': '+str(exc)}
        return result
    collisions=[]
    for root_path in [tool_path,*finger_paths]:
        root=stage.GetPrimAtPath(root_path)
        if not root:raise ValueError('Actual native collision root missing: '+root_path)
        inverse=cache.GetLocalToWorldTransform(root).GetInverse()
        for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):continue
            api=PhysxSchema.PhysxCollisionAPI(prim);row=dict(root=root_path,path=str(prim.GetPath()),schemas=prim.GetAppliedSchemas())
            for field,attr in [('torsionalPatchRadius',api.GetTorsionalPatchRadiusAttr()),('minTorsionalPatchRadius',api.GetMinTorsionalPatchRadiusAttr())]:
                key='physxCollision:'+field
                try:fallback=Usd.SchemaRegistry().FindAppliedAPIPrimDefinition('PhysxCollisionAPI').GetAttributeFallbackValue(key)
                except Exception as exc:fallback={'error':repr(exc)}
                row[field]=dict(value=attr.Get(),authored=attr.HasAuthoredValueOpinion(),registered_schema_fallback=fallback)
            if prim.IsA(UsdGeom.Mesh):
                mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),float)
                transform=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
                row['vertices_body_local_m']=(points@transform[:3,:3]+transform[3,:3]).tolist()
                row['approximation']=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()
            collisions.append(row)
    scenes=[]
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.Scene):
            s=UsdPhysics.Scene(prim);p=PhysxSchema.PhysxSceneAPI(prim)
            scenes.append(dict(path=str(prim.GetPath()),gravity_direction=list(s.GetGravityDirectionAttr().Get()),gravity_magnitude=s.GetGravityMagnitudeAttr().Get(),usd_solver_type=p.GetSolverTypeAttr().Get()))
    active=[s for s in scenes if s['path']==getattr(c.sim.cfg,'physics_prim_path',None)]or scenes
    if len(active)!=1:raise ValueError('One actual native physics scene required')
    gravity=np.asarray(active[0]['gravity_direction'],float);gravity=gravity/np.linalg.norm(gravity)*float(active[0]['gravity_magnitude'])
    actual=dict(tool=props(tool.root_physx_view))
    for path in finger_paths:
        try:actual[path]=props(physics.create_rigid_body_view(path))
        except Exception as exc:actual[path]={'error':repr(exc)}
    robot=scene.robots[side];finger_ids=c.ids[side][1]
    drives={'joint_names':[robot.joint_names[i]for i in finger_ids]}
    for field in ('joint_stiffness','joint_damping','joint_effort_limits','joint_pos','joint_vel','computed_torque','applied_torque'):
        try:drives[field]=cpu_copy(getattr(robot.data,field)[0,finger_ids]).tolist()
        except Exception as exc:drives[field]={'error':repr(exc)}
    metadata=dict(read_only=True,task=scene.spec['id'],side=side,actor=actor,room_root=scene.root_path,
        active_scene=active[0],runtime_cfg_solver_type=getattr(c.sim.cfg.physx,'solver_type',None),colliders=collisions,
        actual_properties=actual,actual_finger_drives=drives,buffer_capacity_per_pair=1024,
        additional_read_only_contact_targets=extra,
        buffer_semantics='Valid counts/starts rows only; forces act on sensor tool; raw friction-point count does not expose patch ID or anchor cardinality')
    (author.out/(stem+'-properties.private.json')).write_text(json.dumps(metadata,indent=2)+'\n')
    count=[0];last=[None]
    def record(controller,render):
        if count[0]>=max_samples or last[0]==controller.physics_ticks:return
        last[0]=controller.physics_ticks;count[0]+=1;rows={};centers=[];wrenches=[]
        root=_matrix(cpu_copy(tool.data.root_pos_w[0]),cpu_copy(tool.data.root_quat_w[0]))
        com_local=cpu_copy(tool.root_physx_view.get_coms()).reshape(-1,7)[0,:3];com=root[:3,:3]@com_local+root[:3,3]
        mass=float(cpu_copy(tool.root_physx_view.get_masses()).reshape(-1)[0])
        for path,view in views.items():
            try:
                normal=decode_patch(view.get_contact_data(controller.dt));friction=decode_patch(view.get_friction_data(controller.dt),True)
                force=np.asarray(normal['force']).reshape(-1,1)*normal['normal'];matrix=cpu_copy(view.get_contact_force_matrix(controller.dt))[0,0]
                weights=np.abs(np.asarray(normal['force']).reshape(-1));total=float(weights.sum())
                if total>0:centers.append((weights[:,None]*normal['point']).sum(0)/total)
                row=dict(normal={k:v.tolist()for k,v in normal.items()},friction={k:v.tolist()for k,v in friction.items()},
                    normal_point_count=len(weights),reported_friction_point_count=len(friction['force']),
                    independent_matrix_force_world_n=matrix.tolist(),point_force_sum_error_n=float(np.linalg.norm(force.sum(0)-matrix)))
                wrenches.append((force,normal['point'],np.asarray(friction['force']).reshape(-1,3),friction['point']))
                rows[path]=row
            except Exception as exc:rows[path]={'error':repr(exc)}
        robot=scene.robots[side];names=list(robot.body_names);positions=cpu_copy(robot.data.body_pos_w[0])
        jaw=positions[names.index(scene.embodiment.fingers[0])]-positions[names.index(scene.embodiment.fingers[1])];jaw/=np.linalg.norm(jaw)
        hand_index=controller.ids[side][2]
        hand=_matrix(positions[hand_index],cpu_copy(robot.data.body_quat_w[0,hand_index]))
        hand_angular=cpu_copy(robot.data.body_ang_vel_w[0,hand_index])
        hand_linear=cpu_copy(robot.data.body_lin_vel_w[0,hand_index])
        tool_velocity=cpu_copy(tool.data.root_vel_w[0])
        row=dict(tick=controller.physics_ticks,steps=controller.steps,stage=author.stage,pairs=rows,
            tool_com_world_m=com.tolist(),tool_com_actor_local_m=com_local.tolist(),tool_root_world=root.tolist(),
            tool_velocity_world=tool_velocity.tolist(),jaw_axis_world=jaw.tolist(),
            measured_hand_world=hand.tolist(),tool_relative_hand_matrix=(np.linalg.inv(hand)@root).tolist(),
            hand_angular_velocity_world=hand_angular.tolist(),relative_spin_about_jaw_rad_s=float((tool_velocity[3:]-hand_angular)@jaw),
            hand_linear_velocity_world=hand_linear.tolist(),
            finger_positions_m=cpu_copy(robot.data.joint_pos[0,c.ids[side][1]]).tolist(),
            actual_tool_grasps=list(controller.snapshot()[0][actor]['grasp']))
        if len(centers)==2:
            midpoint=np.mean(centers,0);gn=np.cross(com-midpoint,mass*gravity)
            normal_torque=sum((np.cross(points-midpoint,force).sum(0)for force,points,_,_ in wrenches),np.zeros(3))
            friction_torque=sum((np.cross(points-midpoint,force).sum(0)for _,_,force,points in wrenches),np.zeros(3))
            row.update(contact_midpoint_world_m=midpoint.tolist(),gravity_torque_jaw_nm=float(gn@jaw),
                normal_torque_jaw_nm=float(normal_torque@jaw),friction_torque_jaw_nm=float(friction_torque@jaw))
        with (author.out/(stem+'-patches.private.jsonl')).open('a')as stream:stream.write(json.dumps(row)+'\n')
    c.tick_hooks.append(record)
    return dict(read_only=True,metadata=metadata,max_samples=max_samples,samples=count)
