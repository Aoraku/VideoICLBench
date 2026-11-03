from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e47_fixture import digest

@pytest.mark.parametrize('variant','ABC')
def test_passive_device_preserves_every_source_card_and_rule_in_paired_environments(variant):
    old=load('E47',variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False);saved=deepcopy(old)
    r=apply_execution_inputs(old,condition='R',seed=4201,revision=REVISION_V3);e=apply_execution_inputs(old,condition='E',seed=4201,revision=REVISION_V3)
    assert old==saved
    for k in('objects','mechanisms','goals'):assert r[k]==old[k]
    for k,val in old['semantic'].items():assert r['semantic'][k]==val
    assert r['fixtures']==e['fixtures']and len(r['fixtures'])==10
    marker=r['semantic']['execution_design_flip_fixture'];assert marker['fixture_geometry_sha256']==digest(r['fixtures'])
    assert r['execution_design']['paired_physical_input_sha256']==e['execution_design']['paired_physical_input_sha256']
    for card in [o for o in r['objects']if o['id']in marker['card_slot_fixtures']]:
        for n in marker['card_slot_fixtures'][card['id']]:
            f=r['fixtures'][int(n.removeprefix('fixture'))];p=np.array(f['mesh_data']['vertices']).reshape(-1,3)+[*f['xy'],f['z']]
            assert p[:,0].min()==pytest.approx(card['xy'][0]+card['size'][0]+.003)
            assert max(abs(p[:,1]-card['xy'][1]))<card['size'][1]
            assert f['passive']and 'drive'not in f and 'joint'not in f
