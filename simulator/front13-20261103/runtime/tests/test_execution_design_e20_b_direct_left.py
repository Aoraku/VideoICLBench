import numpy as np
import pytest
from test_execution_design_e20_slots import actual423
from videoicl_isaaclab import execution_design_e20_b_direct_left as direct
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def current(monkeypatch):
    a,p,state,contacts,r=actual423(monkeypatch);a.scene.spec['variant']='B'
    a._engineering_resume_checkpoint['source']={'steps':424,'physics_ticks':43240}
    contacts.add(frozenset(('blue_supply_4','compartment_tray')));calls=[]
    def pickup(p,name,side_override):
        calls.append((name,side_override));state[name]['grasp']=[True,False];state[name]['pos'][2]+=.03
        contacts.update(frozenset((name,'left_finger'+str(i)))for i in(1,2));return p.ref(name),'left'
    monkeypatch.setattr(P,'pickup',pickup)
    return a,state,contacts,calls


def test_B424_direct_left_reuses_real_original_source_without_handover(monkeypatch):
    a,state,contacts,calls=current(monkeypatch);r=direct.run_segment(a,'e20_b_pickup_blue_left_from424',{})
    assert r['local_completed']and calls==[('blue_supply_1','left')]


@pytest.mark.parametrize('fault',['step','source','held'])
def test_B424_rejects_other_or_unavailable_actual_source(monkeypatch,fault):
    a,state,contacts,calls=current(monkeypatch)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=425
    elif fault=='source':contacts.discard(frozenset(('blue_supply_1','fixture3')))
    else:state['blue_supply_1']['grasp'][1]=True
    with pytest.raises(ToolExecutionError):direct.run_segment(a,'e20_b_pickup_blue_left_from424',{})
    assert not calls
