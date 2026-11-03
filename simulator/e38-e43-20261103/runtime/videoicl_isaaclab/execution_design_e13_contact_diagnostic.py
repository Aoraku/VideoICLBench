"""Explicit engineering-only E13 passive contact recording; no actuation."""
import json
from pathlib import Path

FLAG='VIC_E13_CONTACT_DIAGNOSTIC'

def enabled(spec,execution_control,environ):
    return (((environ.get(FLAG)=='1' and spec.get('id')=='E13')
             or (environ.get('VIC_E08_CONTACT_DIAGNOSTIC')=='1' and spec.get('id')=='E08'))
            and execution_control=='positive'
            and spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102')

def attach(scene):
    from isaaclab.sensors import ContactSensor,ContactSensorCfg
    from pxr import PhysxSchema
    import omni.usd
    stage=omni.usd.get_context().get_stage();sensors={}
    target='left_shoe' if scene.spec['id']=='E08' else 'phone'
    filters=[scene.rig_root+'/Table',scene.root_path+'/Props/'+target]
    scene._diagnostic_target=target
    for side in ('left','right'):
        for name in ('panda_hand',*scene.embodiment.fingers):
            path=f'{scene.root_path}/{side}_robot/{name}'
            prim=stage.GetPrimAtPath(path)
            if not prim.IsValid():raise RuntimeError('Missing E13 diagnostic rigid body '+path)
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.)
            sensors[side+'/'+name]=ContactSensor(ContactSensorCfg(prim_path=path,
                filter_prim_paths_expr=filters,history_length=0,update_period=0.))
    scene._e13_contact_diagnostic=sensors

def install(controller,folder):
    sensors=getattr(controller.scene,'_e13_contact_diagnostic',{})
    if not sensors:return
    folder=Path(folder);folder.mkdir(exist_ok=True,parents=True)
    task=controller.scene.spec['id'].lower();target=controller.scene._diagnostic_target
    minimum_step=90 if task=='e08' else 260
    path=folder/(task+'-robot-contact-ticks.private.jsonl')
    patch_views={}
    def record(c,render):
        # Force sensors are independent observers, not evaluator inputs.
        rows={}
        for name,sensor in sensors.items():
            try:
                sensor.update(c.dt,force_recompute=True)
                if c.steps<minimum_step:continue
                def array(v):return None if v is None else v.detach().cpu().tolist()
                rows[name]=dict(force_matrix_w=array(sensor.data.force_matrix_w),
                                net_forces_w=array(sensor.data.net_forces_w),
                                position_w=array(sensor.data.pos_w),quaternion_w=array(sensor.data.quat_w))
            except Exception as exc:
                rows[name]=dict(diagnostic_error=type(exc).__name__+': '+str(exc))
        if rows and c.steps>=minimum_step:
            from .author_native_grip_probe import decode_patch
            for name,sensor in sensors.items():
                if not name.startswith('left/') or 'finger'not in name:continue
                try:
                    if name not in patch_views:
                        body=name.split('/')[1]
                        patch_views[name]=sensor._physics_sim_view.create_rigid_contact_view(
                            f'{c.scene.root_path}/left_robot/{body}',
                            filter_patterns=[c.scene.root_path+'/Props/'+target],max_contact_data_count=1024)
                    view=patch_views[name]
                    # Decode/copy immediately: native methods reuse buffer storage.
                    normal=decode_patch(view.get_contact_data(c.dt))
                    friction=decode_patch(view.get_friction_data(c.dt),True)
                    rows[name]['normal_patch']={k:v.tolist()for k,v in normal.items()}
                    rows[name]['friction_patch']={k:v.tolist()for k,v in friction.items()}
                    rows[name]['body_transform_world']=sensor.body_physx_view.get_transforms().detach().cpu().tolist()
                except Exception as exc:
                    rows[name]['patch_error']=type(exc).__name__+': '+str(exc)
        if rows:
            with path.open('a')as f:f.write(json.dumps(dict(tick=c.physics_ticks,step=c.steps,
                filters=['table',target],bodies=rows,public_feedback=c.public_feedback()))+'\n')
    controller.tick_hooks.append(record)
