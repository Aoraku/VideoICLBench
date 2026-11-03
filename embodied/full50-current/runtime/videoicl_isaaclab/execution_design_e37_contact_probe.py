"""Exact passive robot-link/table forces for one restored E37 hold."""
import json
import numpy as np


def run(author,policy):
    scene=author.scene;c=author.c
    if not(author.control_report.get('engineering_reference_only')and scene.spec['id']=='E37'
            and getattr(c,'_engineering_diagnostic_only',False)):
        raise ValueError('Admitted E37 engineering diagnostic required')
    physics=next(iter(scene.contacts.values()))[0]._physics_sim_view
    target=scene.rig_root+'/Table';views={};peak={};last={};errors={};samples=[0]
    for side in ('left','right'):
        for name in scene.robots[side].body_names:
            label=side+'/'+name;source=f'{scene.root_path}/{side}_robot/{name}'
            view=physics.create_rigid_contact_view(source,filter_patterns=[target],max_contact_data_count=1024)
            if view.sensor_count!=1 or view.filter_count!=1:raise ValueError('Exact one-link/table native filter required')
            views[label]=view;peak[label]=0.;last[label]=0.
    def observe(controller,render):
        samples[0]+=1
        for label,view in views.items():
            try:
                value=view.get_contact_force_matrix(controller.dt)
                raw=value.detach().cpu().numpy()if hasattr(value,'detach')else value
                force=np.asarray(raw,float).reshape(-1,3)
                if force.shape!=(1,3)or not np.isfinite(force).all():raise ValueError('Finite exact native link/table force required')
                norm=float(np.linalg.norm(force[0]));last[label]=norm;peak[label]=max(peak[label],norm)
            except Exception as exc:errors[label]=type(exc).__name__+': '+str(exc)
    c.tick_hooks.append(observe);initial=c.steps;start_tick=c.physics_ticks
    try:
        policy.stage('checkpoint-e37-passive-whole-robot-table-force-readback')
        policy.act()
    finally:
        c.tick_hooks.remove(observe)
        report=dict(read_only_force_views=True,diagnostic_only=True,source_initial_episode=False,
            native_task_acceptance=False,segment_passed=False,measurement_completed=samples[0]>0 and not errors,
            source_actions=[initial,c.steps],native_ticks=[start_tick,c.physics_ticks],samples=samples[0],
            exact_filter_table=target,all_link_table_peak_force_n=peak,last_frame_link_table_force_n=last,
            read_errors=errors,physical_parameters_or_states_written_by_observer=False,
            maximum_link_table_force_n=max(peak.values())if not errors else None)
        (author.out/'E37-native-all-link-table-forces.private.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
