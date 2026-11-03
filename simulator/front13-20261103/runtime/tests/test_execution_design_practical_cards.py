from copy import deepcopy
from pathlib import Path
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_practical_cards import configure_spec
from videoicl_isaaclab.execution_design_card_contract import card_reference_contract
from videoicl_isaaclab.execution_design_thin_cooking import settings_for
from videoicl_isaaclab.execution_design_cards_reference import slot_placement
import numpy as np

V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'


@pytest.mark.parametrize('task',('E47','E48','E49','E50'))
def test_one_mm_is_explicit_and_keeps_original_rule_and_identity(task,monkeypatch):
    monkeypatch.delenv('VIC_ENGINEERING_PRACTICAL_CARD_THICKNESS',raising=False)
    old=load(task,'A',4201,V/'e38-e50-matrix/bindings-R.private.json',verify_files=False)
    new=deepcopy(old);names=configure_spec(new)
    assert new['goals']==old['goals']
    before={o['id']:o for o in old['objects']}
    for o in new['objects']:
        original=deepcopy(before[o['id']])
        if task=='E48':original['xy'][0]-=.10
        if o['id']not in names:
            assert o==original;continue
        assert o['size'][:2]==original['size'][:2]
        assert o['size'][2]==.0005
        for key in('xy','quaternion','mass','contact_offset','rest_offset'):
            assert o.get(key)==original.get(key)
        assert o['source_asset']==dict(original['source_asset'],allow_nonuniform_scale=True)
        assert any('approximation'in s for s in o['adaptations'])
        assert o['center_z']-o['size'][2]==pytest.approx(original['center_z']-original['size'][2])
        assert o['engineering_practical_card']['source_exact_geometry']is False
        assert settings_for(o,100)['coordinate_factor']==100
    if task!='E50':card_reference_contract(new)
    with pytest.raises(ValueError,match='Fresh'):configure_spec(new)


def test_three_mm_stack_fits_original_same_slot():
    lo=np.array([-.045,-.0041,-.019]);hi=np.array([.045,.00065,-.011])
    for rank in range(3):
        rotation,center=slot_placement([0,0,0],np.eye(3),lo,hi,[.044,.0315,.0005],rank)
        edge=center-rotation[:,0]*.044
        assert lo[1]+.0005<=edge[1]<=hi[1]-.0005
