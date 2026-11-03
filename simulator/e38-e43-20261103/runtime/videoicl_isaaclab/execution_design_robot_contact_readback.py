"""Passive exact link/scene-body force readback for engineering diagnostics.

Independent Tensor read views only; no USD, collision, material, robot target,
object state, or evaluator label is authored by this observer.
"""
import json
import numpy as np


def install(author,targets,*,stem='native-robot-contact',sample_period=10,max_samples=300):
    c=author.c;scene=author.scene
    if not(author.control_report.get('engineering_reference_only')and getattr(c,'_engineering_diagnostic_only',False)):
        raise ValueError('Admitted engineering diagnostic required for passive link readback')
    physics=next(iter(scene.contacts.values()))[0]._physics_sim_view
    paths=[]
    for name in targets:
        if name=='table':path=scene.rig_root+'/Table'
        elif name in scene.objects:path=str(scene.objects[name].root_physx_view.prim_paths[0])
        else:raise ValueError('Actual native body target required')
        paths.append(path)
    views={};peak={};last={};errors={};samples=[0];last_tick=[None]
    for side in ('left','right'):
        for body in scene.robots[side].body_names:
            label=side+'/'+body;path=f'{scene.root_path}/{side}_robot/{body}'
            view=physics.create_rigid_contact_view(path,filter_patterns=paths,max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=len(paths):raise ValueError('Exact native link/targets view required')
            views[label]=view
            for target in targets:peak[label+'|'+target]=0.;last[label+'|'+target]=[0.,0.,0.]
    def observe(controller,render):
        if samples[0]>=max_samples or controller.physics_ticks%sample_period or last_tick[0]==controller.physics_ticks:return
        samples[0]+=1;last_tick[0]=controller.physics_ticks
        for label,view in views.items():
            try:
                value=view.get_contact_force_matrix(controller.dt)
                raw=value.detach().cpu().numpy()if hasattr(value,'detach')else value
                force=np.asarray(raw,float).reshape(-1,3)
                if force.shape!=(len(targets),3)or not np.isfinite(force).all():raise ValueError('Finite exact native contact force matrix required')
                for target,vector in zip(targets,force):
                    key=label+'|'+target;last[key]=vector.tolist();peak[key]=max(peak[key],float(np.linalg.norm(vector)))
            except Exception as exc:errors[label]=repr(exc)
        report=dict(diagnostic_only=True,read_only=True,physical_parameters_or_states_written=False,
            tick=controller.physics_ticks,actions=controller.steps,stage=author.stage,samples=samples[0],
            sample_period_ticks=sample_period,exact_target_paths=dict(zip(targets,paths)),
            peak_force_n=peak,last_force_world_n=last,read_errors=errors)
        path=author.out/(stem+'.private.json');temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(path)
    c.tick_hooks.append(observe)
    return dict(read_only=True,samples=samples)
