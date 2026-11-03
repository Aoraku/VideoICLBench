from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e42_edge import edge_distance, enabled, VERTICES, TRIANGLES


def source():
    from videoicl_isaaclab.realworld_scenes import load
    s=load('E42','A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    return s,next(o for o in s['objects']if o['id']=='spatula')


def test_measured_curved_front_contact_is_not_rejected_by_chord():
    s,obj=source();point=np.array([.15298845380600373,-.0010275374142597743,-.012774322462202406])
    from videoicl_isaaclab.realworld_tool_evidence import _segment_distance
    old=_segment_distance(point,*np.array(s['semantic']['tools']['main']['edge_segment']))
    assert old>.019
    assert .012<edge_distance(point,obj)<.014


@pytest.mark.parametrize('point',[[-.09,0,0],[.10,0,.01],[.12,0,.04],[.133,0,-.05],[.14,.07,-.013]])
def test_handle_blade_back_top_and_wrong_side_are_not_front_rim(point):
    _,obj=source()
    assert edge_distance(point,obj)>.01616


def test_exact_source_triangles_have_zero_surface_distance():
    _,obj=source()
    for triangle in TRIANGLES[::5]:
        assert edge_distance(triangle.mean(axis=0),obj)<1e-12
    assert np.isfinite(TRIANGLES).all() and len(VERTICES)==59


def test_unknown_asset_and_scale_fail_closed():
    from copy import deepcopy
    _,obj=source();changed=deepcopy(obj);changed['size'][0]*=1.01
    with pytest.raises(ValueError,match='dimensions'):edge_distance([.153,0,-.013],changed)
    changed=deepcopy(obj);changed['source_asset']['sha256']='unreviewed'
    with pytest.raises(ValueError,match='SHA'):edge_distance([.153,0,-.013],changed)


def test_only_e42_v3_uses_new_contact_surface():
    revision={'revision':'embodied50-execution-v3-20261102'}
    assert enabled({'id':'E42','execution_design':revision})
    assert not enabled({'id':'E42'})
    for task in ('E28','E46'):assert not enabled({'id':task,'execution_design':revision})


def test_control_centre_point_lies_on_true_bowed_edge_ahead_of_old_chord():
    from videoicl_isaaclab.execution_design_e42_edge import central_reference
    s,obj=source();point=central_reference(obj)
    old=np.mean(s['semantic']['tools']['main']['edge_segment'],axis=0)
    assert abs(point[1])<1e-12 and edge_distance(point,obj)<1e-10
    assert .006<point[0]-old[0]<.007
    assert -.014<point[2]<-.012


@pytest.mark.parametrize('lateral',[-.020,-.010,.010,.020])
def test_control_can_use_an_actual_lateral_front_patch(lateral):
    from videoicl_isaaclab.execution_design_e42_edge import central_reference
    _,obj=source();point=central_reference(obj,lateral)
    assert point[1]==pytest.approx(lateral)and edge_distance(point,obj)<1e-10
    with pytest.raises(ValueError):central_reference(obj,.03)
