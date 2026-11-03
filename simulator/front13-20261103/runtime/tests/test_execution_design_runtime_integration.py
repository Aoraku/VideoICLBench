"""Opt-in loading and live-server initial admission; no PhysX claims."""
import json
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design import REVISION,WORKFLOW_TASKS
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
from videoicl_isaaclab.realworld_progress_evidence import initial_diagnostics,seal_initial
SOURCE=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
def binding(tmp_path,condition='I',revision=REVISION):
 d=json.loads(SOURCE.read_text());d['execution_design']={'revision':revision,'condition':condition};p=tmp_path/'bindings.json';p.write_text(json.dumps(d));return p
@pytest.mark.parametrize('task',sorted(WORKFLOW_TASKS))
def test_load_dispatch_and_public_contract(task,tmp_path):
 p=binding(tmp_path);specs=[load(task,v,1,p,verify_files=False)for v in 'ABC']
 assert len({s['instruction']for s in specs})==1
 for s in specs:
  assert s['task_revision']==REVISION and not s['release_ready']
  assert set(s['public_order'])=={'batch','destination'}
  e=create_evaluator(s);d=initial_diagnostics(e,room_id='test')
  assert d['room_id']=='test' and not d['can_seal']
  with pytest.raises(ValueError):seal_initial(e)
  assert e.result()['task_score_100'] is None
  assert not e.result()['strict_success']
def test_unsupported_revision_rejected(tmp_path):
 with pytest.raises(ValueError,match='revision'):load('E01','A',1,binding(tmp_path,revision='unknown'),verify_files=False)
def test_ie_only_does_not_accept_full_workflow_R(tmp_path):
 with pytest.raises(ValueError,match='support'):load('E01','A',1,binding(tmp_path,condition='R'),verify_files=False)
def test_legacy_source_remains_local_rule():
 s=load('E01','A',1,SOURCE,verify_files=False)
 assert 'execution_design'not in s
 assert type(create_evaluator(s)).__name__=='StructuralTaskEvaluator'
