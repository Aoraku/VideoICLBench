from copy import deepcopy
from pathlib import Path
import hashlib,json
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs_v3 import apply_execution_inputs_v3,physical_input_signature
P=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_clip_instances_retain_rule_opening_geometry_and_pairing(variant,seed):
    base=load('E40',variant,0,P,verify_files=False);saved=deepcopy(base)
    changed=apply_execution_inputs_v3(base,condition='I',seed=seed)
    paired=apply_execution_inputs_v3(base,condition='E',seed=seed)
    assert physical_input_signature(changed)==physical_input_signature(paired)
    assert changed['goals']==base['goals']
    for a,b in zip(base['mechanisms'],changed['mechanisms']):
        assert a['mechanical_asset']['sha256']!=b['mechanical_asset']['sha256']
        assert b['mechanical_asset']['instance_derivation']['joints_preserved']
        assert b['mechanical_asset']['root_env']=='VIC_EXECUTION_DESIGN_ASSETS'
        old,new=base['semantic']['clips'][a['id']],changed['semantic']['clips'][b['id']]
        assert new['capture_radius']==old['capture_radius']
        assert new['expert']['open_gap_m']==old['expert']['open_gap_m']
        assert new['expert']['handle_grasp']['jaw_axis_local']==old['expert']['handle_grasp']['jaw_axis_local']
    fixed=apply_execution_inputs_v3(base,condition='R',seed=seed)
    assert physical_input_signature(fixed)==physical_input_signature(base)
    assert base==saved

def test_actual_usd_width_changes_all_visual_and_collision_points_but_not_joints():
    Usd=pytest.importorskip('pxr.Usd');from pxr import UsdGeom,UsdPhysics,Gf
    rt=P.parents[1];assets=rt/'execution-design-v3/assets'
    src=rt.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/binder_clip_spring_v3.usda'
    old=Usd.Stage.Open(str(src));cache=UsdGeom.XformCache()
    meta=json.loads((assets/'E40/instances.private.json').read_text())
    for row in meta['instances']:
        stage=Usd.Stage.Open(str(assets/row['asset']['relative_path']));factor=row['width_scale'];count=0
        for p in old.Traverse():
            q=stage.GetPrimAtPath(p.GetPath());assert q
            if p.IsA(UsdPhysics.Joint):
                for a in p.GetAttributes():assert q.GetAttribute(a.GetName()).Get()==a.Get()
                for r in p.GetRelationships():assert q.GetRelationship(r.GetName()).GetTargets()==r.GetTargets()
            if p.IsA(UsdGeom.Mesh):
                before=UsdGeom.Mesh(p).GetPointsAttr().Get();after=UsdGeom.Mesh(q).GetPointsAttr().Get()
                assert len(before)==len(after)
                m=cache.GetLocalToWorldTransform(p)
                for a,b in zip(before,after):
                    a,b=m.Transform(Gf.Vec3d(*a)),m.Transform(Gf.Vec3d(*b))
                    assert tuple(b)==pytest.approx((a[0]*factor,a[1],a[2]),abs=1e-8)
                if p.HasAPI(UsdPhysics.CollisionAPI):
                    assert q.HasAPI(UsdPhysics.CollisionAPI);count+=1
            if p.HasAPI(UsdPhysics.MassAPI):
                assert UsdPhysics.MassAPI(q).GetMassAttr().Get()==pytest.approx(UsdPhysics.MassAPI(p).GetMassAttr().Get()*factor)
        assert count==row['collision_mesh_count']==87
        for item in [row['asset'],*row['asset']['dependencies']]:
            assert hashlib.sha256((assets/item['relative_path']).read_bytes()).hexdigest()==item['sha256']
