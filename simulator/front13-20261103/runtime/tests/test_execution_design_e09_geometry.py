"""Real v15 pose: reject actual material escape, not empty rotated box corners."""
from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import re
import numpy as np
from scipy.spatial import ConvexHull
from videoicl_isaaclab.execution_design_e09_geometry import local_vertices, contained, TRIANGLE_SHA256


def actual_case():
    obj=dict(size=[.02,.017320508,.003],source_asset=dict(
        relative_path='source_three_hole_triangle_v2.usda',sha256=TRIANGLE_SHA256,
        source_rotation=[1,0,0,0]))
    body=dict(pos=np.array([.07141009718179706,.08755108714103699,.8112146830558777]),
        mat=np.array([[.7631588231116885,.6036514172878199,.23063732810017815],
                      [-.6138210555162947,.7887421641323203,-.03330931288282489],
                      [-.2020205992260312,-.11614975215759367,.9724694918413046]]))
    anchor=dict(pos=np.array([.0999999269843102,.1000000387430191,.8219999647140503]),
        mat=np.array([[.9999999999999103,4.2146847157274794e-7,-4.315316667027725e-8],
                      [-4.214684773354774e-7,.9999999999999023,-1.33541365421596e-7],
                      [4.315311038679786e-8,1.3354138360928348e-7,.9999999999999902]]))
    return obj,body,anchor,np.array([-.055,-.047,-.016]),np.array([.055,.047,.022])


def test_pinned_original_collision_mesh_has_exact_declared_hull():
    path=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS/source_three_hole_triangle_v2.usda'
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==TRIANGLE_SHA256
    text=raw.decode().split('def Xform "Collisions"',1)[1]
    points=np.asarray(ast.literal_eval(re.search(r'point3f\[\] points = (\[[^\n]+\])',text)[1]))
    assert len(points)==298
    hull=points[ConvexHull(points).vertices]
    assert set(map(tuple,hull))==set(map(tuple,local_vertices(actual_case()[0])))


def test_native_triangle_pose_is_inside_original_unchanged_region():
    obj,body,anchor,lower,upper=actual_case()
    assert contained(obj,body,anchor,lower,upper,.003)
    radius=abs(anchor['mat'].T@body['mat'])@obj['size']
    center=anchor['mat'].T@(body['pos']-anchor['pos'])
    assert (center-radius)[2]<lower[2]-.003  # Empty BBox corner caused v15 rejection.


def test_actual_material_outside_any_original_face_is_rejected():
    obj,body,anchor,lower,upper=actual_case()
    points=(local_vertices(obj)@body['mat'].T+body['pos']-anchor['pos'])@anchor['mat']
    for axis in range(3):
        for sign in(-1,1):
            shifted=deepcopy(body)
            delta=(upper[axis]+.003-points[:,axis].max()+.0001 if sign>0
                   else lower[axis]-.003-points[:,axis].min()-.0001)
            shifted['pos']+=anchor['mat'][:,axis]*delta
            assert not contained(obj,shifted,anchor,lower,upper,.003)


def test_source_geometry_repin_is_required():
    obj,*_=actual_case()
    obj['source_asset']['sha256']='0'*64
    import pytest
    with pytest.raises(ValueError):local_vertices(obj)


def test_rotated_original_circle_contains_material_instead_of_empty_box_corners():
    from videoicl_isaaclab.execution_design_e09_geometry import RING_SHA256
    angle=.67;c,s=np.cos(angle),np.sin(angle)
    obj=dict(size=[.02,.02,.004],source_asset=dict(relative_path='native_ring.usdz',sha256=RING_SHA256))
    body=dict(pos=np.array([.031,-.0098,-.012]),mat=np.array([[c,-s,0],[s,c,0],[0,0,1.]]))
    anchor=dict(pos=np.zeros(3),mat=np.eye(3));lower=np.array([-.055,-.047,-.016]);upper=np.array([.055,.047,.022])
    assert contained(obj,body,anchor,lower,upper,.003)
    assert body['pos'][0]+(abs(body['mat'])@obj['size'])[0]>upper[0]+.003
    body['pos'][0]+=.008
    assert not contained(obj,body,anchor,lower,upper,.003)


def test_ring_source_pin_and_extents_remain_required():
    from videoicl_isaaclab.execution_design_e09_geometry import RING_SHA256
    import pytest
    obj=dict(size=[.02,.02,.004],source_asset=dict(relative_path='native_ring.usdz',sha256=RING_SHA256))
    assert local_vertices(obj).shape==(11904,3)
    obj['source_asset']['sha256']='0'*64
    with pytest.raises(ValueError):local_vertices(obj)
