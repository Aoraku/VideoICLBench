from pathlib import Path
import hashlib,re
import numpy as np
import pytest
from scipy.spatial import ConvexHull
from videoicl_isaaclab.execution_design_e10_collision import source_prisms,configure_spec
from videoicl_isaaclab.realworld_scenes import load

ROOT=Path(__file__).resolve().parents[2]

def source(name):
    p=ROOT/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/name
    text=p.read_text().split('def Xform "Collisions"')[1]
    v=np.fromstring(re.search(r'point3f\[\] points = \[([^\]]+)\]',text)[1].translate(str.maketrans({'(':None,')':None})),sep=',').reshape(-1,3)
    f=np.fromstring(re.search(r'int\[\] faceVertexIndices = \[([^\]]+)\]',text)[1],sep=',',dtype=int).reshape(-1,3)
    return v,f,hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.mark.parametrize('filename,actor',[('source_four_hole_plate.usda','red_square'),('source_three_hole_triangle_v2.usda','red_triangle')])
def test_original_hole_sweep_open_and_original_material_still_solid(filename,actor):
    v,f,sha=source(filename);prisms,audit=source_prisms(v,f,sha)
    hulls=[ConvexHull(p)for p in prisms]
    def inside(p):return any(np.max(h.equations[:,:3]@p+h.equations[:,3])<=1e-10 for h in hulls)
    spec=load('E10','A',0,ROOT/'runtime/configs/realworld_full50_bindings.json',verify_files=False)
    for hole in spec['semantic']['holes'][actor]:
        for angle in np.linspace(0,2*np.pi,36,endpoint=False):
            for z in np.linspace(-.003,.003,11):
                p=np.array(hole['center_local'])+[.00265*np.cos(angle),.00265*np.sin(angle),z]
                assert not inside(p)
    for prism in prisms:assert inside(prism.mean(0))
    assert np.isclose(audit['original_volume_m3'],audit['prism_union_volume_m3'],rtol=1e-5)
    assert all(6<=len(p)<=48 and len(p)%2==0 for p in prisms)

def test_wrong_source_and_changed_thickness_fail_closed():
    v,f,sha=source('source_four_hole_plate.usda')
    with pytest.raises(ValueError,match='identity'):source_prisms(v,f,'wrong')
    v[:,2]*=2
    with pytest.raises(ValueError,match='thickness'):source_prisms(v,f,sha)

def test_flags_only_original_six_plates_and_legacy_not_implicitly_modified():
    spec=load('E10','A',0,ROOT/'runtime/configs/realworld_full50_bindings.json',verify_files=False)
    assert not any('reviewed_e10_extruded_collision'in o for o in spec['objects'])
    configure_spec(spec)
    assert sum('reviewed_e10_extruded_collision'in o for o in spec['objects'])==6
    assert not any('reviewed_e10_extruded_collision'in o for o in spec['objects']if o['id'].endswith('circle')or o['id']=='board')


def test_normalized_cook_coordinates_exactly_recover_skinny_prism_without_shear():
    from videoicl_isaaclab.execution_design_e10_collision import normalized_prism
    top=np.array([[.1,.1,.003],[.15,.15,.003],[.125,.125001,.003]])
    bottom=top.copy();bottom[:,2]=-.003;p=np.vstack([top,bottom])
    normalized,matrix=normalized_prism(p)
    np.testing.assert_allclose(np.ptp(normalized,axis=0),[1,1,1],atol=1e-10)
    np.testing.assert_allclose(np.c_[normalized,np.ones(6)]@matrix,np.c_[p,np.ones(6)],atol=1e-12)
    basis=matrix[:3,:3]/np.linalg.norm(matrix[:3,:3],axis=1)[:,None]
    np.testing.assert_allclose(basis@basis.T,np.eye(3),atol=1e-12)


def test_runtime_unions_keep_every_original_skinny_material_corner_and_total_volume():
    from videoicl_isaaclab.execution_design_e10_collision import runtime_prisms,normalized_prism
    v,f,sha=source('source_three_hole_triangle_v2.usda');original,audit=source_prisms(v,f,sha)
    cooked,merges=runtime_prisms(original,sha)
    assert len(cooked)==150 and len(merges)==2
    assert sum(ConvexHull(p).volume for p in cooked)==pytest.approx(sum(ConvexHull(p).volume for p in original),rel=1e-12)
    for pair in [(109,132),(111,144)]:
        union=next(p for p in cooked if len(p)==8 and all(any(np.linalg.norm(corner-point)<1e-12 for point in p)for corner in original[pair[0]]))
        hull=ConvexHull(union)
        for i in pair:
            assert np.max(original[i]@hull.equations[:,:3].T+hull.equations[:,3])<1e-12
        normalized,matrix=normalized_prism(union)
        np.testing.assert_allclose(np.c_[normalized,np.ones(len(union))]@matrix,np.c_[union,np.ones(len(union))],atol=1e-12)
    broken=[p.copy()for p in original]
    shared=next(i for i,p in enumerate(broken[132][:3])if any(np.linalg.norm(p-q)<1e-12 for q in original[109][:3]))
    broken[132][shared,0]+=.001
    with pytest.raises(ValueError):runtime_prisms(broken,sha)
