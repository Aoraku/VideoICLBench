"""Private read-only independent1024-buffer target-ball/table diagnostics."""
from __future__ import annotations
import json
import numpy as np
from .author_native_grip_probe import cpu_copy,decode_patch


def normal_patch_summary(normal,matrix):
    force=(normal['force'].reshape(-1,1)*normal['normal']).sum(0)
    return dict(normal_point_count=len(normal['force']),normal_force_sum_world_n=force.tolist(),
                independent_normal_matrix_world_n=np.asarray(matrix).tolist(),
                point_matrix_difference_n=float(np.linalg.norm(force-matrix)),
                raw_valid_normal={k:np.asarray(v).tolist()for k,v in normal.items()})


class NativeBallSupportProbe:
    def __init__(self,author,balls):
        self.a=author;self.last_tick=None;self.views={};self.balls=balls
        import omni.usd
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysicsSchemaTools,Sdf,PhysxSchema
        self.simulation=get_physx_simulation_interface();self.stage_id=omni.usd.get_context().get_stage_id()
        self.body_paths={n:PhysicsSchemaTools.sdfPathToInt(Sdf.Path('/World/Props/'+n))for n in balls}
        metadata={}
        for name in balls:
            sensor,_=author.scene.contacts[name]
            view=sensor._physics_sim_view.create_rigid_contact_view('/World/Props/'+name,filter_patterns=['/World/Table'],max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=1:raise RuntimeError('Exact native ball/table contact view required')
            self.views[name]=view;body=author.scene.objects[name].root_physx_view;props={}
            for method in('get_masses','get_coms','get_inertias','get_material_properties','get_contact_offsets','get_rest_offsets','get_sleep_thresholds','get_stabilization_thresholds','get_disable_gravities','get_disable_simulations'):
                fn=getattr(body,method,None)
                if fn is not None:
                    try:props[method]=cpu_copy(fn()).tolist()
                    except Exception as exc:props[method]=dict(read_error=repr(exc))
            metadata[name]=dict(actual_body_properties=props,native_body_read_methods=[n for n in dir(body)if n.startswith(('get_','is_'))],
                                sensor_sim_physics_dt=getattr(sensor,'_sim_physics_dt',None))
            prim=omni.usd.get_context().get_stage().GetPrimAtPath('/World/Props/'+name);api=PhysxSchema.PhysxRigidBodyAPI(prim)
            metadata[name]['actual_usd_sleep_threshold']=api.GetSleepThresholdAttr().Get()
            metadata[name]['actual_usd_stabilization_threshold']=api.GetStabilizationThresholdAttr().Get()
        physics_prim=omni.usd.get_context().get_stage().GetPrimAtPath(author.c.sim.cfg.physics_prim_path)
        scene_api=PhysxSchema.PhysxSceneAPI(physics_prim)
        scene_attributes={str(attr.GetName()):attr.Get()for attr in physics_prim.GetAttributes()if any(k in str(attr.GetName()).lower()for k in('stabil','sleep','solver'))}
        (author.out/'E42-ball-support-properties.private.json').write_text(json.dumps(dict(read_only=True,buffer_capacity=1024,balls=metadata,
              actual_simulation_config_stabilization=author.c.sim.cfg.physx.enable_stabilization,actual_scene_stabilization=scene_api.GetEnableStabilizationAttr().Get(),actual_scene_attributes=scene_attributes),indent=2,default=str)+'\n')

    def tick(self,controller,render):
        if self.last_tick==controller.physics_ticks:return
        self.last_tick=controller.physics_ticks;rows={}
        for name,view in self.views.items():
            sensor,filters=self.a.scene.contacts[name];obj=self.a.scene.objects[name];body=obj.root_physx_view
            # Count/start arrays alias: copy/decode normal BEFORE friction.
            normal=decode_patch(view.get_contact_data(controller.dt));friction=decode_patch(view.get_friction_data(controller.dt),True)
            row=normal_patch_summary(normal,cpu_copy(view.get_contact_force_matrix(controller.dt))[0,0])
            row.update(raw_valid_friction={k:np.asarray(v).tolist()for k,v in friction.items()},native_transforms=cpu_copy(body.get_transforms()).tolist(),
                       native_is_sleeping=bool(self.simulation.is_sleeping(self.stage_id,self.body_paths[name])),
                       native_velocities=cpu_copy(body.get_velocities()).tolist(),cached_position_world=cpu_copy(obj.data.root_pos_w).tolist(),cached_velocity_world=cpu_copy(obj.data.root_vel_w).tolist(),
                       cached_sensor_normal_matrix_world_n=cpu_copy(sensor.data.force_matrix_w).tolist(),sensor_filter_actors=list(filters),
                       sensor_sim_physics_dt=getattr(sensor,'_sim_physics_dt',None),sensor_timestamp=cpu_copy(getattr(sensor,'_timestamp',[])).tolist(),
                       sensor_timestamp_last_update=cpu_copy(getattr(sensor,'_timestamp_last_update',[])).tolist())
            rows[name]=row
        with(self.a.out/'E42-ball-support-raw.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(physics_tick=controller.physics_ticks,stage=self.a.stage,dt=controller.dt,render=bool(render),balls=rows))+'\n')
