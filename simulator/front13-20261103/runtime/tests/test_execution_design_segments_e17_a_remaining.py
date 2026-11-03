"""A37 begins from true held green and preserves the completed original layer."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context,native_stand
from test_execution_design_segments_e17 import Policy as BasePolicy
from videoicl_isaaclab import execution_design_segments_e17_a_remaining as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_e17_insertion as lower
from videoicl_isaaclab import execution_design_segments_e17_remaining as upper
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Policy(BasePolicy):
    def require_held(self,ref,side):
        if not self.a.state[ref['actor']]['grasp'][1]:raise ToolExecutionError('Actual held green lost')


def prepared(monkeypatch,mode='good'):
    a,state,contacts=context('E17','A',('green_triangle','right'));a.state=state;a.contacts=contacts;a.grasps={};a.events=[];a.smooth=False;a._execution_design_reference_authorized=True
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':37,'physics_ticks':3702}}
    state['stand']['pos']=np.array([.04,.05,.8]);state['green_square']['pos']=np.array([-.004,.006,.8198]);contacts.update([frozenset(('green_square','stand')),frozenset(('stand','table')),frozenset(('packing_lid','table'))])
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy);monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    def act(*args,**kwargs):
        a.c.steps+=1
        if mode=='fail':raise RuntimeError('actual native motion refused')
    a.act=act
    def place_lower(p,name,actor,target,ref,side):
        a.events.append(('held-lower',name,side));assert target[:2]==[.044,-.044]
        state[name]['pos']=state['stand']['pos']+[.044,-.044,.0198];state[name]['grasp'][1]=False;contacts.add(frozenset((name,'stand')));a.act()
    def place_upper(p,name,xy):
        a.events.append(('upper',name));state[name]['pos']=state['stand']['pos']+[*xy,.223];contacts.add(frozenset((name,'stand')));a.act()
    monkeypatch.setattr(lower,'place_held_lower',place_lower);monkeypatch.setattr(upper,'_place_upper',place_upper)
    return a,state,contacts


def test_actual_green_held_continues_without_pickup_then_blue_and_original_cleanup_delivery(monkeypatch):
    a,state,contacts=prepared(monkeypatch);old=a.act;r=segment.run_segment(a,'e17_a_resume_held_green_and_remaining_37',{})
    assert r['local_completed']and a.act is old
    assert a.events==[('held-lower','green_triangle','right'),('upper','blue_square'),('upper','blue_triangle'),('package',),('deliver',)]
    assert set(r)=={'local_completed','operations','active_actions'}


@pytest.mark.parametrize('fault',['old18','wrong_tick','not_native','not_held','lost_prefix','overhanging_prefix','parameter'])
def test_cannot_replay_old_source_or_assume_current_green_grip(monkeypatch,fault):
    a,state,contacts=prepared(monkeypatch);cp=a._engineering_resume_checkpoint;params={}
    if fault=='old18':cp['source']['steps']=18
    elif fault=='wrong_tick':cp['source']['physics_ticks']=3802
    elif fault=='not_native':cp['state_quality']='measured_pose_fixture'
    elif fault=='not_held':state['green_triangle']['grasp'][1]=False
    elif fault=='lost_prefix':contacts.discard(frozenset(('green_square','stand')))
    elif fault=='overhanging_prefix':state['green_square']['pos'][0]=state['stand']['pos'][0]+.06
    else:params={'assume_held':True}
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_resume_held_green_and_remaining_37',params)
    assert not a.c.steps and not a.events


def test_first_native_error_ends_tail_before_new_piece_or_package(monkeypatch):
    a,state,contacts=prepared(monkeypatch,'fail');old=a.act
    with pytest.raises(RuntimeError):segment.run_segment(a,'e17_a_resume_held_green_and_remaining_37',{})
    assert a.c.steps==1 and a.act is old and len(a.events)==1


def test_native1_regrasps_actual_lost_green_before_original_remaining(monkeypatch):
    a,state,contacts=prepared(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':1,'physics_ticks':102}
    state['green_triangle']['grasp'][1]=False
    def pickup(p,name,side_override):
        assert name=='green_triangle'and side_override=='right'
        a.events.append(('actual-regrasp',name));state[name]['grasp'][1]=True
        return p.ref(name),side_override
    monkeypatch.setattr(Policy,'pickup',pickup,raising=False)
    r=segment.run_segment(a,'e17_a_regrasp_after_lost_green_1',{})
    assert r['local_completed']and a.events[0]==('actual-regrasp','green_triangle')
