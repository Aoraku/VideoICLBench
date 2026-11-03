from types import SimpleNamespace
import math
import pytest
from videoicl_isaaclab.execution_design_e15_b_reference import wrap,run_segment,MeasuredT

def test_circular_goal_is_unchanged_across_pi():
 assert math.degrees(wrap(math.radians(270)-math.radians(-90)))==pytest.approx(0,abs=1e-10)

def test_blue_suffix_requires_the_completed_original_red_boundary_before_native_access():
 a=SimpleNamespace(scene=SimpleNamespace(spec=dict(seed=4201)),_engineering_resume_checkpoint=dict(source=dict(steps=94,physics_ticks=9403)),c=SimpleNamespace(_engineering_checkpoint_readback_passed=True))
 with pytest.raises(ValueError,match='95/9503'):run_segment(a,'e15_b_complete_blue_from95',{})

def test_full_helper_rejects_other_variant_before_robot_access(monkeypatch):
 from videoicl_isaaclab import execution_design_e15_wrist as wrist
 monkeypatch.setattr(wrist,'_scope',lambda _:None)
 a=SimpleNamespace(c=object(),scene=SimpleNamespace(spec=dict(variant='A',execution_design=dict(condition='I'))))
 with pytest.raises(ValueError,match='B/I'):MeasuredT(a,'red_t')

@pytest.mark.parametrize('variant',['A','B','C'])
def test_actual_source_variant_pins_both_distinct_t_assets(variant,tmp_path):
 import json
 from pathlib import Path
 from videoicl_isaaclab.realworld_scenes import load
 from videoicl_isaaclab.execution_design_e15_b_reference import SOURCE_HASHES
 bindings=Path(__file__).resolve().parents[1]/'configs/realworld_full50_bindings.json'
 config=json.loads(bindings.read_text());config['execution_design']=dict(revision='embodied50-execution-v3-20261102',condition='I')
 path=tmp_path/'bindings.json';path.write_text(json.dumps(config))
 spec=load('E15',variant,4201,path,verify_files=False)
 assert {o['id']:o['source_asset']['sha256']for o in spec['objects']}==SOURCE_HASHES
