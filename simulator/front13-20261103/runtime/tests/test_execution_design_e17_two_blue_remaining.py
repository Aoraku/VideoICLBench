import numpy as np
import pytest
from test_execution_design_segments_e17_remaining import prepared,Policy
from videoicl_isaaclab import execution_design_e17_two_blue_remaining as segment
from videoicl_isaaclab import execution_design_e17_empty_exit as escape
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 a,state,contacts=prepared(monkeypatch);a._engineering_resume_checkpoint.update(state_quality='measured_native_state',context={})
 state['blue_triangle']['pos']=state['stand']['pos']+[-.044,.044,.223];contacts.add(frozenset(('blue_triangle','stand')))
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy)
 monkeypatch.setattr(escape,'retreat_west',lambda p,n:(a.events.append(('west-exit',n)),a.act()))
 def place(p,name,xy):state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')));a.events.append(('remaining-green',name));a.act()
 monkeypatch.setattr(segment,'place_right_column',place)
 return a,state,contacts


def test_two_real_blues_preserved_then_only_greens_and_original_delivery(monkeypatch):
 a,state,contacts=setup(monkeypatch);r=segment.run_segment(a,'e17_c_resume_after_two_blues_1',{})
 assert r['local_completed']and a.events==[('west-exit','blue_triangle'),('remaining-green','green_square'),('remaining-green','green_triangle'),('package',),('deliver',)]
 assert set(r)=={'local_completed','operations','active_actions'}


def test_first_blue_only_source_is_rejected_before_any_replay(monkeypatch):
 a,state,contacts=setup(monkeypatch);contacts.remove(frozenset(('blue_triangle','stand')))
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_resume_after_two_blues_1',{})
 assert a.c.steps==0


@pytest.mark.parametrize('entry,steps,tick',[('e17_c_low_ingress_from_held100',100,10002),('e17_c_low_ingress_from_held2',2,202)])
def test_exact_held100_continues_current_green_without_regrasp(monkeypatch,entry,steps,tick):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':steps,'physics_ticks':tick}
 calls=[]
 def place(p,name,xy,**kw):
  calls.append((name,kw));state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')));a.act()
 monkeypatch.setattr(segment,'place_right_column',place)
 from videoicl_isaaclab import execution_design_e17_recycle_delivery as recycle
 monkeypatch.setattr(recycle,'recycle_all',lambda p:a.events.append(('recycle',)))
 monkeypatch.setattr(recycle,'deliver_stand',lambda p:a.events.append(('deliver',)))
 result=segment.run_segment(a,entry,{})
 assert calls==[('green_square',{'edge_grip':True,'already_held':True}),('green_triangle',{'edge_grip':True,'already_held':False})]
 assert result['local_completed'] and set(result)=={'local_completed','operations','active_actions'}
 assert not any(row[0]=='west-exit' for row in a.events)


def test_held100_rejects_wrong_tick_before_any_action(monkeypatch):
 a,state,contacts=setup(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':100,'physics_ticks':10003}
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_low_ingress_from_held100',{})
 assert a.c.steps==0
