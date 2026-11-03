from pathlib import Path
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs as _apply, e26_targets, score_e26

def apply_execution_inputs(*args, **kwargs):
    return _apply(*args, revision="embodied50-execution-v2-20261102", **kwargs)
BINDINGS=Path(__file__).resolve().parents[1]/'configs/realworld_full50_bindings.json'

def base(task, variant='A', seed=0):
    return load(task, variant, seed, BINDINGS, verify_files=False)

@pytest.mark.parametrize('task',['E04','E05'])
def test_explicit_changed_layout_and_paired_environment(task):
    b=base(task);i=apply_execution_inputs(b,condition='I',seed=4201);e=apply_execution_inputs(b,condition='E',seed=4201)
    assert [o['xy']for o in i['objects']] != [o['xy']for o in b['objects']]
    assert [z['xy']for z in i['zones']] != [z['xy']for z in b['zones']]
    assert i['semantic']==e['semantic']==b['semantic']
    assert i['execution_design']['semantic_input_identity']==e['execution_design']['semantic_input_identity']
    for io,eo in zip(i['objects'],e['objects']):
        assert eo['xy']==pytest.approx([io['xy'][0]+.035,io['xy'][1]-.025])
        assert io['source_asset']==eo['source_asset']

@pytest.mark.parametrize('task',['E12','E29','E37','E44','E47','E48','E49','E50'])
def test_r_only_fixed_initial_objects(task):
    b=base(task);r=apply_execution_inputs(b,condition='R',seed=900)
    assert r['objects']==b['objects'] and r['zones']==b['zones']
    with pytest.raises(ValueError):apply_execution_inputs(b,condition='I',seed=900)

def test_unimplemented_i_does_not_fall_back_to_jitter():
    with pytest.raises(NotImplementedError):apply_execution_inputs(base('E41'),condition='I',seed=1)
    with pytest.raises(ValueError):apply_execution_inputs(base('E12',seed=1),condition='R',seed=1)

def events(counts):
    out=[];step=0
    for side,n in counts.items():
        for _ in range(n):
            out.extend([dict(side=side,event='press',step=step,contact=True),dict(side=side,event='release',step=step+1,contact=False)]);step+=2
    return out

@pytest.mark.parametrize('variant',['A','B','C'])
def test_e26_rendered_new_digits_and_evaluator_agree(variant):
    s=apply_execution_inputs(base('E26',variant),condition='I',seed=7)
    assert s['semantic']['digit_cards']=={'left':3,'right':2}
    target=e26_targets(s);expected={'A':{'left':3,'right':2},'B':{'left':2,'right':3},'C':{'left':5,'right':0}}[variant]
    assert target==expected
    good=dict(bell_events=events(target),released=True,stable=True)
    assert score_e26(s,good)['strict_success']
    assert score_e26(s,good)['task_score_100']==100
    assert not score_e26(s,dict(good,released=False))['strict_success']
    old={'A':{'left':9,'right':1},'B':{'left':1,'right':9},'C':{'left':10,'right':0}}[variant]
    assert not score_e26(s,dict(good,bell_events=events(old)))['strict_success']
    s['zones'][0]['digit']=9
    with pytest.raises(ValueError):e26_targets(s)
