"""B213 skips all three placed pieces and completes only the remaining workflow."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from test_execution_design_segments_e17 import Policy
from videoicl_isaaclab import execution_design_segments_e17_b_remaining as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_segments_e17_remaining as upper
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def prepared(monkeypatch,mode='good'):
    a,state,contacts=context('E17','B');a.state=state;a.contacts=contacts;a.grasps={};a.events=[];a.smooth=False;a._execution_design_reference_authorized=True
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':213,'physics_ticks':21302}}
    state['stand']['pos']=np.array([.04,.05,.8]);contacts.update([frozenset(('stand','table')),frozenset(('packing_lid','table'))])
    for name,local in [('blue_square',[-.044,-.044,.0198]),('green_square',[.044,-.044,.0198]),('blue_triangle',[-.044,-.046,.223])]:
        state[name]['pos']=state['stand']['pos']+local;contacts.add(frozenset((name,'stand')))
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    def act(*args,**kwargs):
        a.c.steps+=1
        if mode=='fail':raise RuntimeError('actual public motion rejected')
    a.act=act
    monkeypatch.setattr(upper,'_retreat',lambda p,name,sign:(a.events.append(('retreat',name,sign)),a.act()))
    def place(p,name,xy):
        a.events.append(('remaining',name,xy));state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')));a.act()
    monkeypatch.setattr(upper,'_place_upper',place)
    return a,state,contacts


def test_only_last_green_then_original_cleanup_delivery_after_real_retreat(monkeypatch):
    a,state,contacts=prepared(monkeypatch);old=a.act;r=segment.run_segment(a,'e17_b_resume_remaining_after_upper_213',{})
    assert r['local_completed']and a.act is old
    assert a.events==[('retreat','blue_triangle',-1),('remaining','green_triangle',[.044,-.044]),('package',),('deliver',)]
    assert set(r)=={'local_completed','operations','active_actions'}


@pytest.mark.parametrize('fault',['old722','wrong_tick','not_native','missing_support','overhang','parameter'])
def test_three_completed_pieces_and_exact_native213_are_required(monkeypatch,fault):
    a,state,contacts=prepared(monkeypatch);cp=a._engineering_resume_checkpoint;params={}
    if fault=='old722':cp['source']['steps']=722
    elif fault=='wrong_tick':cp['source']['physics_ticks']=21402
    elif fault=='not_native':cp['state_quality']='measured_pose_fixture'
    elif fault=='missing_support':contacts.discard(frozenset(('green_square','stand')))
    elif fault=='overhang':state['blue_triangle']['pos'][0]=state['stand']['pos'][0]+.065
    else:params={'assume_complete':True}
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_resume_remaining_after_upper_213',params)
    assert not a.events and not a.c.steps


def test_first_native_error_does_not_continue_to_last_piece(monkeypatch):
    a,state,contacts=prepared(monkeypatch,'fail');old=a.act
    with pytest.raises(RuntimeError):segment.run_segment(a,'e17_b_resume_remaining_after_upper_213',{})
    assert a.c.steps==1 and a.act is old and len(a.events)==1
