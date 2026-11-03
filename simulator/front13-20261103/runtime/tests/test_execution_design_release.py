import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import pytest

p=Path(__file__).resolve().parents[1]/'scripts/build_execution_design_release.py'
spec=importlib.util.spec_from_file_location('execution_release_builder',p);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def workflow_release(destination,**kwargs):
    return b.build_release(destination,tasks=sorted(b.WORKFLOW_TASKS),**kwargs)


def test_new_release_builds_independent_cases_and_blocks_pending(tmp_path):
    release=tmp_path/'release';m=workflow_release(release)
    assert len(m['cases'])==90 and not m['model_launch_enabled']
    loaded=subprocess.run([sys.executable,str(release/'load_case.py'),m['cases'][0]['case_id'],'--offline'],check=True,capture_output=True,text=True)
    status=json.loads(loaded.stdout);assert not status['release_ready'] and status['source_files_verified'] is False and status['objects']>0
    profile_check=subprocess.run([sys.executable,'-c',
        'from videoicl_isaaclab.embodiments import select; assert select("E01","franka").name=="franka"'],
        cwd=release/'runtime',check=True,capture_output=True,text=True)
    assert profile_check.returncode==0
    assert len({c['assignment_identity_sha256']for c in m['cases']})==90
    result=b.validate_release(release)
    assert not result['ready']
    assert sum(e.endswith(':native_pending') for e in result['errors'])==450
    assert sum(e.endswith(':local_media_pending') for e in result['errors'])==180
    assert 'qa_runtime_acceptance_pending' in result['errors']
    before=(release/'manifest.private.json').read_bytes()
    with pytest.raises(RuntimeError):b.set_model_launch_enabled(release,True)
    assert (release/'manifest.private.json').read_bytes()==before
    for case in m['cases']:
        bp=json.loads((release/case['binding_file']).read_text())
        assert bp['execution_design']==dict(revision=b.REVISION,condition=case['condition'])
        inputs=[json.loads((release/path).read_text())for path in case['input_specs'].values()]
        assert len({i['assignment_identity_sha256']for i in inputs})==3
        assert all(i['rule_qa']['fresh_first_answer_required']for i in inputs)
        assert all(set(i['qa_public_packet']['options'])==set('ABCD') for i in inputs)
        assert all('correct_option' not in i['qa_public_packet'] for i in inputs)
        assert len({i['qa_public_packet']['packet_id']for i in inputs})==3
        assert all(not i['model_launch_enabled']for i in inputs)
        scene=b.load_scene(case['task'],case['variant'],case['seed'],release/case['binding_file'],verify_files=False)
        assert all(i['public_task']['instruction']==scene['instruction'] for i in inputs)
        assert all(i['public_task']['order']==scene['public_order'] for i in inputs)
        assert set(inputs[0]['public_task'])=={'task','title','instruction','revision','order'}
    with pytest.raises(FileExistsError):workflow_release(release)


def test_cpu_fixture_cannot_satisfy_native_gate(tmp_path):
    release=tmp_path/'release';m=workflow_release(release);case=m['cases'][0]
    fixture=release/'cpu-fixture.json';b.write(fixture,dict(schema='videoicl-native-execution-v2-control-v1',backend='cpu_fixture',strict_success=True))
    case['native_controls']['positive']={'path':'cpu-fixture.json','sha256':b.sha(fixture)};b.write(release/'manifest.private.json',m)
    result=b.validate_release(release)
    assert not result['ready'] and any('non_native_evidence'in e for e in result['errors'])
    with pytest.raises(RuntimeError):b.set_model_launch_enabled(release,True)


def test_hash_changes_and_seed_shortcut_fail_closed(tmp_path):
    with pytest.raises(ValueError):workflow_release(tmp_path/'bad',seeds=(1,2))
    release=tmp_path/'release';m=workflow_release(release)
    file=release/'runtime/videoicl_isaaclab/execution_design.py';file.write_text(file.read_text()+'\n# altered\n')
    assert any('source_hash_mismatch'in e for e in b.validate_release(release)['errors'])


def test_input_prompt_and_qa_tampering_fail_even_with_updated_file_digest(tmp_path):
    release=tmp_path/'release';m=workflow_release(release);case=m['cases'][0]
    path=release/case['input_specs']['sim'];value=json.loads(path.read_text())
    value['qa_public_packet']['correct_option']=value['qa_grading_private']['correct_option']
    b.write(path,value);case['input_spec_hashes']['sim']=b.sha(path);b.write(release/'manifest.private.json',m)
    errors=b.validate_release(release)['errors']
    assert any('qa_public_packet_mismatch' in e for e in errors)
    assert not b.validate_release(release)['ready']


def test_missing_input_mode_and_unbound_media_block_admission(tmp_path):
    release=tmp_path/'release';m=workflow_release(release);m['cases'][0]['input_specs'].pop('real')
    b.write(release/'manifest.private.json',m)
    errors=b.validate_release(release)['errors']
    assert any('input_modes_incomplete' in e for e in errors)
    assert any('sim:local_media_pending' in e for e in errors)
    with pytest.raises(RuntimeError):b.set_model_launch_enabled(release,True)


def test_prepared_gate_exports_actual_sdk_task_without_unlocking_native(tmp_path):
    preparation=tmp_path/'qa-preparation';preparation.mkdir()
    from videoicl_isaaclab.execution_design_qa import export_sdk
    receipt=export_sdk(preparation/'sdk')
    tests=b.RUNTIME/'tests/test_execution_design_qa_integration.py'
    junit=preparation/'tests.xml'
    subprocess.run([sys.executable,'-m','pytest','-q',str(tests),'--junitxml='+str(junit),'-p','no:cacheprovider'],
                   check=True,capture_output=True,text=True)
    b.write(preparation/'preparation.private.json',dict(revision=b.REVISION,sdk_files=receipt['files'],media=[],
        integration_test=dict(path='tests.xml',sha256=b.sha(junit),source_sha256=b.sha(tests),passed=True)))
    release=tmp_path/'release';m=workflow_release(release,qa_preparation=preparation)
    errors=b.validate_release(release)['errors']
    assert 'qa_runtime_acceptance_pending' not in errors
    assert sum(e.endswith(':native_pending') for e in errors)==450
    assert sum(e.endswith(':local_media_pending') for e in errors)==180
    assert len(errors)==631 and 'full50_scope_incomplete' in errors
    with pytest.raises(RuntimeError):b.set_model_launch_enabled(release,True)
    case=m['cases'][0];package=release/case['sdk_task_package']['path']
    native=json.loads((package/'environment/native.json').read_text())
    assert native['generalization_condition']==case['condition']
    assert native['task_revision']==b.REVISION and native['model_launch_enabled'] is False
    assert set(native['qa_assignment_identities'])=={'text_rule'}
    assert not list(package.rglob('*private*'))
    assert (package/'environment/rule-qa/text_rule.json').is_file()
    native['qa_assignment_identities']['text_rule']='f'*64
    b.write(package/'environment/native.json',native)
    case['sdk_task_package']['files']['environment/native.json']=b.sha(package/'environment/native.json')
    b.write(release/'manifest.private.json',m)
    assert any('sdk_task_qa_identity_mismatch' in e for e in b.validate_release(release)['errors'])
    assignment=package/'environment/rule-qa/text_rule.json';a=json.loads(assignment.read_text())
    native['qa_assignment_identities']['text_rule']=a['assignment_identity_sha256'];b.write(package/'environment/native.json',native)
    case['sdk_task_package']['files']['environment/native.json']=b.sha(package/'environment/native.json')
    a['packet']['options']['A']='tampered public option';b.write(assignment,a)
    case['sdk_task_package']['files']['environment/rule-qa/text_rule.json']=b.sha(assignment)
    b.write(release/'manifest.private.json',m)
    assert any('sdk_task_qa_content_mismatch' in e for e in b.validate_release(release)['errors'])


def test_boolean_only_qa_receipt_cannot_satisfy_test_matrix(tmp_path):
    p=tmp_path/'empty.xml';p.write_text('<testsuites><testsuite tests="11" failures="0" /></testsuites>')
    with pytest.raises(ValueError,match='matrix incomplete'):b._validate_qa_junit(p)


def test_default_full50_release_requires_all_1233_cases_and_6165_native_controls(tmp_path):
    release=tmp_path/'full50';manifest=b.build_release(release)
    assert manifest['scope']=='full50' and len(manifest['cases'])==1233
    assert manifest['required_full50_cases']==1233 and manifest['required_full50_controls']==6165
    assert len(manifest['coverage'])==50 and all(r['included']for r in manifest['coverage'])
    assert sum(r['support_mask']==['R','E']for r in manifest['coverage'])==8
    result=b.validate_release(release)
    assert not result['ready'] and not result['full50_ready']
    assert sum(e.endswith(':native_pending')for e in result['errors'])==6165
    assert 'full50_scope_incomplete'not in result['errors']
    assert len({c['assignment_identity_sha256']for c in manifest['cases']})==1233
    for case in manifest['cases']:
        assert case['declared_pairing']['environment_base'] in ('R','I')
    with pytest.raises(RuntimeError):b.set_model_launch_enabled(release,True)
