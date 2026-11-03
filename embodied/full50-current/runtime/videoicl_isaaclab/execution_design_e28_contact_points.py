"""Passive exact food/blade native contact-point and zero-impulse evidence."""
import json
import numpy as np
from .author_native_grip_probe import cpu_copy,decode_patch


def install(policy,food,tool,maximum_samples=35000):
    from .execution_design_e28_source import _scope
    _scope(policy);a=policy.a;c=policy.c;scene=a.scene
    physics=scene.contacts[food][0]._physics_sim_view
    food_path=str(scene.objects[food].root_physx_view.prim_paths[0]);tool_path=str(scene.objects[tool['actor']].root_physx_view.prim_paths[0])
    view=physics.create_rigid_contact_view(food_path,filter_patterns=[tool_path],max_contact_data_count=1024)
    if view.sensor_count!=1 or view.filter_count!=1:raise ValueError('One exact native food/blade contact pair required')
    count=[0];last=[None]
    metadata=dict(read_only=True,sensor_path=food_path,filter_path=tool_path,normal_buffer_semantics='force times normal acts on food; independent force matrix is normal-only',
        food_contact_offsets=cpu_copy(scene.objects[food].root_physx_view.get_contact_offsets()).tolist(),
        tool_contact_offsets=cpu_copy(scene.objects[tool['actor']].root_physx_view.get_contact_offsets()).tolist(),
        food_rest_offsets=cpu_copy(scene.objects[food].root_physx_view.get_rest_offsets()).tolist(),
        tool_rest_offsets=cpu_copy(scene.objects[tool['actor']].root_physx_view.get_rest_offsets()).tolist())
    (a.out/'E28-food-blade-contact-point-metadata.private.json').write_text(json.dumps(metadata,indent=2)+'\n')
    def record(controller,render):
        if count[0]>=maximum_samples or last[0]==controller.physics_ticks:return
        count[0]+=1;last[0]=controller.physics_ticks
        row=dict(read_only=True,physics_tick=controller.physics_ticks,actions=controller.steps,stage=a.stage)
        try:
            normal=decode_patch(view.get_contact_data(controller.dt));friction=decode_patch(view.get_friction_data(controller.dt),True)
            matrix=cpu_copy(view.get_contact_force_matrix(controller.dt))[0,0]
            row.update(normal_point_count=len(normal['force']),friction_point_count=len(friction['force']),
                normal_force_world_n=np.asarray(normal['force']).reshape(-1,1).__mul__(normal['normal']).sum(0).tolist(),
                independent_normal_force_world_n=matrix.tolist(),normal_force_norm_n=float(np.linalg.norm(matrix)),
                separations_m=normal['separation'].reshape(-1).tolist(),normal_forces_n=normal['force'].reshape(-1).tolist(),
                actual_force_contact=policy.contact(food,tool['actor']),food_task_position=np.asarray(policy.snapshot()[0][food]['pos']).tolist())
            # Preserve actual valid point geometry on zero-impulse frames.
            if np.linalg.norm(matrix)<=.001:
                row.update(points_world_m=normal['point'].tolist(),normals_world=normal['normal'].tolist())
        except Exception as exc:row['read_error']=repr(exc)
        with(a.out/'E28-food-blade-contact-points.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
    c.tick_hooks.append(record)
    return dict(read_only=True,samples=count)
