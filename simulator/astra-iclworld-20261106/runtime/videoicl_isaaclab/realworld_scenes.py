"""New E-task scenes driven by reviewed upstream asset bindings.

Asset bindings are independent of ABC. Missing objects never become primitives
or fall back to the legacy F task. This initial native adapter covers E05/E32.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re
from .realworld_contracts import metadata as _private_metadata, provenance, public_assignment, VARIANTS
from .source_assets import resolve_asset
from .inference_generalization import public_instruction

IMPLEMENTED = ('E05', 'E32')


def load(task, variant, seed, bindings_path, *, verify_files=True):
    """Explicitly opt into a new execution revision; legacy files stay frozen."""
    binding_file = json.loads(Path(bindings_path).read_bytes())
    selection = binding_file.get('execution_design')
    if selection is None:
        return _load_source(task, variant, seed, bindings_path, verify_files=verify_files)
    from .execution_design import SUPPORTED_REVISIONS, WORKFLOW_TASKS, build_task_contract
    if not isinstance(selection, dict) or selection.get('revision') not in SUPPORTED_REVISIONS:
        raise ValueError('Explicit supported execution-design revision required')
    revision = selection['revision']
    contract = build_task_contract(task, variant, seed, selection.get('condition'), revision=revision)
    condition = contract['execution_design']['condition']
    # R fixes the demonstration input, including the source layout.
    # All adapters start from the same reviewed reset. Input variation is
    # explicit below, not accidental legacy seed jitter or ABC target leakage.
    canonical = revision == 'embodied50-execution-v3-20261102' or condition == 'R'
    base = _load_source(task, variant, 0 if canonical else seed,
                        bindings_path, verify_files=verify_files)
    if revision=='embodied50-execution-v3-20261102' and task=='E33':
        from .e33_source_geometry import augment_e33_execution_spec
        base=augment_e33_execution_spec(base,Path(__file__).resolve().parents[1])
    if task in WORKFLOW_TASKS:
        from .execution_design_scenes import build_execution_scene
        spec = build_execution_scene(base, condition=condition, seed=seed, revision=revision,
            e09_operable_packaging=selection.get('e09_operable_packaging',False) if task=='E09' else False)
    else:
        from .execution_design_inputs import apply_execution_inputs
        spec = apply_execution_inputs(base, condition=condition, seed=seed, revision=revision)
    campaign_instances = binding_file.get('remaining90_instances')
    if campaign_instances is not None:
        from .remaining90_instances import apply as apply_campaign_instances
        apply_campaign_instances(spec, campaign_instances)
    pairing = binding_file.get('full_campaign_paired_E')
    if pairing is not None:
        if condition != 'E' or pairing.get('schema') != 'iclworld-full-paired-E-complete-v1':
            raise ValueError('Explicit fresh-campaign paired E binding required')
        filename = pairing.get('paired_binding_by_task', {}).get(task)
        if filename not in ('I-reviewed-objects.private.json', 'R-original.private.json'):
            raise ValueError('Explicit paired I/R binding filename required')
        paired_path = Path(bindings_path).resolve().parent / filename
        paired = load(task, variant, seed, paired_path, verify_files=verify_files)
        canonical_name = 'I-canonical-v3.private.json' if filename.startswith('I-') else 'R-original.private.json'
        canonical_path = Path(bindings_path).resolve().parent / canonical_name
        baseline = load(task, variant, seed, canonical_path, verify_files=verify_files)
        from .full_campaign_pairing import apply as apply_paired_environment
        spec = apply_paired_environment(spec, paired, baseline, paired_binding_path=paired_path,
            canonical_binding_path=canonical_path)
    adapter_design = spec.get('execution_design', {})
    spec['execution_design'] = dict(adapter_design, **contract['execution_design'])
    # Contract is authoritative for identity/source; the adapter is
    # authoritative for what it actually changed. Empty planned fields must
    # never erase the measured/authored pairing record.
    for key in ('environment_changes', 'paired_physical_input_sha256',
                'applied_input_changes', 'pairing_verification'):
        if key in adapter_design:
            spec['execution_design'][key] = adapter_design[key]
    if ((task=='E09' and adapter_design.get('operable_packaging'))
            or (task=='E24' and spec.get('e24_lid_initial_layout'))):
        # Declared physical adapters bind their own environment/assignment
        # identity. Preserve that binding through the authoritative contract
        # merge, just as the adapter's physical input signature is preserved.
        for key in ('environment_identity','assignment_identity_sha256','paired_input_identity'):
            if key in adapter_design:
                spec['execution_design'][key]=adapter_design[key]
    spec.update(seed=seed, title=contract['title'], instruction=contract['instruction'],
                task_revision=revision, rule_qa=contract['rule_qa'],
                demo_quality=contract['demo_quality'], release_ready=False)
    order = spec['execution_design'].get('public_order')
    if order is not None:
        if set(order) != {'batch', 'destination'} or any(type(v) is not int or v < 1 for v in order.values()):
            raise ValueError('Invalid public execution order')
        spec['public_order'] = dict(order)
        spec['instruction'] += f"\n本次公开订单：批次 {order['batch']}，交付到 {order['destination']} 号目标工位。"
    return spec


def public_metadata(task):
    """Neutral task information for any of the 50 tasks; no private rule data.

    ``load`` returns a private author/evaluator contract, including goals and
    provenance. It must never be serialized wholesale into policy observation.
    """
    item = _private_metadata(task)
    return dict(id=task, title=item['title'], instruction=public_assignment(task))


def _vector(value, length, label, *, positive=False):
    if (not isinstance(value, (list, tuple)) or len(value) != length
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)
            or (positive and any(v <= 0 for v in value))):
        raise ValueError('Invalid ' + label)
    return [float(v) for v in value]


def _asset_record(record):
    """Validate declarations even during an explicit offline planning load."""
    if not isinstance(record, dict):
        raise ValueError('Reviewed source_asset record required')
    relative = record.get('relative_path')
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts):
        raise ValueError('Source asset must have a safe relative path')
    if not isinstance(record.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', record['sha256']):
        raise ValueError('Reviewed source SHA256 required')
    if 'source_rotation' in record:
        q = _vector(record['source_rotation'], 4, 'source rotation quaternion')
        if not math.isclose(sum(v*v for v in q), 1., abs_tol=1e-5):
            raise ValueError('Source rotation quaternion must be normalized')
    if 'allow_nonuniform_scale' in record and type(record['allow_nonuniform_scale']) is not bool:
        raise ValueError('Nonuniform scale adaptation flag must be boolean')


def _load_source(task, variant, seed, bindings_path, *, verify_files=True):
    """Build a private source-asset contract; never silently substitute geometry.

    Source object identities, sizes and bindings are invariant across ABC. E05
    paper positions explicitly match the reviewed source clips: +x is farther
    from the operator, A is triangle/square/circle and B/C square/triangle/circle.
    ``verify_files=False`` is for offline inspection only and is recorded in
    the returned contract; the default validates every source file's hash.
    """
    item = _private_metadata(task)
    if task not in IMPLEMENTED:
        from .realworld_recipes import load_reviewed_recipe
        return load_reviewed_recipe(task,variant,seed,bindings_path,verify_files=verify_files)
    if variant not in VARIANTS or type(seed) is not int or seed < 0:
        raise ValueError('Invalid variant/seed')
    if type(verify_files) is not bool:
        raise ValueError('verify_files must be boolean')
    path = Path(bindings_path)
    raw = path.read_bytes()
    catalog = json.loads(raw)
    binding = catalog.get('tasks', {}).get(task)
    if not isinstance(binding, dict) or not isinstance(binding.get('objects'), dict):
        raise ValueError(f'{task}: reviewed source asset bindings required')
    if binding.get('scene_adapter')=='full50-source-v1':
        from .realworld_recipes import load_reviewed_recipe
        return load_reviewed_recipe(task,variant,seed,bindings_path,verify_files=verify_files)
    assets = binding['objects']
    required = {'cube','sphere','triangle'} if task == 'E05' else {'sprite_bottle','pink_cube','cola_bottle'}
    if not required.issubset(assets):
        raise ValueError(f'{task}: missing reviewed source assets {sorted(required-set(assets))}')
    if task == 'E05' and set(assets) != required:
        raise ValueError('E05 has exactly the three source shape objects')
    jitter = binding.get('position_jitter', 0.)
    if type(jitter) not in (int, float) or not math.isfinite(jitter) or jitter < 0:
        raise ValueError('Position jitter must be a finite nonnegative distance')
    jitter = float(jitter) if seed else 0.
    rng = random.Random(seed)
    objects = []
    for name, entry in assets.items():
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Object IDs must be valid USD identifiers')
        if not isinstance(entry, dict):
            raise ValueError('Reviewed source object record required: ' + name)
        _asset_record(entry.get('source_asset'))
        if verify_files:
            resolve_asset(entry['source_asset'])
        obj = deepcopy(entry)
        obj.update(id=name, identity=name, role='movable')
        obj.setdefault('kind', 'source_mesh')
        obj.setdefault('yaw', 0.)
        obj.setdefault('rgba', [.7,.7,.7,1.])
        obj.setdefault('collision_shapes', [])
        obj.setdefault('bottom', .801)
        obj['size'] = _vector(obj.get('size'), 3, 'reviewed half extents for ' + name, positive=True)
        obj['xy'] = _vector(obj.get('xy'), 2, 'reviewed initial layout for ' + name)
        obj['rgba'] = _vector(obj['rgba'], 4, 'RGBA for ' + name)
        if any(v < 0 or v > 1 for v in obj['rgba']):
            raise ValueError('RGBA components must be within [0, 1]')
        for key in ('bottom', 'yaw'):
            if type(obj[key]) not in (int, float) or not math.isfinite(obj[key]):
                raise ValueError('Invalid ' + key + ' for ' + name)
        if 'quaternion' in obj:
            q = _vector(obj['quaternion'], 4, 'object quaternion for ' + name)
            if not math.isclose(sum(v*v for v in q), 1., abs_tol=1e-5):
                raise ValueError('Object quaternion must be normalized')
            obj['quaternion'] = q
            # The source adapter centres the complete imported geometry. Set
            # explicit centre height to avoid legacy spawn's size[0] shortcut
            # for quaternion-authored objects; a rotated box has a new extent.
            w, x, y, z = q
            vertical = [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]
            height = obj['size'][0] if obj['kind'] == 'sphere' else sum(abs(a)*b for a,b in zip(vertical,obj['size']))
            obj.setdefault('center_z', obj['bottom'] + height)
        if 'center_z' in obj and (type(obj['center_z']) not in (int, float) or not math.isfinite(obj['center_z'])):
            raise ValueError('Invalid centre height for ' + name)
        # Only opt-in position jitter; never randomize the operator frame or
        # change source identity/geometry as a function of the private variant.
        obj['xy'] = [float(v)+rng.uniform(-jitter,jitter) for v in obj['xy']]
        objects.append(obj)
    if task == 'E05':
        paper_order = ('triangle', 'square', 'circle') if variant == 'A' else ('square', 'triangle', 'circle')
        marker_for = dict(circle=0, triangle=1, square=2)
        zones = [dict(id=identity, xy=[x,-.08], half_size=[.055,.055], marker=marker_for[identity])
                 for identity,x in zip(paper_order,(.15,0.,-.15))]
        targets = {'A':{'cube':'square','sphere':'circle','triangle':'triangle'},
                   'B':{'cube':'circle','sphere':'triangle','triangle':'square'},
                   'C':{'cube':'triangle','sphere':'square','triangle':'circle'}}[variant]
    else:
        target_xy = _vector(binding.get('target_xy',[0.,-.23]), 2, 'delivery target XY')
        zones = [dict(id='target',xy=target_xy,half_size=[.11,.12],marker=None,outline=True)]
        targets = {dict(A='sprite_bottle',B='pink_cube',C='cola_bottle')[variant]:'target'}
    for zone in zones:
        zone['surface_z'] = .8
        zone['rgba'] = [.95,.95,.95,1.]
    goals = [dict(type='place', object=n, target=z, required_support='table') for n,z in targets.items()]
    return dict(id=task,variant=variant,seed=seed,title=item['title'],
                instruction=public_instruction(binding,public_assignment(task)),provenance=provenance(task,variant),
                objects=objects,zones=zones,fixtures=[],goals=goals,embodiment='franka',
                head_view=dict(eye_task=[-.60,0.,1.75],target_task=[0.,0.,.83],profile='realworld-operator-v2'),
                task_adapter='realworld-source-assets-v1',expert_action_budget=1800,
                expert_arm='right' if task == 'E32' else 'left',
                source_binding_sha256=hashlib.sha256(raw).hexdigest(),
                source_task_binding_sha256=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                source_binding_file=str(path.resolve()),asset_fidelity_status=binding.get('fidelity_status','pending_visual_review'),
                layout_revision='realworld-operator-paper-order-v2',
                source_files_verified=bool(verify_files),
                release_ready=False,source_asset_only=True)
