import copy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e46_partition import configure_spec
from videoicl_isaaclab.execution_design_e46_partition_data import PARTS,SOURCE_SHA,NATIVE_BASELINE

def scene():
    return dict(id='E46',objects=[dict(id='spatula',size=[.14,.03761496517,.01481387076],mass=.1,source_asset=dict(sha256=SOURCE_SHA),reviewed_collision_settings=dict(source_sha256=SOURCE_SHA,approximation='convexHull',hull_vertex_limit=255,coordinate_factor=100.)),dict(id='yellow_block',mass=.02)])

def test_exact79_source_pieces_fit_native_vertex_limit_and_preserve_dynamics_binding():
    assert len(PARTS)==79 and max(map(len,PARTS))<=128
    assert all(np.isfinite(p).all()for p in PARTS)
    s=scene();old=copy.deepcopy(s);configure_spec(s)
    assert s['objects'][1]==old['objects'][1]
    assert s['objects'][0]['mass']==old['objects'][0]['mass']
    assert s['objects'][0]['reviewed_collision_settings']['preserve_native_mass_properties']==NATIVE_BASELINE['spatula']

@pytest.mark.parametrize('bad',['source','geometry','task','adapter'])
def test_exact_partition_rejects_other_tasks_or_geometry(bad):
    s=scene()
    if bad=='source':s['objects'][0]['source_asset']['sha256']='bad'
    if bad=='geometry':s['objects'][0]['size'][0]*=1.1
    if bad=='task':s['id']='E28'
    if bad=='adapter':s['objects'][0]['reviewed_collision_settings']['coordinate_factor']=1.
    with pytest.raises(ValueError):configure_spec(s)
