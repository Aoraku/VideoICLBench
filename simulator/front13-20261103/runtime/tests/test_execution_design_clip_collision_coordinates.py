import copy
import pytest
from videoicl_isaaclab.execution_design_clip_collision_coordinates import (
    SOURCES, FIELD, configure_spec, verify_only_coordinate_change, verify_record)


def spec():
    path, sha = next(iter(SOURCES.items()))
    return dict(id='E40', mechanisms=[dict(id='clip1', position=[.1, -.1, .802],
        mechanical_asset=dict(root_env='VIC_EXECUTION_DESIGN_ASSETS', relative_path=path, sha256=sha))],
        objects=[], fixtures=[], joints=[], zones=[], goals=[], semantic={})


def test_source_bound_numerical_change_preserves_all_other_physical_fields():
    old = spec(); new = copy.deepcopy(old)
    assert configure_spec(new) == ['clip1']
    assert verify_only_coordinate_change(old, new) == ['clip1']
    assert FIELD not in old['mechanisms'][0]['mechanical_asset']
    new['mechanisms'][0]['position'][0] += .001
    with pytest.raises(ValueError, match='another physical input'):
        verify_only_coordinate_change(old, new)


@pytest.mark.parametrize('key,value', [('sha256', 'unreviewed'), ('root_env', 'another-root'),
                                     (FIELD, 1000)])
def test_unknown_source_or_factor_rejected(key, value):
    new = spec(); configure_spec(new)
    record = new['mechanisms'][0]['mechanical_asset']; record[key] = value
    with pytest.raises(ValueError):
        verify_record(record)


def test_no_cross_task_or_repeated_override():
    new = spec(); new['id'] = 'E50'
    with pytest.raises(ValueError):
        configure_spec(new)
    new = spec(); configure_spec(new)
    with pytest.raises(ValueError, match='Existing'):
        configure_spec(new)


def test_frozen_conditioning_flag_binds_actual_main_input_and_keeps_paired_environment(monkeypatch):
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_inputs_v3 import apply_execution_inputs_v3, physical_input_signature
    binding=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
    original=load('E40','A',0,binding,verify_files=False)
    monkeypatch.setenv('VIC_ENGINEERING_E40_COLLISION_COORDINATES','1')
    one=apply_execution_inputs_v3(original,condition='I',seed=4201)
    paired=apply_execution_inputs_v3(original,condition='E',seed=4201)
    assert one['execution_design']['paired_physical_input_sha256']==physical_input_signature(one)
    assert physical_input_signature(one)==physical_input_signature(paired)
    assert one['goals']==original['goals']
    assert all(m['mechanical_asset'][FIELD]==100. for m in one['mechanisms'])
    assert all(FIELD not in m['mechanical_asset']for m in original['mechanisms'])
