"""Source-bound CPU convex fidelity for the four original 350um card meshes."""
import copy
import math

TASKS=frozenset(('E47','E48','E49','E50'))
SOURCES={
 'card_H_2.usda':'e6d4c721b74a3b6f3d273c987d06698c3b4f162de30189554de47ddee51b3f81',
 'card_S_2.usda':'6d421066b8c2ecfc51432478ff6cca05b07a3807c1ac22cc6d8ded18ac4f9a2c',
 'card_D_3.usda':'1334a3240acfd3e0843bb4778419adc11128d6733cf5278bdb54134ad4ba770c',
 'card_C_3.usda':'e7e6ec6c5aaf72a7b8327d652c322117cf6ab992df21fcb9fd5fa47a552cf17c'}


def settings_for(obj,coordinate_factor=None):
    source=obj.get('source_asset',{})
    if (source.get('root_env')!='VIC_FULL50_RIGID_ASSETS' or
            SOURCES.get(source.get('relative_path'))!=source.get('sha256')):
        raise ValueError('Original SHA-pinned thin card source required')
    marker=obj.get('engineering_practical_card',{})
    practical=(marker.get('schema')=='engineering-practical-card-1mm-v1'
               and marker.get('approximate_thickness_m')==.001
               and marker.get('source_exact_geometry')is False)
    half_thickness=.0005 if practical else .000175
    if not all(math.isclose(a,b,rel_tol=0,abs_tol=1e-12)for a,b in zip(obj['size'],[.04415271966527,.0315,half_thickness])):
        raise ValueError('Original 350um card geometry required')
    settings=dict(source_sha256=source['sha256'],approximation='convexHull',
        hull_vertex_limit=255,min_thickness_m=2*obj['size'][2]*.1)
    if coordinate_factor is not None:
        if coordinate_factor!=100:raise ValueError('Explicit 100x thin cooking numerical coordinates required')
        settings['coordinate_factor']=100
    return settings


def configure_spec(spec,coordinate_factor=None):
    if spec.get('id')not in TASKS:raise ValueError('Explicit thin-card task scope required')
    changed=[]
    for obj in spec['objects']:
        if obj.get('source_asset',{}).get('relative_path')not in SOURCES:continue
        if obj.get('reviewed_collision_settings'):raise ValueError('Existing source cooking settings require separate review')
        settings=settings_for(obj,coordinate_factor);obj['reviewed_collision_settings']=settings;changed.append(obj['id'])
    if not changed:raise ValueError('No original thin cards in explicit task')
    return changed


def verify_only_cooking_change(old,new):
    """Allow only the exact source-bound cooking adapter; retain every other key."""
    if old.get('id')not in TASKS or old.get('id')!=new.get('id'):
        raise ValueError('Thin cooking migration task scope mismatch')
    factors={o.get('reviewed_collision_settings',{}).get('coordinate_factor')for o in new.get('objects',[])if o.get('source_asset',{}).get('relative_path')in SOURCES}
    if len(factors)!=1:raise ValueError('Uniform explicit thin cooking coordinate scope required')
    expected=copy.deepcopy(old);changed=configure_spec(expected,next(iter(factors)))
    from .engineering_checkpoint import PHYSICAL_KEYS
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):
        raise ValueError('Migration changed physical input beyond reviewed thin cooking fields')
    return changed
