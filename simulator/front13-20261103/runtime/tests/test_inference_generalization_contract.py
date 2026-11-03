from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('compile_inference',ROOT/'scripts/build_inference_generalization.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from videoicl_isaaclab.inference_generalization import public_instruction
C=m.read(ROOT/'inference-generalization-v1/catalog.private.json')
B=m.read(ROOT/'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json')

def patches():
    out={'tasks':{}}
    for task,info in C['tasks'].items():
        if info['group']=='G0':continue
        b=deepcopy(B['tasks'][task])
        if b['objects']:
            first=next(iter(b['objects']));b['objects'][first]['review_marker']='synthetic-test-only'
        else:b['mechanisms'][0]['review_marker']='synthetic-test-only'
        out['tasks'][task]=b
    return out

def compile(p=None):return m.compile_bindings(B,C,[p or patches()],g2_profile='configs/ur5.json',g2_profile_sha256='a'*64)

def test_design_partition_and_all150_variants():
    assert m.validate_catalog(C)=={'G0':20,'G1':20,'G2':10}
    assert sum(len(x['variants']) for x in C['tasks'].values())==150
    assert '小柑橘' in C['tasks']['E06']['inference_prompt']
    assert '鸡蛋' not in C['tasks']['E06']['inference_prompt']


def test_compiler_preserves_g0_exact_and_all_abc_relations():
    result,checks=compile()
    assert len(checks)==50
    for task,info in C['tasks'].items():
        new=result['tasks'][task];old=B['tasks'][task]
        if info['group']=='G0':assert new==old
        else:
            assert new['variants']==old['variants']
            assert public_instruction(new,'old')==info['inference_prompt']
            assert new['inference_generalization']['demo_unchanged'] is True
            if info['group']=='G2':assert new['embodiment']=='ur5_wsg'
            else:assert new.get('embodiment')==old.get('embodiment')

@pytest.mark.parametrize('change', ['missing','extra','rule','identity','environment','nochange'])
def test_compiler_rejects_scope_and_semantic_drift(change):
    p=patches()
    if change=='missing':p['tasks'].pop('E01')
    elif change=='extra':p['tasks']['E03']=deepcopy(B['tasks']['E03'])
    elif change=='rule':p['tasks']['E01']['variants']['A']['semantic']['mode']='wrong'
    elif change=='identity':p['tasks']['E01']['objects'][next(iter(p['tasks']['E01']['objects']))]['identity']='wrong'
    elif change=='environment':p['tasks']['E01']['embodiment']='ur5_wsg'
    else:p['tasks']['E01']=deepcopy(B['tasks']['E01'])
    with pytest.raises(ValueError):compile(p)

def test_legacy_bindings_opt_out_and_prompt_answer_table_rejected():
    assert public_instruction(B['tasks']['E01'],'original')=='original'
    b=deepcopy(B['tasks']['E01']);b['inference_generalization']=dict(schema='videoicl-inference-task-v1',group='G1',demo_unchanged=True,instruction='**A：** answer')
    with pytest.raises(ValueError):public_instruction(b,'original')


def test_generated_assets_hash_and_all150_recipe_semantics():
    from videoicl_isaaclab.realworld_scenes import load
    import hashlib
    compiled=ROOT/'inference-generalization-v1/inference-bindings.json'
    result=m.read(compiled)
    pinned=0
    for task,item in C['tasks'].items():
        binding=result['tasks'][task]
        for obj in list(binding.get('objects',{}).values())+binding.get('mechanisms',[]):
            record=obj.get('source_asset') or obj.get('mechanical_asset')
            if record.get('root_env')=='VIC_INFERENCE_ASSETS':
                source=ROOT/'inference-generalization-v1/assets'/record['relative_path']
                assert source.is_file()
                assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
                pinned+=1
        for variant in 'ABC':
            recipe=load(task,variant,4201,compiled,verify_files=False)
            original=load(task,variant,4201,ROOT/'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json',verify_files=False)
            assert recipe['semantic']==original['semantic']
            assert recipe['goals']==original['goals']
            assert recipe['instruction']==(original['instruction'] if item['group']=='G0' else item['inference_prompt'])
    assert pinned>=30


@pytest.mark.parametrize('variant',['A','B','C'])
def test_e24_yarn_requires_event_order_support_and_lid_but_not_cup_pose(variant):
    from videoicl_isaaclab.realworld_semantic_checks import check_task
    from videoicl_isaaclab.realworld_progress import score_progress
    from progress_v2_fixtures import progress_example
    from videoicl_isaaclab.inference_generalization import e24_yarn_rule
    from videoicl_isaaclab.realworld_scenes import load
    spec=load('E24',variant,4201,ROOT/'inference-generalization-v1/inference-bindings.json',verify_files=False)
    assert e24_yarn_rule(spec)
    assert not e24_yarn_rule(dict(spec,id='E03'))
    old=deepcopy(spec);old.pop('inference_generalization');assert not e24_yarn_rule(old)
    obs,_=progress_example('E24',variant)
    obs['released']=True;obs['stable']=True
    obs['upright']=[];obs['left_to_right']=list(reversed(obs['left_to_right']))
    assert not check_task('E24',variant,obs)['success']
    assert score_progress('E24',variant,obs)['task_score_100']==0
    obs['inference_rule_profile']='e24-yarn-insertion-v1'
    obs.pop('upright');obs.pop('left_to_right')
    assert check_task('E24',variant,obs)['success']
    assert score_progress('E24',variant,obs)['task_score_100']==100
    for defect in ('wrong_order','no_support','no_lid','early_lid','missing_object'):
        bad=deepcopy(obs)
        if defect=='wrong_order':bad['placement_events'][0]['object'],bad['placement_events'][1]['object']=bad['placement_events'][1]['object'],bad['placement_events'][0]['object']
        elif defect=='no_support':bad['supported_in_box']=[]
        elif defect=='no_lid':bad['lid_closed']=False
        elif defect=='early_lid':bad['lid_close_step']=0
        else:bad['in_box'].pop()
        assert not check_task('E24',variant,bad)['success'],defect
        assert score_progress('E24',variant,bad)['task_score_100']<100,defect
