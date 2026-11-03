"""A floor triangle can be pinched without pushing its full outline into a bay."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab import execution_design_segments_e17_regrasp_edge as segment
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def policy(monkeypatch):
    a,state,contacts=context('E17','A');p=segment.ExecutionDesignAuthor(a)
    state['packing_box']['pos']=np.array([0.,0.,.826]);state['packing_box']['mat']=np.eye(3)
    state['green_triangle']['pos']=np.array([.01757,.11546,.817]);state['green_triangle']['mat']=np.eye(3)
    monkeypatch.setattr(segment,'_finger_offsets',lambda policy:(np.array([-.06655,-.01062,-.009]),np.array([.06626,.01039,.04511])))
    return p,state


def test_exposed_base_contact_target_clears_real_bay_without_whole_triangle_containment(monkeypatch):
    p,state=policy(monkeypatch);target,evidence=segment.edge_target(p)
    assert evidence['exposed_pad_strip_overlap_m']>.005
    assert evidence['target_tcp_box_local_m'][1]==pytest.approx(.106-.01039-.0025)
    assert state['green_triangle']['pos'][1]>.106  # whole-shape old guard would fail
    assert target[2]==pytest.approx(.826-.012+.0025+.009)


@pytest.mark.parametrize('fault',['raised','outside_pad','outside_jaws'])
def test_edge_candidate_still_requires_actual_floor_and_reachable_material(monkeypatch,fault):
    p,state=policy(monkeypatch)
    if fault=='raised':state['green_triangle']['pos'][2]+=.012
    elif fault=='outside_pad':state['green_triangle']['pos'][1]+=.012
    else:state['green_triangle']['pos'][0]+=.08
    with pytest.raises(ToolExecutionError):segment.edge_target(p)


@pytest.mark.parametrize('fault',['old223','wrong_tick','quasistatic','variant','parameter'])
def test_exact_native57_boundary_cannot_replay_old_push(monkeypatch,fault):
    a,state,contacts=context('E17','A');a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':57,'physics_ticks':5702}};params={}
    if fault=='old223':a._engineering_resume_checkpoint['source']['steps']=223
    elif fault=='wrong_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=5802
    elif fault=='quasistatic':a._engineering_resume_checkpoint['state_quality']='measured_pose_fixture'
    elif fault=='variant':a.scene.spec['variant']='B'
    else:params={'assume_held':True}
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',lambda *args:pytest.fail('must reject before policy/action'))
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_grasp_green_floor_edge_57',params)


def test_native18_base_entry_requires_the_new_complete_failure_boundary(monkeypatch):
    a,state,contacts=context('E17','A');a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':57,'physics_ticks':5702}}
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',lambda *args:pytest.fail('must refuse old pre-push source'))
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_grasp_green_base_18',{})

