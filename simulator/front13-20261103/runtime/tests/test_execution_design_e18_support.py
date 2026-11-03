from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_inputs_v3 import base,apply
from test_execution_design_e18_pinch import geometry
from videoicl_isaaclab.execution_design_e18_pinch import finite_bar_pinch_candidate
from videoicl_isaaclab.execution_design_e18_support import apply_support,LIFT_M


@pytest.mark.parametrize('variant',list('ABC'))
def test_candidate_moves_whole_cabinet_and_contents_preserves_rule_and_pair(monkeypatch,variant):
    original=base('E18',variant);copy=deepcopy(original)
    prior=apply(original,'I')
    monkeypatch.setenv('VIC_ENGINEERING_E18_SUPPORT','1')
    changed=apply(original,'I');paired=apply(original,'E')
    assert original==copy
    assert changed['semantic']==prior['semantic'] and changed['goals']==prior['goals']
    assert changed['mechanisms'][0]['mechanical_asset']==prior['mechanisms'][0]['mechanical_asset']
    assert changed['mechanisms'][0]['position'][2]-prior['mechanisms'][0]['position'][2]==pytest.approx(LIFT_M)
    for old,new in zip(prior['objects'],changed['objects']):
        assert new['xy']==old['xy'] and new['source_asset']==old['source_asset']
        assert new['center_z']-old['center_z']==pytest.approx(LIFT_M)
        assert new['bottom']-old['bottom']==pytest.approx(LIFT_M)
    assert changed['zones']==prior['zones']
    assert len(changed['fixtures'])==len(prior['fixtures'])+1
    f=changed['fixtures'][-1]
    assert f['type']=='box' and f['z']-f['size'][2]==pytest.approx(.8)
    d=changed['execution_design'];e=paired['execution_design']
    assert d['paired_input_identity']==e['paired_input_identity']
    assert d['paired_physical_input_sha256']==e['paired_physical_input_sha256']
    assert d['environment_identity']!=prior['execution_design']['environment_identity']
    assert d['source_environment_identity']==prior['execution_design']['environment_identity']
    assert not changed['release_ready'] and not changed['e18_support_layout']['native_verified']
    with pytest.raises(ValueError):apply_support(changed)


def test_support_flag_does_not_change_other_tasks(monkeypatch):
    original=apply(base('E19'),'I')
    monkeypatch.setenv('VIC_ENGINEERING_E18_SUPPORT','1')
    assert apply(base('E19'),'I')==original


def test_real_bar_thickness_allows_transverse_pinch_only_with_table_clearance():
    rotation=np.array([[0,0,1],[-1,0,0],[0,-1,0.]])
    old=finite_bar_pinch_candidate(geometry(),rotation,[-.084,.075,.8779254],[-1,0,0],[0,-1,0])
    raised=finite_bar_pinch_candidate(geometry(),rotation,[-.084,.075,.8779254+LIFT_M],[-1,0,0],[0,-1,0])
    assert not old['feasible'] and min(old['hand_floor_clearances_m'])<-.02
    assert raised['feasible'] and min(raised['hand_floor_clearances_m'])>.012
    assert .0005<raised['closing_opening_m']<.003
    assert not raised['open_fingers_intersect_bar']
    assert not raised['native_grip_verified'] and not raised['collision_verified']


def test_no_substitute_source_cabinet_is_silently_supported():
    s=base('E18');s['mechanisms'][0]['mechanical_asset']['sha256']='different'
    with pytest.raises(ValueError,match='Pinned'):apply_support(s)
