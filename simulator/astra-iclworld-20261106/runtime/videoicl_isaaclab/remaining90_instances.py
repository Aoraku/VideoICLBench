"""Explicit campaign-only physical instances; source R and scoring stay intact.

Metric descriptions transform with visual/collision geometry. These are newly
parameterized source instances, not new scans and not native acceptance proof.
"""
from copy import deepcopy
import hashlib
import json
import math

REVISION='remaining90-instances-v1-20261105'
SCALES={'E03':(1.04,1.04,1.04),'E19':(1.04,1.04,1.),
        'E23':(1.04,1.04,1.),'E24':(.94,.94,.94),'E43':(.94,.94,.94)}
SPOOL_SHA={'red':'80778b1463a8edb0d027a446bd65d9105bfed0b03b8678c63c78933cb80dffa0',
 'blue':'ba25dfbafee14672c6d4ad010fe564ddb76b39f948f5d9d17ef19588aebc0f0a',
 'green':'337c0e8b42e7094366bfee7f30d9feb0a514d24e9a649f8293c27aaba2305429'}
POINT_FIELDS=('grasp_point_local','grasp_point','working_point','local_bounds_center')


def vec(point,scale):
    if len(point)!=3 or not all(math.isfinite(x)for x in point):raise ValueError('finite local3 required')
    return [float(x*s)for x,s in zip(point,scale)]


def scale_actor(obj,scale):
    if obj.get('collision_shapes'):raise ValueError('Explicit collision parts need own adaptation')
    if not obj.get('source_asset'):raise ValueError('Reviewed source asset required')
    before=deepcopy(obj['size']);obj['size']=vec(before,scale)
    volume=math.prod(scale)
    for key in ('mass','physical_mass_kg'):
        if key in obj:obj[key]*=volume
    for key in POINT_FIELDS:
        if key in obj:obj[key]=vec(obj[key],scale)
    if 'sphere_radius'in obj:
        if max(scale)-min(scale)>1e-9:raise ValueError('Sphere requires uniform scale')
        obj['sphere_radius']*=scale[0]
    if 'hole_radius'in obj:
        if abs(scale[0]-scale[1])>1e-9:raise ValueError('Circular bore requires equal XY scale')
        obj['hole_radius']*=scale[0]
    if 'source_containment_hull'in obj:
        hull=obj['source_containment_hull']
        if hull['descriptor_half_size']!=before:raise ValueError('Canonical hull size mismatch')
        hull['vertices_local']=[vec(p,scale)for p in hull['vertices_local']]
        hull['descriptor_half_size']=deepcopy(obj['size'])
        hull['instance_derivation']=dict(campaign_revision=REVISION,scale=list(scale))
    if max(scale)-min(scale)>1e-9:
        obj['source_asset']=deepcopy(obj['source_asset'])
        obj['source_asset']['allow_nonuniform_scale']=True
        obj['source_asset']['instance_scale_adaptation']=dict(revision=REVISION,scale=list(scale),
          visual_collision_and_metric_descriptors_scaled_together=True)
    obj['execution_instance']=dict(kind='campaign_parameterized_dimension_variant',revision=REVISION,
      scale=list(scale),canonical_size=before,actual_size=deepcopy(obj['size']),
      source_sha256=obj['source_asset']['sha256'],native_acceptance='pending')
    return dict(object=obj['id'],scale=list(scale),canonical_size=before,actual_size=deepcopy(obj['size']))


def apply(spec,marker):
    if not isinstance(marker,dict)or marker.get('revision')!=REVISION:raise ValueError('Explicit campaign instance revision required')
    task=spec['id']
    if task not in marker.get('tasks',[]):return None
    if spec['execution_design']['condition']!='I'or spec['seed']!=4201:raise ValueError('Campaign instances only I/4201')
    before_goals=deepcopy(spec['goals']);before_mode=spec['semantic']['mode'];sem=spec['semantic']
    objects={o['id']:o for o in spec['objects']};rows=[]
    if task in SCALES:
        scale=SCALES[task]
        names=(sem['groups']['cups']if task in('E03','E23','E24')else
               sem['groups']['caps']+sem['groups']['bottles']if task=='E19'else sem['groups']['balls'])
        for name in names:
            obj=objects[name];rows.append(scale_actor(obj,scale))
            grasp=sem.get('structural_grasps',{}).get(name)
            if grasp and 'local'in grasp:grasp['local']=vec(grasp['local'],scale)
            cup=sem.get('cups',{}).get(name)
            if cup:
                for key in ('bottom_local','rim_local'):cup[key]=vec(cup[key],scale)
                for key in ('inner_profile','outer_profile'):
                    cup[key]=[[float(h*scale[2]),float(r*scale[0])]for h,r in cup[key]]
            for table in ('mouths','caps'):
                metric=sem.get(table,{}).get(name)
                if metric:
                    metric['center_local']=vec(metric['center_local'],scale)
                    for key in ('inner_radius','outer_radius'):
                        if key in metric:metric[key]*=scale[0]
                    if 'depth'in metric:metric['depth']*=scale[2]
        # Initial xy/yaw/bottom remain fixed: the bottom support plane is not
        # raised when a sphere shrinks or when cup height changes.
    elif task=='E10':
        for color,sha in SPOOL_SHA.items():
            name=color+'_circle';obj=objects[name]
            if obj.get('reviewed_e10_extruded_collision'):raise ValueError('Unexpected circle collision override')
            before=deepcopy(obj['source_asset'])
            obj['source_asset']=dict(root_env='VIC_INFERENCE_ASSETS',relative_path='g1/E38/'+color+'.usda',
              sha256=sha,dependencies=[],source_rotation=[1,0,0,0])
            obj['size']=[.01999999317560597,.01999999600011981,.003]
            obj['hole_radius']=.0048
            sem['structural_grasps'][name]['local']=[.014,0.,0.]
            obj['execution_instance']=dict(kind='existing_same_category_source_instance',revision=REVISION,
              source_task='E38',source_sha256=sha,source_ring_hole_radius=.0048,native_acceptance='pending')
            rows.append(dict(object=name,old_source=before,new_source=deepcopy(obj['source_asset']),
              metric_grasp_local=[.014,0.,0.],hole_radius=.0048,unchanged_E10_holes=deepcopy(sem['holes'][name])))
    elif task=='E26':
        from .remaining90_e26_instance import apply as apply_e26
        rows=apply_e26(spec)
    else:raise ValueError('Unimplemented explicit campaign instance '+task)
    if spec['goals']!=before_goals or sem['mode']!=before_mode:raise ValueError('Instance adapter changed rule/goal')
    from .execution_design_inputs_v3 import physical_input_signature
    receipt=dict(revision=REVISION,task=task,objects=rows,native_acceptance='pending',
      scoring_rule_and_goals_unchanged=True,source_meshes_not_new_scans=True)
    spec['remaining90_instance']=receipt
    spec['execution_design']['paired_physical_input_sha256']=physical_input_signature(spec)
    spec['execution_design'].setdefault('applied_input_changes',{}).setdefault('operations',[]).append(receipt)
    return receipt
