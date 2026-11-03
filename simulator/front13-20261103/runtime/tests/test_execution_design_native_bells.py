import importlib.util
from pathlib import Path
from copy import deepcopy
import pytest
from videoicl_isaaclab.execution_design_inputs import e26_targets
from videoicl_isaaclab.realworld_mechanism_evidence import MechanismTaskEvaluator
from videoicl_isaaclab.realworld_mechanism_expert import _Author

source=Path(__file__).resolve().parents[3]/'isaaclab_tasks/tests/test_realworld_mechanism_evidence.py'
specmod=importlib.util.spec_from_file_location('legacy_bell_fixtures',source);f=importlib.util.module_from_spec(specmod);specmod.loader.exec_module(f)

def spec(variant='A'):
    s=f.mechanism_spec('E26',variant)
    s['execution_design']={'revision':'embodied50-execution-v2-20261102','condition':'I'}
    s['semantic']['digit_cards']={'left':3,'right':2}
    s['zones']=[{'id':'left_digit','digit':3},{'id':'right_digit','digit':2}]
    return s

@pytest.mark.parametrize('variant',['A','B','C'])
@pytest.mark.parametrize('revision',['embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'])
def test_new_counts_use_native_contact_history_and_raw_progress(variant,revision):
    s=spec(variant);s['execution_design']['revision']=revision
    e=MechanismTaskEvaluator(s);state=f.state_for(s);f.tick(e,state)
    for side,n in e26_targets(s).items():
        for _ in range(n):f.bell_cycle(e,state,side)
    r=f.settle(e,state)
    assert r['success'] and r['progress_result']['task_score_100']==100
    assert r['progress_result']['required_change_count']==5
    assert r['progress_result']['progress_available']
    assert r['progress_evidence']['digit_cards']=={'left':3,'right':2}

@pytest.mark.parametrize('fault',['wrong_counts','no_contact','invalid_history','not_released'])
def test_new_bells_cannot_pass_without_native_guards(fault):
    s=spec();e=MechanismTaskEvaluator(s);state=f.state_for(s);f.tick(e,state)
    counts={'left':9,'right':1} if fault=='wrong_counts' else {'left':3,'right':2}
    for side,n in counts.items():
        for _ in range(n):f.bell_cycle(e,state,side,body='machine/base' if fault=='no_contact' else None)
    if fault=='invalid_history':e.update(state,set(),float('nan'))
    if fault=='not_released':
        for _ in range(7):r=f.tick(e,state, f.contact(('machine/left','left_finger1')),positions={'left':.004})
    else:r=f.settle(e,state)
    assert not r['success']
    if fault=='invalid_history':assert r['progress_result']['task_score_100'] is None
    else:assert r['progress_result']['task_score_100']<100


def test_private_expert_uses_new_counts_without_changing_legacy():
    for use_new,expected in [(True,5),(False,10)]:
        a=_Author.__new__(_Author);a.task='E26';a.variant='A';a.spec=spec() if use_new else f.mechanism_spec('E26');a.operations=[]
        a.press=lambda role,index:a.operations.append((role,index));a.act=lambda:None;a.stage=lambda value:None
        result=a.solve();assert len(result['operations'])==expected


def test_v3_private_expert_does_not_use_demo_counts():
    a=_Author.__new__(_Author);a.task='E26';a.variant='A';a.spec=spec();a.operations=[]
    a.spec['execution_design']['revision']='embodied50-execution-v3-20261102'
    a.press=lambda role,index:a.operations.append((role,index));a.act=lambda:None;a.stage=lambda value:None
    assert len(a.solve()['operations'])==5
