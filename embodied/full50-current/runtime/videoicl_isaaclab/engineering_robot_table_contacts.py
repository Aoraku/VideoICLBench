"""Passive exact E28/E37 robot-link/table views; no extra physical ticks."""
import json
import numpy as np


def install(author,*,stem='native-robot-table-contacts'):
    scene=author.scene;c=author.c
    if scene.spec['id']not in('E28','E37')or not author.control_report.get('engineering_reference_only'):
        raise ValueError('Explicit E28/E37 engineering contact observation required')
    physics=next(iter(scene.contacts.values()))[0]._physics_sim_view
    target=scene.rig_root+'/Table';views={};peak={};last={};errors={};samples=[0]
    first_tick=[c.physics_ticks];step=[c.steps];closed=[False]
    for side in('left','right'):
        for name in scene.robots[side].body_names:
            label=side+'/'+name
            view=physics.create_rigid_contact_view(f'{scene.root_path}/{side}_robot/{name}',
                filter_patterns=[target],max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=1:raise ValueError('Exact one-link/table native filters required')
            views[label]=view;peak[label]=0.;last[label]=0.
    def snapshot():
        return dict(read_only=True,stage=author.stage,actions=[step[0],c.steps],
            physics_ticks=[first_tick[0],c.physics_ticks],samples=samples[0],
            measurement_completed=samples[0]>0 and not errors,exact_filter_table=target,
            all_link_table_peak_force_n=dict(peak),last_frame_link_table_force_n=dict(last),
            read_errors=dict(errors),no_physics_schema_material_state_or_target_changes=True)
    def flush():
        with(author.out/(stem+'.private.jsonl')).open('a')as stream:
            stream.write(json.dumps(snapshot())+'\n')
        first_tick[0]=c.physics_ticks;step[0]=c.steps;samples[0]=0
        for label in peak:peak[label]=0.;last[label]=0.
        errors.clear()
    def observe(controller,render):
        if c.steps!=step[0]:
            try:flush()
            except Exception as exc:errors['observer_flush']=type(exc).__name__+': '+str(exc)
        samples[0]+=1
        for label,view in views.items():
            try:
                value=view.get_contact_force_matrix(c.dt)
                raw=value.detach().cpu().numpy()if hasattr(value,'detach')else value
                force=np.asarray(raw,float).reshape(-1,3)
                if force.shape!=(1,3)or not np.isfinite(force).all():raise ValueError('Finite exact native force matrix required')
                norm=float(np.linalg.norm(force[0]));last[label]=norm
                if peak[label]is not None:peak[label]=max(peak[label],norm)
            except Exception as exc:
                errors[label]=type(exc).__name__+': '+str(exc);peak[label]=None;last[label]=None
    c.tick_hooks.append(observe)
    def close():
        if closed[0]:return
        closed[0]=True;c.tick_hooks.remove(observe);flush()
    return dict(snapshot=snapshot,flush=flush,close=close,read_only=True,exact_pairs=list(views))
