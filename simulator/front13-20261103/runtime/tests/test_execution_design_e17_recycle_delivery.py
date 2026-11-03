import numpy as np
import pytest
from test_execution_design_e17_complete_layers import setup,Policy
from videoicl_isaaclab import execution_design_e17_recycle_delivery as segment
from videoicl_isaaclab import execution_design_segments_e17_e20 as grip
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_contact_stops_descent_without_exact_target_chasing():
 class P:
  def __init__(self):self.events=[]
  def contact(self,*args):return True
  def require_held(self,*args):pass
  def release(self,*args):self.events.append('release')
  def move_point(self,*args,**kwargs):pytest.fail('Already supported: no coordinate chasing')
  def act(self,*args,**kwargs):pytest.fail('Already supported: no extra downward action')
 p=P();segment.descend_release(p,'packing_box',{},'right',{},'recycle_box',.806)
 assert p.events==['release']


def test_held999_skips_all_placements_then_recycles_and_delivers(monkeypatch):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':999,'physics_ticks':99902}
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(grip,'_held_with_contacts',lambda *args:None)
 monkeypatch.setattr(segment,'park_left',lambda p:a.events.append(('park-left',)))
 monkeypatch.setattr(segment,'recycle_box',lambda p,r,s:(a.events.append(('box',)),a.act()))
 monkeypatch.setattr(segment,'recycle_lid',lambda p:(a.events.append(('lid',)),a.act()))
 monkeypatch.setattr(segment,'deliver_stand',lambda p:p.deliver())
 r=segment.run_segment(a,'e17_b_recycle_low_from_held999',{})
 assert r['local_completed']and a.events==[('park-left',),('box',),('lid',),('deliver',)]
 assert set(r)=={'local_completed','operations','active_actions'}


def test_wrong_native_source_rejected_before_actions(monkeypatch):
 a,state,contacts=setup(monkeypatch)
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_recycle_low_from_held999',{})
 assert a.c.steps==0


def test_exact187_starts_real_box_handover_without_repeating_retreat(monkeypatch):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':187,'physics_ticks':18702}
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(grip,'_held_with_contacts',lambda *args:None)
 monkeypatch.setattr(segment,'park_left',lambda p:pytest.fail('Already clear: do not repeat retreat'))
 monkeypatch.setattr(segment,'hand_box_to_left',lambda p:(a.events.append(('handover',)) or ({'actor':'packing_box'},'left')))
 monkeypatch.setattr(segment,'recycle_box',lambda p,r,s:a.events.append(('box',s)))
 monkeypatch.setattr(segment,'clear_left_after_recycle',lambda p:a.events.append(('clear-left',)))
 monkeypatch.setattr(segment,'recycle_lid',lambda p:a.events.append(('lid',)))
 monkeypatch.setattr(segment,'deliver_stand',lambda p:p.deliver())
 result=segment.run_segment(a,'e17_b_handover_recycle_from_held187',{})
 assert result['local_completed']and a.events==[('handover',),('box','left'),('clear-left',),('lid',),('deliver',)]
 assert set(result)=={'local_completed','operations','active_actions'}


def test_handover_entry_rejects_non187_source(monkeypatch):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':186,'physics_ticks':18602}
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_handover_recycle_from_held187',{})
 assert a.c.steps==0
