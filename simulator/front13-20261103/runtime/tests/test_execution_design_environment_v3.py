from copy import deepcopy
import json
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design_environment_v3 import environment_settings,apply_native_environment,REVISION


def spec(task='E29',condition='E'):
    return dict(id=task,execution_design=dict(revision=REVISION,condition=condition),
                execution_environment=environment_settings(task,condition))


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(26,51)if i!=39])
def test_scope(task):
    assert environment_settings(task,'E')
    assert environment_settings(task,'I') is None
    assert environment_settings(task,'R') is None

@pytest.mark.parametrize('task',('E01','E25','E39','E51'))
def test_other_owners_unchanged(task):assert environment_settings(task,'E') is None


def material(stage,path,color,roughness):
    from pxr import UsdShade,Sdf,Gf
    m=UsdShade.Material.Define(stage,path);shader=UsdShade.Shader.Define(stage,path+'/Surface')
    shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(roughness)
    m.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    return m


def make_stage(kind):
    from pxr import Usd,UsdGeom,UsdShade,UsdPhysics,UsdLux,Gf
    s=Usd.Stage.CreateInMemory();root='/World/Rooms/room_01/Rig'
    UsdGeom.Xform.Define(s,root)
    wall=root+('/Wall'if kind=='robotwin'else'/Room/WallMesh')
    p=UsdGeom.Cube.Define(s,wall).GetPrim();UsdGeom.Xformable(p).AddTranslateOp().Set(Gf.Vec3d(0,2,1))
    UsdPhysics.CollisionAPI.Apply(p)
    phys=UsdShade.Material.Define(s,root+'/Materials/Physics');a=UsdPhysics.MaterialAPI.Apply(phys.GetPrim());a.CreateStaticFrictionAttr(.7)
    UsdShade.MaterialBindingAPI.Apply(p).Bind(phys,UsdShade.Tokens.weakerThanDescendants,'physics')
    UsdLux.DomeLight.Define(s,root+'/Dome').CreateIntensityAttr(450)
    if kind=='robotwin':UsdLux.DistantLight.Define(s,root+'/Directional0').CreateIntensityAttr(900)
    # Neighbor light and target colors must never be touched.
    UsdLux.DomeLight.Define(s,'/World/Rooms/room_02/Rig/Dome').CreateIntensityAttr(123)
    target=UsdGeom.Cube.Define(s,'/World/Rooms/room_01/Task/red').GetPrim()
    mat=material(s,'/World/Rooms/room_01/Task/RedMaterial',[1,0,0],.4)
    UsdShade.MaterialBindingAPI.Apply(target).Bind(mat)
    return s,root

@pytest.mark.parametrize('kind',('robotwin','robodojo'))
def test_real_usd_material_light_readback_preserves_physics_and_other_rooms(kind,tmp_path):
    pytest.importorskip('pxr.Usd')
    from pxr import UsdShade,UsdLux
    s,root=make_stage(kind);initial=spec();before=deepcopy(initial)
    receipt=apply_native_environment(s,root,initial,material)
    assert receipt['physical_before_sha256']==receipt['physical_after_sha256']
    assert receipt['usd_readback_verified'] is True
    assert receipt['native_physics_validated'] is False
    assert receipt['render_visibility_review']=='pending'
    assert receipt['lights'][0]['intensity_after']==pytest.approx(382.5)
    assert UsdLux.LightAPI(s.GetPrimAtPath('/World/Rooms/room_02/Rig/Dome')).GetIntensityAttr().Get()==123
    assert str(UsdShade.MaterialBindingAPI(s.GetPrimAtPath('/World/Rooms/room_01/Task/red')).ComputeBoundMaterial()[0].GetPath()).endswith('/RedMaterial')
    assert initial==before
    with pytest.raises(ValueError,match='already authored'):apply_native_environment(s,root,initial,material)
    (tmp_path/f'{kind}-readback.json').write_text(json.dumps(receipt))


def test_contract_rejected_before_usd_edits():
    s=spec('E29','R');s['execution_environment']=environment_settings('E29','E')
    with pytest.raises(ValueError,match='explicit second-half'):apply_native_environment(None,'/World',s,None)
    s=spec();s['execution_environment']['light_intensity_scale']=3
    with pytest.raises(ValueError,match='reviewed visual-only'):apply_native_environment(None,'/World',s,None)

@pytest.mark.parametrize('missing',('background','lights'))
def test_missing_native_rig_parts_reject(missing):
    pytest.importorskip('pxr.Usd')
    s,root=make_stage('robodojo');s.RemovePrim(root+('/Room'if missing=='background'else'/Dome'))
    with pytest.raises(ValueError):apply_native_environment(s,root,spec(),material)
