"""Execute production spawn dispatch against recorded API calls, not PhysX.

This protects opt-in dynamic assets without asserting collision cooking or
grasp feasibility. Those require the native GPU acceptance route.
"""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoicl_isaaclab import mechanical_asset_adapters


class Prim:
    def __init__(self, path, *, collision=False, mesh=False):
        self.path, self.collision, self.mesh = path, collision, mesh

    def HasAPI(self, api):
        return self.collision and api.name == 'CollisionAPI'

    def IsA(self, schema):
        return self.mesh and schema == 'mesh'


def actual_spawn(monkeypatch):
    calls = {}

    class Api:
        def __init__(self, name):self.name=name
        def __call__(self, prim):return self.Apply(prim)
        def Apply(self, prim):
            family=self.name
            class Applied:
                def __getattr__(self, attr):
                    def record(*values):calls[(family,prim.path,attr)]=values[0] if len(values)==1 else values
                    return record
            return Applied()

    root=Prim('/World/Props/stand')
    parts=[root,*[Prim(root.path+'/collision_'+str(i),collision=True,mesh=True) for i in range(7)]]
    monkeypatch.setattr(mechanical_asset_adapters,'spawn_mechanical_asset',lambda *args,**kwargs:dict(root=root))
    physics=SimpleNamespace(**{n:Api(n) for n in ('RigidBodyAPI','MassAPI','CollisionAPI','MeshCollisionAPI','MaterialAPI')})
    physx=SimpleNamespace(**{n:Api(n) for n in ('PhysxRigidBodyAPI','PhysxContactReportAPI','PhysxCollisionAPI')})
    def define(stage,path):return SimpleNamespace(GetPrim=lambda:Prim(path))
    shade=SimpleNamespace(Material=SimpleNamespace(Define=define),MaterialBindingAPI=Api('MaterialBindingAPI'),
                          Tokens=SimpleNamespace(strongerThanDescendants='strong',weakerThanDescendants='weak'))
    ns=dict(__package__='videoicl_isaaclab',math=math,UsdPhysics=physics,PhysxSchema=physx,UsdShade=shade,
            Usd=SimpleNamespace(PrimRange=lambda _:parts),UsdGeom=SimpleNamespace(Mesh='mesh',Xform=SimpleNamespace(Define=define)),
            omni=SimpleNamespace(usd=SimpleNamespace(get_context=lambda:SimpleNamespace(get_stage=lambda:object()))),
            enable_continuous_prop_contacts=lambda _:None,transform=lambda *args:None,
            style=SimpleNamespace(linear=lambda x:x,color=lambda x:x),material=lambda *args:None,
            geometry=lambda stage,path,*args:Prim(path))
    source=Path(__file__).parents[1]/'videoicl_isaaclab/scene.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='spawn_prop')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
    return ns['spawn_prop'],calls,root


def mechanical_recipe(**extra):
    return dict(role='movable',mass=.45,mechanical_asset=dict(kind='static_mesh',joint_count=0),**extra)


def test_dynamic_mechanical_prop_uses_gravity_and_separate_convex_colliders(monkeypatch):
    spawn,calls,root=actual_spawn(monkeypatch)
    spawn(root.path,SimpleNamespace(recipe=mechanical_recipe(dynamic_mechanical_asset=True)))
    assert calls['RigidBodyAPI',root.path,'CreateKinematicEnabledAttr'] is False
    assert calls['PhysxRigidBodyAPI',root.path,'CreateDisableGravityAttr'] is False
    assert calls['MassAPI',root.path,'CreateMassAttr']==.45
    hulls={key:value for key,value in calls.items() if key[0]=='MeshCollisionAPI'}
    assert len(hulls)==7 and set(hulls.values())=={'convexHull'}
    assert calls['PhysxRigidBodyAPI',root.path,'CreateEnableCCDAttr'] is True
    bindings={key:value for key,value in calls.items() if key[0]=='MaterialBindingAPI'}
    assert len(bindings)==7 and all(v[-1]=='physics' for v in bindings.values())


def test_legacy_static_mechanical_prop_stays_kinematic(monkeypatch):
    spawn,calls,root=actual_spawn(monkeypatch)
    spawn(root.path,SimpleNamespace(recipe=mechanical_recipe()))
    assert calls['RigidBodyAPI',root.path,'CreateKinematicEnabledAttr'] is True
    assert calls['PhysxRigidBodyAPI',root.path,'CreateDisableGravityAttr'] is True
    assert not any(key[0]=='MeshCollisionAPI' for key in calls)
    assert not any(key[0]=='MaterialBindingAPI' for key in calls)


@pytest.mark.parametrize('patch',[dict(dynamic_mechanical_asset=1),dict(role='fixture'),dict(mechanical_asset=dict(kind='static_mesh',joint_count=1))])
def test_dynamic_mechanical_asset_rejects_ambiguous_or_jointed_recipe(monkeypatch,patch):
    spawn,calls,root=actual_spawn(monkeypatch)
    recipe=mechanical_recipe(dynamic_mechanical_asset=True);recipe.update(patch)
    with pytest.raises(ValueError):spawn(root.path,SimpleNamespace(recipe=recipe))
    assert not calls


def test_explicit_new_mass_and_legacy_density_stay_separate(monkeypatch):
    from videoicl_isaaclab.task_recipes import prop
    for explicit in (False,True):
        spawn,calls,root=actual_spawn(monkeypatch)
        recipe=prop('lid','box',[.128,.178,.003],[0,0],mass=.06)
        if explicit:recipe['physical_mass_kg']=.06
        spawn(root.path,SimpleNamespace(recipe=recipe))
        mass_calls={k[-1]:v for k,v in calls.items() if k[0]=='MassAPI'}
        # Positive authored mass overrides density under USD mass precedence.
        if explicit:assert mass_calls['CreateMassAttr']==.06
        else:assert mass_calls=={'CreateDensityAttr':450.}


@pytest.mark.parametrize('mass',[True,0,-1,float('nan'),float('inf'),'0.06'])
def test_invalid_explicit_new_mass_is_not_authored(monkeypatch,mass):
    from videoicl_isaaclab.task_recipes import prop
    spawn,calls,root=actual_spawn(monkeypatch)
    recipe=prop('lid','box',[.128,.178,.003],[0,0],physical_mass_kg=mass)
    with pytest.raises(ValueError):spawn(root.path,SimpleNamespace(recipe=recipe))
    assert not any(k[0]=='MassAPI' and k[-1]=='CreateMassAttr' for k in calls)
