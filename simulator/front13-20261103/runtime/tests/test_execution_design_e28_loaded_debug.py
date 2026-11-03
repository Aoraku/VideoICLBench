from types import SimpleNamespace
import numpy as np
from videoicl_isaaclab.execution_design_e28_loaded_debug import supported_footprint


def policy(center):
    state={'blade':{'pos':np.zeros(3),'mat':np.eye(3)},'food':{'pos':np.asarray(center),'mat':np.eye(3)}}
    p=SimpleNamespace(snapshot=lambda:(state,set()),spec={'objects':[dict(id='food',size=[.017,.025,.007])]})
    tool=dict(actor='blade',support_bounds={'lower':[.070,-.037,-.014],'upper':[.125,.037,.014]},
        support_normal_local=[.310511,.003563,.950563],support_plane_offset=.0308164)
    return p,tool


def test_real_footprint_can_overlap_blade_when_center_is_six_mm_past_patch():
    p,t=policy([.131,0.,-.003])
    assert supported_footprint(p,t,'food')[0]


def test_actual_load_outside_blade_and_food_extent_is_rejected():
    p,t=policy([.170,0.,-.003])
    assert not supported_footprint(p,t,'food')[0]
