"""Native C423 geometry regression and one-piece continuation admission."""
from copy import deepcopy
from types import SimpleNamespace as N
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab import execution_design_e20_slots as slots
from videoicl_isaaclab import execution_design_e20_reference as reference
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def actual423(monkeypatch):
    a,state,contacts=context('E20','C');p=ExecutionDesignAuthor(a)
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':423,'physics_ticks':43140}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    state['compartment_tray'].update(pos=np.array([0.,.1,.826]),mat=np.eye(3))
    # Actual full424 same-boundary physical poses, not proposed target poses.
    state['blue_supply_3'].update(pos=np.array([.11445382982492452,.11670903116464615,.8149869418144227]),
        mat=np.array([[.8498681187629703,-.5269941091537474,.0011238057631999256],
                      [.5269944667816161,.8498685956001285,-.00011041354446206269],
                      [-.0008968999609351158,.0006860765279270709,.9999993443489075]]))
    state['blue_supply_4'].update(pos=np.array([.1110010221600533,.08099934458732604,.8149870610237122]),mat=np.eye(3))
    contacts.add(frozenset(('blue_supply_3','compartment_tray')))
    monkeypatch.setattr(reference,'robot_bases',lambda _:dict(left=np.array([-.65,.3,.81]),right=np.array([-.65,-.3,.81])))
    region=next(r for r in p.d['local_regions']if r['id']=='triangle')
    return a,p,state,contacts,region


def test_real_rotated_blue423_has_an_original_bound_safe_outer_corner(monkeypatch):
    a,p,state,contacts,r=actual423(monkeypatch);before=deepcopy(state);spec=deepcopy(a.scene.spec)
    target=np.asarray(p.free_chip_slot(r,'blue_supply_1'));half=np.abs(state['blue_supply_1']['mat'])@p.objects['blue_supply_1']['size']
    assert target[0]>.16
    assert np.all(target[:2]-half[:2]>=np.asarray(r['lower'])[:2]+.002-1e-12)
    assert np.all(target[:2]+half[:2]<=np.asarray(r['upper'])[:2]-.002+1e-12)
    for name in('blue_supply_3','blue_supply_4'):
        center=state[name]['pos']-state['compartment_tray']['pos'];extent=np.abs(state[name]['mat'])@p.objects[name]['size']
        assert np.any(abs(center[:2]-target[:2])>=extent[:2]+half[:2]+.002)
    assert a.control_report['e20_boundary_slot_search'][-1]['original_four_cells_exhausted']
    assert a.scene.spec==spec
    for name in state:np.testing.assert_array_equal(state[name]['pos'],before[name]['pos'])


def test_old_available_cells_do_not_enter_fallback_or_change_choice(monkeypatch):
    a,p,state,contacts,r=actual423(monkeypatch)
    state['blue_supply_3']['pos']=np.array([-.02,-.12,.837])
    monkeypatch.setattr(slots,'boundary_slot',lambda *args:pytest.fail('original four cells still have room'))
    np.testing.assert_allclose(p.free_chip_slot(r,'blue_supply_1'),[.111,.019,-.012])


def test_all_four_outer_candidates_keep_actual_AABB_occupancy(monkeypatch):
    a,p,state,contacts,r=actual423(monkeypatch)
    # An occupied full 2x2 cell cannot accept a fifth body by using the fallback.
    for name,xy in zip(('blue_supply_3','blue_supply_4','blue_supply_2','blue_initial'),((.111,-.019),(.149,-.019),(.111,.019),(.149,.019))):
        state[name].update(pos=np.array([xy[0],xy[1]+.1,.815]),mat=np.eye(3))
    with pytest.raises(ToolExecutionError,match='No measured free chip slot'):p.free_chip_slot(r,'blue_supply_1')


def test_C423_places_only_original_next_blue_and_does_not_replay_completed(monkeypatch):
    a,p,state,contacts,r=actual423(monkeypatch);calls=[]
    monkeypatch.setattr(reference,'replenishment_candidates',lambda policy,region:['blue_supply_3','blue_supply_1','blue_supply_2'])
    monkeypatch.setattr(reference,'remember_freed_source_rail',lambda policy,name:calls.append(('freed',name)))
    def place(policy,name,actor,local):
        calls.append(('place',name));base,rot=policy.frame({'actor':actor})
        state[name]['pos']=base+rot@(np.asarray(local)+[0,0,.001])
        state[name]['mat']=rot.copy();contacts.add(frozenset((name,actor)));policy.c.steps+=1
    monkeypatch.setattr(ExecutionDesignAuthor,'place',place)
    result=slots.run_segment(a,'e20_c_place_next_blue_from423',{})
    assert result['local_completed']and result['placed_actor']=='blue_supply_1'
    assert calls==[('freed','blue_supply_3'),('place','blue_supply_1')]
    assert not {'success','task_score_100','native_history'}&result.keys()


@pytest.mark.parametrize('fault',['steps','tick','diagnostic','readback','mode','variant','seed','parameters','held','previous_support'])
def test_C423_boundary_and_real_completed_blue_are_mandatory(monkeypatch,fault):
    a,p,state,contacts,r=actual423(monkeypatch);params={}
    if fault=='steps':a._engineering_resume_checkpoint['source']['steps']=424
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=43240
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='variant':a.scene.spec['variant']='B'
    elif fault=='seed':a.scene.spec['seed']=4202
    elif fault=='parameters':params={'skip_previous_check':True}
    elif fault=='held':state['blue_supply_3']['grasp'][0]=True
    else:contacts.discard(frozenset(('blue_supply_3','compartment_tray')))
    monkeypatch.setattr(ExecutionDesignAuthor,'place',lambda *args:pytest.fail('must reject before any action'))
    with pytest.raises(ToolExecutionError):slots.run_segment(a,'e20_c_place_next_blue_from423',params)
