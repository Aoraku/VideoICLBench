"""Build benchmark infrastructure from the selected embodiment's layout data."""
import math,os
from contextlib import contextmanager
from pathlib import Path
from pxr import Gf,UsdGeom,UsdShade,UsdPhysics,UsdLux
import isaaclab.sim as sim


@contextmanager
def visible_rooms_render(stage, room_roots, selected_roots):
    """Expose one room's graphics/lights while leaving PhysX state untouched.

    Legacy RTX does not reliably honor all USD light-link collections. Hiding
    foreign geometry also excludes their large overlapping ground meshes.
    Restore exact authored render opinions even if camera readback fails.
    """
    from pxr import Usd
    selected_roots = set(selected_roots)
    if not selected_roots or not selected_roots.issubset(room_roots):
        raise ValueError('Render target is not a registered room root')
    restore = []
    try:
        for root in room_roots:
            prim = stage.GetPrimAtPath(root)
            if not prim.IsValid():raise ValueError('Render room root is absent: '+root)
            visibility = UsdGeom.Imageable(prim).GetVisibilityAttr()
            restore.append((visibility, visibility.HasAuthoredValueOpinion(), visibility.Get()))
            visibility.Set('inherited' if root in selected_roots else 'invisible')
            if root not in selected_roots:
                for child in Usd.PrimRange(prim):
                    if child.HasAPI(UsdLux.LightAPI):
                        intensity = UsdLux.LightAPI(child).GetIntensityAttr()
                        restore.append((intensity, intensity.HasAuthoredValueOpinion(), intensity.Get()))
                        intensity.Set(0.)
        yield
    finally:
        for attr, authored, value in reversed(restore):
            if authored:attr.Set(value)
            else:attr.Clear()


@contextmanager
def isolated_room_render(stage, room_roots, selected_root):
    with visible_rooms_render(stage, room_roots, [selected_root]):
        yield


def link_room_lights(stage, room_root):
    """Author USD light/shadow links for one namespaced room.

    This is a renderer input, not a claim that RTX image parity is verified.
    A native standalone-versus-pool camera comparison must accept it first.
    """
    from pxr import Sdf, Usd
    linked = []
    for prim in Usd.PrimRange(stage.GetPrimAtPath(room_root)):
        if not prim.HasAPI(UsdLux.LightAPI):
            continue
        light = UsdLux.LightAPI(prim)
        for collection in (light.GetLightLinkCollectionAPI(), light.GetShadowLinkCollectionAPI()):
            collection.CreateIncludeRootAttr().Set(False)
            collection.CreateExpansionRuleAttr().Set('expandPrims')
            collection.CreateIncludesRel().SetTargets([Sdf.Path(room_root)])
        linked.append(str(prim.GetPath()))
    return linked


def spawn_reference_rig(stage,profile,geometry,material,transform,root_path='/World'):
    """Spawn infrastructure below an identity or caller-translated rig root."""
    def path(suffix):return root_path+suffix
    c=profile.config['layout'];table=c['table'];background=c['background']
    if c['kind']=='robodojo':
        root=os.environ.get(background['assets_env'])
        if not root:root=str(Path(profile.asset_path()).parents[2])
        assets=Path(root)
        for key in ('room','stand','hdr','table_mdl'):
            if not (assets/background[key]).is_file():raise FileNotFoundError(assets/background[key])
        room=sim.UsdFileCfg(usd_path=str(assets/background['room']),scale=tuple(background['room_scale']))
        room.func(path('/Room'),room)
        stand=sim.UsdFileCfg(usd_path=str(assets/background['stand']))
        stand.func(path('/CameraStand'),stand,translation=tuple(background['stand_position']),orientation=tuple(background['stand_rotation']))
        from omni.kit import commands
        commands.execute('CreateMeshPrimCommand',prim_type='Cube',prim_path=path('/Table'),u_patches=10,v_patches=10,w_patches=10)
        prim=stage.GetPrimAtPath(path('/Table'));transform(prim,table['position'],scale=table['size'])
        UsdPhysics.CollisionAPI.Apply(prim)
        mdl=sim.MdlFileCfg(mdl_path=str(assets/background['table_mdl']))
        mdl.func(path('/Materials/Table'),mdl)
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(UsdShade.Material(stage.GetPrimAtPath(path('/Materials/Table'))))
        dome=sim.DomeLightCfg(intensity=background['intensity'],texture_file=str(assets/background['hdr']))
        dome.func(path('/Dome'),dome)
    elif c['kind']=='robotwin':
        # Recreate create_table/create_box geometry and clean-scene light poses.
        neutral=material(stage,path('/Materials/Table'),background['table_color'],.5)
        wall=material(stage,path('/Materials/Wall'),background['wall_color'],.5)
        ground=material(stage,path('/Materials/Ground'),(.5,.5,.5),.5)
        geometry(stage,path('/Ground'),dict(type='box',size=[100,100,.05],pos=[0,0,-.05]),ground)
        geometry(stage,path('/Wall'),dict(type='box',size=background['wall_half_size'],pos=background['wall_position']),wall)
        geometry(stage,path('/Table'),dict(type='box',size=[x/2 for x in table['size']],pos=table['position']),neutral)
        # RoboTwin legs: spacing .1, center table_top - height/2 - .002.
        height=table['top'];thickness=table['size'][2]
        for i,(sx,sy) in enumerate([(-1,-1),(-1,1),(1,-1),(1,1)]):
            position=[sx*(table['size'][0]/2-.05),sy*(table['size'][1]/2-.05),height/2-.002]
            geometry(stage,f'{root_path}/TableLeg{i}',dict(type='box',size=[thickness/2,thickness/2,height/2-.002],pos=position),neutral)
        dome=sim.DomeLightCfg(intensity=450,color=tuple(background['ambient_color']))
        dome.func(path('/Dome'),dome)
        import torch
        from isaaclab.utils.math import quat_from_matrix
        for i,light in enumerate(background['directional_lights']):
            direction=torch.tensor(light['direction'],dtype=torch.float64);direction/=direction.norm()
            up=torch.tensor([0.,1.,0.],dtype=torch.float64)
            right=torch.linalg.cross(direction,up);right/=right.norm();up=torch.linalg.cross(right,direction)
            quat=quat_from_matrix(torch.stack((right,up,-direction),dim=1)).tolist()
            cfg=sim.DistantLightCfg(intensity=900,color=tuple(light['color']))
            cfg.func(f'{root_path}/Directional{i}',cfg,orientation=tuple(quat))
        for i,light in enumerate(background['point_lights']):
            prim=UsdLux.SphereLight.Define(stage,f'{root_path}/Point{i}')
            prim.CreateRadiusAttr(.02);prim.CreateIntensityAttr(250)
            prim.CreateColorAttr(Gf.Vec3f(*light['color']));transform(prim.GetPrim(),light['position'])
    else:raise ValueError('Unsupported layout kind: '+c['kind'])
    physical=UsdShade.Material.Define(stage,path('/Materials/TableFriction'))
    api=UsdPhysics.MaterialAPI.Apply(physical.GetPrim())
    api.CreateStaticFrictionAttr(table['static_friction']);api.CreateDynamicFrictionAttr(table['dynamic_friction'])
    api.CreateRestitutionAttr(table['restitution'])
    UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(path('/Table'))).Bind(physical,UsdShade.Tokens.weakerThanDescendants,'physics')
