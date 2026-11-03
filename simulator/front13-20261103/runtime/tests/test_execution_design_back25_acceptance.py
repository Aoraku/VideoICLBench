from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design import build_task_contract,REVISION_V3
from videoicl_isaaclab.execution_design_back25_acceptance import requirements,validate_case


def spec(task,variant='A'):
    c=build_task_contract(task,variant,4201,'E',revision=REVISION_V3)
    return dict(id=task,variant=variant,execution_design=c['execution_design'])

@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(26,51)])
def test_applicability_never_fills_fake_native_pass(task,tmp_path):
    s=spec(task);r=validate_case(s,{},tmp_path)
    assert not r['native_acceptance_ready'] and not r['model_launch_enabled']
    assert all(x['native_passed']is None for x in r['controls'])
    for row in r['controls']:
        assert row['source_reason']
        if row['applicability']=='not_applicable':assert row['status']=='not_applicable'and row['witness_key']is None
        else:assert row['status']=='pending'

@pytest.mark.parametrize('task',('E28','E32','E33','E34','E36','E40','E42','E43','E46','E47','E48'))
def test_alias_uses_one_source_identity_bound_witness(task):
    rows=requirements(spec(task));required={r['control']:r for r in rows}
    for r in rows:
        if r['applicability']=='alias':
            assert r['witness_key']==required[r['canonical_control']]['witness_key']
            assert required[r['canonical_control']]['applicability']=='required'


def make_witness(s,r,root):
    positive=r['canonical_control']=='positive'
    w=dict(assignment_identity_sha256=s['execution_design']['assignment_identity_sha256'],source_sha256=s['execution_design']['source_sha256'],
        witness_key=r['witness_key'],control=r['canonical_control'],native_evidence_valid=True,initial_sealed=True,capture_complete=True,
        control_execution_completed=True,strict_success=positive,task_score_100=100 if positive else 0,
        negative_condition_observed=not positive,reviewer='unit-test-only',observed_condition='fixture counterexample',other_conditions_checked=True,artifacts={})
    for kind in ('trajectory','native_score','final_state','head_image'):
        p=root/(r['canonical_control']+'-'+kind)
        p.write_text(json.dumps(dict(native_evidence_valid=True,strict_success=positive,task_score_100=100 if positive else 0))if kind=='native_score'else 'synthetic test artifact, not actual evidence')
        w['artifacts'][kind]=dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return w


def test_source_alias_ready_only_with_correct_reviewed_native_artifacts(tmp_path):
    s=spec('E33');rows=requirements(s);w={r['witness_key']:make_witness(s,r,tmp_path)for r in rows if r['applicability']=='required'}
    result=validate_case(s,w,tmp_path)
    assert result['native_acceptance_ready']
    assert result['independent_required_witnesses']==4
    assert next(x for x in result['controls']if x['control']=='wrong_rule')['status']=='verified_shared_witness'
    key=next(r['witness_key']for r in rows if r['control']=='wrong_members')
    old=deepcopy(w);w[key]['negative_condition_observed']=None
    assert not validate_case(s,w,tmp_path)['native_acceptance_ready']
    w=old;w[key]['artifacts']['trajectory']['sha256']='0'*64
    assert not validate_case(s,w,tmp_path)['native_acceptance_ready']


def test_native_score_not_replaced_by_envelope(tmp_path):
    s=spec('E29');rows=requirements(s);w={r['witness_key']:make_witness(s,r,tmp_path)for r in rows if r['applicability']=='required'}
    neg=next(v for v in w.values()if v['control']=='wrong_rule');p=tmp_path/neg['artifacts']['native_score']['path']
    p.write_text(json.dumps(dict(native_evidence_valid=True,strict_success=None,task_score_100=None)))
    neg['artifacts']['native_score']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    assert not validate_case(s,w,tmp_path)['native_acceptance_ready']


def test_first_half_not_touched():
    with pytest.raises(ValueError):requirements(spec('E01'))
