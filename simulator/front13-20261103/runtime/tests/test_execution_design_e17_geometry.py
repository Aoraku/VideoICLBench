"""Source mesh extrema, actual support and unchanged non-E17 box predicates."""
from pathlib import Path
import hashlib,re
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e17_geometry import SUPPORT_POINTS,TRIANGLE_SHA,bounds,contained
from videoicl_isaaclab.execution_design_evidence import ExecutionDesignEvaluator
from test_execution_design_evidence import fixture


def test_support_vertices_reproduce_every_original_mesh_extent_in_rotated_frames():
    from scipy.spatial.transform import Rotation
    p=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS/source_three_hole_triangle_v2.usda'
    assert hashlib.sha256(p.read_bytes()).hexdigest()==TRIANGLE_SHA
    blocks=re.findall(r'point3f\[\] points = \[(.*?)\]',p.read_text(),re.S)
    for block in blocks:
        points=np.array([tuple(map(float,row.split(',')))for row in re.findall(r'\(([^()]*)\)',block)])
        for matrix in Rotation.from_euler('xyz',[[0,0,0],[90,30,15],[57,-81,22]],degrees=True).as_matrix():
            actual=points@matrix.T;support=SUPPORT_POINTS@matrix.T
            assert np.allclose(actual.min(0),support.min(0),atol=1e-9)and np.allclose(actual.max(0),support.max(0),atol=1e-9)


def captured():
    obj=dict(size=[.02,.017320508,.003],source_asset=dict(sha256=TRIANGLE_SHA))
    row=dict(pos=np.array([.066286646,.017773505,1.0296666]),mat=np.array([[-.03286544,.056912,.99783814],[-.49740493,.86502564,-.06571991],[-.86689579,-.49848956,-.00012112]]),grasp=(False,False))
    anchor=dict(pos=np.array([.04,.05,.8]),mat=np.eye(3));region=dict(actor='box',lower=[-.068,-.068,.20771],upper=[.068,.068,.26971])
    return obj,row,anchor,region


def test_captured_vertical_triangle_is_contained_and_physically_seated_without_blank_box_corner():
    obj,row,anchor,region=captured();low,high=bounds(obj,row,anchor)
    assert contained(obj,row,anchor,region)and .219<low[2]<.223
    spec,state,contacts=fixture('E17');spec['objects'][0].update(obj);e=ExecutionDesignEvaluator(spec);e.state=dict(cargo=row,box=anchor)
    assert e.contained('cargo',region)and e.seated('cargo','box',region)
    boxlow=row['pos'][2]-np.abs(row['mat'][2])@obj['size']-anchor['pos'][2]
    assert boxlow<region['lower'][2]-.003


def test_actual_outside_and_missing_real_contact_still_fail():
    obj,row,anchor,region=captured();row['pos'][0]+=.08
    assert not contained(obj,row,anchor,region)
    spec,state,contacts=fixture('E17');spec['objects'][0].update(obj);e=ExecutionDesignEvaluator(spec);e.state=dict(cargo=row,box=anchor);e.contacts=set()
    assert not e.members(dict(region,members=['cargo']))


def test_other_task_keeps_original_bbox_semantics():
    obj,row,anchor,region=captured();spec,state,contacts=fixture('E20');spec['objects'][0].update(obj);e=ExecutionDesignEvaluator(spec);e.state=dict(cargo=row,box=anchor)
    assert not e.contained('cargo',region)
