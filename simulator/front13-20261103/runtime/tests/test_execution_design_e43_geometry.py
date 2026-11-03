from pathlib import Path
from copy import deepcopy
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
import hashlib,json
from videoicl_isaaclab.execution_design_e43_geometry import ramp_top_at_local_x

BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

@pytest.mark.parametrize('variant',list('ABC'))
def test_gate_and_world_anchor_follow_input_assembly_with_real_ramp_clearance(variant):
    source=load('E43',variant,0,BINDINGS,verify_files=False);original=deepcopy(source)
    s=apply_execution_inputs(source,condition='I',seed=4201,revision=REVISION_V3)
    o={v['id']:v for v in s['objects']};gate=o['gate'];ramp=o['launcher'];joint=next(j for j in s['joints']if j['child']=='gate')
    assert joint['anchor0']==pytest.approx([*gate['xy'],gate['bottom']+gate['size'][2]])
    assert joint['anchor0'][1]==pytest.approx(.035)
    assert ramp_top_at_local_x(ramp,.063)==pytest.approx(.8279921192861471,abs=2e-9)
    assert gate['bottom']==pytest.approx(.8294921192861471,abs=2e-9)
    assert source==original
    assert gate['source_asset']==next(v for v in source['objects']if v['id']=='gate')['source_asset']
    assert gate['size']==[.003,.025,.025]
    digest=hashlib.sha256(json.dumps(s['joints'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    op=s['execution_design']['applied_input_changes']['operations'][0]
    assert op['assembly_joints_sha256']==digest
