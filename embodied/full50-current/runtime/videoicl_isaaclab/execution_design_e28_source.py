"""Private source-author pieces for the measured shallow E28 tool route."""
import json
import numpy as np


def _scope(policy):
    if not (policy.a.control_report.get('engineering_reference_only') is True
            and policy.spec.get('id')=='E28' and policy.spec.get('seed')==4201
            and policy.spec.get('execution_design',{}).get('condition')=='I'
            and policy.spec['execution_design'].get('revision')=='embodied50-execution-v3-20261102'):
        raise ValueError('Explicit E28 I4201 engineering source author required')


def acquire_near_com(policy,tool,side='right'):
    """Acquire the proven source material station directly, without regrips."""
    _scope(policy)
    from .execution_design_tools_debug import _near_blade_ref
    from .realworld_tool_expert import ToolExecutionError
    old=getattr(policy,'_e28_grasp_station',None)
    policy._e28_grasp_station=.025
    try:ref=_near_blade_ref(policy,tool)
    finally:
        if old is None:del policy._e28_grasp_station
        else:policy._e28_grasp_station=old
    policy.acquire(ref,side)
    sensor,labels=policy.a.scene.contacts[tool['actor']]
    evidence=[]
    for _ in range(3):
        policy.require_held(ref,side)
        values=sensor.data.force_matrix_w[0].sum(axis=0).detach().cpu().numpy()
        forces=[np.asarray(values[labels.index(side+'_finger'+str(i))],float)for i in (1,2)]
        norms=[float(np.linalg.norm(f))for f in forces]
        opposition=float(-forces[0]@forces[1]/max(norms[0]*norms[1],1e-12))
        evidence.append(dict(step=policy.c.steps,forces_n=norms,opposition=opposition))
        if min(norms)<=.7 or opposition<=.7:
            raise ToolExecutionError('Source near-COM grip lacks measured opposed force')
        policy.act()
    policy.require_held(ref,side)
    (policy.a.out/'e28-source-near-com-grip.private.json').write_text(json.dumps(
        dict(grasp=ref,evidence=evidence,source_geometry_unchanged=True),indent=2)+'\n')
    return ref


def plate_destination(policy,name,slot,total):
    """Keep the two C foods in distinct lateral regions of the original plate."""
    _scope(policy)
    if total not in (1,2)or not 0<=slot<total:
        raise ValueError('One original A/B food or two original C foods required')
    container=policy.s['containers']['plate'];body=policy.snapshot()[0][container['object']]
    axis=int(container.get('floor_axis',2))
    local=(np.asarray(container['lower'],float)+np.asarray(container['upper'],float))/2
    local[axis]=(container['lower']if container.get('floor_side','lower')=='lower'else container['upper'])[axis]
    lateral=next(i for i in (0,1,2)if i!=axis)
    if total==2:local[lateral]+=(-.035,.035)[slot]
    return np.asarray(body['pos'])+np.asarray(body['mat'])@local
