"""Actual G1 USD geometry regressions and physical support negative controls."""
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_structural_evidence import StructuralTaskEvaluator
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('e08_g1_builder', ROOT/'scripts/build_inference_g1_assets.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
BINDING=json.loads((ROOT/'inference-generalization-v1/g1-bindings-patch.json').read_text())['tasks']['E08']


def evaluator():
 e=StructuralTaskEvaluator.__new__(StructuralTaskEvaluator)
 e.task='E08';e.objects=copy.deepcopy(BINDING['objects'])
 e.semantic=copy.deepcopy(BINDING['variants']['B']['semantic'])
 e.state={n:dict(pos=np.zeros(3),mat=np.eye(3),grasp=[False,False]) for n in e.objects}
 e.contacts=set();e.forces={};e.hand_force=lambda n:0.
 for n in ['left_shoe','right_shoe']:
  obj=e.objects[n];mesh=b.shape(n,b.color_for(n));mesh.normalize(obj['size'])
  actual=(ROOT/'inference-generalization-v1/assets'/obj['source_asset']['relative_path']).read_bytes()
  assert hashlib.sha256(actual).hexdigest()==obj['source_asset']['sha256']
  assert mesh.text().encode()==actual
  b.bind_shoe_containment(obj,mesh)
 return e


def contact(e,a,b):
 pair=frozenset((a,b));e.contacts.add(pair);e.forces[pair]=1.


def test_actual_shoe_tilt_can_fit_when_empty_bbox_corner_cannot():
 e=evaluator();n='right_shoe';points=np.array(e.objects[n]['containment_points_local'])
 c=e.semantic['containers']['box'];lo=np.array(c['lower']);hi=np.array(c['upper'])
 witness=None
 for deg in range(5,176,5):
  a=np.deg2rad(deg);r=np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
  q=points@r.T
  if np.any(np.ptp(q,axis=0)>hi-lo):continue
  e.state[n]['mat']=r;e.state[n]['pos']=(lo+hi-q.min(axis=0)-q.max(axis=0))/2
  corners=e.corners(n,c['ref'])
  if np.any(corners.min(axis=0)<lo-[.002,.002,.003]) or np.any(corners.max(axis=0)>hi+[.002,.002,.003]):
   witness=deg;break
 assert witness is not None
 assert e.contained('box',[n])[0]==[n]
 # Genuine geometry outside stays rejected; same cavity and tolerances.
 e.state[n]['pos'][1]+=.15
 assert e.contained('box',[n])[0]==[]


def test_source_identity_mismatch_rejected():
 e=evaluator();e.objects['right_shoe']['containment_points_source_sha256']='0'*64
 with pytest.raises(ValueError,match='matching source'):e.contained('box',['right_shoe'])


def support_fixture():
 e=evaluator()
 # Small boxes isolate support semantics without changing production assets.
 for n in ['left_shoe','right_shoe']:
  e.objects[n]={'size':[.02,.02,.01]}
 e.state['left_shoe']['pos']=np.array([0,0,-.04264])
 e.state['right_shoe']['pos']=np.array([0,0,-.02264])
 contact(e,'left_shoe','box');contact(e,'right_shoe','left_shoe')
 return e


def test_other_shoe_support_matches_declared_task_contract():
 e=support_fixture()
 assert e.contained('box',['left_shoe','right_shoe'])==(['left_shoe','right_shoe'],['left_shoe','right_shoe'])


@pytest.mark.parametrize('fault',['no_floor_contact','no_shoe_contact','held_base','finger_support','base_outside','floating_cycle'])
def test_invalid_support_is_not_promoted(fault):
 e=support_fixture()
 if fault=='no_floor_contact':e.contacts.remove(frozenset(('left_shoe','box')))
 elif fault=='no_shoe_contact':e.contacts.remove(frozenset(('right_shoe','left_shoe')))
 elif fault=='held_base':e.state['left_shoe']['grasp']=[True,True]
 elif fault=='finger_support':e.hand_force=lambda n:1. if n=='left_shoe' else 0.
 elif fault=='base_outside':e.state['left_shoe']['pos'][0]=.3
 elif fault=='floating_cycle':
  e.state['left_shoe']['pos'][2]=0.;e.state['right_shoe']['pos'][2]=.02
 assert 'right_shoe' not in e.contained('box',['left_shoe','right_shoe'])[1]


def test_other_tasks_keep_floor_support_rule():
 e=support_fixture();e.task='E24'
 assert e.contained('box',['left_shoe','right_shoe'])[1]==['left_shoe']


def test_offline_augmentation_is_source_bound_and_nonmutating():
 from videoicl_isaaclab.e08_source_geometry import augment_e08_bindings
 original={'tasks':{'E08':copy.deepcopy(BINDING)}}
 candidate=augment_e08_bindings(original,ROOT)
 assert 'containment_points_local' not in original['tasks']['E08']['objects']['right_shoe']
 assert len(candidate['tasks']['E08']['objects']['right_shoe']['containment_points_local'])>8
 original['tasks']['E08']['objects']['right_shoe']['source_asset']['sha256']='0'*64
 with pytest.raises(ValueError,match='SHA mismatch'):augment_e08_bindings(original,ROOT)


@pytest.mark.parametrize('fault',['missing_points','mismatched_sha','bad_points','unknown_version'])
def test_declared_geometry_contract_never_silently_falls_back(fault):
 e=evaluator();e.semantic['source_acceptance_geometry']='E08-source-geometry-v1'
 if fault=='missing_points':del e.objects['left_shoe']['containment_points_local']
 elif fault=='mismatched_sha':e.objects['left_shoe']['containment_points_source_sha256']='0'*64
 elif fault=='bad_points':e.objects['left_shoe']['containment_points_local']=[[0,0,float('nan')]]
 else:e.semantic['source_acceptance_geometry']='unknown'
 with pytest.raises(ValueError,match='geometry contract'):e.contained('box',['right_shoe'])


def test_augmentation_marks_all_variants():
 from videoicl_isaaclab.e08_source_geometry import augment_e08_bindings
 candidate=augment_e08_bindings({'tasks':{'E08':BINDING}},ROOT)
 assert all(v['semantic']['source_acceptance_geometry']=='E08-source-geometry-v1'
            for v in candidate['tasks']['E08']['variants'].values())


@pytest.mark.parametrize('axis',[0,1,2])
@pytest.mark.parametrize('side',['lower','upper'])
def test_actual_shoe_cavity_tolerance_boundary(axis,side):
 """Every real vertex obeys the existing 2mm/3mm bound, including tilt."""
 e=evaluator();n='right_shoe';c=e.semantic['containers']['box']
 lo=np.asarray(c['lower']);hi=np.asarray(c['upper'])
 angle=np.deg2rad(70.)
 rotation=np.array([[1,0,0],[0,np.cos(angle),-np.sin(angle)],[0,np.sin(angle),np.cos(angle)]])
 points=np.asarray(e.objects[n]['containment_points_local'])@rotation.T
 position=(lo+hi-points.min(axis=0)-points.max(axis=0))/2
 e.state[n]['mat']=rotation
 tolerance=.003 if axis==c.get('axis',2) else .002
 for beyond in [False,True]:
  epsilon=1e-6 if beyond else -1e-6
  shifted=position.copy()
  if side=='upper':shifted[axis]=hi[axis]+tolerance+epsilon-points[:,axis].max()
  else:shifted[axis]=lo[axis]-tolerance-epsilon-points[:,axis].min()
  e.state[n]['pos']=shifted
  assert (n in e.contained('box',[n])[0]) is (not beyond)
