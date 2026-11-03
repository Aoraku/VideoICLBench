import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e34_balanced_grasp import material_midpoint


def box(lower,upper):
    return np.asarray(list(itertools.product(*zip(lower,upper))),float)


def test_near_mass_grasp_uses_one_real_section_not_empty_merged_bounds():
    low=box([-.06,-.008,-.003],[.04,-.004,.003])
    high=box([-.06,.004,-.002],[.04,.008,.002])
    point,evidence=material_midpoint([-.054,-.006,0],[0,0,0],[low,high])
    assert point[0]==pytest.approx(-.027)
    assert -.008<=point[1]<=-.004
    assert abs(point[2])<=.003
    assert evidence['chosen_com_lever_m']<evidence['canonical_com_lever_m']*.6
    assert evidence['native_collision_piece_index']==0


def test_material_gap_at_candidate_x_rejects_aabb_only_grasp():
    left=box([-.06,-.005,-.003],[-.04,.005,.003])
    right=box([-.02,-.005,-.003],[.04,.005,.003])
    with pytest.raises(RuntimeError,match='No native fork material'):
        material_midpoint([-.054,0,0],[0,0,0],[left,right])
