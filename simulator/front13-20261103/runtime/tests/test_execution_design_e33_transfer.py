import copy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e33_transfer import insertion_plane,rim_and_center,handoff_position,solve

def test_entire_true_bottle_and_fingers_clear_actual_tall_rim():
    tcp=np.array([.1,0,1.08]);vertices=np.array([[.08,-.02,.93],[.12,.02,1.10]])
    plane=insertion_plane(tcp,vertices,{'lowest_z_task_m':1.07},1.143)
    assert plane==pytest.approx(1.308)
    assert vertices[:,2].min()+plane-tcp[2]>=1.143+.015-1e-9
    assert 1.07+plane-tcp[2]>1.143+.015
    assert 1.10<plane  # Former constant waypoint intersected tall bin corridor.

def test_rotated_moved_actual_container_is_used_without_modifying_bounds():
    angle=.1;c,s=np.cos(angle),np.sin(angle)
    container=dict(lower=[-.09,-.043,-.0746],upper=[.1,.043,.17])
    body=dict(pos=[.02,.22,.973],mat=[[c,0,s],[0,1,0],[-s,0,c]])
    before=copy.deepcopy(container);rim,center=rim_and_center(container,body)
    assert rim>.973+.17*c
    assert np.allclose(center,(np.array(body['pos'])+np.array(body['mat'])@np.array([.005,0,.0477]))[:2])
    assert container==before

def test_handoff_requires_real_free_table_patch_not_object_overlap():
    spec=dict(objects=[dict(id='bottle',size=[.03,.03,.08]),dict(id='bin',size=[.15,.1,.17])])
    state={'bottle':dict(pos=[.1,-.18,.88],mat=np.eye(3)), 'bin':dict(pos=[0,.22,.973],mat=np.eye(3))}
    bounds=dict(lower=[-.4,-.4,.8],upper=[.4,.4,.8])
    assert np.allclose(handoff_position(spec,state,bounds,'bottle'),[-.3,0])
    state['bin']['pos']=[-.3,0,.973];spec['objects'][1]['size']=[.2,.3,.17]
    with pytest.raises(RuntimeError,match='No collision-clear'):handoff_position(spec,state,bounds,'bottle')

def test_handoff_cannot_place_beyond_physical_table():
    spec=dict(objects=[dict(id='bottle',size=[.03,.03,.08])]);state={'bottle':dict(pos=[0,0,1],mat=np.eye(3))}
    with pytest.raises(RuntimeError):handoff_position(spec,state,dict(lower=[-.2,-.4,.8],upper=[.4,.4,.8]),'bottle')

def test_route_is_not_available_to_formal_or_other_tasks():
    a=SimpleNamespace(scene=SimpleNamespace(spec=dict(id='E33',execution_design={'revision':'embodied50-execution-v3-20261102'})))
    with pytest.raises(ValueError,match='Explicit E33'):solve(a)


def test_horizontal_bottle_reserves_its_current_long_table_footprint():
    spec=dict(objects=[dict(id='bottle',size=[.023,.023,.085])])
    state={'bottle':dict(pos=[0,0,1],mat=np.array([[0,0,1],[0,1,0],[-1,0,0]]))}
    # Upright width would fit at x=-.3; a horizontal bottle extends .085m,
    # and neither candidate x=-.30 nor -.25 has its full footprint supported.
    with pytest.raises(RuntimeError,match='No collision-clear'):
        handoff_position(spec,state,dict(lower=[-.34,-.4,.8],upper=[-.20,.4,.8]),'bottle')


def test_horizontal_bottle_finds_adjacent_supported_handoff_column():
    spec=dict(objects=[dict(id='bottle',size=[.023,.023,.085]),dict(id='bin',size=[.15,.1,.17])])
    state={'bottle':dict(pos=[.04,-.16,.823],mat=np.array([[0,0,1],[0,1,0],[-1,0,0]])),
           'bin':dict(pos=[0,.22,.973],mat=np.eye(3))}
    bounds=dict(lower=[-.35,-.6,.8],upper=[.35,.6,.8])
    p=handoff_position(spec,state,bounds,'bottle')
    # Both old columns overhang the table; the unchanged horizontal bottle
    # fits farther inward without colliding with the bin.
    assert p[0]-.085-.025 >= bounds['lower'][0]
    assert p[0]+.085+.025 <= bounds['upper'][0]
    assert np.any(abs(p-np.array(state['bin']['pos'][:2])) > np.array([.15,.1])+[.11,.048])
