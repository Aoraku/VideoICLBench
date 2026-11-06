"""Apply the COMPLETE existing E transform to the reviewed paired I/R input.

Pure reset-time three-way scene merge; no live simulator, policy or scorer.
Unknown conflicting geometry/semantic changes fail closed with their field path.
"""
from copy import deepcopy
import hashlib,json
from pathlib import Path
SCHEMA='iclworld-full-paired-E-complete-v1'
ABSENT=object()
POSE_FIELDS={'xy','center','position','center_z','bottom','surface_z','anchor_world','position_world','translation'}
META={'execution_design','provenance','instruction','rule_qa','demo_quality','release_ready','title','task_revision','source_binding_sha256','source_bindings_path','source_binding_file'}
INTRINSIC=('source_asset','mechanical_asset','size','parts','collision_shapes','geometry','mass','physical_mass_kg','sphere_radius','hole_radius','source_containment_hull','reviewed_collision_settings')
def same(a,b):return a is b or a is not ABSENT and b is not ABSENT and a==b
def merge(base,environment,paired,path=()):
    if same(base,environment):return deepcopy(paired)if paired is not ABSENT else ABSENT
    if same(base,paired)or same(environment,paired):return deepcopy(environment)if environment is not ABSENT else ABSENT
    if isinstance(base,dict)and isinstance(environment,dict)and isinstance(paired,dict):
        out={}
        for key in base.keys()|environment.keys()|paired.keys():
            value=merge(base.get(key,ABSENT),environment.get(key,ABSENT),paired.get(key,ABSENT),path+(key,))
            if value is not ABSENT:out[key]=value
        return out
    if all(isinstance(x,list)for x in(base,environment,paired)):
        if all(all(isinstance(row,dict)and'id'in row for row in rows)for rows in(base,environment,paired)):
            b={r['id']:r for r in base};e={r['id']:r for r in environment};p={r['id']:r for r in paired}
            order=list(e)+[key for key in p if key not in e]
            values=[merge(b.get(key,ABSENT),e.get(key,ABSENT),p.get(key,ABSENT),path+(key,))for key in order]
            return [x for x in values if x is not ABSENT]
        if path and path[-1]in POSE_FIELDS and len(base)==len(environment)==len(paired)and all(type(n)in(int,float)for rows in(base,environment,paired)for n in rows):
            return [a+(e-b)for b,e,a in zip(base,environment,paired)]
    if path and path[-1]in POSE_FIELDS and all(type(n)in(int,float)for n in(base,environment,paired)):
        return paired+(environment-base)
    raise ValueError('Paired E transformation conflict at '+'.'.join(map(str,path)))
def intrinsic(spec):
    return {row['id']:{k:row[k]for k in INTRINSIC if k in row}for row in[*spec.get('objects',[]),*spec.get('mechanisms',[])]}
def apply(original_e,paired,baseline,*,paired_binding_path,canonical_binding_path):
    design=original_e.get('execution_design',{})
    if design.get('condition')!='E'or design.get('revision')!='embodied50-execution-v3-20261102':raise ValueError('Explicit existing v3 E required')
    original_e=deepcopy(original_e)
    if design.get('seed',paired['seed'])!=paired['seed']:raise ValueError('E design seed mismatch')
    original_e['seed']=paired['seed']  # Workflow adapter receives canonical reset seed before final load() stamps assignment seed.
    if any((x['id'],x['variant'],x['seed'])!=(paired['id'],paired['variant'],paired['seed'])for x in(original_e,baseline)):raise ValueError('Paired task/variant/seed mismatch')
    clean=lambda x:{k:v for k,v in x.items()if k not in META}
    out=merge(clean(baseline),clean(original_e),clean(paired))
    out.update({k:deepcopy(v)for k,v in paired.items()if k in META})
    # Existing E geometry/layout/material changes are all retained. Shared actor
    # intrinsic geometry remains the exact reviewed I replacement, not canonical R.
    actual,expected=intrinsic(out),intrinsic(paired)
    corrections=[]
    if any(actual.get(key)!=value for key,value in expected.items()):
        # E46's existing fresh-I thickness revision was conditioned on I only.
        # Its old E therefore retained the obsolete task-object instance. That
        # is not an environment change: E must keep the paired I task objects.
        if paired['id'] != 'E46':
            raise ValueError('E lost paired I/R physical object geometry')
        actors={row['id']:row for row in [*out.get('objects',[]),*out.get('mechanisms',[])]}
        source_actors={row['id']:row for row in [*paired.get('objects',[]),*paired.get('mechanisms',[])]}
        for actor,value in expected.items():
            if actual.get(actor)==value:continue
            corrections.append(dict(actor=actor,reason='retain_existing_fresh_I_thickness_instance_in_E'))
            for key in INTRINSIC:
                if key in source_actors[actor]:actors[actor][key]=deepcopy(source_actors[actor][key])
                else:actors[actor].pop(key,None)
        out['semantic']=deepcopy(paired['semantic'])
        if intrinsic(out)!=expected:raise ValueError('E46 paired physical instance mismatch')
    relation=lambda s:[{k:g[k]for k in('type','object','target','required_support')if k in g}for g in s['goals']]
    if relation(out)!=relation(paired)or out['semantic']['mode']!=paired['semantic']['mode']:raise ValueError('E changed rule/goal relations')
    from .execution_design_inputs_v3 import physical_input_signature
    out['execution_design']=deepcopy(design)
    out['execution_design'].update(paired_physical_input_sha256=physical_input_signature(paired),
        applied_input_changes=deepcopy(paired.get('execution_design',{}).get('applied_input_changes',{})),
        pairing_verification='complete_existing_E_transform_applied_to_reviewed_I_R_geometry_CPU',
        full_campaign_pairing=dict(schema=SCHEMA,paired_condition=paired['execution_design']['condition'],
            paired_binding_sha256=hashlib.sha256(Path(paired_binding_path).read_bytes()).hexdigest(),
            canonical_binding_sha256=hashlib.sha256(Path(canonical_binding_path).read_bytes()).hexdigest(),
            source_environment_changes=deepcopy(design.get('environment_changes',[])),
            all_existing_environment_changes_preserved=True,
            non_environment_pairing_corrections=corrections,
            paired_actor_intrinsics_exact=True,native_environment_initialization_verified=False))
    return out
