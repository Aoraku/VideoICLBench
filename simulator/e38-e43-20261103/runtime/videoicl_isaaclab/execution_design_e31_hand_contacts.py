"""Passive exact native object/palm views; never authors physics or motion."""
import json
from pathlib import Path
import numpy as np


def install(a,*,all_robot_links=False):
    if not(a.control_report.get('engineering_reference_only')and a.scene.spec['id']=='E31'):
        raise ValueError('Explicit E31 engineering contact readback required')
    scene=a.scene;c=a.c;views={}
    for actor in('plate','bowl'):
        physics=scene.contacts[actor][0]._physics_sim_view
        source=str(scene.objects[actor].root_physx_view.prim_paths[0])
        for side in('left','right'):
            bodies=list(scene.robots[side].body_names)if all_robot_links else[scene.embodiment.hand]
            paths=[f'{scene.root_path}/{side}_robot/{body}'for body in bodies]
            view=physics.create_rigid_contact_view(source,filter_patterns=paths,max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=len(paths):raise ValueError('Exact object/robot native filters required')
            views[actor+'/'+side]=(view,bodies)
    if all_robot_links:
        physics=scene.contacts['plate'][0]._physics_sim_view
        for side in('left','right'):
            for body in scene.robots[side].body_names:
                source=f'{scene.root_path}/{side}_robot/{body}'
                view=physics.create_rigid_contact_view(source,
                    filter_patterns=[scene.rig_root+'/Table'],max_contact_data_count=1024)
                if view.sensor_count!=1 or view.filter_count!=1:
                    raise ValueError('Exact one-link native table filter required')
                views['robot_table/'+side+'/'+body]=(view,['table'])
    folder=Path(a.out);acc={key+'/'+body:0. for key,(_,bodies)in views.items()for body in bodies};latest={key:None for key in acc};last=[None];samples=[0];errors={}
    def record(controller,render):
        for key,(view,bodies)in views.items():
            try:
                value=view.get_contact_force_matrix(controller.dt)
                force=np.asarray(value.detach().cpu().numpy()if hasattr(value,'detach')else value,float).reshape(-1,3)
                if force.shape!=(len(bodies),3)or not np.isfinite(force).all():raise ValueError('Invalid exact native force matrix')
                for body,magnitude in zip(bodies,np.linalg.norm(force,axis=1)):
                    label=key+'/'+body
                    latest[label]=float(magnitude)
                    if acc[label] is not None:acc[label]=max(acc[label],float(magnitude))
            except Exception as exc:
                errors[key]=type(exc).__name__+': '+str(exc)
                for body in bodies:acc[key+'/'+body]=None;latest[key+'/'+body]=None
        if last[0]!=controller.steps:
            with(folder/'e31-exact-palm-contacts.private.jsonl').open('a')as f:
                f.write(json.dumps(dict(read_only=True,steps=controller.steps,tick=controller.physics_ticks,
                    stage=a.stage,peak_force_since_last_action_n=dict(acc),
                    read_errors=dict(errors),no_schema_material_geometry_or_state_changes=True))+'\n')
            for key in acc:acc[key]=0.
            errors.clear()
            last[0]=controller.steps;samples[0]+=1
    c.tick_hooks.append(record)
    result=dict(read_only=True,exact_pairs=list(acc),samples=samples,current_forces_n=latest,flush=lambda:record(c,False))
    a._e31_native_contact_reader=result
    return result
