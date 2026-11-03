from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e46_scoop import ScoopWitness, enabled, REVISION


def sample(w, step, **changes):
    args=dict(step=step, table_supported=True, held=True, hand_grasp=False,
              hand_contact=False, tool_contact=True, edge_under=True,
              relative_edge=-.02, food_bottom=.8, supported_on_blade=True)
    args.update(changes)
    return w.observe('yellow_block', **args)


@pytest.mark.parametrize('variant', list('ABC'))
def test_e46_gate_enabled_without_engineering_flag(variant):
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
    s=load('E46',variant,4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    s['execution_design']={'revision':REVISION}
    assert enabled(s)
    e=ToolTaskEvaluator(s)
    assert e.e46_scoop is not None and e.e28_scoop is None
    assert not enabled({'id':'E28','execution_design':{'revision':REVISION}})
    assert not enabled({'id':'E46'})


@pytest.mark.parametrize('insertion,lift,passes',[(.0039,.01,False),(.0041,.0059,False),(.0041,.0061,True)])
def test_measured_entry_and_lift_boundaries(insertion,lift,passes):
    w=ScoopWitness();sample(w,1)
    sample(w,2,relative_edge=-.02+insertion)
    assert sample(w,3,relative_edge=-.02+insertion,food_bottom=.8+lift,table_supported=False) is passes


@pytest.mark.parametrize('mode',['hand_load','top_contact','side_push','lost_grip'])
def test_false_scoops_never_qualify(mode):
    w=ScoopWitness()
    changes={'hand_load':{'hand_grasp':True},'top_contact':{'edge_under':False},
             'side_push':{},'lost_grip':{'held':False}}[mode]
    sample(w,1,**changes)
    sample(w,2,relative_edge=-.02 if mode=='side_push' else -.01,**changes)
    assert not sample(w,3,table_supported=False,food_bottom=.82)
    assert not w.records


def test_post_scoop_hand_loading_revokes_evidence():
    w=ScoopWitness();sample(w,1);sample(w,2,relative_edge=-.01)
    assert sample(w,3,table_supported=False,food_bottom=.82)
    assert not sample(w,4,hand_contact=True)
    assert not w.records


def test_actual_e46_collector_rejects_hand_loaded_transport():
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
    from videoicl_isaaclab.realworld_tool_expert import _push_rotation
    s=load('E46','A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    s['execution_design']={'revision':REVISION};e=ToolTaskEvaluator(s)
    t=e.tool;name,=e.group('cargo');r=_push_rotation(t['support_normal_local'],[1,0,0],[1,0,0])
    e.state={n:dict(pos=np.zeros(3),mat=np.eye(3),grasp=(False,False))for n in e.objects}
    e.state[t['actor']]=dict(pos=np.array([0,0,.9]),mat=r,grasp=(False,True))
    normal=np.asarray(t['support_normal_local'],float);normal/=np.linalg.norm(normal)
    local=np.asarray(t['working_local'],float)
    local+=normal*(t['support_plane_offset']+e.objects[name]['size'][2]-float(normal@local))
    e.forces={frozenset((name,t['actor'])):1.};e.contacts=set(e.forces)
    for step in range(5):
        e.steps=step;e.state[t['actor']]['pos'][0]=step*.02
        e.state[name]['pos']=e.state[t['actor']]['pos']+r@local
        e._spatula_history([name])
    assert not e.transports and not e.e46_scoop.records
    assert not e.progress_causal[e.label(name)]['transport_achieved']
    # The old collector accepted the same unsupported origin of a carry.
    e.e46_scoop=None
    for step in range(5,10):
        e.steps=step;e.state[t['actor']]['pos'][0]=step*.02
        e.state[name]['pos']=e.state[t['actor']]['pos']+r@local
        e._spatula_history([name])
    assert e.progress_causal[e.label(name)]['transport_achieved']


@pytest.mark.parametrize('variant',list('ABC'))
def test_final_e46_check_requires_scoop_even_with_destination_and_transport(variant):
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
    s=load('E46',variant,4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    s['execution_design']={'revision':REVISION};e=ToolTaskEvaluator(s)
    e.state={n:dict(pos=np.zeros(3),mat=np.eye(3),grasp=(False,False))for n in e.objects}
    e.contacts=set();e.forces={}
    e._target_stable=lambda released:True;e._mechanism_stable=lambda:True
    e._spatula_history=lambda names:None;e._region=lambda name:('circle','triangle','square')['ABC'.index(variant)]
    name,=e.group('cargo');e.transports[name]=[{'prior_transport':True}]
    e.derive(True)
    assert e.extra_checks['true_blade_entry_and_lift'] is False
    # An independently measured scoop supplies the missing rule evidence.
    sample(e.e46_scoop,1);sample(e.e46_scoop,2,relative_edge=-.01)
    sample(e.e46_scoop,3,table_supported=False,food_bottom=.82)
    e.derive(True)
    assert e.extra_checks['true_blade_entry_and_lift'] is True
