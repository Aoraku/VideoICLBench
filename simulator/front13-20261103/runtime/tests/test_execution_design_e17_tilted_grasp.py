"""Actual closing envelopes retain floor/wall/rail guards for a tilted piece."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab import execution_design_e17_tilted_grasp as candidate
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def prepared(monkeypatch):
    a,state,contacts=context('E17','C');state['packing_box']['pos']=np.array([0.,0.,.826]);state['packing_box']['mat']=np.eye(3)
    state['blue_triangle']['pos']=np.array([-.012,-.032,.8228]);state['blue_triangle']['mat']=Rotation.from_euler('y',-45,degrees=True).as_matrix()
    tip=np.array([0.,0.,1.12]);a.tip=lambda side:tip.copy();clouds=[]
    for low,high in[(-.0665,-.0395),(.0395,.0665)]:clouds.append(np.array([tip+[x,y,z]for x in(-.0106,.0106)for y in(low,high)for z in(-.009,.045)]))
    monkeypatch.setattr(candidate,'_finger_state',lambda p:(clouds,np.array([0.,1.,0.])))
    return ExecutionDesignAuthor(a),state


def test_horizontal_source_pinches_fit_with_complete_closing_sweeps_outside_rails(monkeypatch):
    p,state=prepared(monkeypatch);target,evidence=candidate.planned_target(p,'blue_triangle')
    assert target[0]<=-.0161+1e-10 and target[2]==pytest.approx(.8255)
    assert evidence['minimum_closing_sweep_rail_clearance_m']>=.0025
    assert evidence['measured_material_strip_overlap_m']>.003
    assert state['blue_triangle']['pos'][0]==-.012


def test_material_outside_the_real_tray_is_not_replaced_by_a_fitted_pose(monkeypatch):
    p,state=prepared(monkeypatch);state['blue_triangle']['pos'][0]=-.3;before=state['blue_triangle']['pos'].copy()
    with pytest.raises(ToolExecutionError):candidate.planned_target(p,'blue_triangle')
    assert np.array_equal(state['blue_triangle']['pos'],before)
