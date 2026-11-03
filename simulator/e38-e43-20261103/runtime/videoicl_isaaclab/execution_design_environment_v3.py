"""Visual-only second-half E authoring on existing rig geometry and USD lights."""
import hashlib
import json
import math

SCHEMA='execution-environment-half26-50-v3'
REVISION='embodied50-execution-v3-20261102'
TASKS=frozenset(f'E{i:02}'for i in range(26,51)if i!=39)


def environment_settings(task,condition):
    if task not in TASKS or condition!='E':return None
    return dict(schema=SCHEMA,background_color=[.43,.46,.49],background_roughness=.85,
                light_intensity_scale=.85,light_color_preserved=True)


def _physical_snapshot(root,Usd):
    rows=[]
    for prim in Usd.PrimRange(root):
        # Transform/geometry/physical material/contact attributes and physical
        # material binding targets are invariant. Rendering shader attrs excluded.
        attrs={}
        for attr in prim.GetAttributes():
            n=attr.GetName()
            if (n.startswith(('physics:','physx','xformOp:')) or n in
                    ('xformOpOrder','points','faceVertexCounts','faceVertexIndices','extent','size','radius','height','axis')):
                attrs[n]=str(attr.Get())
        rels={r.GetName():[str(p)for p in r.GetTargets()]for r in prim.GetRelationships()
              if 'physics' in r.GetName().lower()}
        if attrs or rels:rows.append([str(prim.GetPath()),attrs,rels])
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def apply_native_environment(stage,rig_root,spec,material_factory):
    """Only fresh initialization; no geometry, collision or task material writes."""
    config=spec.get('execution_environment')
    if config is None:return None
    d=spec.get('execution_design',{})
    if spec.get('id') not in TASKS or d.get('revision')!=REVISION or d.get('condition')!='E':
        raise ValueError('Environment override requires explicit second-half v3 E')
    if config!=environment_settings(spec['id'],'E'):
        raise ValueError('Environment settings must match the reviewed visual-only contract')
    from pxr import Usd,UsdGeom,UsdLux,UsdShade
    root=stage.GetPrimAtPath(rig_root)
    if not root.IsValid():raise ValueError('Native rig root missing')
    marker=stage.GetPrimAtPath(rig_root+'/Materials/ExecutionBackgroundV3')
    if marker.IsValid():raise ValueError('Environment already authored; cannot reapply to live world')
    background=None
    for name in ('Wall','Room'):
        p=stage.GetPrimAtPath(rig_root+'/'+name)
        if p.IsValid():background=p;break
    if background is None:raise ValueError('Native Wall/Room background missing')
    geometry=[p for p in Usd.PrimRange(background)if p.IsA(UsdGeom.Gprim)]
    if not geometry:raise ValueError('Existing background has no renderable native geometry')
    lights=[]
    for p in Usd.PrimRange(root):
        if p.HasAPI(UsdLux.LightAPI):
            api=UsdLux.LightAPI(p);value=api.GetIntensityAttr().Get()
            if value is None or not math.isfinite(float(value))or float(value)<=0:
                raise ValueError('Native light needs finite positive baseline intensity: '+str(p.GetPath()))
            lights.append((p,api,float(value)))
    if not lights:raise ValueError('No native USD rig lights')
    before=_physical_snapshot(root,Usd)
    mat=material_factory(stage,rig_root+'/Materials/ExecutionBackgroundV3',
                         config['background_color'],config['background_roughness'])
    shader=UsdShade.Shader(stage.GetPrimAtPath(str(mat.GetPath())+'/Surface'))
    actual_color=list(shader.GetInput('diffuseColor').Get())
    actual_roughness=float(shader.GetInput('roughness').Get())
    if (any(not math.isclose(a,b,rel_tol=1e-6) for a,b in zip(actual_color,config['background_color']))
            or not math.isclose(actual_roughness,config['background_roughness'],rel_tol=1e-6)):
        raise RuntimeError('Background shader color/roughness readback mismatch')
    # Bind actual existing mesh descendants so Room references cannot keep
    # an authored child material stronger than a parent override.
    bindings=[]
    for p in geometry:
        UsdShade.MaterialBindingAPI.Apply(p).Bind(mat,UsdShade.Tokens.strongerThanDescendants)
        actual=UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
        if str(actual.GetPath())!=str(mat.GetPath()):raise RuntimeError('Background material readback mismatch')
        bindings.append(dict(prim=str(p.GetPath()),material=str(actual.GetPath())))
    light_rows=[]
    for p,api,value in lights:
        color=api.GetColorAttr().Get();api.GetIntensityAttr().Set(value*config['light_intensity_scale'])
        actual=float(api.GetIntensityAttr().Get())
        if not math.isclose(actual,value*.85,rel_tol=1e-6):raise RuntimeError('Light intensity readback mismatch')
        if api.GetColorAttr().Get()!=color:raise RuntimeError('Rule-color light spectrum changed')
        light_rows.append(dict(prim=str(p.GetPath()),intensity_before=value,intensity_after=actual,
            color=list(color)if color is not None else None))
    after=_physical_snapshot(root,Usd)
    if before!=after:raise RuntimeError('Visual environment unexpectedly changed physical rig')
    return dict(schema=SCHEMA,background_bindings=bindings,lights=light_rows,
        background_color_readback=actual_color,background_roughness_readback=actual_roughness,
        physical_before_sha256=before,physical_after_sha256=after,
        usd_readback_verified=True,render_visibility_review='pending',
        rule_color_readability_review='pending',native_physics_validated=False)
