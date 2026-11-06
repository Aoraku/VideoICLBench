"""Empty westward exit from C's existing shallow palm/cap proximity."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _step(policy,payload):
    from scipy.optimize import least_squares
    from .execution_design_e24_transit import capture_model,prefix_transforms
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .author_orientation import _axis_angle
    from .execution_design_segments_e17_upper import _check,_native_parts
    from .execution_design_e17_palm_escape import signed_sat_margin
    model,_=capture_model(policy,'right');cap=next(r for r in _native_parts(policy)if r['name']=='stand/2')['points'];q=model['q'];point=model['position']+[-.002,0,0]
    before={c['name']:signed_sat_margin(c['points'],cap)for c in model['clouds']}
    if min(before.values())<-.002:raise ToolExecutionError('Existing cap envelope overlap is outside shallow empty escape scope')
    lo=model['limits'][:,0]+.05;hi=model['limits'][:,1]-.05
    def residual(value):
        p,r=forward_at_delta(model['position'],model['rotation'],model['jacobian'],value-q);axis,angle=_axis_angle(model['rotation']@r.T)
        return np.r_[10*(p-point),axis*angle,.005*(value-q)]
    fit=least_squares(residual,q,bounds=(lo,hi),max_nfev=100);prior=dict(before)
    for t in np.linspace(0,1,9)[1:]:
        transforms=prefix_transforms(model['position'],model['jacobian'],(fit.x-q)*t)
        for c in model['clouds']:
            tr=transforms[c['influence']];points=c['points']@tr[:3,:3].T+tr[:3,3];value=signed_sat_margin(points,cap)
            if value<min(.002,prior[c['name']])-2e-6:raise ToolExecutionError('Fixed empty west exit would deepen/add cap overlap')
            prior[c['name']]=value
    _check(policy,point,payload=payload,carrying=False,ignored_components=('stand/2',));policy.act('right','BACK',mm=2.)
    actual,_=capture_model(policy,'right');cap=next(r for r in _native_parts(policy)if r['name']=='stand/2')['points']
    for c in actual['clouds']:
        if signed_sat_margin(c['points'],cap)<min(.002,before[c['name']])-2e-6:raise ToolExecutionError('Actual empty west exit deepened/added cap overlap')
    policy.operations.append(dict(operation='fixed_empty_west_cap_exit',requested_west_m=.002,before_minimum_signed_hull_margin_m=min(before.values())))


def retreat_west(policy,payload):
    from .execution_design_segments_e17_remaining import _move
    from .execution_design_segments_e17_upper import _check
    base,_=policy.frame({'actor':'stand'});goal=float(base[0]-.230)
    policy.stage('local-e17c-two-blue-empty-west-exit')
    for _ in range(120):
        tip=policy.tip('right')
        if tip[0]<=goal+.002:break
        target=tip.copy();target[0]-=min(.004,float(tip[0]-goal))
        try:_check(policy,target,payload=payload,carrying=False,maximum_swept_bound_m=.0005)
        except ToolExecutionError as exc:
            if ' / stand/2'not in str(exc):raise
            _step(policy,payload);continue
        policy.act('right','BACK',mm=float(tip[0]-target[0])*1000)
    else:raise ToolExecutionError('Empty west exit exceeded bounded corridor')
    point=policy.tip('right');_move(policy,None,[*point[:2],max(1.12,float(point[2]))],payload=payload,carrying=False)
