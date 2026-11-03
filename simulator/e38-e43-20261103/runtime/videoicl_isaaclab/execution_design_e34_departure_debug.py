"""Read measured geometry around a legal tiny-yaw/departure diagnostic segment."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from .execution_design_e34_reference import scope


def run(a,payload):
    scope(a)
    if a.scene.spec.get('variant')!='C'or not getattr(a.c,'_engineering_diagnostic_only',False):raise ValueError('E34C checkpoint diagnostic only')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    side=payload.get('side','left');ix=('left','right').index(side);name='fork';fingers=[side+'_finger1',side+'_finger2'];a.carried_payload=(name,side)
    if getattr(a,'_engineering_resume_context',{}).get('retarget_measured_hold')is True:raise ValueError('Probe requires preserved source controller promises')
    state,_=a.c.snapshot();baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name};initial_z=float(state[name]['pos'][2]);trace=[]
    report=dict(local_debug_only=True,fixed36_positive=False,source_controller_promise_preserved=True,trace=trace,passed=False)
    out=Path(a.out)/'e34-departure-yaw-probe.private.json';floor=table_bounds_task(a.scene)['top']
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    policy=SimpleNamespace(a=a,frame=frame)
    def measure(label):
        values,contacts=a.c.snapshot();body=values[name]
        if not body['grasp'][ix]or not all(force(name,f)>.001 for f in fingers):raise RuntimeError('Actual fork grasp lost during departure probe')
        for n,old in baseline.items():
            b=values[n]
            if any(b['grasp'])or np.linalg.norm(np.asarray(b['pos'])-old['pos'])>.002 or np.linalg.norm(np.asarray(b['mat'])-old['mat'])>.03 or any(force(n,f)>.001 for f in fingers):raise RuntimeError('Departure probe touched or moved unselected '+n)
        meshes={n:actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)};meshes[name]=material_collision_points_task(policy,dict(actor=name))
        row=dict(label=label,step=a.c.steps,tcp=np.asarray(a.tip(side)).tolist(),fork_position=np.asarray(body['pos']).tolist(),fork_rotation=np.asarray(body['mat']).tolist(),actual_mesh_minimum_z={n:float(m[:,2].min())for n,m in meshes.items()},actual_mesh_minimum_point={n:m[int(np.argmin(m[:,2]))].tolist()for n,m in meshes.items()},table_top_m=float(floor),actual_fork_table_force_n=force(name,'table'),actual_pad_forces_n=[force(name,f)for f in fingers],actual_grasp=body['grasp'][ix],fork_table_contact=frozenset((name,'table'))in contacts)
        trace.append(row);out.write_text(json.dumps(report,indent=2));return row
    try:
        measure('restored-preserved-promise')
        yaw=float(payload.get('yaw_degrees',.5));up_count=int(payload.get('up_count',12))
        if yaw not in (0.,.5)or not 1<=up_count<=12:raise ValueError('Bounded matched departure probe parameters required')
        report.update(public_yaw_degrees=yaw,maximum_up_count=up_count)
        if yaw:
            a.stage='e34-local-half-degree-yaw';a.act('ROTATE_CCW'if side=='left'else'STILL','ROTATE_CCW'if side=='right'else'STILL',5.,rotation_deg=yaw);measure('after-public-half-degree-yaw')
        a.stage='e34-local-real-monitored-up';token='UP'if a.generated_axis_signs[side][2]==1 else'DOWN'
        for _ in range(up_count):
            a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',5.);row=measure('after-real-up')
            if row['fork_position'][2]-initial_z>=.004 and not row['fork_table_contact']and min(row['actual_mesh_minimum_z'].values())>=floor+.0015:
                report.update(passed=True,segment_passed=True,final_step=a.c.steps,actual_mesh_clearance_m=min(row['actual_mesh_minimum_z'].values())-floor);out.write_text(json.dumps(report,indent=2));return report
        raise RuntimeError('Departure diagnostic did not establish true unsupported mesh-clear pickup')
    except Exception as exc:
        report.update(error=type(exc).__name__+': '+str(exc),final_step=a.c.steps);out.write_text(json.dumps(report,indent=2));raise
