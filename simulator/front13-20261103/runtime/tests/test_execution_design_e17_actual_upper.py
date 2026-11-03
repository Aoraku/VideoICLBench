"""Actual held suffix protects native regions and binds the newest boundary."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from test_execution_design_segments_e17 import Policy
from videoicl_isaaclab import execution_design_e17_actual_upper as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_segments_e17_e20 as grip
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 a,state,contacts=context('E17','B',('green_triangle','right'));a.state=state;a.contacts=contacts;a.grasps={};a.events=[];a.smooth=False;a._execution_design_reference_authorized=True
 a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':492,'physics_ticks':49202}}
 state['stand']['pos']=np.array([.04,.05,.8])
 for name,point in [('blue_square',[-.044,-.044,.0198]),('green_square',[.044,-.044,.0198]),('blue_triangle',[-.044,-.044,.223])]:state[name]['pos']=state['stand']['pos']+point;contacts.add(frozenset((name,'stand')))
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand());monkeypatch.setattr(grip,'_held_with_contacts',lambda p,n,s:None)
 def act():a.c.steps+=1
 a.act=act
 def place(p,name,xy,guard,**kwargs):
  guard();a.act();state[name]['grasp'][1]=False;state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')))
 monkeypatch.setattr(segment,'place_current',place)
 return a,state,contacts


def test_492_places_current_piece_without_regrasp_or_full_grade(monkeypatch):
 a,state,contacts=setup(monkeypatch);r=segment.run_segment(a,'e17_b_release_actual_upper_green_492',{})
 assert r['local_completed']and r['active_actions']==1 and set(r)=={'local_completed','operations','active_actions'}


@pytest.mark.parametrize('fault',['old_source','wrong_tick','missing_support','overhang','parameters'])
def test_boundary_and_native_completed_piece_protection(monkeypatch,fault):
 a,state,contacts=setup(monkeypatch);params={}
 if fault=='old_source':a._engineering_resume_checkpoint['source']['steps']=213
 elif fault=='wrong_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=49203
 elif fault=='missing_support':contacts.remove(frozenset(('blue_triangle','stand')))
 elif fault=='overhang':state['blue_triangle']['pos'][0]=.12
 else:params={'pass':True}
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_release_actual_upper_green_492',params)
 assert a.c.steps==0


def test_lowest_reference_is_actual_mesh_vertex_for_vertical_triangle():
 class P:
  def frame(self,ref):return np.zeros(3),np.array([[0,0,1],[0,1,0],[-1,0,0.]])
 p=P();ref=segment.lowest_reference(p,'green_triangle');rot=p.frame(ref)[1];point=rot@ref['local']
 assert point[2]==pytest.approx((segment.TRIANGLE@rot.T)[:,2].min())
