"""Exact E17 source-triangle support vertices, without nonexistent box corners.

The source mesh has three holes. Its outer convex hull certifies every vertex
for axis bounds in any rigid frame; no aperture is filled for collision tests.
This module affects region/support measurements only, never physics or scores.
"""
import numpy as np

TRIANGLE_SHA='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b'
# Exact coordinates from both source Visuals and Collisions. The extra pair is
# source floating-point roundoff on an outer edge, retained rather than rounded.
SUPPORT_POINTS=np.array([[x,y,z]for x,y in[(-.02,-.017320508),(-.006666667,.005773503),(.02,-.017320508),(0.,.017320508)]for z in(-.003,.003)])


def bounds(obj,row,anchor):
    rotation=np.asarray(anchor['mat'],float);relative=rotation.T@(np.asarray(row['pos'])-anchor['pos'])
    actual=rotation.T@np.asarray(row['mat'])
    if obj.get('source_asset',{}).get('sha256')==TRIANGLE_SHA:
        points=SUPPORT_POINTS@actual.T+relative
        return points.min(0),points.max(0)
    center=relative+actual@np.asarray(obj.get('local_bounds_center',[0,0,0]));radius=np.abs(actual)@np.asarray(obj['size'])
    return center-radius,center+radius


def contained(obj,row,anchor,region,tolerance=.003):
    low,high=bounds(obj,row,anchor)
    return bool(np.all(low>=np.asarray(region['lower'])-tolerance)and np.all(high<=np.asarray(region['upper'])+tolerance))
