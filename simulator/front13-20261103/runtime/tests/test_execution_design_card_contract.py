from pathlib import Path
from copy import deepcopy
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_card_contract import card_reference_contract


def spec(t,v='A',condition='R',seed=4201):
    return apply_execution_inputs(load(t,v,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition=condition,seed=seed,revision=REVISION_V3)


@pytest.mark.parametrize('t',('E47','E48','E49'))
@pytest.mark.parametrize('v','ABC')
@pytest.mark.parametrize('condition',('R','E'))
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_full_paired_card_panel_retains_original_order_and_physical_dependencies(t,v,condition,seed):
    s=spec(t,v,condition,seed);saved=deepcopy(s);p=card_reference_contract(s)
    assert s==saved and not p['native_verified'] and not p['reference_enabled']
    assert set(p['delivery_order'])<=set(p['flip_order'])
    assert not set(p['untouched'])&set(p['flip_order'])
    assert 'actual_bilateral_grasp'in p['acquisition_requires']
    if t=='E48':assert 'actual_lower_card_edge_in_slot_bounds'in p['delivery_requires']
    assert p['flip_order']+p['untouched']==['card1','card2','card3','card4','card5']


def test_wrong_prefix_colour_and_tray_mapping_are_rejected_without_touching_world():
    s=spec('E47');s['goals'][0]['object']='card3'
    with pytest.raises(ValueError,match='prefix'):card_reference_contract(s)
    s=spec('E47');s['goals'][-1]['object']='card2'
    with pytest.raises(ValueError,match='colour'):card_reference_contract(s)
    s=spec('E49');s['goals'][-1]['required_support']='green_plate'
    with pytest.raises(ValueError,match='mapping'):card_reference_contract(s)
