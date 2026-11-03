"""Continue after successful C release, never replay its blue or packing lid."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from test_execution_design_segments_e17 import Policy
from videoicl_isaaclab import execution_design_segments_e17_remaining as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def prepared(monkeypatch,mode='good'):
    a,state,contacts=context('E17','C');a.state=state;a.contacts=contacts;a.events=[];a.grasps={};a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_pose_fixture','source':{'steps':1,'physics_ticks':102},'context':{'scene_input_provenance':{'terminal_measurement_hydrated':True}}}
    state['stand']['pos']=np.array([.04,.05,.8]);state['blue_square']['pos']=np.array([-.004,.006,1.023]);contacts.update([frozenset(('blue_square','stand')),frozenset(('stand','table')),frozenset(('packing_lid','table'))])
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    def act(*args,**kwargs):
        a.c.steps+=1
        if mode=='first_failure':raise RuntimeError('actual native increment rejected')
        if mode=='lose_blue':contacts.discard(frozenset(('blue_square','stand')))
    a.act=act
    def retreat(p,name,sign):a.events.append(('retreat',name,sign));a.act()
    def place(p,name,xy):
        a.events.append(('remaining',name,xy));state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')));a.act()
    monkeypatch.setattr(segment,'_retreat',retreat);monkeypatch.setattr(segment,'_place_upper',place)
    return a,state,contacts


def test_successful_blue_is_preserved_then_remaining_three_and_original_cleanup_delivery(monkeypatch):
    a,state,contacts=prepared(monkeypatch);old=a.act;result=segment.run_segment(a,'e17_c_resume_remaining_after_blue_release_1',{})
    assert result['local_completed']and a.act is old
    assert a.events[0]==('retreat','blue_square',-1)
    assert [e[1]for e in a.events if e[0]=='remaining']==['blue_triangle','green_square','green_triangle']
    assert a.events[-2:]==[('package',),('deliver',)]
    assert len({tuple(xy)for xy in segment.SLOTS.values()}|{(-.044,-.044)})==4
    assert set(result)=={'local_completed','operations','active_actions'}


@pytest.mark.parametrize('fault',['old222','old490','wrong_tick','not_terminal','not_pose','parameter','blue_unsupported'])
def test_source_is_the_successful_terminal_not_an_earlier_boundary(monkeypatch,fault):
    a,state,contacts=prepared(monkeypatch);cp=a._engineering_resume_checkpoint;params={}
    if fault in('old222','old490'):cp['source']['steps']=int(fault[3:])
    elif fault=='wrong_tick':cp['source']['physics_ticks']=2
    elif fault=='not_terminal':cp['context']['scene_input_provenance'].clear()
    elif fault=='not_pose':cp['state_quality']='measured_native_state'
    elif fault=='parameter':params={'skip_native':True}
    else:contacts.discard(frozenset(('blue_square','stand')))
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_resume_remaining_after_blue_release_1',params)
    assert not a.c.steps and not a.events


@pytest.mark.parametrize('mode',['first_failure','lose_blue'])
def test_first_actual_failure_preserves_failure_and_stops_remainder(monkeypatch,mode):
    a,state,contacts=prepared(monkeypatch,mode);old=a.act
    with pytest.raises((ToolExecutionError,RuntimeError)):segment.run_segment(a,'e17_c_resume_remaining_after_blue_release_1',{})
    assert a.c.steps==1 and a.events==[('retreat','blue_square',-1)]and a.act is old


def test_native93_skips_completed_retreat_and_delegates_tilted_blue_source_only(monkeypatch):
    from videoicl_isaaclab import execution_design_e17_tilted_grasp as tilted
    a,state,contacts=prepared(monkeypatch);a._engineering_resume_checkpoint.update(state_quality='measured_native_state',source={'steps':93,'physics_ticks':9302},context={})
    original=segment._place_upper;seen=[]
    monkeypatch.setattr(tilted,'acquire',lambda p,ref,side:seen.append((ref['actor'],side)))
    def place(p,name,xy):
        p.acquire_chip_with_wrist_margin(p.ref(name),'right');original(p,name,xy)
    monkeypatch.setattr(segment,'_place_upper',place)
    result=segment.run_segment(a,'e17_c_resume_remaining_after_relevel_93',{})
    assert result['local_completed']and seen==[('blue_triangle','right')]
    assert not any(e[0]=='retreat'for e in a.events)
    assert [e[1]for e in a.events if e[0]=='original-acquire']==['green_square','green_triangle']


def test_native121_uses_rail_top_grip_and_does_not_relevel_low_blue_wrist(monkeypatch):
    from videoicl_isaaclab import execution_design_e17_rail_top_grasp as rail
    a,state,contacts=prepared(monkeypatch);a._engineering_resume_checkpoint.update(state_quality='measured_native_state',source={'steps':121,'physics_ticks':12102},context={})
    original=segment._place_upper;seen=[];levels=[]
    monkeypatch.setattr(rail,'acquire',lambda p,ref,side:seen.append((ref['actor'],side)))
    def place(p,name,xy,**kwargs):
        levels.append((name,kwargs.get('relevel',True)));p.acquire_chip_with_wrist_margin(p.ref(name),'right');original(p,name,xy)
    monkeypatch.setattr(segment,'_place_upper',place)
    result=segment.run_segment(a,'e17_c_resume_remaining_above_rail_121',{})
    assert result['local_completed']and seen==[('blue_triangle','right'),('green_triangle','right')]
    assert levels[0]==('blue_triangle',False)and not any(e[0]=='retreat'for e in a.events)
