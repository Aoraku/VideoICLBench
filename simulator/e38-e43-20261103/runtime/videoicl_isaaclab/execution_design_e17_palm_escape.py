"""One fixed positive-X palm tilt recovering a pre-existing shallow cap contact.

SAT values describe the same convex envelopes used by the existing geometric
filter, not a claimed PhysX cook penetration measurement. No direction search.
"""
import math
import numpy as np
from scipy.spatial import ConvexHull
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def _directions(vectors):
    a=np.asarray(vectors,float).reshape(-1,3);length=np.linalg.norm(a,axis=1);a=a[length>1e-9]/length[length>1e-9,None]
    if not len(a):return a
    sign=np.sign(a[np.arange(len(a)),np.argmax(abs(a),axis=1)]);a*=sign[:,None]
    _,ids=np.unique(np.round(a,7),axis=0,return_index=True)
    return a[np.sort(ids)]


def signed_sat_margin(a,b):
    """Positive separating lower bound; negative convex-envelope MTD depth."""
    a=np.asarray(a,float);b=np.asarray(b,float);ha=ConvexHull(a);hb=ConvexHull(b)
    def edges(points,hull):
        pairs={(min(x,y),max(x,y))for tri in hull.simplices for x,y in zip(tri,np.roll(tri,-1))}
        return _directions([points[y]-points[x]for x,y in pairs])
    ea=edges(a,ha);eb=edges(b,hb);cross=np.cross(ea[:,None,:],eb[None,:,:]).reshape(-1,3)
    axes=_directions(np.r_[ha.equations[:,:3],hb.equations[:,:3],cross])
    ap=a@axes.T;bp=b@axes.T
    return float(np.max(np.maximum(bp.min(0)-ap.max(0),ap.min(0)-bp.max(0))))


def _state(policy,payload):
    from .execution_design_e24_transit import capture_model
    from .execution_design_segments_e17_upper import _native_parts
    model,_=capture_model(policy,'right');parts=_native_parts(policy)
    cap=next((r for r in parts if r['name']=='stand/2'),None)
    if cap is None:raise ToolExecutionError('Actual stand cap component unavailable')
    base,rotation=policy.frame({'actor':'stand'});local=(cap['points']-base)@rotation
    if not(np.allclose(local.min(0),[-.02729462,-.02594982,.33818859],atol=2e-5)and np.allclose(local.max(0),[.02729462,.02594982,.34501225],atol=2e-5)):
        raise ToolExecutionError('Unreviewed actual E17 top cap geometry')
    names={'panda_link7','panda_hand','panda_leftfinger','panda_rightfinger'}
    clouds=[c for c in model['clouds']if c['name']in names]
    clouds.extend(dict(name='held:'+r['name'],points=r['points'])for r in parts if r['actor']==payload)
    return model,clouds,cap['points']


def escape_to_default_tilt(policy,payload,guard):
    """Five public1.5-degree steps along the already reviewed C tilt direction.

    Only stand/2 is taken out of the generic swept filter during this recovery;
    every wrist/hand/finger/payload pair with it is checked below, and all other
    unchanged colliders retain their original checks. No deeper hull overlap
    is accepted in the prediction or actual readback.
    """
    from .execution_design_segments_e17_upper import _check
    for step in range(5):
        guard();model,clouds,cap=_state(policy,payload);before={c['name']:signed_sat_margin(c['points'],cap)for c in clouds}
        if min(before.values())<-.002:raise ToolExecutionError('E17 palm contact is not shallow enough for the one fixed recovery')
        prior=dict(before)
        for degrees in(.25,.5,.75,1.,1.25,1.5):
            delta=_axis_rotation([1,0,0],math.radians(degrees))
            for c in clouds:
                moved=(c['points']-model['position'])@delta.T+model['position'];value=signed_sat_margin(moved,cap);initial=before[c['name']]
                if initial<.002:
                    if value<prior[c['name']]-2e-6:raise ToolExecutionError('E17 fixed palm escape would deepen the cap contact')
                elif value<.002:raise ToolExecutionError('E17 fixed palm escape creates a new cap collision')
                prior[c['name']]=value
        desired=_axis_rotation([1,0,0],math.radians(1.5))@model['rotation']
        _check(policy,model['position'],rotation=desired,payload=payload,wrist_only=True,ignored_components=('stand/2',))
        policy.act('right','ROLL_LEFT',degrees=1.5);guard()
        _,actual,cap=_state(policy,payload);after={c['name']:signed_sat_margin(c['points'],cap)for c in actual}
        for name,value in after.items():
            if (before[name]<.002 and value<before[name]-2e-6)or(before[name]>=.002 and value<.002):
                raise ToolExecutionError('Actual E17 palm escape deepened or added a cap contact')
        policy.operations.append(dict(operation='fixed_outward_palm_tilt',public_step=step+1,requested_degrees=1.5,
            before_minimum_signed_hull_margin_m=min(before.values()),after_minimum_signed_hull_margin_m=min(after.values())))
    _check(policy,payload=payload,wrist_only=True)
