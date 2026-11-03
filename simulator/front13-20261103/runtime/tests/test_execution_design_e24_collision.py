"""Reject-only geometry regression; no native acceptance is asserted."""
import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e24_collision import separation_certificate
from videoicl_isaaclab.execution_design_e24_transit import screen_joint_segment


def cube(center,half):
    return np.array(list(itertools.product(*[(v-half,v+half)for v in center])))


def test_empty_box_faces_do_not_fill_the_cavity():
    payload=cube([0,0,.5],.02)
    # The enclosing box bounds overlap this payload. Each unchanged wall
    # remains a separate triangle surface with positive actual separation.
    wall=np.array([[.3,-.3,0],[.3,.3,0],[.3,.3,1.]])
    assert separation_certificate(payload,wall)>.27
    model=dict(position=np.zeros(3),jacobian=np.empty((6,0)),q=np.empty(0),
        clouds=[dict(name='panda_link0',influence=0,points=payload)])
    result=screen_joint_segment(model,[],[],[dict(name='box-wall',lo=wall.min(0),hi=wall.max(0),points=wall)])
    assert result['minimum_clearance_lower_bound_m']>.27


def test_overlapping_bounds_can_have_separating_plane():
    a=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1.]])
    b=a+[.6,.6,.6]
    # Three AABB intervals overlap; x+y+z separates the convex sets.
    assert np.all(a.max(0)>b.min(0))
    assert separation_certificate(a,b)>.45
    assert separation_certificate(a,a)==pytest.approx(0.)
