"""Engineering control planning tests, never native-negative certificates."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.execution_design_negative_expert import (
    CONTROLS,TASKS,ExecutionDesignNegativeAuthor,UnsupportedNegativeControl)
from videoicl_isaaclab.execution_design_scenes import build_execution_scene
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'


def author(task,variant='A',seed=4201):
    spec=build_execution_scene(load(task,variant,seed,BINDINGS,verify_files=False))
    return SimpleNamespace(c=SimpleNamespace(steps=0),scene=SimpleNamespace(spec=spec,
        embodiment=SimpleNamespace(config={'control':{'step_mm':[1,10],'rotation_deg':[1,10]}})))


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('control',CONTROLS)
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_control_plan_never_mutates_scene_or_claims_observed(task,variant,control,seed):
    a=author(task,variant,seed);before=deepcopy(a.scene.spec)
    positive=ExecutionDesignAuthor(a);before_positive=deepcopy(positive.d)
    negative=ExecutionDesignNegativeAuthor(a,control)
    assert a.scene.spec==before and positive.d==before_positive
    assert negative.perturbation['validation']=='native_observation_required'
    assert 'negative_condition_observed' not in negative.perturbation
    if control=='wrong_members':
        if negative.extra_member is None:
            assert len(negative.member_substitution)==1
            original,spare=next(iter(negative.member_substitution.items()))
            assert original in before['execution_design']['target_members']
            assert spare in before['execution_design']['batch_members']['distractor']
            if task=='E20':assert all(original not in ids for ids in before['execution_design']['initial_preserved'].values())
        else:
            assert task=='E20' and negative.perturbation['mode']=='extra_member'
            assert negative.extra_member['member'] in before['execution_design']['batch_members']['distractor']
    if control=='wrong_destination':assert negative.d['destination_zone']!=positive.d['destination_zone']


def test_wrong_e39_rule_copies_sealed_baseline_and_default_is_unchanged():
    a=author('E39','B')
    rule=dict(pieces=['a','b'],expected_order=['a','b'],expected_yaws={'a':.1,'b':.2},match_order=False)
    a.c.evaluator=SimpleNamespace(initial_sealed=True,initial_order_rule=deepcopy(rule))
    positive=ExecutionDesignAuthor(a);negative=ExecutionDesignNegativeAuthor(a,'wrong_rule')
    assert positive.order_rule()==rule
    assert negative.order_rule()['expected_yaws']['a']>3.14/2
    assert a.c.evaluator.initial_order_rule==rule
    assert positive.order_rule()==rule


def test_not_released_delivery_requires_actual_hold_without_release_call():
    p=ExecutionDesignNegativeAuthor(author('E01'),'not_released')
    p.stage=lambda *args:None;p.pickup=lambda n:(dict(actor=n),'left')
    p.bottom_local=lambda n:np.array([0,0,-.09]);p.point=lambda ref:np.array([0,0,1.])
    checks=[];moves=[]
    p.require_held=lambda *args:checks.append(args)
    def move_point(side,ref,target,guard):
        guard();moves.append(np.asarray(target))
    p.move_point=move_point;p.rotate_actor=lambda *args:None;p.wait=lambda *args:None
    p.release=lambda *args:pytest.fail('not_released control must not release at destination')
    p.deliver()
    assert len(moves)==3 and len(checks)==4
    zone=next(z for z in p.spec['zones'] if z['id']==p.d['destination_zone'])
    np.testing.assert_allclose(moves[-1],[*zone['xy'],.801])


def test_unknown_control_and_missing_distractor_fail_closed():
    a=author('E09')
    with pytest.raises(UnsupportedNegativeControl):ExecutionDesignNegativeAuthor(a,'positive')
    a.scene.spec['execution_design']['batch_members']['distractor']=[]
    with pytest.raises(UnsupportedNegativeControl):ExecutionDesignNegativeAuthor(a,'wrong_members')


def test_negative_interface_is_not_wired_into_model_or_positive_dispatch():
    root=Path(__file__).parents[1]/'videoicl_isaaclab'
    for path in (root/'demonstration.py',root/'execution_design_expert.py'):
        assert 'solve_execution_design_negative' not in path.read_text()


def test_e20_fixed_seed_4202_preserves_initial_and_adds_extra_in_measured_free_cell():
    a=author('E20','A',4202);before=deepcopy(a.scene.spec)
    p=ExecutionDesignNegativeAuthor(a,'wrong_members')
    assert [len(x) for x in p.d['initial_preserved'].values()]==[2,2,2]
    assert p.member_substitution=={}
    assert p.perturbation['mode']=='extra_member'
    assert p.d['initial_preserved']==before['execution_design']['initial_preserved']
    # Feed measured native-style positions at the actual authored seed rather
    # than mocking the free-cell decision or changing seed to create additions.
    oo={o['id']:o for o in p.spec['objects']};tray=oo['compartment_tray']
    base=np.array([*tray['xy'],tray.get('center_z',tray['bottom']+tray['size'][2])])
    state={n:dict(pos=np.array([*o['xy'],o.get('center_z',o['bottom']+o['size'][2])]),mat=np.eye(3)) for n,o in oo.items()}
    p.frame=lambda ref:(base,np.eye(3));p.snapshot=lambda:(state,set())
    placements=[];p.place=lambda *args:placements.append(args)
    p.local_stage()
    assert len(placements)==1
    name,actor,point=placements[0]
    assert name==p.extra_member['member'] and actor=='compartment_tray'
    assert point[1]>0  # The two preserved seed-4202 cells occupy the lower row.
    assert a.scene.spec==before
    r=next(r for r in p.d['local_regions'] if r['id']==p.extra_member['region'])
    # Real occupancy can contradict the nominal count: fail rather than force
    # the extra piece onto an occupied cell.
    free_ids=[n for n in r['candidates'] if n not in p.d['initial_preserved'][r['id']]][:2]
    middle=(np.array(r['lower'])+r['upper'])/2
    for n,x in zip(free_ids,[-.019,.019]):state[n]['pos']=base+np.array([middle[0]+x,.019,0])
    with pytest.raises(ToolExecutionError,match='No measured free chip slot'):p.local_stage()
