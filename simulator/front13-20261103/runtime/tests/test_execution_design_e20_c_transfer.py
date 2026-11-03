from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e20_slots import actual423
from videoicl_isaaclab import execution_design_e20_c_transfer as transfer
from videoicl_isaaclab import execution_design_e20_far_blue as far
from videoicl_isaaclab import engineering_front25_suffix as dispatcher
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def current(monkeypatch):
    a,p,state,contacts,region=actual423(monkeypatch);calls=[]
    a._engineering_resume_checkpoint['source']={'steps':321,'physics_ticks':32102}
    name='blue_supply_1';state[name].update(pos=np.array([-.28497,-.11491,.84578]),mat=np.eye(3),grasp=[False,True])
    contacts.update(frozenset((name,'right_finger'+str(i)))for i in (1,2))
    contacts.add(frozenset(('blue_supply_4','compartment_tray')))
    def move_point(p,side,ref,target,guard,**kw):
        guard();calls.append(('point',p.max_mm));state[name]['pos']=np.asarray(target)-np.asarray(ref['local']);p.c.steps+=1;guard()
    def release(p,ref,side):
        calls.append(('release',p.max_mm));state[name]['grasp']=[False,False]
        contacts.difference_update(frozenset((name,'right_finger'+str(i)))for i in(1,2));contacts.add(frozenset((name,'fixture2')));p.c.steps+=1
    def pickup(p,n,side_override):
        calls.append(('pickup',side_override));state[name]['grasp']=[True,False];contacts.discard(frozenset((name,'fixture2')))
        contacts.update(frozenset((name,'left_finger'+str(i)))for i in(1,2));return p.ref(n),side_override
    def place(p,n,ref,side,actor,local):
        calls.append(('place',side));state[name]['grasp']=[False,False];state[name]['pos']=state[actor]['pos']+np.asarray(local)+[0,0,.001]
        contacts.add(frozenset((name,actor)))
    monkeypatch.setattr(P,'move_point',move_point);monkeypatch.setattr(P,'release',release)
    monkeypatch.setattr(P,'move',lambda p,*args,**kw:calls.append(('retreat',p.max_mm)))
    monkeypatch.setattr(P,'pickup',pickup);monkeypatch.setattr(far,'place',place)
    return a,state,contacts,calls


def test_C321_short_alignment_preserves_real_handover_and_original_destination(monkeypatch):
    a,state,contacts,calls=current(monkeypatch);before=deepcopy(a.scene.spec)
    result=dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_c_finish_blue_transfer_from321','parameters':{}})
    assert result['segment_passed']and not result['full_task_acceptance']
    assert calls==[('point',2.),('point',2.),('release',2.),('retreat',10.),('pickup','left'),('place','left')]
    assert a.scene.spec==before


@pytest.mark.parametrize('fault',['step','tick','readback','held','previous_support'])
def test_C321_other_boundary_or_lost_real_support_rejects_without_motion(monkeypatch,fault):
    a,state,contacts,calls=current(monkeypatch)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=320
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=32103
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='held':state['blue_supply_1']['grasp'][1]=False
    else:contacts.discard(frozenset(('blue_supply_3','compartment_tray')))
    with pytest.raises((ValueError,ToolExecutionError)):transfer.run_segment(a,'e20_c_finish_blue_transfer_from321',{})
    assert not calls


def test_C1_uses_actual_supported_release_then_only_left_acquisition(monkeypatch):
    a,state,contacts,calls=current(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':1,'physics_ticks':110}
    state['blue_supply_1']['grasp']=[False,False]
    contacts.difference_update(frozenset(('blue_supply_1','right_finger'+str(i)))for i in(1,2))
    contacts.add(frozenset(('blue_supply_1','fixture2')))
    monkeypatch.setattr(P,'act',lambda p,side,token:calls.append((side,token)))
    result=dispatcher.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_c_reacquire_supported_blue_from1','parameters':{}})
    assert result['segment_passed']and calls==[('right','RELEASE'),('retreat',10.),('pickup','left'),('place','left')]


def test_C1_missing_actual_rail_support_rejects_before_opening(monkeypatch):
    a,state,contacts,calls=current(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':1,'physics_ticks':110}
    state['blue_supply_1']['grasp']=[False,False]
    monkeypatch.setattr(P,'act',lambda *args:pytest.fail('must reject before public act'))
    with pytest.raises(ToolExecutionError,match='support'):transfer.run_segment(a,'e20_c_reacquire_supported_blue_from1',{})
    assert not calls
