"""Private measured progress evidence, not a model observation or reward API.

The local stability windows are deliberately independent: moving a second
object cannot erase an already resting object's physical evidence. No requested
pose, selected answer, model declaration or commanded action enters this module.
"""
from copy import deepcopy
import hashlib
import json
import numpy as np
from .realworld_stability import for_evaluator as stability_policy

SCHEMA = 'videoicl-native-progress-evidence-v2'
FINGERS = tuple(f'{s}_finger{i}' for s in ('left', 'right') for i in (1, 2))


def json_value(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)): return [json_value(v) for v in value]
    return value


def reset(e):
    e.progress_anchors = {}
    e.progress_hold = {}
    e.progress_status_by_actor = {}
    e.progress_initial_observation = None
    e.progress_initial_sealed = False
    e.progress_initial_step = None
    e.progress_initial_objects = None
    e.progress_extra_anchors = {}
    e.progress_extra_hold = {}
    e.progress_extra_status = {}


def measured_group(e, label, poses, released, supported, dt):
    """Local stability for a measured articulated body or clip assembly."""
    anchor=e.progress_extra_anchors.get(label);settling=stability_policy(e)
    bounded=anchor is not None and set(anchor)==set(poses) and all(
        np.linalg.norm(v['pos']-anchor[n]['pos'])<=settling.translation_m and
        np.linalg.norm(v['mat']-anchor[n]['mat'])<=settling.rotation_matrix for n,v in poses.items())
    if released and e.history_valid:
        if not bounded:
            e.progress_extra_anchors[label]=deepcopy(poses);e.progress_extra_hold[label]=0.
        else:e.progress_extra_hold[label]+=float(dt)
    else:
        e.progress_extra_anchors.pop(label,None);e.progress_extra_hold[label]=0.
    e.progress_extra_status[label]=dict(released=bool(released),stable=bool(released and e.progress_extra_hold[label]>=settling.seconds),
        supported=bool(supported),hold_seconds=e.progress_extra_hold[label],actor_id=None)


def update_physical(e, dt):
    """Track per-body release and the existing 0.5s measured pose envelope."""
    fingers = tuple(getattr(e, 'fingers', FINGERS));settling=stability_policy(e)
    for name, value in e.state.items():
        released = not any(value['grasp']) and not any(e.contact(name, f) for f in fingers)
        anchor = e.progress_anchors.get(name)
        sphere = e.objects[name].get('kind') == 'sphere'
        bounded = anchor is not None and np.linalg.norm(value['pos']-anchor['pos']) <= settling.translation_m and (
            sphere or np.linalg.norm(value['mat']-anchor['mat']) <= settling.rotation_matrix)
        if released and e.history_valid:
            if not bounded:
                e.progress_anchors[name] = deepcopy(value)
                e.progress_hold[name] = 0.
            else:
                e.progress_hold[name] = e.progress_hold.get(name, 0.) + float(dt)
        else:
            e.progress_anchors.pop(name, None)
            e.progress_hold[name] = 0.
        # Some articulated support bodies are absent from the rigid-body graph;
        # finish_observation augments these using measured task-specific support.
        supported = name in getattr(e, 'grounded', set())
        e.progress_status_by_actor[name] = dict(released=bool(released),
            stable=bool(released and e.progress_hold[name] >= settling.seconds),
            supported=bool(supported), hold_seconds=e.progress_hold[name])


def finish_observation(e, obs):
    support_labels = set()
    for key in ('supported', 'supported_in_plate', 'supported_in_box', 'supported_in_tray',
                'supported_in_bin', 'supported_on_post', 'supported_in_compartment',
                'physically_inserted', 'outer_supported', 'seated', 'in_drawer', 'delivered'):
        value = obs.get(key, [])
        if isinstance(value, (list, tuple)):
            support_labels.update(v for v in value if isinstance(v, str))
    for key in ('support_layers', 'branch_for_cup'):
        if isinstance(obs.get(key), dict): support_labels.update(obs[key])
    # E19's cap contacts are explicitly verified by covering_cap.
    if e.task == 'E19':
        support_labels.update('cap_'+v for v in obs.get('cap_for_bottle', {}).values())
    if e.task == 'E06': support_labels.update(obs.get('ball_to_cell', {}))
    status = {}
    # A static reference and a movable item may share a colour label (E39).
    # Movable actors take precedence; actor_status remains lossless.
    order = sorted(e.objects, key=lambda n: e.objects[n].get('role') != 'fixture')
    for name in order:
        label = e.label(name)
        value = deepcopy(e.progress_status_by_actor.get(name, {}))
        if label in support_labels: value['supported'] = True
        value['actor_id'] = name
        status[label] = value
    if e.task == 'E07':
        obs['rank_label_map'] = {str(e.objects[n]['rank']): e.label(n) for n in e.group('blocks')}
        for rank,label in obs['rank_label_map'].items(): status[rank]=deepcopy(status[label])
    status.update(deepcopy(e.progress_extra_status))
    # Semantic role aliases are backed by measured physical actors, never by
    # default True flags or substitutions of the global success condition.
    if e.task=='E37':
        for role,entry in e.semantic['screw_roles'].items():status[role]=deepcopy(status[e.label(entry['screw'])])
    if e.task=='E45':status['cup']=deepcopy(status[e.label(e.semantic['containers']['cup']['object'])])
    if (e.task == 'E19' and getattr(e, 'spec', {}).get('execution_design', {}).get('revision')
            == 'embodied50-execution-v3-20261102'):
        # Structural observations name cap colours "yellow", while the
        # progress contract asks for "cap_yellow". Bind that role to the
        # same measured actor; never infer release/stability from seating.
        for actor in e.semantic['caps']:
            label = e.label(actor)
            alias = 'cap_' + label.removeprefix('cap_')
            value = deepcopy(status[label])
            if value.get('actor_id') != actor:
                raise ValueError('Ambiguous measured cap identity: ' + alias)
            if alias in status and status[alias].get('actor_id') != actor:
                raise ValueError('Conflicting measured cap alias: ' + alias)
            if alias in support_labels:
                value['supported'] = True
            status[alias] = value
    obs['progress_physical'] = status
    if e.progress_initial_sealed:
        return obs
    if e.progress_initial_observation is None:
        e.progress_initial_observation = json_value(deepcopy(obs))
    else:
        # Initial stability is attested only while still at the initial pose.
        initial_status=e.progress_initial_observation.get('progress_physical', {})
        for label, item in status.items():
            name=item['actor_id']
            if name is None:continue
            initial=e.initial[name]; current=e.state[name]
            unchanged=np.linalg.norm(current['pos']-initial['pos'])<=.002 and (e.objects[name].get('kind')=='sphere' or np.linalg.norm(current['mat']-initial['mat'])<=.02)
            if unchanged and item.get('stable') and label in initial_status:
                initial_status[label]['stable']=True
    return obs


def initial_layout_failures(e):
    """Admission-only geometry checks for the diagnosed E13/E25 sources.

    Compare measured task-frame poses to the loaded (seed-resolved) recipe,
    never the first snapshot: that snapshot can already be below the table.
    This does not change task success, history or any measured contact flag.
    """
    names={'E13':('phone','stand'),'E25':('fork','spoon','knife','tray')}.get(e.task,())
    failures=[]
    for name in names:
        obj=e.objects.get(name);state=getattr(e,'state',{}).get(name)
        status=getattr(e,'progress_status_by_actor',{}).get(name,{})
        reasons=[];detail=dict(actor_id=name)
        if obj is None or state is None:
            failures.append(dict(actor_id=name,reasons=['missing_actor_or_pose']));continue
        try:
            expected=np.array([*obj['xy'],obj.get('center_z',obj['bottom']+obj['size'][2])],float)
            pos=np.asarray(state['pos'],float);mat=np.asarray(state['mat'],float)
            if expected.shape!=(3,) or pos.shape!=(3,) or mat.shape!=(3,3) or not all(np.isfinite(x).all() for x in (expected,pos,mat)):
                raise ValueError('Invalid measured pose')
            if 'quaternion' in obj:
                w,x,y,z=obj['quaternion']
                expected_mat=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                    [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                    [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            else:
                yaw=obj['yaw'];c,s=np.cos(yaw),np.sin(yaw)
                expected_mat=np.array([[c,-s,0],[s,c,0],[0,0,1]])
            distance=float(np.linalg.norm(pos-expected))
            angle=float(np.degrees(np.arccos(np.clip((np.trace(expected_mat.T@mat)-1)/2,-1,1))))
            detail.update(measured_position=pos.tolist(),expected_position=expected.tolist(),
                center_error_m=distance,orientation_error_deg=angle,
                max_center_error_m=.02,max_orientation_error_deg=10.)
            if distance>.02:reasons.append('initial_center_displaced')
            if angle>10.:reasons.append('initial_orientation_displaced')
        except (KeyError,TypeError,ValueError):reasons.append('missing_or_invalid_recipe_pose')
        if status.get('supported') is not True:reasons.append('no_measured_physical_support')
        if status.get('released') is not True:reasons.append('not_released')
        if reasons:
            detail.update(reasons=reasons,measured_status=deepcopy(status));failures.append(detail)
    return failures


def initial_diagnostics(e, *, room_id=None):
    """Describe the measured baseline and explicit diagnosed-source admission.

    Only a dynamic scoring denominator needs a fully settled set of relevant
    initial actors. Other tasks keep their actual initial stable=False values.
    The source initial-state checker and native-history validity remain separate
    mandatory checks for every task. E13/E25 additionally reject displaced or
    unsupported source actors independently of their stable flag.
    """
    if getattr(e, 'spec', {}).get('execution_design') and hasattr(e, 'initial_diagnostics'):
        return e.initial_diagnostics(room_id=room_id)
    groups={'E07':('blocks',),'E09':('pieces',),'E39':('blocks','reference')}
    required=[];missing_groups=[]
    for group in groups.get(e.task,()):
        names=e.group(group,[])
        if not names:missing_groups.append(group)
        required.extend(names)
    required=sorted(set(required))
    actor_status=getattr(e,'progress_status_by_actor',{})
    unstable=[]
    for name in sorted(getattr(e,'objects',{})):
        item=actor_status.get(name,{})
        if item.get('released') is not True or item.get('stable') is not True:
            unstable.append(dict(actor_id=name,label=e.label(name),
                required_for_denominator=name in required,
                released=item.get('released'),stable=item.get('stable'),
                supported=item.get('supported'),hold_seconds=item.get('hold_seconds')))
    required_unstable=[item for item in unstable if item['required_for_denominator']]
    source_failures=[deepcopy(c) for c in getattr(e,'current_conditions',[])
        if c.get('type')=='source_initial_state' and c.get('passed') is not True]
    layout_failures=initial_layout_failures(e)
    native_valid=bool(e.history_valid and not e.errors and e.observation and e.initial is not None)
    return dict(room_id=room_id,task=e.task,variant=e.variant,physics_step=e.steps,
        dynamic_denominator=e.task in groups,required_actors=required,
        missing_required_groups=missing_groups,unstable_actors=unstable,
        required_unstable_actors=required_unstable,
        source_initial_failures=source_failures,initial_layout_failures=layout_failures,history_valid=bool(e.history_valid),
        native_errors=list(e.errors),native_evidence_valid=native_valid,
        can_seal=bool(native_valid and not source_failures and not layout_failures and not missing_groups and not required_unstable))


def seal_initial(e):
    """Freeze actual pre-agent evidence; never resample or invent stability."""
    if getattr(e, 'spec', {}).get('execution_design') and hasattr(e, 'seal_initial'):
        return e.seal_initial()
    if e.progress_initial_sealed:
        raise ValueError('Progress initial evidence is already sealed')
    diagnostic=initial_diagnostics(e)
    prefix=f"{e.task}/{e.variant}"
    if not diagnostic['native_evidence_valid']:
        raise ValueError(prefix+': cannot seal invalid or missing initial native evidence')
    if diagnostic['source_initial_failures']:
        raise ValueError(prefix+': source_initial_state rejected')
    if diagnostic['initial_layout_failures']:
        raise ValueError(prefix+': source layout invalid: '+json.dumps(diagnostic['initial_layout_failures']))
    if diagnostic['missing_required_groups']:
        raise ValueError(prefix+': missing denominator actor groups '+','.join(diagnostic['missing_required_groups']))
    if diagnostic['required_unstable_actors']:
        detail=', '.join(f"{x['actor_id']}[{x['label']}]:released={x['released']},stable={x['stable']},hold={x['hold_seconds']}"
            for x in diagnostic['required_unstable_actors'])
        raise ValueError(prefix+': dynamic denominator actors lack released 0.5s pose-stability window: '+detail)
    e.progress_initial_observation=json_value(deepcopy(e.observation))
    e.progress_initial_objects=json_value(deepcopy(e.state))
    e.progress_initial_step=e.steps
    e.progress_initial_sealed=True


def attach_score(result):
    """Bind the pure private rubric result to the exact native evidence."""
    from .realworld_progress import score_progress
    evidence=result['progress_evidence']
    score=score_progress(evidence['task'],evidence['variant'],evidence)
    encoded=json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    score['evidence_sha256']=hashlib.sha256(encoded.encode()).hexdigest()
    result['progress_result']=score
    return result


def envelope(e):
    return dict(schema=SCHEMA, task=e.task, variant=e.variant, physics_step=e.steps,
        history_valid=bool(e.history_valid), observation=json_value(deepcopy(e.observation)),
        object_status=deepcopy(e.observation.get('progress_physical', {})),
        actor_status=json_value(deepcopy(e.progress_status_by_actor)),
        initial=dict(observation=deepcopy(e.progress_initial_observation),
                     object_status=deepcopy((e.progress_initial_observation or {}).get('progress_physical', {})),
                     objects=deepcopy(e.progress_initial_objects) if e.progress_initial_sealed else json_value(e.initial or {}),
                     sealed=e.progress_initial_sealed,physics_step=e.progress_initial_step),
        source='trusted_native_per_physics_tick',
        stability_definition='per-body '+stability_policy(e).description+' while released',
        stability_policy=stability_policy(e).record())
