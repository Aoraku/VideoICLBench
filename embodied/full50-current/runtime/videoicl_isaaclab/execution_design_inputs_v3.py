"""Source-design input changes, applied only during fresh world construction.

No live-state writes. Layout authoring is not physics acceptance: every output
remains release-blocked until its native positive/negative controls pass.
"""
from copy import deepcopy
import hashlib
import json
import math
from .execution_design import build_task_contract, metadata, WORKFLOW_TASKS

REVISION = 'embodied50-execution-v3-20261102'
RE_TASKS = frozenset(('E12','E29','E37','E44','E47','E48','E49','E50'))
# Identity-preserving permutations of actual source object positions. Groups
# are explicit so containers, tools, fixtures and supporting bodies do not get
# exchanged with cargo of incompatible geometry.
LAYOUT_GROUPS = {
    'E02': ('blocks',), 'E03': ('cups',), 'E06': ('balls',),
    'E08': ('shoes',), 'E10': ('pieces',), 'E11': ('blocks',),
    'E18': ('balls',), 'E19': ('bottles','caps'), 'E21': ('blocks',),
    'E23': ('cups',), 'E24': ('cups',), 'E25': ('cutlery',),
    'E27': ('cutlery',), 'E28': ('foods',), 'E33': ('bottles',),
    'E34': ('cutlery',), 'E36': ('balls',), 'E38': ('rings',),
    'E42': ('balls',),
}
SPECIAL = frozenset(('E04','E05','E07','E13','E14','E15','E16','E22',
                     'E26','E30','E31','E32','E35','E40','E41','E43','E45','E46'))
IMPLEMENTED = frozenset(LAYOUT_GROUPS) | SPECIAL | RE_TASKS | WORKFLOW_TASKS
assert IMPLEMENTED == {f'E{n:02}' for n in range(1,51)}


def condition_capability_v3(task, condition):
    if condition not in metadata(task, revision=REVISION)['support_mask']:
        return dict(implemented=False, reason='unsupported_by_source_design')
    return dict(implemented=True, adapter='execution_workflow_scenes' if task in WORKFLOW_TASKS else 'explicit_inputs_v3',
                physics_validated=False, release_ready=False)


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def physical_input_signature(spec):
    """Exclude render-only properties and run identity, include actual targets."""
    fields=('objects','zones','mechanisms','semantic','goals')
    if ((spec.get('id')=='E44'and spec.get('semantic',{}).get('execution_design_fold_fixture'))
            or(spec.get('id')=='E47'and spec.get('semantic',{}).get('execution_design_flip_fixture'))):fields+=('fixtures',)
    return _hash({k:spec.get(k)for k in fields})


def _cycle(items, seed, fields=('xy',)):
    if len(items) < 2:
        raise ValueError('An input permutation needs at least two objects')
    offset = 1 + seed % (len(items)-1)
    old = [{k:deepcopy(o[k]) for k in fields} for o in items]
    for i,o in enumerate(items):o.update(deepcopy(old[(i+offset)%len(items)]))
    return offset


def _group(spec, name):
    ids=spec['semantic']['groups'][name];objects={o['id']:o for o in spec['objects']}
    return [objects[n] for n in ids]


def _update_grid_mapping(spec):
    objects=_group(spec,'blocks')
    # Operator coordinates: far=+X, left=+Y, same as native grid().
    rows=[sorted(objects,key=lambda o:o['xy'][0],reverse=True)[:2],
          sorted(objects,key=lambda o:o['xy'][0],reverse=True)[2:]]
    grid=[[o['id'] for o in sorted(row,key=lambda o:o['xy'][1],reverse=True)]for row in rows]
    if spec['variant']=='B':grid=[list(row)for row in zip(*grid[::-1])]
    elif spec['variant']=='C':grid=[row[::-1]for row in grid]
    cells=spec['semantic']['grid_cells'];mapping={grid[r][c]:cells[r][c]for r in range(2)for c in range(2)}
    spec['semantic']['mapping']=mapping
    for goal in spec['goals']:
        if goal.get('object') in mapping:goal['target']=mapping[goal['object']]


def _update_layout_transfer(spec):
    pieces=_group(spec,'pieces');tray=next(o for o in spec['objects']if o['id']=='tray')
    center=[sum(o['xy'][i]for o in pieces)/len(pieces)for i in range(2)]
    targets={}
    for o in pieces:
        rel=[o['xy'][i]-center[i]for i in range(2)]
        if spec['variant']=='C':rel[0]*=-1
        targets[o['id']]=dict(xy=[tray['xy'][i]+rel[i]for i in range(2)],
                              yaw=o.get('yaw',0)+(math.pi/2 if spec['variant']=='B'else 0))
    spec['semantic']['targets']=targets
    for z in spec['zones']:
        name=z['id'].removesuffix('_target')
        if name in targets:z['xy']=deepcopy(targets[name]['xy'])
    for g in spec['goals']:
        if g.get('object') in targets:g['yaw']=targets[g['object']]['yaw']


def _update_stack_goals(spec):
    objects={o['id']:o for o in spec['objects']};zones={z['id']:z for z in spec['zones']}
    if spec['id']=='E14':
        initial=sorted(objects,key=lambda n:objects[n]['bottom'],reverse=True)
        desired=initial[:]
        if spec['variant']=='A':desired[0],desired[1]=desired[1],desired[0]
        elif spec['variant']=='B':desired[1],desired[2]=desired[2],desired[1]
        else:desired.reverse()
        goals=[dict(type='place',object=n,target='stage_'+n)for n in initial]
        height=.8;previous='table'
        for n in desired[::-1]:
            zones['rebuild_'+n]['surface_z']=height
            goals.append(dict(type='place',object=n,target='rebuild_'+n,required_support=previous))
            height+=2*objects[n]['size'][2];previous=n
        spec['goals']=goals
    else:
        height=.8
        for g in spec['goals']:
            zones[g['target']]['surface_z']=height
            height+=2*objects[g['object']]['size'][2]


def _update_swap_goals(spec):
    objects=_group(spec,'blocks');other={objects[0]['id']:objects[1],objects[1]['id']:objects[0]}
    zones={z['id']:z for z in spec['zones']};targets={}
    for o in objects:
        target=other[o['id']]if spec['variant']in('A','C')else o
        orientation=other[o['id']]if spec['variant']in('B','C')else o
        zones[o['id']+'_target']['xy']=deepcopy(target['xy']);targets[o['id']]=orientation['yaw']
    for g in spec['goals']:
        # Temporary staging is not the final swapped orientation.
        if g['target']!='temporary':g['yaw']=targets[g['object']]
        else:g['yaw']=next(o['yaw']for o in objects if o['id']==g['object'])


def _input(spec, seed):
    task=spec['id'];objects={o['id']:o for o in spec['objects']};sem=spec['semantic']
    change=dict(kind='task_specific_input', operations=[])
    ops=change['operations']
    if task in LAYOUT_GROUPS:
        for group in LAYOUT_GROUPS[task]:
            members=_group(spec,group);offset=_cycle(members,seed)
            ops.append(dict(kind='object_position_derangement',group=group,offset=offset,objects=[o['id']for o in members]))
        if task=='E11':_update_grid_mapping(spec)
        # E06 moves the whole six-hole fixture slightly while retaining its
        # topology and operator-left reference; balls were separately shuffled.
        if task=='E06':
            dx=(-.025,.025,.04)[seed%3];objects['eggtray']['xy'][0]+=dx
            for z in spec['zones']:z['xy'][0]+=dx
            # Native E06 cells are expressed in task coordinates. Move their
            # physical cavity floors with the actual fixture, not only the
            # expert's placement zones; retain every radius/floor threshold.
            for cell in sem['cells'].values():cell['center'][0]+=dx
            ops.append(dict(kind='tray_initial_position',dx=dx))
    elif task in ('E04','E05'):
        movable=[o for o in spec['objects']if o.get('role')!='fixture']
        regions=[z for z in spec['zones']if z.get('shape')in ('triangle','square','circle')]
        if len(movable)!=3 or len(regions)!=3:raise ValueError('Expected three pieces and graph regions')
        offset=_cycle(movable,seed);_cycle(regions,seed)
        ops.append(dict(kind='object_and_graph_region_derangement',offset=offset))
    elif task in ('E07','E35'):
        members=_group(spec,'blocks');factor=(.86,.91,.96)[seed%3]
        _cycle(members,seed)
        for o in members:
            o['size']=[x*factor for x in o['size']]
            o['mass']*=factor**3
        if task=='E35':_update_stack_goals(spec)
        ops.append(dict(kind='new_ordered_sizes_and_layout',scale=factor,sizes={o['id']:o['size']for o in members}))
    elif task=='E13':
        objects['phone']['yaw']+=math.pi/2
        objects['phone']['xy'][0]=(-.06,.06,.09)[seed%3]
        ops.append(dict(kind='phone_initial_pose',yaw=objects['phone']['yaw'],xy=objects['phone']['xy']))
    elif task=='E14':
        offset=_cycle(_group(spec,'blocks'),seed,('bottom',))
        _update_stack_goals(spec)
        ops.append(dict(kind='new_tower_layer_input',offset=offset))
    elif task in ('E15','E16'):
        members=_group(spec,'blocks'if task=='E15'else'pieces')
        _cycle(members,seed)
        for i,o in enumerate(members):o['yaw']+=((seed+i)%3+1)*math.pi/2
        if task=='E16':_update_layout_transfer(spec)
        else:_update_swap_goals(spec)
        ops.append(dict(kind='new_position_orientation_input',poses={o['id']:dict(xy=o['xy'],yaw=o['yaw'])for o in members}))
    elif task=='E22':
        car=objects['car'];angle=(math.pi/2,math.pi,-math.pi/2)[seed%3];car['yaw']+=angle
        _cycle(_group(spec,'blocks'),seed)
        for z in spec['zones']:
            x,y=[z['xy'][i]-car['xy'][i]for i in range(2)]
            z['xy']=[car['xy'][0]+math.cos(angle)*x-math.sin(angle)*y,
                     car['xy'][1]+math.sin(angle)*x+math.cos(angle)*y]
        ops.append(dict(kind='new_car_reference_heading_and_block_layout',heading_delta=angle))
    elif task=='E26':
        cards=dict(left=1+seed%5,right=1+(seed//5)%5)
        for side,value in cards.items():
            zone=next(z for z in spec['zones']if z['id']==side+'_digit');zone['digit']=value
        sem['digit_cards']=cards;sem['execution_design_bell_rule']='paired-digit-correspondence-v3'
        ops.append(dict(kind='new_digit_pair',digits=cards))
    elif task=='E30':
        cabinet=spec['mechanisms'][0]
        from .execution_design_cabinet_instances import apply_cabinet_instance
        ops.append(apply_cabinet_instance(cabinet,seed))
        # Source board_5 is 97.94mm long along body X, wider than the
        # Panda 80mm opening. Pinch its 2.742mm body-Y cross-section.
        for point in sem['handle_points'].values():point['pinch_axis_local']=[0.,1.,0.]
        # Same physical input for ABC: both are above closed and below open.
        # A/B must really close the non-target and open the target; C opens both.
        from .execution_design_drawers import SCHEMA
        values={side:(.007,.009,.011)[(seed+i)%3]for i,side in enumerate(('lower','upper'))}
        positions={sem['joint_roles'][side]['joint']:sem['joint_roles'][side]['closed']+sem['joint_roles'][side]['direction']*v for side,v in values.items()}
        cabinet['initial_joint_positions']=positions
        sem['execution_design_drawer_input']=dict(schema=SCHEMA,normalized_displacements=values)
        ops.append(dict(kind='new_initial_half_open_drawers',joint_positions=positions,normalized_displacements=values))
    elif task=='E31':
        _cycle([objects['plate'],objects['bowl']],seed)
        support=objects[sem['support']]
        for z in spec['zones']:
            if z['id']=='support_center':z['xy']=deepcopy(support['xy'])
        ops.append(dict(kind='bowl_plate_position_swap'))
    elif task=='E32':
        # The former far column at x=.25 placed the small cube about .903m
        # horizontally from the nearest Panda base. Its public approach
        # stalled at x=.177 before acquisition. Keep a cluttered new input,
        # but use a nearer source column; category and delivery rule stay fixed.
        # This changes only fresh I inputs (and their paired E environment).
        nearer=[]
        for name in ('sprite_bottle','cola_bottle','pink_cube'):
            obj=objects[name]
            if obj['xy'][0]>.20:
                before=deepcopy(obj['xy']);obj['xy']=[.16,-.28]
                nearer.append(dict(object=name,before=before,after=deepcopy(obj['xy'])))
        _cycle([objects[n]for n in ('sprite_bottle','cola_bottle','pink_cube')],seed)
        ops.append(dict(kind='target_instances_in_new_clutter_positions',objects=['sprite_bottle','cola_bottle','pink_cube'],nearer_source_column=nearer,native_reachability_requires_validation=True))
    elif task=='E40':
        from .execution_design_clip_instances import apply_clip_instances
        ops.append(apply_clip_instances(spec,seed))
        _cycle(spec['mechanisms'],seed,('position',))
        ops.append(dict(kind='clip_instance_initial_arrangement'))
    elif task=='E41':
        # New physical plank lengths, with all metric endpoint/goal metadata
        # recomputed. Rank identities alone must never hide stale geometry.
        lengths=(dict(short=.068,medium=.096,long=.132),dict(short=.072,medium=.100,long=.138),dict(short=.064,medium=.092,long=.128))[seed%3]
        for o in spec['objects']:
            rank=o['id'].split('_')[0];length=lengths[rank]
            old=o['size'][0]*2;o['size'][0]=length/2;o['mass']*=length/old
            sem['lengths'][o['id']]=length
            field='end_points'if o['id'].endswith('_ref')else'start_points'
            sem[field][o['id']][0]=(-1 if field=='end_points'else 1)*length/2
        _cycle(_group(spec,'extensions'),seed)
        zones={z['id']:z for z in spec['zones']}
        for ref,piece in sem['mapping'].items():
            r,p=objects[ref],objects[piece]
            zones[piece+'_target']['xy']=[r['xy'][0]-r['size'][0]-p['size'][0]-.001,r['xy'][1]]
        ops.append(dict(kind='new_rank_preserving_lengths',lengths=lengths))
    elif task=='E43':
        # Shift launch assembly together so ball still starts supported by its
        # actual release mechanism, but the incoming line and targets change.
        dy=(-.035,.035,.055)[seed%3]
        for n in ('launcher','gate','ball'):objects[n]['xy'][1]+=dy
        # The gate is constrained to the world, so its anchor must follow the
        # actual assembly rather than pulling it back to the source Y origin.
        for joint in spec.get('joints',[]):
            if joint.get('child')=='gate' and not joint.get('parent'):
                joint['anchor0'][1]+=dy
        sem['launcher']['guide_intercept_task'][1]+=dy
        _cycle(spec['zones'],seed)
        ops.append(dict(kind='new_ball_start_and_region_layout',launch_y_shift=dy,
            assembly_joints_sha256=_hash(spec.get('joints',[]))))
    elif task=='E45':
        dx=(-.065,.065,.085)[seed%3]
        for n in ['cup',*sem['groups']['balls']]:objects[n]['xy'][0]+=dx
        sem['tool_expert']['park_point_task'][0]+=dx
        ops.append(dict(kind='new_cup_and_contained_ball_start',dx=dx))
    elif task=='E46':
        objects['yellow_block']['xy'][0]=(-.065,.065,.085)[seed%3]
        ops.append(dict(kind='new_cargo_initial_position',xy=objects['yellow_block']['xy']))
    else:raise NotImplementedError(task)
    return change


def apply_execution_inputs_v3(base_spec, *, condition, seed):
    task=base_spec['id']
    if task in WORKFLOW_TASKS:raise ValueError('Use the workflow builder')
    if base_spec.get('inference_generalization'):raise ValueError('Canonical source assets required, not old G1/G2')
    if base_spec.get('seed') != 0:raise ValueError('V3 input adapters require canonical source seed 0')
    contract=build_task_contract(task,base_spec['variant'],seed,condition,revision=REVISION)
    spec=deepcopy(base_spec)
    if task=='E23':
        from .execution_design_e23_geometry import calibrate_source_branches
        calibrate_source_branches(spec)
    if task=='E10':
        from .execution_design_e10_collision import configure_spec
        configure_spec(spec)
    if task=='E43':
        from .execution_design_e43_geometry import calibrate_gate
        calibrate_gate(spec)
    import os
    if task=='E43' and os.environ.get('VIC_ENGINEERING_E43_ANALYTIC_BALL')=='1':
        from .execution_design_e43_ball import configure_spec
        configure_spec(spec)
    if task=='E46' and os.environ.get('VIC_ENGINEERING_E46_SOURCE_COOKING')=='1':
        from .execution_design_e46_cooking import configure_spec
        configure_spec(spec)
    if task=='E37' and os.environ.get('VIC_ENGINEERING_E37_SOURCE_SDF')=='1':
        from .execution_design_e37_cooking import configure_spec
        configure_spec(spec)
    if task=='E28' and os.environ.get('VIC_ENGINEERING_E28_SOURCE_SDF')=='1':
        from .execution_design_e28_cooking import configure_spec
        configure_spec(spec)
    if task=='E18' and os.environ.get('VIC_ENGINEERING_E18_SUPPORT')=='1':
        from .execution_design_e18_support import apply_support
        apply_support(spec)
    if task=='E24' and os.environ.get('VIC_ENGINEERING_E24_CLEAR_LID_LAYOUT')=='1':
        from .execution_design_e24_layout import apply_layout
        apply_layout(spec)
    if task=='E44':
        from .execution_design_e44_fixture import add_passive_folding_fixture
        add_passive_folding_fixture(spec)
    if task=='E47':
        from .execution_design_e47_fixture import add_passive_flip_fixture
        add_passive_flip_fixture(spec)
    if task in ('E47','E48','E49','E50')and os.environ.get('VIC_ENGINEERING_PRACTICAL_CARD_THICKNESS')=='1':
        from .execution_design_practical_cards import configure_spec
        configure_spec(spec)
    if task in ('E47','E48','E49','E50')and os.environ.get('VIC_ENGINEERING_PRACTICAL_CARD_SUPPORT')=='1':
        from .execution_design_practical_card_support import configure_spec
        configure_spec(spec)
    if task in ('E47','E48','E49','E50')and os.environ.get('VIC_ENGINEERING_THIN_COOKING_FIDELITY')=='1':
        from .execution_design_thin_cooking import configure_spec
        factor=os.environ.get('VIC_ENGINEERING_THIN_COLLISION_COORDINATES')
        configure_spec(spec,int(factor)if factor else None)
    if task=='E45':
        from .execution_design_e45_acceptance_geometry import bind
        bind(spec)
    canonical_signature=physical_input_signature(spec)
    fixed=condition=='R' or task in RE_TASKS
    changes=dict(kind='fixed_demo_input',semantic_seed=None)if fixed else _input(spec,seed)
    if not fixed and 26<=int(task[1:])<=50:
        from .execution_design_instances_v3 import apply_instance_variation
        instance_change=apply_instance_variation(spec,seed)
        if instance_change:changes['operations'].append(instance_change)
    if task=='E45' and os.environ.get('VIC_ENGINEERING_E45_ANALYTIC_BALLS')=='1':
        from .execution_design_e45_balls import configure_spec
        configure_spec(spec)
    if task=='E46' and condition=='I' and seed==4201:
        from .execution_design_e46_input_v2 import apply
        changes['operations'].append(apply(spec))
    if task=='E46' and os.environ.get('VIC_ENGINEERING_E46_EXACT_PARTITION')=='1':
        from .execution_design_e46_partition import configure_spec
        configure_spec(spec)
    paired_signature=physical_input_signature(spec)
    if not fixed and paired_signature==canonical_signature:
        raise ValueError(f'{task}: I must change a real input, not only metadata')
    if condition=='E':
        # Visual-only material: no replacement physics material, no rescaling,
        # no mirror/coordinate change, no rule-color recoloring.
        spec['table_visual']=dict(color=[.32,.43,.48],roughness=.8)
    from .execution_design_environment_v3 import environment_settings
    environment=environment_settings(task,condition)
    if environment is not None:spec['execution_environment']=environment
    spec.update(seed=seed,title=contract['title'],instruction=contract['instruction'],
                execution_design=contract['execution_design'],release_ready=False)
    spec['execution_design'].update(applied_input_changes=changes,
        paired_physical_input_sha256=paired_signature,
        environment_changes=(['table_visual','native_background_material','native_light_intensity'] if environment is not None else ['table_visual'])if condition=='E'else[],
        physical_acceptance_status='pending')
    if spec.get('e18_support_layout'):
        from .execution_design_e18_support import bind_identity
        bind_identity(spec)
    if spec.get('e24_lid_initial_layout'):
        from .execution_design_e24_layout import bind_identity
        bind_identity(spec)
    if task=='E43' and os.environ.get('VIC_ENGINEERING_E43_PASSIVE_RAIL')=='1':
        from .execution_design_e43_rail import configure_spec
        configure_spec(spec)
        spec['execution_design']['paired_physical_input_sha256'] = physical_input_signature(spec)
    if task == 'E40' and os.environ.get('VIC_ENGINEERING_E40_COLLISION_COORDINATES') == '1':
        from .execution_design_clip_collision_coordinates import configure_spec
        configure_spec(spec)
        spec['execution_design']['paired_physical_input_sha256'] = physical_input_signature(spec)
    if os.environ.get('VIC_ENGINEERING_THIN_CONTACT_SKIN_UM') == '50':
        from .engineering_thin_contact_skin import configure_spec
        configure_spec(spec)
        spec['execution_design']['paired_physical_input_sha256'] = physical_input_signature(spec)
    return spec


def initial_joint_positions(spec, mechanism, moving_names):
    """Validate explicit E30 reset before Isaac receives any initial positions."""
    if spec.get('id')!='E30' or spec.get('execution_design',{}).get('revision')!=REVISION:
        raise ValueError('Custom mechanism reset requires explicit E30 v3')
    values=mechanism['initial_joint_positions'];roles=spec['semantic']['joint_roles']
    if set(values)!={r['joint']for r in roles.values()} or not set(values)<=set(moving_names):
        raise ValueError('Initial positions must name exactly the actual drawer joints')
    result={n:0. for n in moving_names}
    for side,role in roles.items():
        value=values[role['joint']]
        if type(value)not in(int,float)or not math.isfinite(value):raise ValueError('Invalid drawer reset value')
        distance=(value-role['closed'])*role['direction']
        if not 0<=distance<=spec['semantic']['joint_motion'][side]['max_travel']:
            raise ValueError('Drawer reset outside physical travel')
        result[role['joint']]=float(value)
    return result
