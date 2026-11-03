import json
from pathlib import Path
import pytest
from videoicl_isaaclab import execution_design as d


def test_full_support_masks_and_unmodified_local_rules():
    legacy = json.loads((d.ROOT.parent / 'configs/realworld50_catalog.json').read_bytes())
    r_only = {'E12', 'E29', 'E37', 'E44', 'E47', 'E48', 'E49', 'E50'}
    for old in legacy['tasks']:
        new = d.metadata(old['id'])
        assert new['local_demo_variants'] == old['variants']
        expected = ['I', 'E'] if old['id'] in d.WORKFLOW_TASKS else ['R','E'] if old['id'] in r_only else ['R', 'I', 'E']
        assert new['support_mask'] == expected
        assert new['difficulty'] in ('easy', 'medium', 'hard')
        assert new['main_condition'] == ('I' if 'I' in expected else 'R')
        assert new['environment_base']==('I' if 'I' in expected else 'R')


@pytest.mark.parametrize('task,invalid', [('E01', 'R'), ('E12', 'I'), ('E47', 'I'), ('E04', 'G1')])
def test_invalid_conditions_rejected(task, invalid):
    with pytest.raises(ValueError):
        d.build_task_contract(task, 'A', 0, invalid)


def test_pairing_identity_and_no_old_qa_reuse():
    i = d.build_task_contract('E01', 'A', 4, 'I')
    e = d.build_task_contract('E01', 'A', 4, 'E')
    nxt = d.build_task_contract('E01', 'A', 5, 'I')
    assert i['execution_design']['semantic_input_identity'] == e['execution_design']['semantic_input_identity']
    assert i['execution_design']['environment_identity'] != e['execution_design']['environment_identity']
    assert i['execution_design']['semantic_input_identity'] != nxt['execution_design']['semantic_input_identity']
    assert i['rule_qa']['assignment_identity_sha256'] != e['rule_qa']['assignment_identity_sha256']
    assert i['rule_qa']['fresh_first_answer_required'] and not i['rule_qa']['reuse_previous_assignment_answer']
    assert i['execution_design']['physics_acceptance_status'] == 'pending'
    assert d.build_task_contract('E12', 'A', 4, 'R')['execution_design']['semantic_input_identity'] == d.build_task_contract('E12', 'A', 5, 'R')['execution_design']['semantic_input_identity']


def test_public_goal_does_not_depend_on_variant_or_include_private_dependencies(tmp_path):
    for task in d.WORKFLOW_TASKS:
        contracts = [d.build_task_contract(task, v, 0) for v in 'ABC']
        assert len({c['instruction'] for c in contracts}) == 1
        assert any(word in contracts[0]['instruction'] for word in ('交付', '送往', '送到', '展台'))
    m = d.export_task_packages(tmp_path / 'new', tasks=['E01'], seeds=[0], conditions=['I', 'E'])
    assert len(m['assignments']) == 6 and m['model_launch_enabled'] is False
    for item in m['assignments']:
        public = json.loads((tmp_path / 'new' / item['path'] / 'task.public.json').read_text())
        assert set(public) == {'revision', 'task', 'title', 'instruction', 'assignment_identity_sha256'}
        assert '汉堡和薯条' not in public['instruction']
    with pytest.raises(FileExistsError):
        d.export_task_packages(tmp_path / 'new', tasks=['E01'], seeds=[0])


def test_e05_incomplete_supervision_is_not_silently_accepted():
    assert d.metadata('E05')['demo_quality']['E05-A'] == 'incomplete_requires_explicit_supervision_confirmation'


def test_unsupported_export_leaves_no_partial_directory(tmp_path):
    with pytest.raises(ValueError):
        d.export_task_packages(tmp_path / 'bad', tasks=['E01', 'E12'], seeds=[0], conditions=['I'])
    assert not (tmp_path / 'bad').exists()


def test_v2_is_explicit_immutable_and_does_not_gain_e_support():
    assert d.metadata('E12',revision=d.REVISION_V2)['support_mask']==['R']
    with pytest.raises(ValueError):d.build_task_contract('E12','A',1,'E',revision=d.REVISION_V2)
    old=d.build_task_contract('E01','A',4,'I',revision=d.REVISION_V2)
    assert old['execution_design']['revision']==d.REVISION_V2
    assert 'environment_base' not in old['execution_design']
    assert old['execution_design']['assignment_identity_sha256']!=d.build_task_contract('E01','A',4,'I')['execution_design']['assignment_identity_sha256']
    assert d.source_sha256(d.REVISION_V2)=='aee2299f7e86e9ab05e6e1def6b741d58f0d26aab58ab8d1e0d908f5510b88b7'
    assert d.source_sha256()=='b798ea7529d0b8164185af7651d064d7441a6fff0415e43329a1bdf9130e7fc3'


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(1,51)])
def test_every_v3_e_condition_has_explicit_paired_input_and_invariants(task):
    meta=d.metadata(task);base=meta['environment_base']
    for variant in 'ABC':
        first=d.build_task_contract(task,variant,4201,base)['execution_design']
        paired=d.build_task_contract(task,variant,4201,'E')['execution_design']
        assert first['paired_input_identity']==paired['paired_input_identity']
        assert first['semantic_input_identity']==paired['semantic_input_identity']
        assert first['environment_identity']!=paired['environment_identity']
        assert paired['environment_changes']==[] and paired['pairing_verification']=='pending_native_adapter_measurement'
        assert paired['pairing_invariants'] and paired['allowed_environment_changes']
        if base=='R':
            assert paired['paired_input_identity']==d.build_task_contract(task,variant,4202,'E')['execution_design']['paired_input_identity']
            assert set(paired['allowed_environment_changes'])=={'workspace_appearance','background','lighting'}
            assert {'geometry','contact_parameters','dynamics','initial_physical_state'}<=set(paired['pairing_invariants'])


def test_v3_export_records_environment_pairing_and_v2_stays_legacy(tmp_path):
    m=d.export_task_packages(tmp_path/'v3',tasks=['E12'],seeds=[1],conditions=['R','E'])
    assert all(r['environment_base']=='R' and r['pairing_verification'].startswith('pending') for r in m['assignments'])
    old=d.export_task_packages(tmp_path/'v2',tasks=['E12'],seeds=[1],revision=d.REVISION_V2)
    assert old['revision']==d.REVISION_V2
    assert all('environment_base'not in r for r in old['assignments'])
