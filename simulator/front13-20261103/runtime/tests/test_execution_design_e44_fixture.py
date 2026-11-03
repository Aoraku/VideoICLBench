from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e44_fixture import nominal_final_clearance,digest


def original(v):return load('E44',v,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)


@pytest.mark.parametrize('variant','ABC')
def test_passive_rails_preserve_source_cardboard_goals_and_paired_physics(variant):
    old=original(variant);saved=deepcopy(old)
    r=apply_execution_inputs(old,condition='R',seed=4201,revision=REVISION_V3)
    e=apply_execution_inputs(old,condition='E',seed=4201,revision=REVISION_V3)
    assert old==saved
    for field in('objects','mechanisms','goals'):assert r[field]==old[field]
    assert r['fixtures']==e['fixtures']and len(r['fixtures'])==2
    assert r['execution_design']['paired_physical_input_sha256']==e['execution_design']['paired_physical_input_sha256']
    marker=r['semantic']['execution_design_fold_fixture']
    assert marker['fixed_geometry_sha256']==digest(r['fixtures'])
    assert marker['no_actuation']and marker['no_cardboard_constraint']and not marker['native_initial_verified']
    for rail in r['fixtures']:
        vertices=np.asarray(rail['mesh_data']['vertices']).reshape(-1,3)+[*rail['xy'],rail['z']]
        assert vertices[:,0].min()>.1105+.009
        assert vertices[:,2].min()==pytest.approx(.8)
        assert vertices[:,2].max()==pytest.approx(.86)
        assert rail['passive']and 'joint'not in rail and 'drive'not in rail
    c=nominal_final_clearance({'A':90,'B':120,'C':45}[variant])
    assert c['base_to_rail_x_gap_m']>.04
    assert not c['over_rail_x']or c['minimum_vertical_gap_m']>.06
    assert not c['native_verified']
