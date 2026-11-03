from copy import deepcopy
import pytest
from test_execution_design_inputs_v3 import base,apply
from videoicl_isaaclab.execution_design_e24_layout import apply_layout,LID_XY,VERSION


@pytest.mark.parametrize('variant',list('ABC'))
def test_declared_lid_xy_only_preserves_original_meshes_rules_and_other_measurements(monkeypatch,variant):
    original=base('E24',variant);saved=deepcopy(original);before=apply(original,'I')
    monkeypatch.setenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT','1')
    changed=apply(original,'I');paired=apply(original,'E')
    assert original==saved
    assert changed['goals']==before['goals']and changed['semantic']==before['semantic']
    assert changed['zones']==before['zones']
    for old,new in zip(before['objects'],changed['objects']):
        expected=deepcopy(old)
        if old['id']=='lid':expected['xy']=list(LID_XY)
        assert new==expected
    layout=changed['e24_lid_initial_layout']
    assert layout['version']==VERSION and layout['source_envelope_y_gap_m']>.002
    assert not layout['native_verified']
    d=changed['execution_design'];e=paired['execution_design']
    assert d['environment_identity']!=before['execution_design']['environment_identity']
    assert d['source_environment_identity']==before['execution_design']['environment_identity']
    assert d['paired_input_identity']==e['paired_input_identity']
    assert d['paired_physical_input_sha256']==e['paired_physical_input_sha256']
    with pytest.raises(ValueError):apply_layout(changed)


def test_other_tasks_and_default_source_layout_do_not_change(monkeypatch):
    original=apply(base('E18'),'I')
    monkeypatch.setenv('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT','1')
    assert apply(base('E18'),'I')==original
