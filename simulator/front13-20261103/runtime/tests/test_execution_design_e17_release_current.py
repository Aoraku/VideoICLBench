import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from test_execution_design_segments_e17 import Policy
from videoicl_isaaclab import execution_design_e17_release_current as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_segments_e17_e20 as grip
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 a,state,contacts=context('E17','C',('blue_triangle','right'));a.state=state;a.contacts=contacts;a.grasps={};a.smooth=False;a._execution_design_reference_authorized=True
 a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':117,'physics_ticks':11702}}
 state['stand']['pos']=np.array([.04,.05,.8]);state['blue_square']['pos']=np.array([-.004,.006,1.0228]);contacts.add(frozenset(('blue_square','stand')))
 state['blue_triangle'].update(pos=np.array([-.02585317,.09212557,1.03390068]),mat=np.array([[-.0621058,-.11206174,-.99175858],[.56649995,.81414366,-.12746774],[.82171816,-.56974763,.0129199]]))
 monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand());monkeypatch.setattr(grip,'_held_with_contacts',lambda p,n,s:None)
 def act(*args,**kwargs):a.c.steps+=1;state['blue_triangle']['grasp'][1]=False;contacts.add(frozenset(('blue_triangle','stand')))
 a.act=act
 monkeypatch.setattr(Policy,'act',lambda p,*args,**kwargs:p.a.act(*args,**kwargs),raising=False)
 return a,state


def test_already_in_native_region_is_released_without_chasing_center(monkeypatch):
 a,state=setup(monkeypatch);r=segment.run_segment(a,'e17_c_release_in_region_blue_117',{})
 assert r['local_completed']and r['active_actions']==1 and set(r)=={'local_completed','operations','active_actions'}


def test_actual_outside_region_still_refuses_before_action(monkeypatch):
 a,state=setup(monkeypatch);state['blue_triangle']['pos'][0]-=.01
 with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_release_in_region_blue_117',{})
 assert a.c.steps==0
