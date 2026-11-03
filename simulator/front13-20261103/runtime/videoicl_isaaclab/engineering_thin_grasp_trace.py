"""One public thin-card close with read-only per-tick native geometry evidence."""
import json
import numpy as np
from scipy.spatial import ConvexHull
from .realworld_tool_expert import ToolExecutionError


def collision_offsets(author,side,actor):
    import omni.usd
    from pxr import Usd,UsdPhysics,PhysxSchema
    stage=omni.usd.get_context().get_stage();rows=[]
    roots=[f'{author.scene.root_path}/Props/{actor}']+[f'{author.scene.root_path}/{side}_robot/{n}'for n in author.scene.embodiment.fingers]
    for root in roots:
        for prim in Usd.PrimRange(stage.GetPrimAtPath(root),Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):continue
            chain=[];node=prim
            while node:
                values={}
                for suffix in('contactOffset','restOffset'):
                    attr=node.GetAttribute('physxCollision:'+suffix)
                    api=PhysxSchema.PhysxCollisionAPI(node)
                    fallback=(api.GetContactOffsetAttr()if suffix=='contactOffset'else api.GetRestOffsetAttr())
                    values[suffix]=dict(usd_attribute_valid=bool(attr),authored=bool(attr and attr.HasAuthoredValueOpinion()),value=None if not attr or attr.Get()is None else str(attr.Get()),schema_query_value=None if not fallback or fallback.Get()is None else str(fallback.Get()))
                if node==prim or any(v['usd_attribute_valid']or v['schema_query_value']is not None for v in values.values()):chain.append(dict(path=str(node.GetPath()),applied_schemas=list(node.GetAppliedSchemas()),attributes=values))
                node=node.GetParent()
            rows.append(dict(collider=str(prim.GetPath()),enabled=bool(UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()),hierarchy=chain))
    defaults={};definition=Usd.SchemaRegistry().FindAppliedAPIPrimDefinition('PhysxCollisionAPI')
    if definition:
        for name in('physxCollision:contactOffset','physxCollision:restOffset'):
            spec=definition.GetSchemaAttributeSpec(name)
            defaults[name]=None if not spec else str(spec.default)
    native={}
    for name,asset in((side+'_robot',author.scene.robots[side]),(actor,author.scene.objects[actor])):
        view=asset.root_physx_view;record=dict(view_class=type(view).__name__,available_shape_offset_getters=[n for n in dir(view)if n.startswith('get_')and('offset'in n or'shape'in n)])
        for method in('get_contact_offsets','get_rest_offsets'):
            getter=getattr(view,method,None)
            if not callable(getter):continue
            try:
                value=getter()
                if hasattr(value,'cpu'):value=value.cpu()
                record[method]=value.tolist()if hasattr(value,'tolist')else str(value)
            except Exception as exc:record[method]=dict(read_error=type(exc).__name__+': '+str(exc))
        if hasattr(asset,'body_names'):record['body_names']=list(asset.body_names)
        native[name]=record
    return dict(colliders=rows,schema_defaults=defaults,native_view_offsets=native,no_usd_writes=True)


def close_current(p,ref,side,expected_q,card_face_fraction=.85,initial_lift_step_mm=2.,card_points_local=None):
    from isaaclab.utils.math import matrix_from_quat
    from .engineering_cooked_geometry_audit import native_cooked_meshes
    from .execution_design_card_direct import prove_bilateral_lift
    from .engineering_thin_suffix import save_stage
    a=p.a;native=native_cooked_meshes(a,p,ref,side);expected=np.broadcast_to(np.asarray(expected_q,float),(2,)).copy()
    metadata=dict(native_geometry=native,collision_offsets=collision_offsets(a,side,ref['actor']),expected_closed_finger_q_m=expected.tolist(),reference_profile_control={k:v for k,v in a.scene.embodiment.config['control'].items()if k.startswith('public_gripper_reference_')},task_to_world_rotation=np.asarray(a.scene.layout.task_rotation).tolist(),diagnostic_only=True)
    # Exact readonly one-card/one-finger Tensor views expose native manifold
    # points/normals and effective offsets without authoring collision APIs.
    from .author_native_grip_probe import decode_patch,cpu_copy
    physics=next(iter(a.scene.contacts.values()))[0]._physics_sim_view
    patch_views={};metadata['actual_native_finger_offsets']={}
    metadata['actual_native_material_properties']={}
    for name in a.scene.embodiment.fingers:
        body_path=f'{a.scene.root_path}/{side}_robot/{name}'
        try:
            body_view=physics.create_rigid_body_view(body_path)
            metadata['actual_native_finger_offsets'][name]=dict(contact_offsets_m=cpu_copy(body_view.get_contact_offsets()).tolist(),rest_offsets_m=cpu_copy(body_view.get_rest_offsets()).tolist())
            try:
                getter=getattr(body_view,'get_material_properties',None)
                metadata['actual_native_material_properties'][name]=dict(available=callable(getter),getter='get_material_properties',raw=None if not callable(getter)else cpu_copy(getter()).tolist(),api_doc=None if not callable(getter)else str(getter.__doc__)[:1800])
            except Exception as exc:metadata['actual_native_material_properties'][name]=dict(read_error=type(exc).__name__+': '+str(exc))
            view=physics.create_rigid_contact_view(f'{a.scene.root_path}/Props/{ref["actor"]}',filter_patterns=[body_path],max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=1:raise ValueError('Exact card/finger contact view required')
            patch_views[name]=view
        except Exception as exc:metadata['actual_native_finger_offsets'][name]=dict(read_error=type(exc).__name__+': '+str(exc))
    for name,body_path in ((ref['actor'],f'{a.scene.root_path}/Props/{ref["actor"]}'),('table',a.scene.rig_root+'/Table')):
        try:
            view=physics.create_rigid_body_view(body_path);getter=getattr(view,'get_material_properties',None)
            metadata['actual_native_material_properties'][name]=dict(available=callable(getter),getter='get_material_properties',raw=None if not callable(getter)else cpu_copy(getter()).tolist(),api_doc=None if not callable(getter)else str(getter.__doc__)[:1800])
        except Exception as exc:metadata['actual_native_material_properties'][name]=dict(read_error=type(exc).__name__+': '+str(exc))
    (a.out/'thin-grasp-trace-metadata.private.json').write_text(json.dumps(metadata,indent=2))
    source=next(o for o in p.spec['objects']if o['id']==ref['actor']);robot=a.scene.robots[side];parts=[]
    for i,name in enumerate(a.scene.embodiment.fingers):
        row=next(r for r in native['meshes']if r['name']==name)
        if not row['cooked_meshes']:raise ToolExecutionError('Actual native finger hull unavailable for close trace')
        pos=np.asarray(row['native_body_position_task']);rotation=np.asarray(row['native_body_rotation_task']);points=np.concatenate([np.asarray(m['vertices_task'])for m in row['cooked_meshes']]);local=(points-pos)@rotation
        bid=robot.find_bodies(name)[0][0];jaw=np.asarray(a.tcp_rotation_task(side))[:,1]
        if jaw@(np.asarray(native['meshes'][1]['native_body_position_task'])-np.asarray(native['meshes'][2]['native_body_position_task']))<0:jaw=-jaw
        planes=ConvexHull(local).equations;pad=max(planes,key=lambda pl:float((rotation@pl[:3])@((-1.,1.)[i]*jaw)))
        card_pos,card_r=p.frame(ref);z=float(source['size'][2])*float(card_face_fraction)*np.sign(card_r[2,2]);sides=[np.asarray(point)for point in card_points_local]if card_points_local is not None else[np.array([.025,y,z])for y in(-float(source['size'][1]),float(source['size'][1]))]
        selected=min(sides,key=lambda v:float(np.linalg.norm(card_pos+card_r@v-pos)))
        parts.append((name,bid,local,planes,pad,selected))
    sensor,labels=a.scene.contacts[ref['actor']];path=a.out/'thin-grasp-close-ticks.private.jsonl'
    def sample(controller,render):
        card_pos,card_r=p.frame(ref);forces=sensor.data.force_matrix_w.cpu().numpy().reshape(-1,len(labels),3).sum(0);finger_rows=[]
        for name,bid,local,planes,pad,selected in parts:
            rotation=np.asarray(a.scene.layout.task_rotation).T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy();pos=a.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy());point=card_pos+card_r@selected;in_body=rotation.T@(point-pos)
            finger_rows.append(dict(name=name,body_position_task=pos.tolist(),body_rotation_task=rotation.tolist(),native_lowest_z_m=float((local@rotation.T+pos)[:,2].min()),selected_card_side_point_task=point.tolist(),card_point_outside_hull_m=float(np.max(planes[:,:3]@in_body+planes[:,3])),inward_pad_signed_distance_m=float(pad[:3]@in_body+pad[3]),inward_pad_normal_task=(rotation@pad[:3]).tolist()))
        row=dict(physics_tick=int(controller.physics_ticks),action_step=int(controller.steps),tcp=p.tip(side).tolist(),rotation_task=a.tcp_rotation_task(side).tolist(),finger_q_m=robot.data.joint_pos[:,p.c.ids[side][1]].cpu().tolist(),card_position_task=card_pos.tolist(),card_rotation_task=card_r.tolist(),fingers=finger_rows,contact_force_vectors_world={name:forces[j].tolist()for j,name in enumerate(labels)if np.linalg.norm(forces[j])>1e-6})
        row['logical_gripper_goal_m']=float(controller.grips[side])
        if side in getattr(controller,'_public_gripper_reference',{}):
            row['gripper_reference_m']=controller._public_gripper_reference[side].cpu().tolist()
            row['gripper_reference_velocity_m_s']=controller._public_gripper_reference_velocity[side].cpu().tolist()
        row['native_contact_patches']={}
        for name,view in patch_views.items():
            try:
                normal=decode_patch(view.get_contact_data(controller.dt))
                friction=decode_patch(view.get_friction_data(controller.dt),True)
                row['native_contact_patches'][name]=dict(normal={k:v.tolist()for k,v in normal.items()},friction={k:v.tolist()for k,v in friction.items()},force_sign='force*normal and friction act on the card sensor')
            except Exception as exc:row['native_contact_patches'][name]=dict(read_error=type(exc).__name__+': '+str(exc))
        with path.open('a')as stream:stream.write(json.dumps(row)+'\n')
    trace_errors=[]
    lift_steps=[0]
    def observe(controller,render):
        # An evidence observer must never cancel an already accepted action.
        try:
            if lift_steps[0]<4:sample(controller,render)
        except Exception as exc:trace_errors.append(type(exc).__name__+': '+str(exc))
    p.stage('thin-grasp-first-contact-trace');sample(p.c,False);p.c.tick_hooks.append(observe)
    try:
        p.act(side,'GRASP')
        if getattr(p.c,'_public_gripper_limits',None)is not None:
            # One original GRASP goal; idle actions only let that same command
            # reference continue. Neither a new grip goal nor measured-q reset.
            # Bound time by the configured public reference travel. A slower
            # physical close must not inherit a 4.8s timeout from 10mm/s.
            seconds=.04/p.c._public_gripper_limits[0]+2.
            idle_bound=min(128,max(12,int(np.ceil(seconds/max(float(a.scene.embodiment.config['physics']['action_seconds']),.1)))))
            for _ in range(idle_bound):
                q=robot.data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
                qd=robot.data.joint_vel[:,p.c.ids[side][1]].cpu().numpy()
                if p.held(ref,side)and np.max(abs(q-expected))<.003:break
                if np.any(q<expected-.003):raise ToolExecutionError('Slow close crossed planned card width without its actual grip')
                reference=p.c._public_gripper_reference[side].cpu().numpy()
                goal=np.asarray(a.scene.embodiment.gripper_values(p.c.grips[side]/.04))
                if np.max(abs(reference-goal))<1e-7:raise ToolExecutionError('Original GRASP goal fully closed without actual card grip')
                p.stage('thin-grasp-same-goal-idle');p.act()
            else:raise ToolExecutionError('Bounded original GRASP continuation did not form the planned actual grip')
        if trace_errors:raise ToolExecutionError('Read-only close trace failed after the accepted action completed')
        q=robot.data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
        if np.any(q<expected-.003):raise ToolExecutionError('Close trace crossed the planned side-pad width')
        if not p.held(ref,side):raise ToolExecutionError('Close trace did not establish bilateral grip')
        save_stage(a,'trace-real-bilateral',dict(expected_q_m=expected.tolist()))
        def lifted(index):lift_steps[0]=index
        p.stage('thin-grasp-trace-held-lift');raised=prove_bilateral_lift(p,ref,side,initial_lift_step_mm=initial_lift_step_mm,after_action=lifted)
        save_stage(a,'trace-real-card-lift',dict(raised_m=raised));return raised
    finally:
        p.c.tick_hooks.remove(observe)
        if trace_errors:(a.out/'thin-grasp-trace-observer-errors.private.json').write_text(json.dumps(trace_errors))
