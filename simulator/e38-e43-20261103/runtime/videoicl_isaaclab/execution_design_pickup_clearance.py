"""Measured palm clearance and full finger-pad overlap for engineering pickups."""
from types import SimpleNamespace
import json
import numpy as np
from .execution_design import REVISION_V3
from .execution_design_e33_grasp import actual_mesh,plan_grasp
from .execution_design_thin_edge import material_collision_points_task,table_bounds_task


def rim_plan(point,vertices,tcp,palm,fingers,floor,margin=.003):
    point,vertices,tcp,palm=map(lambda x:np.asarray(x,float),(point,vertices,tcp,palm))
    fingers=[np.asarray(f,float)for f in fingers]
    if len(fingers)!=2 or not all(np.isfinite(x).all()for x in [point,vertices,tcp,palm,*fingers]):raise ValueError('Finite actual collision geometry required')
    if any(f.ndim!=2 or f.shape[1]!=3 or len(f)<4 for f in [vertices,palm,*fingers]):raise ValueError('Actual mesh vertices required')
    center=(fingers[0].mean(0)+fingers[1].mean(0))/2
    top=float(vertices[:,2].max());bottom=float(vertices[:,2].min())
    z=max(top-float(palm[:,2].min()-tcp[2])+margin,
          float(floor)-min(float(f[:,2].min()-tcp[2])for f in fingers)+.0003)
    pad=z+float(center[2]-tcp[2])
    if not bottom+.003<pad<top-.003:raise ValueError('No real rim wall overlap at palm/table-clear height')
    target=np.r_[point[:2]-(center-tcp)[:2],z]
    return dict(tcp_target_task_m=target.tolist(),finger_pad_center_z=pad,actual_object_top_z=top,
                palm_clearance_m=float(palm[:,2].min()-tcp[2]+z-top),
                source='actual_collision_geometry_rim_reference',native_grasp_verified=False)


def grasp_position(author,side,obj):
    a=author;spec=a.scene.spec
    if not getattr(a,'_execution_design_reference_authorized',False)or spec.get('execution_design',{}).get('revision')!=REVISION_V3 or a.scene.embodiment.name!='franka':raise ValueError('Explicit v3 Panda engineering reference required')
    if not(spec['id']=='E32' or spec['id']=='E31'and obj['id']=='bowl'):raise ValueError('Unreviewed palm-clear pickup task')
    state,_=a.c.snapshot();body=state[obj['id']]
    policy=SimpleNamespace(a=a,frame=lambda ref:(np.asarray(body['pos']),np.asarray(body['mat'])))
    vertices=material_collision_points_task(policy,dict(actor=obj['id']))
    palm=actual_mesh(a,side,'panda_hand');fingers=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
    floor=table_bounds_task(a.scene)['top']
    if spec['id']=='E32':plan=plan_grasp(vertices,a.tip(side),palm,fingers,floor=floor)
    else:
        point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
        plan=rim_plan(point,vertices,a.tip(side),palm,fingers,floor)
    plan.update(task=spec['id'],object=obj['id'],side=side,step=a.c.steps,actual_object_vertices=len(vertices),source_asset_sha256=obj['source_asset']['sha256'])
    with (a.out/'measured-palm-clear-pickup.private.jsonl').open('a')as f:f.write(json.dumps(plan)+'\n')
    return np.asarray(plan['tcp_target_task_m'])
