from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_execution_design_front13_grasp_negative import spec
from videoicl_isaaclab.execution_design_e03_negative import E03NegativeAuthor,negative_plan,CONTROLS
from videoicl_isaaclab.realworld_structural_expert import StructuralAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('condition','RIE')
def test_reviewed_matrix_leaves_original_scene_immutable(variant,seed,condition):
 s=spec('E03',variant,seed,condition);before=deepcopy(s)
 for control in CONTROLS:
  plan=negative_plan(s,control)
  assert s==before and plan['negative_condition_observed'] is None
  assert plan['native_review_required']
 assert negative_plan(s,'wrong_members')['terminal_predicate']==negative_plan(s,'wrong_destination')['terminal_predicate']
 wrong=negative_plan(s,'wrong_rule');assert wrong['outer_to_inner']!=wrong['original_outer_to_inner']
 assert wrong['terminal_predicate']=='incorrect_full_nesting_order'

@pytest.fixture
def physical_route(monkeypatch):
 def init(self,author):
  self.a=author;self.c=author.c;self.spec=author.scene.spec;self.s=self.spec['semantic']
  self.grasps=deepcopy(self.s['structural_grasps']);self.operations=[];self.start=0;self.index='ABC'.index(self.spec['variant'])
  self.trace=[];self.held_name=None
  self.positions={n:np.array([float(i),0.,.8]) for i,n in enumerate(self.s['cups'])}
 def point(self,ref,local):return self.positions[ref['actor']].copy()
 def pickup(self,name):
  self.trace.append(('pickup',name));self.held_name=name;self.positions[name][2]+=.07
  return {'actor':name},'left'
 def release(self,ref,side):self.trace.append(('release',ref['actor']));self.held_name=None
 def place(self,name,ref,side,local,target,rotation=None,support=None):
  self.trace.append(('place',name,support));self.positions[name]=np.array(target,dtype=float)
  self.release(ref,side)
 def nest(self):
  names=self.perturbation['outer_to_inner']
  for outer,inner in zip(names[:-1],names[1:]):
   ref,side=self.pickup(inner)
   self.lower_place(inner,ref,side,[0,0,0],self.positions[outer]+[0,0,.03],support=outer)
 def held(self,ref,side):
  if self.held_name!=ref['actor']:raise ToolExecutionError('Actual grip lost')
 def wait(self,n):self.c.steps+=n
 def snapshot(self):return ({n:{'mat':np.eye(3)} for n in self.positions},set())
 def stage(self,name):self.operations.append(name)
 for name,fn in dict(__init__=init,body_point=point,pickup=pickup,release=release,lower_place=place,nest=nest,require_held=held,wait=wait,snapshot=snapshot,stage=stage).items():
  monkeypatch.setattr(StructuralAuthor,name,fn)
 def build(control):
  s=spec('E03');a=SimpleNamespace(scene=SimpleNamespace(spec=s),c=SimpleNamespace(steps=0),control_report={'engineering_reference_only':True})
  return E03NegativeAuthor(a,control)
 return build

@pytest.mark.parametrize('control',sorted(CONTROLS))
def test_route_uses_real_first_pair_and_preserves_native_spec(physical_route,control):
 p=physical_route(control);original=p.a.scene;before=deepcopy(original.spec)
 result=p.solve_negative();names=p.perturbation['outer_to_inner']
 assert p.trace[:3]==[('pickup',names[1]),('place',names[1],names[0]),('release',names[1])]
 assert original.spec==before and p.a.scene is original
 assert result['negative_condition_observed'] is None
 if control=='wrong_members':assert len(p.trace)==3
 elif control=='wrong_destination':
  assert ('pickup',names[-1]) in p.trace and ('place',names[-1],'table') in p.trace
  assert np.allclose(p.positions[p.last],p.source_bottom) and p.held_name is None
 elif control=='wrong_rule':
  assert len(p.trace)==6 and p.held_name is None and p.index==1
 else:
  assert p.held_name==p.last and p.hold_checks==3
  assert ('release',p.last) not in p.trace

@pytest.mark.parametrize('control',sorted(CONTROLS))
def test_physical_failure_propagates_not_converted_to_witness(physical_route,control):
 p=physical_route(control)
 def fail(name):raise ToolExecutionError('physical pickup failure')
 p.pickup=fail
 with pytest.raises(ToolExecutionError,match='physical pickup failure'):p.solve_negative()

def test_lost_grip_cannot_be_not_released_witness(physical_route):
 p=physical_route('not_released')
 def lost(ref,side):raise ToolExecutionError('Actual grip lost')
 p.require_held=lost
 with pytest.raises(ToolExecutionError,match='Actual grip lost'):p.solve_negative()

def test_held_wrong_position_cannot_be_witness(physical_route):
 p=physical_route('not_released');original=p.body_point
 def wrong(ref,local):
  position=original(ref,local)
  return position+[0,0,.03] if p.final_target is not None else position
 p.body_point=wrong
 with pytest.raises(ToolExecutionError,match='outside intended'):p.solve_negative()

@pytest.mark.parametrize('mutation',['legacy','sha','task'])
def test_nonreviewed_recipe_rejected(mutation):
 s=spec('E03')
 if mutation=='legacy':s['execution_design']['revision']='legacy'
 elif mutation=='sha':s['execution_design']['source_sha256']='unknown'
 else:s['id']='E14'
 with pytest.raises(ValueError):negative_plan(s,'wrong_members')


def test_last_still_drift_cannot_be_held_witness(physical_route):
 p=physical_route('not_released');original=p.wait
 def drift(n):
  original(n)
  if p.hold_checks==2:p.positions[p.last][0]+=.02
 p.wait=drift
 with pytest.raises(ToolExecutionError,match='drifted outside'):p.solve_negative()


@pytest.mark.parametrize('control',sorted(CONTROLS))
def test_production_v3_dispatch_admission(tmp_path,control):
 import json
 from pathlib import Path
 from videoicl_isaaclab.execution_design_reference import reference_capability
 from videoicl_isaaclab.execution_design_probe import validate_execution_cases
 from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
 cap=reference_capability('E03',control)
 assert cap['implemented'] and not cap['native_validated'] and cap['required_revision']==REVISION_V3
 binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
 binding['execution_design']={'revision':REVISION_V3,'condition':'I'}
 path=tmp_path/'binding.json';path.write_text(json.dumps(binding))
 case=dict(episode_id='e03-negative',task='E03',variant='A',seed=4201,bindings=str(path))
 assert validate_execution_cases([case],control)[0]['native_acceptance']=='not_run'
 binding['execution_design']={'revision':REVISION_V2,'condition':'R'};path.write_text(json.dumps(binding))
 with pytest.raises(ValueError,match='explicit v3'):validate_execution_cases([case],control)
