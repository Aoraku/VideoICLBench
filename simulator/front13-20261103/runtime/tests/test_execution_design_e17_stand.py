"""Actual source-mesh derivation and legacy isolation; CPU checks only."""
import hashlib
from pathlib import Path
import re
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab.execution_design_scenes import build_execution_scene
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import REVISION_V2,REVISION_V3

RUNTIME=Path(__file__).parents[1]
SOURCE=RUNTIME.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/two_tier_cake_stand.usda'


def scene(revision=REVISION_V3,variant='A'):
    return build_execution_scene(load('E17',variant,4201,RUNTIME/'configs/realworld_full50_bindings.json',verify_files=False),seed=4201,revision=revision)


def source_vertices(index):
    source=SOURCE.parent/'two_tier_cake_stand_parts/visual.usda'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==stand.SOURCE_VISUAL_SHA
    mesh=source.read_text().split(f'def Mesh "mesh_{index}_component_{index}"',1)[1]
    points=re.search(r'point3f\[\] points = \[(.*?)\]',mesh,re.S).group(1)
    return np.asarray([tuple(map(float,p.split(',')))for p in re.findall(r'\(([^()]*)\)',points)],dtype=np.float32)


def test_actual_two_tier_derivation_preserves_lower_and_extends_real_rod():
    for index in (0,3):
        before=source_vertices(index)
        assert np.array_equal(stand.transform_points(index,before),before)
    for index in (1,2,4,5):
        before=source_vertices(index);after=stand.transform_points(index,before)
        assert np.array_equal(after[:,:2],before[:,:2])
        assert np.allclose(after[:,2]-before[:,2],.070,atol=2e-8,rtol=0)
    before=source_vertices(6);after=stand.transform_points(6,before)
    assert np.array_equal(after[:,:2],before[:,:2])
    assert after[:,2].min()==before[:,2].min()==0
    assert after[:,2].max()-before[:,2].max()==pytest.approx(.070,abs=2e-8)
    gap=stand.transform_points(1,source_vertices(1))[:,2].min()-source_vertices(0)[:,2].max()
    assert gap==pytest.approx(.186198554,abs=3e-8)
    assert .070 > stand.descriptor()['reviewed_continuous_path_minimum_lift_m']


def test_v2_geometry_and_rules_not_rewritten_and_v3_regions_follow_real_upper():
    old=scene(REVISION_V2);new=scene()
    oldstand=next(o for o in old['objects']if o['id']=='stand')
    newstand=next(o for o in new['objects']if o['id']=='stand')
    assert 'e17_stand_geometry' not in oldstand
    assert oldstand['mass']==.45
    assert newstand['e17_stand_geometry']['derived_geometry_sha256']==stand.GEOMETRY_SHA
    assert newstand['mass']==pytest.approx(.46302993369100737)
    assert newstand['mass']>.45
    assert newstand['center_z']==pytest.approx(oldstand['center_z'])
    assert newstand['local_bounds_center'][2]-oldstand['local_bounds_center'][2]==pytest.approx(.035)
    for a,b in zip(old['execution_design']['local_regions'],new['execution_design']['local_regions']):
        assert a['members']==b['members']
        delta=.070 if a['id']=='upper'else 0.
        assert np.allclose(np.array(b['lower'])-a['lower'],[0,0,delta])
        assert np.allclose(np.array(b['upper'])-a['upper'],[0,0,delta])
    assert old['execution_design']['destination_zone']==new['execution_design']['destination_zone']


def test_usd_generated_visual_and_collision_hash_and_source_unchanged():
    pytest.importorskip('pxr')
    from pxr import Usd,UsdGeom
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    stage=Usd.Stage.CreateInMemory();root=UsdGeom.Xform.Define(stage,'/Stand').GetPrim()
    root.GetReferences().AddReference(str(SOURCE.resolve()))
    obj=next(o for o in scene()['objects']if o['id']=='stand')
    stand.apply_to_usd(root,obj)
    assert root.GetAttribute('videoicl:e17DerivedGeometrySha256').Get()==stand.GEOMETRY_SHA
    for index in range(7):
        visual=UsdGeom.Mesh(stage.GetPrimAtPath(f'/Stand/Visuals/mesh_{index}_component_{index}'))
        collision=UsdGeom.Mesh(stage.GetPrimAtPath(f'/Stand/Collisions/mesh_{index}_component_{index}'))
        assert np.array_equal(np.asarray(visual.GetPointsAttr().Get()),np.asarray(collision.GetPointsAttr().Get()))
        assert np.allclose(visual.GetExtentAttr().Get(),[np.asarray(visual.GetPointsAttr().Get()).min(0),np.asarray(visual.GetPointsAttr().Get()).max(0)])
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before==stand.SOURCE_SHA
    obj['e17_stand_geometry']['derived_geometry_sha256']='tampered'
    with pytest.raises(ValueError,match='Unreviewed opt-in'):
        stand.apply_to_usd(root,obj)


def test_native_readback_reads_actual_mass_and_rejects_missing_geometry():
    pytest.importorskip('pxr')
    from pxr import Usd,UsdGeom,UsdPhysics
    from types import SimpleNamespace
    spec=scene();stage=Usd.Stage.CreateInMemory()
    root=UsdGeom.Xform.Define(stage,'/Room/Props/stand').GetPrim();root.GetReferences().AddReference(str(SOURCE.resolve()))
    obj=next(o for o in spec['objects']if o['id']=='stand');stand.apply_to_usd(root,obj)
    UsdPhysics.RigidBodyAPI.Apply(root).CreateKinematicEnabledAttr(False)
    view=SimpleNamespace(get_masses=lambda:np.array([[.461]]),get_coms=lambda:np.array([[0,0,.103,0,0,0,1]]),get_inertias=lambda:np.array([[.01,0,0,0,.01,0,0,0,.02]]))
    native=SimpleNamespace(spec=spec,root_path='/Room',objects={'stand':SimpleNamespace(root_physx_view=view)})
    result=stand.native_readback(native,stage)
    assert result['measured']and result['mass_kg']==[[.461]]
    assert result['center_of_mass_local'][0][2]==.103
    assert result['kinematic_enabled']is False
    assert result['transport_acceptance']is False
    stage.RemovePrim('/Room/Props/stand')
    assert stand.native_readback(native,stage)['measured']is False
    assert stand.native_readback(SimpleNamespace(spec={'id':'E20'}))is None


def test_geometry_digest_detects_topology_and_vertex_changes():
    parts=[('Collisions/example',[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],[3],[0,1,2])]
    original=stand.geometry_digest(parts)
    assert stand.geometry_digest([('Collisions/example',parts[0][1],[3],[0,2,1])])!=original
    assert stand.geometry_digest([('Collisions/example',[[0.,0.,.06],[1.,0.,0.],[0.,1.,0.]],[3],[0,1,2])])!=original


@pytest.mark.parametrize('variant,upper_count',[('A',2),('B',2),('C',4)])
def test_abc_layer_membership_capacity_and_estimated_loaded_mass(variant,upper_count):
    spec=scene(variant=variant);d=spec['execution_design'];objects={o['id']:o for o in spec['objects']}
    regions={r['id']:r for r in d['local_regions']}
    assert len(regions['upper']['members'])==upper_count
    assert set(regions['lower']['members']+regions['upper']['members'])==set(d['target_members'])
    xy=spec['semantic']['structural_expert']['shelf_positions'];mass=objects['stand']['mass'];moment=np.array([0.,0.,.10693691277918585])*mass
    occupied=[]
    for layer,r in regions.items():
        for name in r['members']:
            o=objects[name];half=np.array(o['size']);point=np.array([*xy[name][:2],(.21980625 if layer=='upper'else .016795216)+half[2]])
            assert np.all(point-half>=np.array(r['lower']))
            assert np.all(point+half<=np.array(r['upper']))
            assert all(z!=layer or np.linalg.norm(point[:2]-p[:2])>.04 for z,p in occupied)
            occupied.append((layer,point));mass+=o['mass'];moment+=o['mass']*point
    assert mass==pytest.approx(.5110299336910074)
    center=moment/mass
    # Only a static uniform-density estimate, not a grasp or transport proof.
    assert np.linalg.norm(center[:2])<.01
    assert .10<center[2]<.12
    assert np.arctan((.10-np.linalg.norm(center[:2]))/center[2])>np.deg2rad(38)


def test_derived_environment_and_assignment_identity_differ_without_leaking_variant():
    from videoicl_isaaclab.execution_design import build_task_contract
    designs=[scene(variant=v)['execution_design']for v in 'ABC']
    assert len({d['environment_identity']for d in designs})==1
    assert len({d['physical_configuration_sha256']for d in designs})==1
    assert len({d['assignment_identity_sha256']for d in designs})==3
    for variant,d in zip('ABC',designs):
        original=build_task_contract('E17',variant,4201,condition='I')['execution_design']
        for key in ('environment_identity','assignment_identity_sha256','paired_input_identity'):
            assert d[key]!=original[key]
            assert d['source_'+key]==original[key]
        assert d['semantic_input_identity']==original['semantic_input_identity']
        assert d['environment_revision_provenance']['derived_geometry_sha256']==stand.GEOMETRY_SHA
    alternate=build_execution_scene(load('E17','A',4201,RUNTIME/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201)['execution_design']
    assert alternate['paired_input_identity']==designs[0]['paired_input_identity']
    assert alternate['environment_identity']!=designs[0]['environment_identity']
    assert alternate['physical_configuration_sha256']==designs[0]['physical_configuration_sha256']
