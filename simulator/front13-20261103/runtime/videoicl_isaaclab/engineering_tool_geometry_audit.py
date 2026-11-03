"""Read-only native geometry at an admitted engineering checkpoint.

No actions, state writes, contact edits or success assertions. Source vertices
and cooked PhysX ray intersections remain distinct evidence.
"""
import json
import math
import numpy as np


def _write(policy,name,result):
    result.update(diagnostic_only=True,public_actions_issued=0,
                  geometry_or_contact_parameters_changed=False,
                  whole_task_success=False)
    (policy.a.out/name).write_text(json.dumps(result,indent=2)+'\n')
    return result


def ball_support_audit(policy):
    import carb,omni.physx
    from pxr import PhysicsSchemaTools
    from .source_reviewed_collisions import ray_hit_value
    from .engineering_cooked_geometry_audit import cooking_metadata
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_e43_geometry import RAMP_ANGLE_DEGREES
    if policy.task!='E43':raise ValueError('Source gravity-ball audit is E43 only')
    scene=policy.a.scene;state,contacts=policy.snapshot();ball=state['ball'];center=np.asarray(ball['pos'])
    theta=math.radians(RAMP_ANGLE_DEGREES)
    n=np.array([-math.sin(theta),0.,math.cos(theta)])
    tangent=np.array([math.cos(theta),0.,math.sin(theta)]);lateral=np.array([0.,1.,0.])
    query=omni.physx.get_physx_scene_query_interface();body=scene.root_path+'/Props/ball';rows=[]
    direction=np.asarray(scene.layout.task_rotation)@n
    for u in np.linspace(-.012,.012,25):
        for v in np.linspace(-.012,.012,25):
            origin=scene.task_to_world(center+n*(-.03)+tangent*u+lateral*v);hits=[]
            def report(hit):
                actor=ray_hit_value(hit,'rigidBody','rigid_body')
                actor=str(actor if isinstance(actor,str)else PhysicsSchemaTools.intToSdfPath(actor))
                if actor==body:
                    point=scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float))
                    normal=np.asarray(scene.layout.task_rotation).T@np.asarray(ray_hit_value(hit,'normal'),float)
                    hits.append(dict(position_task=point.tolist(),normal_task=normal.tolist(),
                        collision=str(ray_hit_value(hit,'collision'))))
                return True
            query.raycast_all(carb.Float3(*map(float,origin)),carb.Float3(*map(float,direction)),.06,report)
            selected=min(hits,key=lambda h:float((np.asarray(h['position_task'])-center)@n))if hits else None
            rows.append(dict(tangent_offset_m=float(u),lateral_offset_m=float(v),native=selected))
    vertices=material_collision_points_task(policy,{'actor':'ball','local':[0,0,0]})
    obj=next(o for o in policy.spec['objects']if o['id']=='ball')
    result=dict(schema='e43-source-cooked-ball-support-audit-v1',coordinate_frame='room_task',
        source_sha256=obj['source_asset']['sha256'],ramp_angle_degrees=RAMP_ANGLE_DEGREES,
        ramp_up_normal_task=n.tolist(),ball_center_task=center.tolist(),ball_rotation_task=ball['mat'].tolist(),
        source_collision_vertices_task=vertices.tolist(),cooking_metadata=cooking_metadata(scene,'ball','left'),
        scene_query_support=carb.settings.get_settings().get('/physics/enableSceneQuerySupport'),
        actual_contacts=[sorted(x)for x in contacts],
        actual_contact_forces=[dict(bodies=sorted(pair),force_n=float(force))for pair,force in policy.c.contact_forces.items()if 'ball'in pair],
        native_surface_hits=sum(r['native']is not None for r in rows),native_rays=rows,
        physical_state={name:dict(position=x['pos'].tolist(),rotation=x['mat'].tolist(),grasp=list(x['grasp']))for name,x in state.items()})
    result['native_mass_properties']={}
    for name,asset in scene.objects.items():
        view=asset.root_physx_view
        result['native_mass_properties'][name]=dict(
            masses_kg=view.get_masses().cpu().tolist(),
            inertias_kg_m2=view.get_inertias().cpu().tolist(),
            centres_of_mass=view.get_coms().cpu().tolist())
    return _write(policy,'ball-cooked-support-audit.private.json',result)


def pour_sweep_audit(policy,side):
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_jacobian_reference import capture
    if policy.task!='E45' or side not in('left','right'):raise ValueError('E45 held cup hand required')
    cup=policy.s['containers']['cup'];ref=dict(actor=cup['object'],local=cup['grasp_local'])
    policy.require_held(ref,side)
    state,contacts=policy.snapshot();names=('panda_hand',*policy.a.scene.embodiment.fingers)
    result=dict(schema='e45-loaded-cup-sweep-audit-v1',coordinate_frame='room_task',side=side,
        native_kinematics=capture(policy.a,policy.c,side),
        hand_meshes_task={name:actual_mesh(policy.a,side,name).tolist()for name in names},
        cup_collision_vertices_task=material_collision_points_task(policy,ref).tolist(),
        receiver_collision_vertices_task=material_collision_points_task(policy,{'actor':policy.s['container'],'local':[0,0,0]}).tolist(),
        physical_state={name:dict(position=x['pos'].tolist(),rotation=x['mat'].tolist(),grasp=list(x['grasp']))for name,x in state.items()},
        actual_contacts=[sorted(x)for x in contacts],source_semantic=policy.s,
        source_objects=policy.spec['objects'],source_recording=policy.a.scene.embodiment.config.get('author_recording',{}))
    return _write(policy,'loaded-cup-sweep-audit.private.json',result)


def passive_ball_roll(policy):
    from .engineering_checkpoint import capture
    from .realworld_tool_expert import ToolExecutionError
    if policy.task!='E43' or not getattr(policy.c,'_engineering_diagnostic_only',False):
        raise ValueError('Explicit E43 restored passive diagnostic required')
    migration=getattr(policy.a,'_engineering_resume_checkpoint',{}).get('context',{}).get('e43_ball_migration')
    if not migration:raise ValueError('Reviewed E43 ball migration required before passive gravity test')
    state,_=policy.snapshot();start=state['ball']['pos'].copy();direction=np.asarray(policy.s['launcher']['release_direction_task'],float)
    direction/=np.linalg.norm(direction);rows=[]
    guide=policy.s['tools']['main'];grip=dict(actor=guide['actor'],local=guide['grasp_local'])
    def guard():
        policy.require_held(grip,guide.get('hand','right'))
        body=policy.snapshot()[0]['ball']
        if any(body['grasp'])or any(policy.contact('ball',s+'_finger'+str(i))for s in('left','right')for i in(1,2)):
            raise ToolExecutionError('Passive gravity diagnostic encountered a real hand/ball interaction')
        if policy.contact('ball','gate'):
            raise ToolExecutionError('Passive gravity diagnostic gate is not clear')
    before=capture(policy.c,'before-passive-gravity-roll')
    for _ in range(50):
        receipt=policy.a.engineering_passive_ticks(5,guard)
        state,contacts=policy.snapshot();delta=state['ball']['pos']-start
        rows.append(dict(native_physics_tick=policy.c.physics_ticks,position_task=state['ball']['pos'].tolist(),
            directed_displacement_m=float(delta@direction),contacts=[sorted(x)for x in contacts],tick_receipt=receipt))
        if float(delta@direction)>=.03:break
    after=capture(policy.c,'after-passive-gravity-roll')
    passed=bool(rows[-1]['directed_displacement_m']>=.03)
    result=dict(schema='e43-same-checkpoint-passive-gravity-roll-v1',source_checkpoint_sha256=policy.a._engineering_resume_checkpoint['checkpoint_sha256'],
        before_native_state=before,after_native_state=after,rows=rows,segment_passed=passed,
        movement_source='native_gravity_and_contacts_no_public_actions',source_initial_full_positive=False)
    _write(policy,'passive-ball-roll.private.json',result)
    if not passed:raise ToolExecutionError('Reviewed native sphere did not passively roll30mm downhill')
    return result


def blade_front_audit(policy):
    import carb,omni.physx
    from scipy.spatial import ConvexHull
    from pxr import PhysicsSchemaTools
    from .source_reviewed_collisions import ray_hit_value
    from .engineering_cooked_geometry_audit import cooking_metadata
    from .execution_design_thin_edge import material_collision_points_task
    if policy.task!='E46':raise ValueError('E46 source blade audit only')
    scene=policy.a.scene;tool=policy.s['tools']['main']['actor'];state,contacts=policy.snapshot()
    body=state[tool];R=np.asarray(body['mat']);p=np.asarray(body['pos']);ref={'actor':tool,'local':[0,0,0]}
    vertices=(material_collision_points_task(policy,ref)-p)@R;planes=ConvexHull(vertices).equations
    query=omni.physx.get_physx_scene_query_interface();expected=scene.root_path+'/Props/'+tool;rows=[]
    for y in np.linspace(-.035,.035,15):
        for z in np.linspace(-.0148,-.0098,11):
            positive=planes[planes[:,0]>1e-10];negative=planes[planes[:,0]<-1e-10];flat=planes[abs(planes[:,0])<=1e-10]
            hi=float(np.min(-(positive[:,1]*y+positive[:,2]*z+positive[:,3])/positive[:,0]))
            lo=float(np.max(-(negative[:,1]*y+negative[:,2]*z+negative[:,3])/negative[:,0]))
            available=lo<=hi+1e-8 and bool(np.all(flat[:,1]*y+flat[:,2]*z+flat[:,3]<=1e-8))
            source_x=hi if available else None
            origin=scene.task_to_world(p+R@np.array([.18,y,z]));direction=np.asarray(scene.layout.task_rotation)@(-R[:,0]);hits=[]
            def report(hit):
                actor=ray_hit_value(hit,'rigidBody','rigid_body')
                actor=str(actor if isinstance(actor,str)else PhysicsSchemaTools.intToSdfPath(actor))
                if actor==expected:
                    point=scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float));local=R.T@(point-p)
                    normal=R.T@np.asarray(scene.layout.task_rotation).T@np.asarray(ray_hit_value(hit,'normal'),float)
                    hits.append(dict(position_tool=local.tolist(),position_task=point.tolist(),normal_tool=normal.tolist(),collision=str(ray_hit_value(hit,'collision'))))
                return True
            query.raycast_all(carb.Float3(*map(float,origin)),carb.Float3(*map(float,direction)),.36,report)
            native=max(hits,key=lambda x:x['position_tool'][0])if hits else None
            rows.append(dict(local_y_m=float(y),local_z_m=float(z),source_convex_front_x_m=source_x,native=native,
                cooked_minus_source_x_m=float(native['position_tool'][0]-source_x)if native and source_x is not None else None))
    result=dict(schema='e46-source-cooked-front-edge-audit-v1',coordinate_frame='source_tool_local',
        source_vertex_count=len(vertices),source_sha256=next(o for o in policy.spec['objects']if o['id']==tool)['source_asset']['sha256'],
        native_surface_hits=sum(x['native']is not None for x in rows),rays=rows,
        cooking_metadata=cooking_metadata(scene,tool,'right'),scene_query_support=carb.settings.get_settings().get('/physics/enableSceneQuerySupport'),
        physical_state={name:dict(position=x['pos'].tolist(),rotation=x['mat'].tolist(),grasp=list(x['grasp']))for name,x in state.items()},
        actual_contacts=[sorted(x)for x in contacts])
    import omni.usd
    root=omni.usd.get_context().get_stage().GetPrimAtPath(expected)
    coordinate=root.GetCustomDataByKey('videoicl:collision_coordinates')
    result['coordinate_reexpression']=json.loads(coordinate)if coordinate else None
    result['native_mass_properties']={}
    for name,asset in scene.objects.items():
        view=asset.root_physx_view
        result['native_mass_properties'][name]={key:value.cpu().tolist()for key,value in(
            ('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms()))}
    return _write(policy,'blade-cooked-front-audit.private.json',result)
