"""Explicit same-category dimensional instances for the revised back half.

These are parameterized instances of reviewed source meshes, not independent
scanned assets. Visual and collision scale share the existing source spawner;
all metric grasp/semantic points are scaled with the actual object geometry.
No instance substitutions apply to fixed R inputs or R/E-only tasks.
"""
from copy import deepcopy
import hashlib
import json

GROUPS={
    'E27':('fork','spoon'), 'E28':('rectangle_food','round_food'),
    'E31':('plate','bowl'), 'E32':('sprite_bottle','cola_bottle','pink_cube'),
    'E33':('sprite','water','coca_cola','pepsi','fanta'),
    'E34':('knife','spoon','fork'), 'E36':('red','pink','lightpink','blue'),
    'E38':('red','green','blue'), 'E42':('pink_ball','red_ball'),
    'E45':('dark_green','red','light_green'), 'E46':('yellow_block',),
}
POINT_FIELDS=('grasp_point_local','grasp_point','working_point','local_bounds_center')


def apply_instance_variation(spec,seed):
    task=spec['id']
    if task not in GROUPS:return None
    # Preserve a ring's insertion clearance by enlarging it, not shrinking the
    # hole. Bowls and plates share one scale to preserve their relative fit.
    factor=((1.04,1.07,1.10) if task=='E38' else (.90,.94,.98))[seed%3]
    objects={o['id']:o for o in spec['objects']};sem=spec['semantic'];rows=[]
    for name in GROUPS[task]:
        obj=objects[name]
        if obj.get('kind') not in ('source_mesh','sphere') or not obj.get('source_asset'):
            raise ValueError('Reviewed source mesh required for instance variation: '+name)
        if obj.get('collision_shapes'):
            raise ValueError('Explicit collision parts require their own metric conversion: '+name)
        before=deepcopy(obj['size']);obj['size']=[float(x*factor) for x in before]
        obj['mass']*=factor**3
        if 'physical_mass_kg' in obj:obj['physical_mass_kg']*=factor**3
        for key in POINT_FIELDS:
            if key in obj:obj[key]=[float(x*factor) for x in obj[key]]
        if 'hole_radius' in obj:obj['hole_radius']*=factor
        if 'sphere_radius' in obj:obj['sphere_radius']*=factor
        if 'source_containment_hull' in obj:
            hull=obj['source_containment_hull']
            if hull['descriptor_half_size']!=before:
                raise ValueError('Containment hull does not match canonical instance: '+name)
            canonical=hashlib.sha256(json.dumps(hull,sort_keys=True).encode()).hexdigest()
            hull['vertices_local']=[[float(x*factor)for x in point]for point in hull['vertices_local']]
            hull['descriptor_half_size']=deepcopy(obj['size'])
            hull['instance_derivation']=dict(canonical_geometry_sha256=canonical,uniform_scale=factor,
                scaled_hull_sha256=hashlib.sha256(json.dumps(hull['vertices_local'],separators=(',',':')).encode()).hexdigest())
        for key in ('handle_points','start_points','end_points'):
            if name in sem.get(key,{}):sem[key][name]=[float(x*factor) for x in sem[key][name]]
        grasp=sem.get('cargo_grasps',{}).get(name)
        if grasp is not None and 'local' in grasp:
            grasp['local']=[float(x*factor) for x in grasp['local']]
        obj['execution_instance']=dict(kind='uniform_dimension_variant',scale=factor,
            canonical_source_sha256=obj['source_asset']['sha256'],canonical_size=before,
            actual_size=deepcopy(obj['size']),category=obj.get('semantic_identity',obj.get('identity',name)))
        rows.append(dict(object=name,scale=factor,canonical_size=before,actual_size=obj['size']))
    if task=='E31':
        support=objects[sem['support']]
        for zone in spec['zones']:
            if zone['id']=='support_center':
                zone['surface_z']=support['bottom']+2*support['size'][2]
    return dict(kind='same_category_parameterized_mesh_instances',objects=rows,
        provenance='reviewed_source_mesh_uniform_scaling',native_acceptance='pending')
