"""Small divider geometry and exact native223 scope regressions."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from videoicl_isaaclab import execution_design_segments_e17_regrasp as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_source_raised_rail_has_a_real_adjacent_empty_floor_bay():
    a,state,contacts=context('E17','A');p=segment.ExecutionDesignAuthor(a)
    state['packing_box']['pos']=np.array([-.2,-.12,.826]);state['green_triangle']['pos']=np.array([-.184,.004,.829])
    obj,rails,floor,low,high=segment._bay(p)
    assert len(rails)==4 and floor==pytest.approx(-.012)
    assert [low,high]==pytest.approx([.054,.106])and (low+high)/2==pytest.approx(.08)


def test_only_planned_tcp_is_fitted_inside_actual_wall_and_bay_clearance():
    point=np.array([.018,.080,.010]);before=point.copy();lo=np.array([-.066,-.011,-.009]);hi=np.array([.066,.011,.045])
    target=segment._fit_xy(point,lo,hi,-.082,.082,.054,.106)
    assert np.array_equal(point,before)and target[0]==pytest.approx(.0135)and target[1]==.08
    with pytest.raises(ToolExecutionError):segment._fit_xy(np.array([.04,.08,0]),lo,hi,-.082,.082,.054,.106)


@pytest.mark.parametrize('fault',['old842','quasistatic','variant','parameter','not_wrong_box'])
def test_no_prefix_replay_or_assumed_green_grip_can_enter_native223(monkeypatch,fault):
    a,state,contacts=context('E17','A');a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':223,'physics_ticks':22311}}
    params={}
    if fault=='old842':a._engineering_resume_checkpoint['source']['steps']=842
    elif fault=='quasistatic':a._engineering_resume_checkpoint['state_quality']='measured_pose_fixture'
    elif fault=='variant':a.scene.spec['variant']='B'
    elif fault=='parameter':params={'assume_held':True}
    monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    a.act=lambda *x,**y:pytest.fail('must reject before any new physical action')
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_release_box_nudge_regrasp_223',params)
