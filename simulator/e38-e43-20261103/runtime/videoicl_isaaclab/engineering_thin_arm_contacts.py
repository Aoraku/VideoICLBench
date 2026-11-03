"""Readonly E44 cross-arm contact peaks and end-frame forces; no extra ticks."""
import json
import numpy as np


def install(author):
    scene=author.scene;c=author.c
    if scene.spec['id']!='E44'or not author.control_report.get('engineering_reference_only'):
        raise ValueError('Explicit E44 engineering contact observer required')
    physics=next(iter(scene.contacts.values()))[0]._physics_sim_view
    targets=[f'{scene.root_path}/right_robot/{n}'for n in scene.robots['right'].body_names]
    names=list(scene.robots['right'].body_names);views={}
    for name in scene.robots['left'].body_names:
        view=physics.create_rigid_contact_view(f'{scene.root_path}/left_robot/{name}',filter_patterns=targets,max_contact_data_count=1024)
        if view.sensor_count!=1 or view.filter_count!=len(targets):raise ValueError('Exact native cross-arm view required')
        views[name]=view
    peak={};last_force={};errors={};step=[None];stage=[None];start=[c.physics_ticks]
    def flush():
        with(author.out/'thin-native-cross-arm-forces.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(stage=stage[0],action_step=step[0],ticks=[start[0],c.physics_ticks],peak_force_n=dict(peak),last_frame_force_n=dict(last_force),read_errors=dict(errors),read_only=True))+'\n')
        peak.clear();last_force.clear();errors.clear();start[0]=c.physics_ticks
    def observe(controller,render):
        if step[0]is not None and c.steps!=step[0]:
            try:flush()
            except Exception as exc:errors['observer_flush']=type(exc).__name__+': '+str(exc)
        step[0]=c.steps;stage[0]=author.stage;last_force.clear()
        for source,view in views.items():
            try:
                value=view.get_contact_force_matrix(c.dt)
                if hasattr(value,'detach'):value=value.detach().cpu().numpy()
                forces=np.asarray(value,float).reshape(-1,3)
                if forces.shape!=(len(targets),3)or not np.isfinite(forces).all():raise ValueError('Finite cross-arm force matrix required')
                for target,magnitude in zip(names,np.linalg.norm(forces,axis=1)):
                    if magnitude>1e-5:
                        key=source+' -> '+target;last_force[key]=float(magnitude);peak[key]=max(peak.get(key,0.),float(magnitude))
            except Exception as exc:errors[source]=type(exc).__name__+': '+str(exc)
    c.tick_hooks.append(observe)
    def close():
        c.tick_hooks.remove(observe);flush()
    return close
