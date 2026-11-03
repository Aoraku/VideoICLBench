"""Private, explicit semantic contracts for all 50 frozen RealWorld50 tasks.

Inputs are observations extracted by a trusted native simulator adapter, never
actor commands or asset declarations. This module checks those observations;
it neither constructs a simulator nor attests their origin. Position/containment
labels must be derived from measured poses and contact, not supplied by a policy.
The contract document specifies the evidence for every task. Source metadata and
answers remain private; public prompts are unchanged in realworld_contracts.

Event samples use physics step indices. Tool traces must cover consecutive
physics steps, including contact losses; selecting only favourable frames is
invalid. Missing, malformed, nonfinite or incomplete evidence fails closed.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

from .realworld_contracts import TASKS, VARIANTS, PILOT_TASKS, DATASET_REVISION, check_pilot


POSITION_TOLERANCE_M = .02
ANGLE_TOLERANCE_DEG = 10.
SOURCE_COLORS = ('red', 'green', 'blue')
SHAPES = ('square', 'triangle', 'circle')
CARDS = ('card1', 'card2', 'card3', 'card4', 'card5')


def _seq(value):
    return isinstance(value, (list, tuple))


def _members(value, expected):
    return (_seq(value) and len(value) == len(expected)
            and all(type(x) in (str, int) for x in value)
            and set(value) == set(expected))


def _unique(value, count=None):
    return (_seq(value) and (count is None or len(value) == count)
            and all(isinstance(x, str) and bool(x) for x in value)
            and len(set(value)) == len(value))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, n):
    return _seq(value) and len(value) == n and all(_number(x) for x in value)


def _distance(a, b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def _angle(a, b):
    return abs((a-b+180.) % 360. - 180.)


def _yaw_mapping(value, expected):
    return (isinstance(value, Mapping) and set(value) == set(expected)
            and all(_number(value[k]) and _number(v) and _angle(value[k],v) <= ANGLE_TOLERANCE_DEG
                    for k,v in expected.items()))


def _pairs(value):
    if not isinstance(value, (list, tuple, set, frozenset)):
        return None
    result = set()
    for pair in value:
        if not isinstance(pair, (list, tuple, set, frozenset)) or len(pair) != 2 or not all(isinstance(x,str) for x in pair):
            return None
        result.add(frozenset(pair))
    return result


def _contact(obs, a, b):
    pairs = _pairs(obs.get('contacts'))
    return pairs is not None and frozenset((a,b)) in pairs


def _chain(obs, order, base='table'):
    edges = obs.get('support_edges')
    if not _seq(edges) or not all(_seq(p) and len(p)==2 and all(isinstance(x,str) for x in p) for p in edges):
        return False
    required = {(base,order[0]), *zip(order[:-1],order[1:])}
    return required <= {tuple(p) for p in edges}


def _pose_map(value, count):
    return (isinstance(value, Mapping) and len(value)==count
            and all(isinstance(k,str) and isinstance(v,Mapping) and _vector(v.get('xy'),2)
                    and _number(v.get('yaw_deg')) for k,v in value.items()))


def _steps(samples, minimum=2):
    return (_seq(samples) and len(samples)>=minimum and all(isinstance(x,Mapping) for x in samples)
            and all(type(x.get('step')) is int and x['step']>=0 for x in samples)
            and all(b['step']==a['step']+1 for a,b in zip(samples[:-1],samples[1:])))


def _force(value):
    return _number(value) and value > 0.


def _transport(samples, object_id, tool='spatula', clamp=False):
    if not _steps(samples):
        return False
    for sample in samples:
        if (sample.get('object') != object_id or sample.get('tool') != tool
                or not _vector(sample.get('object_pos'),3) or sample.get('tool_held') is not True
                or sample.get('direct_hand_contact') is not False):
            return False
        if clamp:
            forces=sample.get('jaw_contact_forces')
            if not _vector(forces,2) or not all(_force(x) for x in forces) or sample.get('between_jaws') is not True:
                return False
        elif not _force(sample.get('support_contact_force')):
            return False
    return _distance(samples[0]['object_pos'],samples[-1]['object_pos']) > .02


def _placement_events(events):
    if not _seq(events) or not events:
        return None
    first=[];seen=set();previous=-1
    for event in events:
        if (not isinstance(event,Mapping) or not isinstance(event.get('object'),str)
                or not isinstance(event.get('target'),str) or type(event.get('step')) is not int
                or event['step']<0 or event['step']<previous or event.get('released') is not True
                or event.get('support_contact') is not True):
            return None
        previous=event['step']
        if event['object'] not in seen:
            if first and event['step']<=first[-1]['step']:
                return None  # Same-step releases do not establish an ordering.
            first.append(event);seen.add(event['object'])
    return first


def _groups(value):
    if not _seq(value) or len(value)!=3 or not all(_unique(group,3) for group in value):
        return None
    flattened=[x for group in value for x in group]
    if len(set(flattened))!=9:
        return None
    return {frozenset(group) for group in value}


def _grid(value):
    return _seq(value) and len(value)==2 and all(_seq(row) and len(row)==2 for row in value) and _unique([x for row in value for x in row],4)


def _clip_opening_update(previous, current, anchor):
    """Net physical opening within one uninterrupted measured-force segment.

    A per-tick displacement threshold would impose an unintended speed floor.
    Reset at loss of force or missing samples, and compare net displacement
    with the segment start so oscillation cannot accumulate artificial credit.
    """
    if (current['handle_contact_force']<=0 or previous is None
            or current['step']!=previous['step']+1):
        return None,False
    if anchor is None:
        anchor=(previous['jaw_gap_m'],previous['joint_pos'])
    driven=(current['jaw_gap_m']>anchor[0]+.001
            and abs(current['joint_pos']-anchor[1])>1e-5)
    return anchor,driven


def _clip_record(record):
    if not isinstance(record,Mapping) or not isinstance(record.get('clip_id'),str):
        return False
    samples=record.get('samples')
    if not _steps(samples,3):
        return False
    if not all(_number(s.get('jaw_gap_m')) and s['jaw_gap_m']>=0 and _number(s.get('handle_contact_force'))
               and s['handle_contact_force']>=0 and _number(s.get('joint_pos')) for s in samples):
        return False
    last=samples[-1]
    # The maximum gap can occur one physics tick after handle release due to
    # inertia. Require an actual force-driven opening interval, not force on
    # the global-maximum frame; then require subsequent released closure.
    anchor=None;driven=None
    for i in range(1,len(samples)-1):
        anchor,opened=_clip_opening_update(samples[i-1],samples[i],anchor)
        if opened:
            driven=i;break
    # Require spring closure during the terminal uninterrupted zero-force
    # segment. Its preceding sample is the release baseline; an inertial peak
    # after release is allowed. Earlier forced closure cannot supply credit.
    release_start=len(samples)-1
    while (release_start>0 and samples[release_start-1]['handle_contact_force']==0
           and samples[release_start]['step']==samples[release_start-1]['step']+1):
        release_start-=1
    release_observed=(last['handle_contact_force']==0 and release_start>0
                      and samples[release_start]['step']==samples[release_start-1]['step']+1)
    closed=(driven is not None and release_observed and driven<release_start
            and last['jaw_gap_m']<max(s['jaw_gap_m'] for s in samples[release_start-1:])-.0005)
    return (closed and last.get('handles_released') is True and last['handle_contact_force']==0
            and _force(last.get('left_jaw_contact_force')) and _force(last.get('right_jaw_contact_force'))
            and last.get('edge_between_jaws') is True)


def _screw_record(samples):
    if not _steps(samples,3):
        return False
    if not all(_number(s.get('angle_rad')) and _number(s.get('axial_m'))
               and _number(s.get('thread_overlap_m')) for s in samples):
        return False
    if samples[0]['thread_overlap_m']<=0 or samples[-1]['thread_overlap_m']>0:
        return False
    driven_rotation=0.
    driven_axial=0.
    undriven_anchor=None
    for a,b in zip(samples[:-1],samples[1:]):
        rotation=b['angle_rad']-a['angle_rad']
        axial=b['axial_m']-a['axial_m']
        if a['thread_overlap_m']>0:
            engaged=(_force(b.get('driver_contact_force')) and _force(b.get('tip_engagement_depth_m'))
                     and _number(b.get('tool_axis_alignment_cos')) and .9<=b['tool_axis_alignment_cos']<=1.)
            if engaged:
                driven_rotation+=rotation
                driven_axial+=axial
                undriven_anchor=None
            else:
                if undriven_anchor is None:undriven_anchor=a['angle_rad']
                # Bound continuous *net* unpowered drift. Summing absolute
                # substep differences would reject harmless solver jitter;
                # resetting this anchor every frame would admit a slow spin.
                if abs(b['angle_rad']-undriven_anchor)>.02:return False
    return (abs(driven_rotation)>.05 and driven_axial>.001
            and abs(samples[-1]['angle_rad']-samples[0]['angle_rad'])>.05
            and samples[-1]['axial_m']>samples[0]['axial_m']+.001
            and samples[-1].get('separated') is True)


def _segment_rectangle(a,b,low,high):
    lo,hi=0.,1.
    for i in range(2):
        delta=b[i]-a[i]
        if abs(delta)<1e-12:
            if not low[i]<=a[i]<=high[i]:
                return False
        else:
            first,second=(low[i]-a[i])/delta,(high[i]-a[i])/delta
            lo=max(lo,min(first,second));hi=min(hi,max(first,second))
            if lo>hi:
                return False
    return True


def _guided_path(obs,target):
    trace=obs.get('trajectory');regions=obs.get('region_bounds');release=obs.get('release')
    if not _steps(trace,4) or not isinstance(regions,Mapping) or set(regions)!=set(SHAPES):
        return False
    if (not isinstance(release,Mapping) or release.get('source')!='fixed_launcher'
            or type(release.get('step')) is not int or release['step']<0 or release['step']>trace[0]['step']
            or release.get('initially_held') is not True or release.get('released') is not True):
        return False
    if not all(_vector(s.get('pos'),3) and s.get('hand_contact_force')==0 and _number(s.get('hand_contact_force'))
               and _number(s.get('guide_contact_force')) and s['guide_contact_force']>=0 for s in trace):
        return False
    bounds=regions[target]
    if (not isinstance(bounds,Mapping) or not _vector(bounds.get('min'),2) or not _vector(bounds.get('max'),2)
            or not all(a<b for a,b in zip(bounds['min'],bounds['max']))):
        return False
    guide_step=None
    for i in range(1,len(trace)-1):
        if trace[i]['guide_contact_force']<=0 or trace[i].get('guide_held') is not True:
            continue
        incoming=[b-a for a,b in zip(trace[i-1]['pos'][:2],trace[i]['pos'][:2])]
        outgoing=[b-a for a,b in zip(trace[i]['pos'][:2],trace[i+1]['pos'][:2])]
        ni=math.hypot(*incoming);no=math.hypot(*outgoing)
        if ni>1e-6 and no>1e-6 and sum(a*b for a,b in zip(incoming,outgoing))/(ni*no)<math.cos(.02):
            guide_step=trace[i]['step'];break
    return (guide_step is not None and any(a['step']>=guide_step and _segment_rectangle(a['pos'],b['pos'],bounds['min'],bounds['max'])
                                         for a,b in zip(trace[:-1],trace[1:])))


def _result(task,variant,checks):
    return dict(task=task,variant=variant,success=all(checks.values()),checks=checks,
                failed_checks=[k for k,v in checks.items() if not v],dataset_revision=DATASET_REVISION,
                evidence_scope='semantic validation of native-adapter observations; not scene or asset certification')


def check_task(task,variant,observation):
    """Check a frozen E01–E50 rule; malformed evidence fails, unknown IDs raise."""
    if task not in TASKS:
        raise ValueError(f'Unknown RealWorld50 task: {task!r}')
    if variant not in VARIANTS:
        raise ValueError(f'Unknown variant: {variant!r}')
    if task in PILOT_TASKS:
        return check_pilot(task,variant,observation)
    obs=observation if isinstance(observation,Mapping) else {}
    # Traversal and percussion are event tasks: no invented final resting pose.
    checks={} if task in ('E29','E43') else dict(released=obs.get('released') is True,stable=obs.get('stable') is True)
    try:
        _evaluate(task,VARIANTS.index(variant),obs,checks)
    except (TypeError,ValueError,KeyError,IndexError,OverflowError):
        checks['well_formed_evidence']=False
    return _result(task,variant,checks)


def _evaluate(task,index,o,c):
    if task=='E01':
        selected=({'burger','fries'},{'burger','drink'},{'fries','drink'})[index]
        c['selected_food_set']=_members(o.get('in_plate'),selected)
        c['unselected_food_outside']=_members(o.get('outside_plate'),{'burger','fries','drink'}-selected)
        c['plate_support']=_members(o.get('supported_in_plate'),selected)
    elif task=='E03':
        order=(('red','green','blue'),('green','blue','red'),('blue','red','green'))[index]
        c['outside_to_inside']=tuple(o.get('outside_to_inside',()))==order
        c['all_cups_up']=_members(o.get('upright'),SOURCE_COLORS)
        c['real_nested_cavities']=_members(o.get('nested_pairs'),[f'{order[0]}>{order[1]}',f'{order[1]}>{order[2]}'])
        c['cup_contacts']=_contact(o,order[0],order[1]) and _contact(o,order[1],order[2])
    elif task=='E04':
        targets=(dict(green='triangle',blue='circle',red='square'),dict(green='square',blue='circle',red='triangle'),dict(green='circle',blue='triangle',red='square'))[index]
        c['color_marker_mapping']=o.get('placements')==targets
        c['all_cups_supported']=_members(o.get('supported'),SOURCE_COLORS)
    elif task=='E07':
        order=([1,2,3,4,5],[5,4,3,2,1],[3,2,1,4,5])[index]
        c['size_order_far_to_near']=o.get('far_to_near')==order and all(type(x)is int for x in o['far_to_near'])
        c['nonoverlap']=o.get('nonoverlapping') is True
        c['all_blocks_supported']=_members(o.get('supported_ranks'),[1,2,3,4,5])
    elif task=='E08':
        expected=(dict(left='toe',right='toe'),dict(left='heel',right='heel'),dict(left='toe',right='heel'))[index]
        c['shoe_orientation_to_label_end']=o.get('toward_label')==expected
        c['shoes_inside']=_members(o.get('in_box'),['left','right'])
        c['shoes_supported']=_members(o.get('supported_in_box'),['left','right'])
    elif task=='E09':
        objects={f'{color}_{shape}' for color in SOURCE_COLORS for shape in SHAPES}
        expected=([{f'{color}_{shape}' for shape in SHAPES} for color in SOURCE_COLORS],
                  [{f'{color}_{shape}' for color in SOURCE_COLORS} for shape in SHAPES],
                  [{'red_circle','green_triangle','blue_square'},{'red_triangle','green_square','blue_circle'},{'red_square','green_circle','blue_triangle'}])[index]
        c['unlabeled_group_partition']=_groups(o.get('groups'))=={frozenset(x) for x in expected}
        c['all_pieces_supported']=_members(o.get('supported'),objects)
    elif task=='E10':
        objects={f'{color}_{shape}' for color in SOURCE_COLORS for shape in SHAPES}
        red={x for x in objects if x.startswith('red_')};square={x for x in objects if x.endswith('_square')}
        selected=(red,square,red|square)[index]
        c['attribute_selection_OR']=_members(o.get('on_post'),selected)
        c['real_hole_post_intersection']=_members(o.get('threaded'),selected)
        c['threaded_pieces_supported']=_members(o.get('supported_on_post'),selected)
        c['unselected_not_on_post']=_members(o.get('off_post'),objects-selected)
    elif task=='E11':
        initial=o.get('initial_grid');final=o.get('final_grid')
        valid=_grid(initial) and _grid(final)
        c['initial_and_final_grid_valid']=valid
        if valid:
            expected=(initial,[[initial[1][0],initial[0][0]],[initial[1][1],initial[0][1]]],[row[::-1] for row in initial])[index]
            c['initial_layout_transform']=final==expected
            c['frame_supported']=_members(o.get('supported'),[x for row in initial for x in row])
    elif task=='E12':
        slots=({1,2},{3,4},{1,4})[index];assignment=o.get('charger_to_slot')
        valid=isinstance(assignment,Mapping) and len(assignment)==2 and all(isinstance(k,str) and type(v)is int for k,v in assignment.items())
        c['selected_slot_set']=valid and set(assignment.values())==slots
        c['real_insertions']=valid and _members(o.get('physically_inserted'),set(assignment))
        c['inserted_chargers_supported']=valid and _members(o.get('supported'),set(assignment))
    elif task=='E13':
        c['camera_end_direction']=o.get('camera_end')==('up','right','left')[index]
        c['back_faces_operator']=o.get('back_faces_operator') is True
        c['physical_stand_support']=o.get('stand_supported') is True
    elif task=='E14':
        initial=o.get('initial_top_to_bottom');final=o.get('final_top_to_bottom')
        valid=_unique(initial,4) and _unique(final,4) and set(initial)==set(final)
        c['four_original_layers']=valid
        if valid:
            expected=([initial[1],initial[0],initial[2],initial[3]],[initial[0],initial[2],initial[1],initial[3]],initial[::-1])[index]
            c['top_indexed_reordering']=final==expected
            c['physical_support_chain']=_chain(o,expected[::-1])
    elif task=='E15':
        initial=o.get('initial');final=o.get('final');valid=_pose_map(initial,2) and _pose_map(final,2) and set(initial)==set(final)
        c['two_original_objects']=valid
        if valid:
            names=list(initial);other={names[0]:names[1],names[1]:names[0]}
            c['position_swap_or_preservation']=all(_distance(final[n]['xy'],initial[other[n] if index in (0,2) else n]['xy'])<=POSITION_TOLERANCE_M for n in names)
            c['orientation_swap_or_preservation']=all(_angle(final[n]['yaw_deg'],initial[other[n] if index in (1,2) else n]['yaw_deg'])<=ANGLE_TOLERANCE_DEG for n in names)
            c['physical_support']=_members(o.get('supported'),names)
    elif task=='E16':
        initial=o.get('initial');final=o.get('final');valid=_pose_map(initial,3) and _pose_map(final,3) and set(initial)==set(final)
        c['three_original_objects']=valid
        c['operator_frame_defined']=o.get('reference_frame')=='operator_far_left'
        if valid:
            names=list(initial);ci=[sum(initial[n]['xy'][a] for n in names)/3 for a in (0,1)];cf=[sum(final[n]['xy'][a] for n in names)/3 for a in (0,1)]
            c['relative_positions']=all(_distance([final[n]['xy'][a]-cf[a] for a in (0,1)],[(initial[n]['xy'][a]-ci[a])*(-1 if index==2 and a==0 else 1) for a in (0,1)])<=POSITION_TOLERANCE_M for n in names)
            c['individual_orientations']=all(_angle(final[n]['yaw_deg'],initial[n]['yaw_deg']+(90 if index==1 else 0))<=ANGLE_TOLERANCE_DEG for n in names)
            c['all_objects_in_tray']=_members(o.get('in_tray'),names) and _members(o.get('supported_in_tray'),names)
    elif task=='E17':
        objects={f'{color}_{shape}' for color in ('blue','green') for shape in ('square','triangle')}
        expected={n:('upper' if (n.startswith('blue') if index==0 else n.endswith('triangle') if index==1 else True) else 'lower') for n in objects}
        c['fixed_shelf_assignment']=o.get('layers')==expected
        c['correct_layer_support']=o.get('support_layers')==expected
    elif task=='E19':
        colors=(('yellow','white','red'),('red','yellow','white'),('white','red','yellow'))[index]
        expected=dict(zip(('sprite_bottle','water_bottle','cola_bottle'),colors))
        c['cap_identity_mapping']=o.get('cap_for_bottle')==expected
        c['caps_cover_mouths']=_members(o.get('seated'),expected)
        c['physical_cap_contacts']=all(_contact(o,bottle,'cap_'+color) for bottle,color in expected.items())
    elif task=='E20':
        colors=o.get('chip_colors');initial=o.get('initial_zone_members');final=o.get('zone_members');expected=dict(circle='yellow',square='red',triangle='blue')
        valid=isinstance(colors,Mapping) and bool(colors) and all(isinstance(k,str) and v in ('yellow','red','blue') for k,v in colors.items()) and isinstance(initial,Mapping) and isinstance(final,Mapping) and set(initial)==set(final)==set(expected)
        c['chip_and_zone_evidence']=valid
        if valid:
            old=[x for ids in initial.values() for x in ids];used=[x for ids in final.values() for x in ids]
            c['source_initial_counts']=all(_unique(initial[z],0 if z=='square' else 1) and all(x in colors and colors[x]==color for x in initial[z]) for z,color in expected.items()) and len(set(old))==len(old)
            c['pure_color_total_counts']=all(_unique(final[z],index+2) and all(x in colors and colors[x]==color for x in final[z]) for z,color in expected.items()) and len(set(used))==len(used)
            c['unused_chips_unmoved']=set(used)<=set(colors) and _members(o.get('unmoved_unused'),set(colors)-set(used))
            c['placed_chips_supported']=_members(o.get('supported'),set(used))
    elif task=='E21':
        order=(['red','yellow','blue','green'],['red','green','blue','yellow'],['green','blue','yellow','red'])[index]
        slots=['top_left','top_right','bottom_left','bottom_right'];expected=dict(zip(order,slots));events=_placement_events(o.get('placement_events'))
        c['terminal_cell_mapping']=o.get('cells')==expected
        c['first_released_placement_sequence']=events is not None and [e['object'] for e in events]==order and [e['target'] for e in events]==slots
        c['all_four_supported']=_members(o.get('supported'),order)
    elif task=='E22':
        order=(('red','green','blue'),('green','blue','red'),('blue','red','green'))[index]
        c['car_local_frame']=o.get('reference_frame')=='car'
        c['car_side_mapping']=o.get('car_sides')==dict(zip(('front','left','right'),order))
        c['all_blocks_supported']=_members(o.get('supported'),SOURCE_COLORS)
    elif task=='E23':
        order=(('red','green','blue'),('red','blue','green'),('blue','green','red'))[index]
        expected=dict(zip(order,('high','middle','low')));branches=o.get('branch_for_cup');levels=o.get('branch_levels')
        valid=isinstance(branches,Mapping) and set(branches)==set(SOURCE_COLORS) and isinstance(levels,Mapping)
        c['branch_level_assignment']=valid and all(isinstance(branches[cup],str) and levels.get(branches[cup])==level for cup,level in expected.items())
        c['mouth_over_branch']=_members(o.get('mouth_contains_branch'),SOURCE_COLORS)
        c['branch_contacts']=valid and all(_contact(o,cup,branches[cup]) for cup in SOURCE_COLORS)
    elif task=='E24':
        order=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[index]
        events=_placement_events(o.get('placement_events'));last_step=max((e['step'] for e in o['placement_events']),default=-1) if events is not None else -1
        c['first_insertion_sequence']=events is not None and [e['object'] for e in events]==order and all(e['target']=='box' for e in events)
        c['three_cups_inside']=_members(o.get('in_box'),SOURCE_COLORS) and _members(o.get('supported_in_box'),SOURCE_COLORS)
        if o.get('inference_rule_profile')!='e24-yarn-insertion-v1':
            c['source_upright_layout']=_members(o.get('upright'),SOURCE_COLORS) and o.get('left_to_right')==order
        c['lid_closed_after_insertions']=o.get('lid_closed') is True and type(o.get('lid_close_step'))is int and last_step>=0 and o['lid_close_step']>last_step
    elif task=='E25':
        names=['spoon','knife','fork']
        regions=dict.fromkeys(names,'far') if index<2 else dict(knife='left',spoon='right',fork='right')
        handles=dict.fromkeys(names,('plate','away_from_plate','operator')[index])
        c['plate_relative_regions']=o.get('regions')==regions
        c['handle_directions']=o.get('handle_toward')==handles
        c['utensil_relative_order']=(o.get('far_left_to_right')==names if index<2 else o.get('right_inner_to_outer')==['spoon','fork'])
        c['utensils_supported']=_members(o.get('supported'),names)
    elif task=='E27':
        regions=(dict(fork='left',spoon='right'),dict(spoon='left',fork='right'),dict(spoon='left',fork='left'))[index]
        c['plate_relative_sides']=o.get('regions')==regions
        c['handles_toward_operator']=o.get('handle_toward')==dict(spoon='operator',fork='operator')
        c['left_inner_outer']=(index!=2 or o.get('left_inner_to_outer')==['spoon','fork'])
        c['outside_plate']=_members(o.get('outside_plate'),['spoon','fork'])
        c['utensils_supported']=_members(o.get('supported'),['spoon','fork'])
    elif task=='E28':
        selected=({'yellow_rectangle'},{'white_yellow_round'},{'yellow_rectangle','white_yellow_round'})[index]
        c['food_selection']=_members(o.get('in_plate'),selected) and _members(o.get('outside_plate'),{'yellow_rectangle','white_yellow_round'}-selected)
        c['food_support']=_members(o.get('supported_in_plate'),selected)
        traces=o.get('transport_samples');c['spatula_transport']=isinstance(traces,Mapping) and set(traces)==selected and all(_transport(traces[n],n) for n in selected)
        c['original_food_face_preserved']=_members(o.get('same_visible_face'),selected)
    elif task=='E29':
        expected=(list(range(1,9)),list(range(8,0,-1)),list(range(1,9))+list(range(8,0,-1)))[index]
        events=o.get('strike_events');valid=_seq(events) and len(events)==len(expected);prior_end=-1
        if valid:
            for event,target in zip(events,expected):
                valid=valid and isinstance(event,Mapping) and event.get('tool')=='mallet' and type(event.get('key'))is int and event['key']==target and type(event.get('step'))is int and type(event.get('release_step'))is int and event['step']>prior_end and event['release_step']>event['step'] and _force(event.get('contact_impulse'))
                if not valid:break
                prior_end=event['release_step']
        c['actual_mallet_contact_sequence_with_separation']=bool(valid)
    elif task=='E30':
        opened=o.get('opened')
        c['drawer_states']=(isinstance(opened,Mapping) and all(type(v)is bool for v in opened.values())
                            and opened==({'upper':True,'lower':False},{'upper':False,'lower':True},{'upper':True,'lower':True})[index])
        joints=o.get('joint_displacements_m');valid=isinstance(joints,Mapping) and set(joints)=={'upper','lower'} and all(_number(v) and v>=0 for v in joints.values())
        # Thresholds distinguish visibly open vs closed; never require equal extension.
        expected=({'upper':True,'lower':False},{'upper':False,'lower':True},{'upper':True,'lower':True})[index]
        c['measured_joint_states']=valid and all((v>=.015 if expected[k] else v<=.005) for k,v in joints.items())
    elif task=='E31':
        c['container_relation']=o.get('relation')==('bowl_in_plate','plate_on_bowl','plate_on_bowl')[index]
        c['bowl_up']=o.get('bowl_up') is True
        c['plate_face_orientation']=o.get('plate_up') is (index!=2)
        c['containment_or_rim_coverage']=o.get('contained_or_covering') is True
        c['real_bowl_plate_contact']=_contact(o,'bowl','plate')
    elif task=='E32':
        # The clutter-delivery task has no geometric label shortcut: the
        # selected identity must be the only object that moved and the final
        # delivery board must contain that same identity.  Keep this check
        # explicit so a legacy ``released/stable`` pair cannot pass by itself.
        target=('sprite_bottle','pink_cube','cola_bottle')[index]
        c['selected_identity_delivered']=_members(o.get('delivered'),[target])
        c['only_selected_object_moved']=_members(o.get('moved_objects'),[target])
    elif task=='E33':
        target=('sprite_bottle','cola_bottle','fanta_bottle')[index];all_bottles=o.get('all_bottles');valid=_unique(all_bottles,5) and { 'sprite_bottle','cola_bottle','fanta_bottle'}<=set(all_bottles)
        c['five_source_bottles']=valid
        c['only_selected_bottle_in_bin']=_members(o.get('in_bin'),[target])
        c['other_bottles_on_table']=valid and _members(o.get('on_table'),set(all_bottles)-{target})
        c['selected_bottle_supported_in_bin']=_members(o.get('supported_in_bin'),[target])
    elif task=='E34':
        target=('knife','spoon','fork')[index]
        c['selected_handle_in_cell']=o.get('handle_in_cell')=={target:'top_left'}
        c['selected_utensil_supported']=_members(o.get('supported'),[target])
    elif task=='E35':
        order=(['large','medium','small'],['small','medium','large'],['large','small','medium'])[index]
        c['size_support_order']=o.get('bottom_to_top')==order
        c['real_support_chain']=_chain(o,order)
    elif task=='E36':
        selected=o.get('in_box');valid=_unique(selected,index+1)
        c['total_ball_count']=valid
        c['ball_support']=valid and _members(o.get('supported_in_box'),selected)
    elif task=='E37':
        selected=({'left'},{'right'},{'left','right'})[index];records=o.get('screw_records')
        c['source_initial_fasteners']=_members(o.get('initial_fastened'),['left','right'])
        c['selected_fasteners_separated']=_members(o.get('separated'),selected)
        c['unselected_fasteners_retained']=_members(o.get('remaining_fastened'),{'left','right'}-selected)
        c['driver_contact_and_thread_motion']=isinstance(records,Mapping) and set(records)==selected and all(_screw_record(records[n]) for n in selected)
    elif task=='E38':
        order=(['red','green','blue'],['red','blue','green'],['blue','green','red'])[index]
        c['color_layer_order']=o.get('bottom_to_top')==order
        c['same_rightmost_post']=o.get('post_for_ring')==dict.fromkeys(SOURCE_COLORS,'rightmost')
        c['all_holes_threaded']=_members(o.get('threaded'),SOURCE_COLORS)
        c['real_support_chain']=_chain(o,order,'rightmost')
    elif task=='E39':
        ref=o.get('reference_order');initial=o.get('initial_order');final=o.get('final_order');ry=o.get('reference_yaws');iy=o.get('initial_yaws')
        valid=_unique(ref,3) and _members(initial,ref) and _members(final,ref) and isinstance(ry,Mapping) and isinstance(iy,Mapping) and set(ry)==set(iy)==set(ref) and all(_number(x) for x in [*ry.values(),*iy.values()])
        c['reference_and_initial_evidence']=valid
        if valid:
            c['required_order_and_preserved_attribute']=final==(initial if index==1 else ref)
            c['required_yaws_and_preserved_attribute']=_yaw_mapping(o.get('final_yaws'),iy if index==0 else ry)
            c['all_objects_supported']=_members(o.get('supported'),ref)
    elif task=='E40':
        selected=({'circle','cross'},{'square','triangle'},{'circle','triangle','cross'})[index];records=o.get('clip_records')
        c['selected_marker_edges']=_members(o.get('clipped_markers'),selected)
        valid=isinstance(records,Mapping) and set(records)==selected and all(_clip_record(records[n]) for n in selected)
        c['opening_release_and_two_jaw_contacts']=valid
        c['distinct_physical_clips']=valid and len({records[n]['clip_id'] for n in selected})==len(selected)
    elif task=='E41':
        expected=(dict(short='long',medium='medium',long='short'),dict(short='short',medium='medium',long='long'),dict(short='long',medium='short',long='medium'))[index]
        c['length_pairing']=o.get('extensions')==expected
        gaps=o.get('end_gaps_m');axes=o.get('axis_alignment_cos')
        c['endpoints_adjacent']=isinstance(gaps,Mapping) and set(gaps)==set(expected) and all(_number(x) and 0<=x<=.015 for x in gaps.values())
        c['axes_collinear']=isinstance(axes,Mapping) and set(axes)==set(expected) and all(_number(x) and math.cos(math.radians(10))<=abs(x)<=1 for x in axes.values())
        c['extensions_supported']=_members(o.get('supported'),expected)
    elif task=='E42':
        target=('circle','triangle','square')[index];balls=o.get('ball_ids');positions=o.get('ball_regions');traces=o.get('push_samples')
        valid=_unique(balls,2)
        c['two_balls_in_paper_region']=valid and positions==dict.fromkeys(balls,target)
        c['balls_supported']=valid and _members(o.get('supported'),balls)
        records=o.get('native_fragmented_push_records')
        if records is not None:
            good=valid and isinstance(records,Mapping) and set(records)==set(balls)
            if good:
                for ball in balls:
                    record=records[ball]
                    good=good and isinstance(record,Mapping) and record.get('policy')=='fragmented_held_edge_net_v1' and record.get('no_forbidden_intervention')is True and _vector(record.get('net_delta_m'),3) and math.sqrt(sum(x*x for x in record['net_delta_m']))>.02 and type(record.get('valid_increment_count'))is int and record['valid_increment_count']>=2 and type(record.get('contact_fragment_count'))is int and record['contact_fragment_count']>=1 and record.get('delivery_chain_valid')is True and type(record.get('last_valid_transport_end_step'))is int and record['last_valid_transport_end_step']>=0
        else:
            good=valid and isinstance(traces,Mapping) and set(traces)==set(balls)
            if good:
                for ball in balls:
                    samples=traces[ball]
                    good=good and _steps(samples) and all(s.get('tool')=='spatula_edge' and _vector(s.get('pos'),3) and _force(s.get('edge_contact_force')) and s.get('tool_held') is True and s.get('hand_contact') is False and s.get('table_supported') is True for s in samples) and _distance(samples[0]['pos'],samples[-1]['pos'])>.02
        c['actual_edge_push']=bool(good)
    elif task=='E43':
        c['released_contact_deflected_path_crosses_paper']=_guided_path(o,('circle','triangle','square')[index])
    elif task=='E44':
        from .crease_motion import contact_driven_motion
        angle=o.get('dihedral_angle_deg');valid=_number(angle) and 0<angle<180
        c['angle_category']=valid and ((80<=angle<=100) if index==0 else (100<angle<180) if index==1 else (0<angle<80))
        c['base_panel_on_table']=_force(o.get('base_table_contact_force'))
        c['no_independent_support']=o.get('external_support_contacts')==[]
        samples=o.get('fold_samples');trace_ok=_steps(samples,3) and all(_number(s.get('angle_deg')) and _number(s.get('hand_contact_force')) and s['hand_contact_force']>=0 for s in samples)
        from .crease_motion import PASSIVE_GUIDE_POLICY,PASSIVE_GUIDE_SCHEMAS,passive_guided_motion
        passive=o.get('native_passive_crease_fixture',{})
        passive_ok=(isinstance(passive,Mapping)and passive.get('policy')==PASSIVE_GUIDE_POLICY
                    and passive.get('schema')in PASSIVE_GUIDE_SCHEMAS and passive.get('final_fixture_contacts')==[] and passive_guided_motion(samples))if trace_ok else False
        if isinstance(passive,Mapping)and passive.get('schema')in PASSIVE_GUIDE_SCHEMAS:
            c['no_independent_support']=c['no_independent_support']and passive.get('final_fixture_contacts')==[]
        c['contact_driven_crease_motion']=trace_ok and abs(samples[-1]['angle_deg']-samples[0]['angle_deg'])>=5 and (contact_driven_motion(samples)or passive_ok) and samples[-1]['hand_contact_force']==0 and valid and abs(samples[-1]['angle_deg']-angle)<=1
    elif task=='E45':
        target=('circle','triangle','square')[index];balls=o.get('initial_in_cup');records=o.get('exit_events');valid=_unique(balls,3)
        c['three_original_balls']=valid
        c['all_in_selected_compartment']=valid and o.get('ball_compartments')==dict.fromkeys(balls,target)
        c['cup_empty']=o.get('in_cup')==[]
        c['cup_returned_to_table']=o.get('cup_on_table') is True and o.get('cup_released') is True
        c['receiver_support']=valid and _members(o.get('supported_in_compartment'),balls)
        good=valid and _seq(records) and len(records)==3 and all(isinstance(e,Mapping) for e in records)
        c['actual_cup_tilt_exit_events']=good and _members([e.get('ball') for e in records],balls) and all(type(e.get('step')) is int and e['step']>=0 and _number(e.get('cup_tilt_deg')) and 30<e['cup_tilt_deg']<=180 and e.get('cup_held') is True and e.get('crossed_cup_rim') is True and e.get('direct_hand_contact') is False and _force(e.get('previous_cup_contact_force')) for e in records)
    elif task=='E46':
        c['yellow_block_target']=o.get('block_region')==('circle','triangle','square')[index]
        c['final_paper_support']=o.get('paper_supported') is True
        c['spatula_transport']=_transport(o.get('transport_samples'),'yellow_block')
    elif task=='E47':
        colors=o.get('initial_face_colors');valid=isinstance(colors,Mapping) and set(colors)==set(CARDS) and all(v in ('red','black') for v in colors.values()) and {colors['card1'],colors['card2']}=={'red','black'}
        c['initial_card_identities']=valid
        selected=({n for n in CARDS[:2] if colors[n]==('red','black')[index]} if index<2 else set(CARDS[:2])) if valid else set()
        c['only_front_two_flipped']=_members(o.get('flipped'),CARDS[:2]) and _members(o.get('face_down'),CARDS[2:])
        c['selected_face_color_in_box']=valid and _members(o.get('in_box'),selected)
        c['selected_cards_supported']=valid and _members(o.get('supported_in_box'),selected)
    elif task=='E48':
        selected=CARDS[:index+1];remaining=CARDS[index+1:];slots=o.get('slot_for_card')
        c['left_prefix_flipped']=_members(o.get('flipped'),selected) and _members(o.get('face_down'),remaining)
        c['all_selected_in_slot']=_members(o.get('in_slot'),selected)
        c['same_physical_slot']=isinstance(slots,Mapping) and set(slots)==set(selected) and all(isinstance(x,str) and x for x in slots.values()) and len(set(slots.values()))==1
        c['actual_slot_insertions']=_members(o.get('physically_inserted'),selected)
    elif task=='E49':
        destinations=(('green','blue','red'),('green','red','blue'),('red','blue','green'))[index]
        c['first_three_flipped']=_members(o.get('flipped'),CARDS[:3])
        c['original_index_to_tray']=o.get('tray_for_card')==dict(zip(CARDS[:3],destinations))
        c['remaining_two_untouched']=_members(o.get('untouched'),CARDS[3:])
        c['selected_cards_supported']=_members(o.get('supported'),CARDS[:3])
    elif task=='E50':
        c['original_card_flipped']=o.get('card_flipped') is True
        c['selected_tray']=o.get('card_tray')==('green','blue','red')[index]
        c['clip_transport_with_two_jaw_contacts']=_transport(o.get('transport_samples'),'card',tool='binder_clip',clamp=True)
        sequence=o.get('clip_sequence')
        c['clip_open_close_mechanism']=_clip_record(sequence)
        trace=o.get('transport_samples')
        steps=[o.get(k) for k in ('card_flip_step','card_release_step','clip_return_step')]
        c['flip_grip_transport_release_return_sequence']=(all(type(s)is int and s>=0 for s in steps)
            and _clip_record(sequence) and _steps(trace)
            and steps[0]<sequence['samples'][0]['step']<=sequence['samples'][-1]['step']<=trace[0]['step']
            and trace[-1]['step']<steps[1]<=steps[2])
        c['card_released_in_tray']=o.get('card_released') is True and o.get('tray_supported') is True
        c['clip_returned_to_table']=o.get('clip_on_table') is True and _contact(o,'binder_clip','table')
    else:
        raise NotImplementedError(task)


__all__=['check_task','POSITION_TOLERANCE_M','ANGLE_TOLERANCE_DEG']
