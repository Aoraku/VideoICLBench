from types import SimpleNamespace
import numpy as np
from videoicl_isaaclab.execution_design_clip_edge_alignment import edge_yaw_turns, insertion_point


def test_open_jaws_align_across_wall_instead_of_along_it():
    points=np.array([[0.,-.01,.9],[0.,.01,.902]])
    for turn in edge_yaw_turns(points):
        gap=turn@(points[1]-points[0])
        assert abs(gap[1])<1e-12 and abs(abs(gap[0])-.02)<1e-12
        assert np.isclose(gap[2],.002)


def test_lower_tip_centres_both_below_real_rim():
    clip=dict(mechanism='clip1',left=dict(body='a',point_local=[0,0,0]),
              right=dict(body='b',point_local=[0,0,0]))
    p=SimpleNamespace(point=lambda ref:np.array([0.,0.,.900 if ref['body']=='a'else .906]))
    target=insertion_point(p,clip,[.1,.2,.842])
    assert np.allclose(target,[.1,.2,.836])
    assert target[2]+.003<.842
