from copy import deepcopy
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_front13_grasp_negative import CAPABILITIES,negative_plan,GraspNegativeAuthor
from test_execution_design_back25_negative import FakeAuthor

def spec(task,variant='A',seed=4201,condition='I'):
 return apply_execution_inputs(load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition=condition,seed=seed,revision=REVISION_V3)

@pytest.mark.parametrize('task',['E02','E05','E11'])
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('condition','RIE')
def test_legal_matrix_preserves_world_and_changes_private_recipe(task,variant,seed,condition):
 s=spec(task,variant,seed,condition);before=deepcopy(s)
 for control in CAPABILITIES[task]:
  p,d=negative_plan(s,control);assert s==before
  for key in ('objects','semantic','execution_design'):assert p[key]==s[key]
  assert d['negative_condition_observed']is None and d['native_review_required']
  if control=='wrong_rule':
   if task=='E02':
    assert [g['object']for g in p['goals']]!=[g['object']for g in s['goals']]
    assert [g['target']for g in p['goals']]==[g['target']for g in s['goals']]
    assert [g['required_support']for g in p['goals']]==['table']+[g['object']for g in p['goals'][:-1]]
   else:assert all(a['target']!=b['target']for a,b in zip(p['goals'],s['goals']))
  elif control=='wrong_members':assert len(p['goals'])==len(s['goals'])-1
  elif control=='wrong_destination':assert p['goals'][-1]['required_support']=='table'
  else:assert p['goals']==s['goals']

@pytest.mark.parametrize('task',['E02','E05','E11'])
@pytest.mark.parametrize('control',sorted(CAPABILITIES['E02']))
def test_actual_runner_restores_original_scene_after_failure(task,control):
 a=FakeAuthor(spec(task));original=a.scene;r=GraspNegativeAuthor(a,control).solve_negative()
 assert a.scene is a.c.scene is original and r['negative_condition_observed']is None
 b=FakeAuthor(spec(task),fail=True);original=b.scene
 with pytest.raises(RuntimeError,match='physical failure'):GraspNegativeAuthor(b,control).solve_negative()
 assert b.scene is b.c.scene is original

@pytest.mark.parametrize('task',['E02','E05','E11'])
def test_failed_grasp_not_a_release_counterexample(task):
 a=FakeAuthor(spec(task),grasp=False)
 with pytest.raises(RuntimeError,match='physically held'):GraspNegativeAuthor(a,'not_released').solve_negative()

@pytest.mark.parametrize('mutation',['legacy','sha','task','control'])
def test_nonreviewed_recipe_refused(mutation):
 s=spec('E02');control='wrong_rule'
 if mutation=='legacy':s['execution_design']['revision']='legacy'
 elif mutation=='sha':s['execution_design']['source_sha256']='unreviewed'
 elif mutation=='task':s['id']='E14'
 else:control='unknown'
 with pytest.raises(ValueError):negative_plan(s,control)

def test_smooth_author_refused():
 a=FakeAuthor(spec('E02'));a.smooth=True
 with pytest.raises(ValueError,match='public actions'):GraspNegativeAuthor(a,'wrong_rule')

@pytest.mark.parametrize('task',['E02','E05','E11'])
@pytest.mark.parametrize('control',sorted(CAPABILITIES['E02']))
def test_production_case_validation_admits_only_fresh_v3_counterexample(tmp_path,task,control):
 import json
 from videoicl_isaaclab.execution_design_reference import reference_capability
 from videoicl_isaaclab.execution_design_probe import validate_execution_cases
 from videoicl_isaaclab.execution_design import REVISION_V2
 cap=reference_capability(task,control);assert cap['implemented'] and not cap['native_validated']
 assert cap['required_revision']==REVISION_V3
 source=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
 binding=json.loads(source.read_text());binding['execution_design']={'revision':REVISION_V3,'condition':'I'}
 path=tmp_path/'binding.json';path.write_text(json.dumps(binding))
 case={'episode_id':'test','task':task,'variant':'A','seed':4201,'bindings':str(path)}
 assert validate_execution_cases([case],control)[0]['native_acceptance']=='not_run'
 binding['execution_design']['revision']=REVISION_V2;binding['execution_design']['condition']='R'
 legacy=tmp_path/'legacy-binding.json';legacy.write_text(json.dumps(binding));case['bindings']=str(legacy)
 with pytest.raises(ValueError,match='explicit v3'):validate_execution_cases([case],control)
