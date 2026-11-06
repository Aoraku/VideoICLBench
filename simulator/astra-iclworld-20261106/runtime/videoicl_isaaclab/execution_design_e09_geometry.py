"""Exact E09 containment vertices for pinned triangular and ring collision CAD.

Linear containment extrema occur on its eight outer convex-hull vertices. The
298 source mesh vertices (including its three holes) have this exact hull;
rotated bounding-box corners outside that hull are empty space.
"""
import itertools
import numpy as np
from .execution_design_e09_ring_hull import SOURCE_SHA256 as RING_SHA256, HULL as RING_HULL

TRIANGLE_SHA256 = 'caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b'
TRIANGLE_FILE = 'source_three_hole_triangle_v2.usda'
TRIANGLE_HULL = np.array([[x,y,z] for x,y in
    ((-.02,-.017320508),(-.006666667,.005773503),
     (.02,-.017320508),(0.,.017320508)) for z in(-.003,.003)])


def local_vertices(obj):
    """Return exact pinned CAD hull, otherwise the existing declared envelope."""
    asset = obj.get('source_asset',{})
    if asset.get('relative_path') == TRIANGLE_FILE:
        if (asset.get('sha256') != TRIANGLE_SHA256
                or asset.get('source_rotation',[1,0,0,0]) != [1,0,0,0]
                or not np.allclose(obj['size'], [.02,.017320508,.003], atol=1e-12, rtol=0)):
            raise ValueError('Pinned original E09 triangle collision geometry required')
        return TRIANGLE_HULL.copy()
    if asset.get('relative_path') == 'native_ring.usdz':
        if (asset.get('sha256') != RING_SHA256
                or asset.get('source_rotation',[1,0,0,0]) != [1,0,0,0]
                or not np.allclose(obj['size'],[.02,.02,.004],atol=1e-12,rtol=0)):
            raise ValueError('Pinned original E09 ring collision geometry required')
        return RING_HULL.copy()
    center = np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    return center+np.array(list(itertools.product((-1,1),repeat=3)))*np.asarray(obj['size'])


def world_vertices(obj, body):
    return np.asarray(body['pos'])+local_vertices(obj)@np.asarray(body['mat']).T


def contained(obj, body, anchor, lower, upper, tolerance):
    points=(world_vertices(obj,body)-np.asarray(anchor['pos']))@np.asarray(anchor['mat'])
    return bool(np.all(points>=np.asarray(lower)-tolerance)
                and np.all(points<=np.asarray(upper)+tolerance))
