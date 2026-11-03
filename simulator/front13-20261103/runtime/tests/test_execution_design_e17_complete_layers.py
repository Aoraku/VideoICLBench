import pytest
from test_execution_design_segments_e17_b_remaining import prepared,Policy
from videoicl_isaaclab import execution_design_e17_complete_layers as segment
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 a,state,contacts=prepared(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':16,'physics_ticks':1602}
 state['green_triangle']['pos']=state['stand']['pos']+[.030,-.044,.223];contacts.add(frozenset(('green_triangle','stand')))
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy)
 return a,state,contacts


def test_completed_real_layers_continue_original_cleanup_delivery_without_regrasp(monkeypatch):
 a,state,contacts=setup(monkeypatch);r=segment.run_segment(a,'e17_b_recycle_deliver_after_release16',{})
 assert r['local_completed']and a.events==[('retreat','green_triangle',-1),('package',),('deliver',)]
 assert set(r)=={'local_completed','operations','active_actions'}


def test_old_source_cannot_be_used_for_completed_layers(monkeypatch):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']['steps']=492
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_recycle_deliver_after_release16',{})
 assert not a.c.steps
