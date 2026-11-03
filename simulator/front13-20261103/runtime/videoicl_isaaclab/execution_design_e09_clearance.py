"""Measured E09 package clearance, independent of task success labels."""
import itertools
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def actual_bounds(obj,body):
    center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    half=np.asarray(obj['size'],float)
    local=np.array([center+half*np.array(sign) for sign in itertools.product((-1,1),repeat=3)])
    return np.asarray(body['pos'])+local@np.asarray(body['mat']).T


def supported_package_payload(root,objects,state,contacts):
    """Only contact-connected bodies wholly inside the carrier envelope.

    A 10mm skin includes a real lid resting on its rim. It never asserts a
    closed package or success; the native evaluator still checks those.
    """
    body=state[root];o=objects[root];center=np.asarray(o.get('local_bounds_center',[0,0,0]))
    half=np.asarray(o['size'])+.010;eligible={root}
    for name,value in state.items():
        if name==root:continue
        local=(actual_bounds(objects[name],value)-body['pos'])@body['mat']
        if np.all(np.abs(local-center)<=half+1e-9):eligible.add(name)
    edges=[set(pair) for pair in contacts];found={root}
    while True:
        newer=set(found)
        for edge in edges:
            if len(edge)==2 and edge&found:newer|=edge&eligible
        if newer==found:return found
        found=newer


def measured_package_clearance(policy,name,side):
    state,contacts=policy.snapshot()
    payload=supported_package_payload(name,policy.objects,state,contacts)
    bottom=min(float(actual_bounds(policy.objects[n],state[n])[:,2].min()) for n in payload)
    top=.8
    for n,value in state.items():
        if n not in payload:top=max(top,float(actual_bounds(policy.objects[n],value)[:,2].max()))
    for f in policy.spec.get('fixtures',[]):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed fixture geometry for E09 package transit')
        top=max(top,float(f['z'])+float(f['size'][2]))
    working_z=float(policy.point(dict(actor=name,local=policy.bottom_local(name)))[2])
    finger_to_working=working_z-float(policy.tip(side)[2])
    height=max(1.0,top+.050+working_z-bottom,
               policy.a.floor_clear_tcp(side,floor=top+.050)+finger_to_working)
    policy.operations.append(dict(operation='measured_e09_package_clearance',actor=name,
                                  actual_payload=sorted(payload),obstacle_top_m=top,
                                  payload_bottom_m=bottom,working_transit_z_m=height))
    return height
