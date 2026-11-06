"""Validate reviewed source-asset recipes for further RealWorld50 tasks.

Every recipe must contain three explicitly authored variants. This module does
not invent missing assets, layouts, task goals, or native evidence adapters.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .realworld_contracts import metadata, public_assignment, provenance, VARIANTS
from .source_assets import resolve_asset
from .inference_generalization import public_instruction


def load_reviewed_recipe(task, variant, seed, bindings_path, *, verify_files=True):
    from .realworld_scenes import _vector, _asset_record
    item = metadata(task)
    path = Path(bindings_path)
    raw = path.read_bytes()
    binding = json.loads(raw).get('tasks', {}).get(task)
    if not isinstance(binding, dict) or binding.get('scene_adapter') != 'full50-source-v1':
        raise NotImplementedError(f'{task}: reviewed native scene recipe unavailable')
    if variant not in VARIANTS or type(seed) is not int or seed < 0 or type(verify_files) is not bool:
        raise ValueError('Invalid native recipe variant, seed, or verification flag')
    if set(binding.get('variants', {})) != set(VARIANTS):
        raise ValueError('A source recipe must explicitly define all three variants')
    selected = binding['variants'][variant]
    if not isinstance(binding.get('objects'), dict) or (not binding['objects'] and not binding.get('mechanisms')):
        raise ValueError('A source recipe requires real source objects')
    if not isinstance(selected.get('semantic'), dict) or not selected['semantic'].get('mode'):
        raise ValueError('A recipe needs a native semantic observation adapter')
    overrides = selected.get('object_overrides', {})
    if set(overrides) - set(binding['objects']):
        raise ValueError('Variant references an absent source object')
    objects = []
    for name, declared in binding['objects'].items():
        if not isinstance(name, str) or not name.isidentifier() or not isinstance(declared, dict):
            raise ValueError('Invalid source object ID or declaration')
        obj = deepcopy(declared)
        change = overrides.get(name, {})
        if set(change) - {'xy','yaw','bottom','center_z','quaternion'}:
            raise ValueError('A variant may change initial pose, never source identity or geometry')
        obj.update(change)
        source_record=obj.get('source_asset') or obj.get('mechanical_asset')
        if bool(obj.get('source_asset'))==bool(obj.get('mechanical_asset')):
            raise ValueError('Exactly one source or mechanical asset is required')
        if obj.get('mechanical_asset') and obj['mechanical_asset'].get('kind')!='static_mesh':
            raise ValueError('Joint assets belong to the separate mechanisms section')
        _asset_record(source_record)
        if verify_files:
            resolve_asset(source_record)
        obj.update(id=name)
        obj.setdefault('identity', name)
        obj.setdefault('role', 'movable')
        if obj.get('mechanical_asset') and obj['role']!='fixture':
            raise ValueError('Static mechanical mesh must be an explicit fixture')
        obj.setdefault('kind', 'source_mesh')
        obj.setdefault('collision_shapes', [])
        obj.setdefault('rgba', [.7,.7,.7,1.])
        obj.setdefault('yaw', 0.)
        obj.setdefault('bottom', .802)
        obj['size'] = _vector(obj.get('size'),3,name+' half extents',positive=True)
        obj['xy'] = _vector(obj.get('xy'),2,name+' initial XY')
        obj['rgba'] = _vector(obj['rgba'],4,name+' RGBA')
        for key in ('yaw','bottom','mass','center_z'):
            if key in obj and (type(obj[key]) not in (int,float) or not math.isfinite(obj[key])):
                raise ValueError(f'Invalid {name} {key}')
        if 'quaternion' in obj:
            q = _vector(obj['quaternion'],4,name+' orientation')
            if not math.isclose(sum(v*v for v in q),1.,abs_tol=1e-5):
                raise ValueError('Object quaternion must be normalized')
            w,x,y,z = q
            vertical = [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]
            obj.setdefault('center_z',obj['bottom']+sum(abs(a)*b for a,b in zip(vertical,obj['size'])))
        objects.append(obj)
    if len({o['identity'] for o in objects}) != len(objects):
        raise ValueError('Native object identities must be unique')
    zones = deepcopy(selected.get('zones', []))
    zone_ids = set()
    for zone in zones:
        if not zone.get('id') or zone['id'] in zone_ids:
            raise ValueError('Missing or duplicate region identity')
        zone_ids.add(zone['id'])
        zone['xy'] = _vector(zone['xy'],2,'region XY')
        zone['half_size'] = _vector(zone['half_size'],2,'region extents',positive=True)
        zone.setdefault('surface_z',.8)
        zone.setdefault('rgba',[.95,.95,.95,1.])
        if zone.get('shape') in ('circle','triangle','square','cross'):
            zone.setdefault('marker',{'circle':0,'triangle':1,'square':2,'cross':3}[zone['shape']])
    goals = deepcopy(selected.get('goals', []))
    for goal in goals:
        if goal.get('object') not in binding['objects'] or goal.get('target') not in zone_ids:
            raise ValueError('Expert goal references a missing source object or region')
    joints = deepcopy(binding.get('joints', []))
    for joint in joints:
        if joint.get('child') not in binding['objects'] or (joint.get('parent') and joint['parent'] not in binding['objects']):
            raise ValueError('Joint references an absent source part')
    mechanisms=deepcopy(binding.get('mechanisms',[]))
    for mechanism in mechanisms:
        if not mechanism.get('id') or not mechanism['id'].isidentifier() or mechanism['id'] in binding['objects']:
            raise ValueError('Invalid or duplicate native mechanism identity')
        record=mechanism['mechanical_asset'];_asset_record(record)
        if verify_files:resolve_asset(record)
        mechanism['position']=_vector(mechanism['position'],3,'mechanism initial position')
    return dict(id=task,variant=variant,seed=seed,title=item['title'],instruction=public_instruction(binding,public_assignment(task)),
                **({'inference_generalization':deepcopy(binding['inference_generalization'])} if 'inference_generalization' in binding else {}),
                provenance=provenance(task,variant),objects=objects,zones=zones,fixtures=[],joints=joints,mechanisms=mechanisms,
                goals=goals,semantic=deepcopy(selected['semantic']),
                embodiment=binding.get('embodiment','franka'),
                head_view=deepcopy(binding.get('head_view',dict(eye_task=[-.60,0.,1.75],target_task=[0.,0.,.83],profile='realworld-operator-v2'))),
                task_adapter='full50-source-v1',expert_action_budget=binding.get('expert_action_budget',2400),
                expert_loaded_step_mm=float(binding.get('expert_loaded_step_mm',8.)),
                expert_preserve_goal_order=bool(binding.get('expert_preserve_goal_order',False)),
                expert_arm=selected.get('expert_arm',binding.get('expert_arm','right')),
                source_binding_sha256=hashlib.sha256(raw).hexdigest(),source_binding_file=str(path.resolve()),
                source_task_binding_sha256=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                asset_fidelity_status=binding.get('fidelity_status','pending_source_video_review'),
                source_files_verified=verify_files,source_asset_only=True,release_ready=False,
                initial_layout_tolerance_m=binding.get('initial_layout_tolerance_m',.025))
