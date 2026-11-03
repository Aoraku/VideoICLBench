"""Private E34C reference grasp closer to measured mass, on native material.

Only a copied author grasp parameter changes. Scene geometry, mass, friction,
task rules and the actual physical grasp/transport checks stay unchanged.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import numpy as np


def material_midpoint(old,com,parts):
    """Choose the real convex material section halfway toward measured COM."""
    from .execution_design_cutlery_grasp import plane_section
    old,com=np.asarray(old,float),np.asarray(com,float)
    if old.shape!=(3,)or com.shape!=(3,)or not np.isfinite(np.r_[old,com]).all():
        raise ValueError('Finite canonical grasp and native COM required')
    x=float((old[0]+com[0])/2);choices=[]
    for index,part in enumerate(parts):
        part=np.asarray(part,float)
        if part.ndim!=2 or part.shape[1]!=3 or not np.isfinite(part).all():
            raise ValueError('Complete actual enabled collision pieces required')
        try:section=plane_section(part[:,[1,2,0]],x)[:,[2,0,1]]
        except ValueError:continue
        # A convex combination of true section vertices lies in this one
        # native convex piece, rather than in the gap between separate parts.
        point=section.mean(0);point[0]=x
        choices.append((float(np.linalg.norm(point[1:]-old[1:])),index,point,section))
    if not choices:raise RuntimeError('No native fork material at near-COM grasp section')
    _,index,point,section=min(choices,key=lambda row:row[0])
    before=float(np.linalg.norm(old-com));after=float(np.linalg.norm(point-com))
    if not after<before-.001:raise RuntimeError('Native material section does not reduce grasp lever')
    return point,dict(canonical_grasp_local=old.tolist(),native_com_local=com.tolist(),
        chosen_grasp_local=point.tolist(),native_collision_piece_index=index,
        section_vertices_local=section.tolist(),canonical_com_lever_m=before,
        chosen_com_lever_m=after,source_object_unchanged=True)


def grasp_spec(a,obj):
    from .execution_design_e34_reference import scope
    from .execution_design_branch_geometry import collision_parts_task
    scope(a);spec=a.scene.spec
    if spec.get('variant')!='C'or spec.get('seed')!=4201 or obj.get('id')!='fork':
        raise ValueError('Private fixed E34C I4201 fork grasp required')
    name=obj['id'];body=a.c.snapshot()[0][name]
    if any(body['grasp']):raise RuntimeError('Near-COM grasp selection requires unheld fork')
    raw=a.scene.objects[name].root_physx_view.get_coms()
    if hasattr(raw,'detach'):raw=raw.detach().cpu().numpy()
    raw=np.asarray(raw,float).reshape(-1,7)
    if raw.shape!=(1,7)or not np.isfinite(raw).all():raise ValueError('One finite native fork COM required')
    def frame(ref):
        value=a.c.snapshot()[0][ref['actor']]
        return np.asarray(value['pos']),np.asarray(value['mat'])
    parts=collision_parts_task(SimpleNamespace(a=a,frame=frame),name)
    local=[(np.asarray(p)-body['pos'])@np.asarray(body['mat'])for p in parts]
    point,evidence=material_midpoint(obj['grasp_point_local'],raw[0,:3],local)
    private=deepcopy(obj);private['grasp_point_local']=point.tolist()
    evidence.update(step=a.c.steps,object=name,source='actual_enabled_native_collision_material_section',
        actual_native_com_pose_local=raw[0].tolist(),native_grasp_verified=False,
        collision_representation_evidence=getattr(a,'_branch_collision_parts_evidence',{}).get(name))
    with(a.out/'e34c-near-com-grasp.private.jsonl').open('a')as stream:
        stream.write(json.dumps(evidence)+'\n')
    return private


def run_debug(a,payload):
    """Empty-hand checkpoint through a new true grasp and continuous tail."""
    if not getattr(a.c,'_engineering_diagnostic_only',False):raise ValueError('Admitted diagnostic checkpoint required')
    from .execution_design_e34_acquire import narrow_material_approach,check_pickup_neighbors
    from .execution_design_e34_tail import finish_from_grasp
    side=payload.get('side','left');name='fork';state,_=a.c.snapshot()
    if any(any(body['grasp'])for body in state.values()):raise RuntimeError('Near-COM diagnostic must start empty-handed')
    baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    obj=grasp_spec(a,next(o for o in a.scene.spec['objects']if o['id']==name));a.carried_payload=None
    from .execution_design_cutlery_grasp import grasp_position
    a.stage='debug-e34c-near-com-empty-orientation';grasp_position(a,side,obj)
    a.stage='debug-e34c-near-com-actual-approach';narrow_material_approach(a,side,obj)
    a.stage='debug-e34c-near-com-real-grasp'
    for _ in range(3):
        a.act('GRASP'if side=='left'else'STILL','GRASP'if side=='right'else'STILL')
        check_pickup_neighbors(a,side,name,baseline)
    state,_=a.c.snapshot()
    if not state[name]['grasp'][0 if side=='left'else 1]:raise RuntimeError('Near-COM actual grasp failed')
    a.carried_payload=(name,side);a.act()
    result=finish_from_grasp(a,name,side)
    return dict(result,segment_passed=True,local_debug_only=True,fixed36_positive=False)
