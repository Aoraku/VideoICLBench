"""Validate the calibration against untouched source USD collision vertices."""
import ast
import hashlib
import re
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e23_geometry import BRANCHES,COLLISION_SOURCE_SHA256,calibrate_source_branches
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs_v3 import apply_execution_inputs_v3

ROOT=Path(__file__).parents[2]
BINDINGS=ROOT/'runtime/configs/realworld_full50_bindings.json'
SOURCE=ROOT/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/three_level_mug_tree_parts/visual.usda'


def test_calibration_matches_pca_end_faces_and_bounds_every_real_collision_corner():
    text=SOURCE.read_text()
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==COLLISION_SOURCE_SHA256
    assert 'xformOp:' not in text
    collisions=text.split('def Xform "Collisions"',1)[1]
    for key,branch in BRANCHES.items():
        i=int(key)+2
        match=re.search(r'def Mesh "mesh_'+str(i)+'_component_'+str(i)+r'".*?point3f\[\] points = (\[[^\n]+\])',collisions,re.S)
        points=np.asarray(ast.literal_eval(match[1]));assert points.shape==(8,3)
        center=points.mean(0);_,axes=np.linalg.eigh((points-center).T@(points-center));projection=(points-center)@axes[:,-1]
        ends=[points[projection<0].mean(0),points[projection>0].mean(0)]
        ends.sort(key=lambda p:np.linalg.norm(p[:2]));base,tip=ends
        np.testing.assert_allclose(branch['base_local'],base,atol=1e-9)
        np.testing.assert_allclose(branch['tip_local'],tip,atol=1e-9)
        axis=(tip-base)/np.linalg.norm(tip-base);delta=points-base
        radius=np.linalg.norm(delta-np.outer(delta@axis,axis),axis=1)
        assert radius.max()==pytest.approx(branch['radius'],abs=1e-9)


@pytest.mark.parametrize('variant',list('ABC'))
def test_fresh_v3_rie_share_actual_rods_without_mutating_legacy_or_physics(variant):
    old=load('E23',variant,0,BINDINGS,verify_files=False);before=deepcopy(old)
    for condition in 'RIE':
        new=apply_execution_inputs_v3(old,condition=condition,seed=4201)
        assert new['semantic']['branches']=={k:dict(ref={'actor':'tree'},**b)for k,b in BRANCHES.items()}
        assert new['source_geometry_calibration']['physical_asset_changed'] is False
        assert next(o for o in new['objects']if o['id']=='tree')==next(o for o in old['objects']if o['id']=='tree')
    assert old==before
    assert old['semantic']['branches']['2']['base_local'][1]<-.11


def test_unreviewed_geometry_is_rejected_instead_of_silently_reusing_calibration():
    spec=load('E23','A',0,BINDINGS,verify_files=False)
    next(o for o in spec['objects']if o['id']=='tree')['mechanical_asset']['sha256']='changed'
    with pytest.raises(ValueError,match='Unreviewed'):calibrate_source_branches(spec)


def measured_cavity_fixture(branch_id):
    """Synthetic transforms of actual source geometry; not a native acceptance."""
    from videoicl_isaaclab.realworld_structural_evidence import StructuralTaskEvaluator
    spec=apply_execution_inputs_v3(load('E23','A',0,BINDINGS,verify_files=False),condition='I',seed=4201)
    e=StructuralTaskEvaluator(spec)
    e.state={'tree':dict(pos=np.array([0.,0.,.8]),mat=np.eye(3),grasp=[False,False])}
    b=e.semantic['branches'][branch_id]
    base=e.point(b['ref'],b['base_local']);tip=e.point(b['ref'],b['tip_local'])
    rod=(tip-base)/np.linalg.norm(tip-base);axis=-rod
    x=np.cross(np.array([0.,0.,1.]),axis);x/=np.linalg.norm(x)
    rotation=np.column_stack([x,np.cross(axis,x),axis])
    rim=tip-rod*.020
    e.state['red']=dict(pos=rim-rotation@np.asarray(e.semantic['cups']['red']['rim_local']),mat=rotation,grasp=[False,False])
    e.contacts={frozenset(('red','tree'))};e.forces={frozenset(('red','tree')):2.}
    return e,b,rod,rim,rotation


@pytest.mark.parametrize('branch_id',list(BRANCHES))
def test_actual_source_rods_require_cavity_insertion_not_just_tree_contact(branch_id):
    e,b,rod,rim,rotation=measured_cavity_fixture(branch_id)
    assert e.branch_inside('red',b)
    correct=deepcopy(e.state['red'])
    # Reverse the actual cup mouth axis while keeping its mouth position.
    opposite=rotation@np.diag([1.,-1.,-1.])
    e.state['red']['mat']=opposite
    e.state['red']['pos']=rim-opposite@np.asarray(e.semantic['cups']['red']['rim_local'])
    assert not e.branch_inside('red',b)
    # Mouth outside the real rod tip; supplied side contact cannot substitute.
    e.state['red']=deepcopy(correct);e.state['red']['pos']+=rod*.05
    assert not e.branch_inside('red',b)
    # Axially aligned but radially outside the actual mouth opening.
    e.state['red']=deepcopy(correct);e.state['red']['pos']+=rotation[:,0]*.06
    assert not e.branch_inside('red',b)
    e.state['red']=deepcopy(correct);e.contacts=set()
    assert not e.branch_inside('red',b)
    e.contacts={frozenset(('red','tree'))};e.forces={}
    assert not e.branch_inside('red',b)
