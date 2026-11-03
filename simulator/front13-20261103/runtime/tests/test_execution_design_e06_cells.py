"""Native scoring coordinates must follow the actual translated E06 fixture."""
import json
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import REVISION_V3


def spec(tmp_path,variant,seed,condition):
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition=condition)
    path=tmp_path/('binding-'+condition+'.json');path.write_text(json.dumps(binding))
    return load('E06',variant,seed,path,verify_files=False)


@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('condition',['I','E'])
def test_shifted_actual_fixture_zones_and_native_cell_coordinates_stay_aligned(tmp_path,seed,variant,condition):
    baseline=spec(tmp_path,variant,seed,'R');actual=spec(tmp_path,variant,seed,condition)
    dx=(-.025,.025,.04)[seed%3]
    holders=lambda s:next(o for o in s['objects']if o['id']=='eggtray')
    assert holders(actual)['xy'][0]-holders(baseline)['xy'][0]==pytest.approx(dx)
    zones={z['id']:z for z in actual['zones']}
    for name,cell in actual['semantic']['cells'].items():
        old=baseline['semantic']['cells'][name]
        assert cell['center']==pytest.approx([old['center'][0]+dx,*old['center'][1:]])
        assert cell['center'][:2]==pytest.approx(zones[name]['xy'])
        assert cell['radius']==old['radius']==.018
    paired=spec(tmp_path,variant,seed,'E'if condition=='I'else'I')
    assert actual['semantic']['cells']==paired['semantic']['cells']
    assert actual['execution_design']['paired_physical_input_sha256']==paired['execution_design']['paired_physical_input_sha256']


def test_native_e06_recorded_placement_matches_new_input_centers_not_stale_seed0(tmp_path):
    # Actual native centers from slot03-pool09/check-04; this tests the scoring
    # frame bug, not a replacement native score or a synthetic episode pass.
    centers=[(.09158021956682207,.02294786833226679),(.04527797177433969,.02272470109164714),(-.0011044837301596951,.022839160636067394)]
    old=spec(tmp_path,'A',4201,'R')['semantic']['cells'];new=spec(tmp_path,'A',4201,'I')['semantic']['cells']
    for xy,name in zip(centers,['left_far','left_middle','left_near']):
        assert np.linalg.norm(np.array(xy)-new[name]['center'][:2])<.001
        assert np.linalg.norm(np.array(xy)-old[name]['center'][:2])>.018
