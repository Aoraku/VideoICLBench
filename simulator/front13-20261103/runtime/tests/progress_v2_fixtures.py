"""Full frozen-panel semantic examples and physical-evidence rejection tests.

Fixtures describe measured outcomes; they are not simulation demonstrations and
must never be passed to a production evaluator as native evidence.
"""
from copy import deepcopy
import math



COLORS=['red','green','blue']
SHAPES=['square','triangle','circle']
CARDS=[f'card{i}' for i in range(1,6)]


def chain(order,base='table'):
    return [[base,order[0]],*[[a,b] for a,b in zip(order,order[1:])]]


def transport(obj,clamp=False):
    trace=[]
    for step,x in enumerate([0.,.02,.04],10):
        sample=dict(step=step,object=obj,object_pos=[x,0.,.95],tool='binder_clip' if clamp else 'spatula',tool_held=True,direct_hand_contact=False)
        sample.update(dict(jaw_contact_forces=[.2,.2],between_jaws=True) if clamp else dict(support_contact_force=.2))
        trace.append(sample)
    return trace


def clip(clip_id='clip1'):
    return dict(clip_id=clip_id,samples=[
        dict(step=4,jaw_gap_m=.001,joint_pos=0.,handle_contact_force=0.),
        dict(step=5,jaw_gap_m=.01,joint_pos=.01,handle_contact_force=.2),
        dict(step=6,jaw_gap_m=.003,joint_pos=.002,handle_contact_force=0.,handles_released=True,left_jaw_contact_force=.1,right_jaw_contact_force=.1,edge_between_jaws=True)])


def placed(objects,targets):
    return [dict(object=n,target=t,step=i+1,released=True,support_contact=True) for i,(n,t) in enumerate(zip(objects,targets))]


def evidence(task,variant):
    """Independent source examples with distinct initial poses/identities."""
    i='ABC'.index(variant)
    o=dict(released=True,stable=True)
    rgb=[['red','green','blue'],['green','blue','red'],['blue','red','green']][i]
    height=[['red','green','blue'],['red','blue','green'],['blue','green','red']][i]
    objects=[f'{c}_{s}' for c in COLORS for s in SHAPES]
    if task=='E01':
        selected=[['burger','fries'],['burger','drink'],['fries','drink']][i]
        o.update(in_plate=selected,outside_plate=list({'burger','fries','drink'}-set(selected)),supported_in_plate=selected)
    elif task=='E02': o.update(bottom_to_top=rgb,support_edges=chain(rgb))
    elif task=='E03': o.update(outside_to_inside=rgb,upright=COLORS,nested_pairs=[f'{a}>{b}' for a,b in zip(rgb,rgb[1:])],contacts=list(zip(rgb,rgb[1:])))
    elif task=='E04': o.update(placements=dict(zip(COLORS,[['square','triangle','circle'],['triangle','square','circle'],['square','circle','triangle']][i])),supported=COLORS)
    elif task=='E05': o.update(placements=dict(zip(['cube','sphere','triangle'],[['square','circle','triangle'],['circle','triangle','square'],['triangle','square','circle']][i])),supported=['cube','sphere','triangle'])
    elif task=='E06':
        cells=[['left_far','left_middle','left_near'],['right_far','right_middle','right_near'],['left_far','left_near','right_middle']][i]
        o.update(ball_to_cell=dict(zip(['x','y','z'],cells)),seated=['x','y','z'])
    elif task=='E07': o.update(far_to_near=[[1,2,3,4,5],[5,4,3,2,1],[3,2,1,4,5]][i],nonoverlapping=True,supported_ranks=[1,2,3,4,5])
    elif task=='E08': o.update(toward_label=dict(zip(['left','right'],[['toe','toe'],['heel','heel'],['toe','heel']][i])),in_box=['left','right'],supported_in_box=['left','right'])
    elif task=='E09':
        groups=([[f'{c}_{s}' for s in SHAPES] for c in COLORS],[[f'{c}_{s}' for c in COLORS] for s in SHAPES],[['red_circle','green_triangle','blue_square'],['red_triangle','green_square','blue_circle'],['red_square','green_circle','blue_triangle']])[i]
        o.update(groups=groups,supported=objects)
    elif task=='E10':
        selected=[n for n in objects if (n.startswith('red_') if i==0 else n.endswith('_square') if i==1 else n.startswith('red_') or n.endswith('_square'))]
        o.update(on_post=selected,threaded=selected,supported_on_post=selected,off_post=list(set(objects)-set(selected)))
    elif task=='E11': o.update(initial_grid=[['a','b'],['c','d']],final_grid=[[['a','b'],['c','d']],[['c','a'],['d','b']],[['b','a'],['d','c']]][i],supported=['a','b','c','d'])
    elif task=='E12': o.update(charger_to_slot=dict(zip(['c1','c2'],[[1,2],[3,4],[1,4]][i])),physically_inserted=['c1','c2'],supported=['c1','c2'])
    elif task=='E13': o.update(camera_end=['up','right','left'][i],back_faces_operator=True,stand_supported=True)
    elif task=='E14':
        final=[['b','a','c','d'],['a','c','b','d'],['d','c','b','a']][i]
        o.update(initial_top_to_bottom=['a','b','c','d'],final_top_to_bottom=final,support_edges=chain(final[::-1]))
    elif task=='E15':
        initial={'red':dict(xy=[0.,0.],yaw_deg=0.),'blue':dict(xy=[.2,.1],yaw_deg=90.)}
        final={n:dict(xy=initial[other if i in (0,2) else n]['xy'],yaw_deg=initial[other if i in (1,2) else n]['yaw_deg']) for n,other in [('red','blue'),('blue','red')]}
        o.update(initial=initial,final=final,supported=['red','blue'])
    elif task=='E16':
        initial={n:dict(xy=xy,yaw_deg=yaw) for n,xy,yaw in [('a',[.1,.1],10.),('b',[-.1,0.],80.),('c',[0.,-.1],-40.)]}
        final={n:dict(xy=[.4+(-1 if i==2 else 1)*v['xy'][0],.3+v['xy'][1]],yaw_deg=v['yaw_deg']+(90 if i==1 else 0)) for n,v in initial.items()}
        o.update(initial=initial,final=final,reference_frame='operator_far_left',in_tray=list(initial),supported_in_tray=list(initial))
    elif task=='E17':
        layers={f'{c}_{s}':('upper' if (c=='blue' if i==0 else s=='triangle' if i==1 else True) else 'lower') for c in ['blue','green'] for s in ['square','triangle']}
        o.update(layers=layers,support_layers=layers)
    elif task=='E18': o.update(delivered=[COLORS[i]],in_drawer=[c for c in COLORS if c!=COLORS[i]],drawer_closed=True)
    elif task=='E19':
        caps=dict(zip(['sprite_bottle','water_bottle','cola_bottle'],[['yellow','white','red'],['red','yellow','white'],['white','red','yellow']][i]))
        o.update(cap_for_bottle=caps,seated=list(caps),contacts=[[n,'cap_'+c] for n,c in caps.items()])
    elif task=='E20':
        colors={f'{c}{n}':c for c in ['yellow','red','blue'] for n in range(5)}
        zones={z:[f'{c}{n}' for n in range(i+2)] for z,c in [('circle','yellow'),('square','red'),('triangle','blue')]}
        used=[n for ns in zones.values() for n in ns]
        o.update(chip_colors=colors,initial_zone_members=dict(circle=['yellow0'],square=[],triangle=['blue0']),zone_members=zones,unmoved_unused=list(set(colors)-set(used)),supported=used)
    elif task=='E21':
        order=[['red','yellow','blue','green'],['red','green','blue','yellow'],['green','blue','yellow','red']][i];slots=['top_left','top_right','bottom_left','bottom_right']
        o.update(cells=dict(zip(order,slots)),placement_events=placed(order,slots),supported=order)
    elif task=='E22': o.update(car_sides=dict(zip(['front','left','right'],rgb)),reference_frame='car',supported=COLORS)
    elif task=='E23': o.update(branch_for_cup=dict(zip(height,['b1','b2','b3'])),branch_levels=dict(b1='high',b2='middle',b3='low'),mouth_contains_branch=COLORS,contacts=list(zip(height,['b1','b2','b3'])))
    elif task=='E24': o.update(placement_events=placed(rgb,['box']*3),in_box=COLORS,supported_in_box=COLORS,upright=COLORS,left_to_right=rgb,lid_closed=True,lid_close_step=10)
    elif task=='E25': o.update(regions=dict.fromkeys(['spoon','knife','fork'],'far') if i<2 else dict(knife='left',spoon='right',fork='right'),handle_toward=dict.fromkeys(['spoon','knife','fork'],['plate','away_from_plate','operator'][i]),far_left_to_right=['spoon','knife','fork'],right_inner_to_outer=['spoon','fork'],supported=['spoon','knife','fork'])
    elif task=='E26':
        events=[]
        for side,count in zip(['left','right'],[(9,1),(1,9),(10,0)][i]):
            for _ in range(count):
                step=len(events)+1;events.extend([dict(side=side,event='press',step=step,contact=True),dict(side=side,event='release',step=step+1)])
        o['bell_events']=events
    elif task=='E27': o.update(regions=[dict(fork='left',spoon='right'),dict(spoon='left',fork='right'),dict(spoon='left',fork='left')][i],handle_toward=dict(spoon='operator',fork='operator'),left_inner_to_outer=['spoon','fork'],outside_plate=['spoon','fork'],supported=['spoon','fork'])
    elif task=='E28':
        selected=[['yellow_rectangle'],['white_yellow_round'],['yellow_rectangle','white_yellow_round']][i]
        o.update(in_plate=selected,outside_plate=list({'yellow_rectangle','white_yellow_round'}-set(selected)),supported_in_plate=selected,transport_samples={n:transport(n) for n in selected},same_visible_face=selected)
    elif task=='E29':
        keys=[list(range(1,9)),list(range(8,0,-1)),list(range(1,9))+list(range(8,0,-1))][i]
        o['strike_events']=[dict(tool='mallet',key=k,step=3*n+1,release_step=3*n+2,contact_impulse=.1) for n,k in enumerate(keys)]
    elif task=='E30':
        opened=[dict(upper=True,lower=False),dict(upper=False,lower=True),dict(upper=True,lower=True)][i]
        o.update(opened=opened,joint_displacements_m={k:.08 if v else 0. for k,v in opened.items()})
    elif task=='E31': o.update(bowl_up=True,plate_up=i!=2,relation='bowl_in_plate' if i==0 else 'plate_on_bowl',contacts=[['bowl','plate']],contained_or_covering=True)
    elif task=='E32':
        target=['sprite_bottle','pink_cube','cola_bottle'][i];o.update(delivered=[target],moved_objects=[target])
    elif task=='E33':
        target=['sprite_bottle','cola_bottle','fanta_bottle'][i];all_bottles=['sprite_bottle','cola_bottle','fanta_bottle','water_bottle','tea_bottle']
        o.update(in_bin=[target],all_bottles=all_bottles,on_table=[n for n in all_bottles if n!=target],supported_in_bin=[target])
    elif task=='E34':
        target=['knife','spoon','fork'][i];o.update(handle_in_cell={target:'top_left'},supported=[target])
    elif task=='E35':
        order=[['large','medium','small'],['small','medium','large'],['large','small','medium']][i];o.update(bottom_to_top=order,support_edges=chain(order))
    elif task=='E36':
        balls=['x','y','z'][:i+1];o.update(in_box=balls,supported_in_box=balls)
    elif task=='E37':
        selected=[['left'],['right'],['left','right']][i]
        trace=[dict(step=n,angle_rad=.2*n,axial_m=.003*n,thread_overlap_m=.005-.003*n,driver_contact_force=.2,tip_engagement_depth_m=.002,tool_axis_alignment_cos=1.,separated=n==2) for n in range(3)]
        o.update(initial_fastened=['left','right'],separated=selected,remaining_fastened=list({'left','right'}-set(selected)),screw_records={n:deepcopy(trace) for n in selected})
    elif task=='E38': o.update(bottom_to_top=height,post_for_ring=dict.fromkeys(COLORS,'rightmost'),threaded=COLORS,support_edges=chain(height,'rightmost'))
    elif task=='E39':
        ref=['red','blue','black'];initial=['blue','black','red'];ry=dict(red=0.,blue=90.,black=180.);iy=dict.fromkeys(ref,270.)
        o.update(reference_order=ref,initial_order=initial,final_order=initial if i==1 else ref,reference_yaws=ry,initial_yaws=iy,final_yaws=iy if i==0 else ry,supported=ref)
    elif task=='E40':
        markers=[['circle','cross'],['square','triangle'],['circle','triangle','cross']][i];o.update(clipped_markers=markers,clip_records={m:clip('clip_'+m) for m in markers})
    elif task=='E41': o.update(extensions=dict(zip(['short','medium','long'],[['long','medium','short'],['short','medium','long'],['long','short','medium']][i])),end_gaps_m=dict.fromkeys(['short','medium','long'],.001),axis_alignment_cos=dict.fromkeys(['short','medium','long'],1.),supported=['short','medium','long'])
    elif task=='E42':
        balls=['a','b'];trace=[dict(step=n,tool='spatula_edge',pos=[n*.03,0.,.82],edge_contact_force=.1,tool_held=True,hand_contact=False,table_supported=True) for n in range(3)]
        o.update(ball_ids=balls,ball_regions=dict.fromkeys(balls,['circle','triangle','square'][i]),supported=balls,push_samples={n:deepcopy(trace) for n in balls})
    elif task=='E43':
        target=['circle','triangle','square'][i]
        o.update(release=dict(source='fixed_launcher',step=0,initially_held=True,released=True),region_bounds={s:dict(min=[.9,.9] if s==target else [3.,3.],max=[1.1,1.1] if s==target else [4.,4.]) for s in SHAPES},trajectory=[dict(step=n,pos=pos,hand_contact_force=0.,guide_contact_force=.2 if n==1 else 0.,guide_held=True) for n,pos in enumerate([[-1.,0.,.82],[0.,0.,.82],[.5,.5,.82],[1.,1.,.82],[1.5,1.5,.82]])])
    elif task=='E44':
        angle=[90.,125.,55.][i];o.update(dihedral_angle_deg=angle,base_table_contact_force=1.,external_support_contacts=[],fold_samples=[dict(step=0,angle_deg=175.,hand_contact_force=0.),dict(step=1,angle_deg=angle,hand_contact_force=.2),dict(step=2,angle_deg=angle,hand_contact_force=0.)])
    elif task=='E45':
        balls=['a','b','c'];o.update(initial_in_cup=balls,ball_compartments=dict.fromkeys(balls,['circle','triangle','square'][i]),in_cup=[],cup_on_table=True,cup_released=True,supported_in_compartment=balls,exit_events=[dict(ball=n,step=j,cup_tilt_deg=100.,cup_held=True,crossed_cup_rim=True,direct_hand_contact=False,previous_cup_contact_force=.2) for j,n in enumerate(balls)])
    elif task=='E46': o.update(block_region=['circle','triangle','square'][i],paper_supported=True,transport_samples=transport('yellow_block'))
    elif task=='E47':
        selected=[['card1'],['card2'],['card1','card2']][i];o.update(initial_face_colors=dict(zip(CARDS,['red','black','red','black','red'])),flipped=CARDS[:2],face_down=CARDS[2:],in_box=selected,supported_in_box=selected)
    elif task=='E48':
        selected=CARDS[:i+1];o.update(flipped=selected,face_down=CARDS[i+1:],in_slot=selected,slot_for_card=dict.fromkeys(selected,'slot1'),physically_inserted=selected)
    elif task=='E49': o.update(flipped=CARDS[:3],tray_for_card=dict(zip(CARDS[:3],[['green','blue','red'],['green','red','blue'],['red','blue','green']][i])),untouched=CARDS[3:],supported=CARDS[:3])
    elif task=='E50': o.update(card_flipped=True,card_tray=['green','blue','red'][i],transport_samples=transport('card',True),clip_sequence=clip(),card_released=True,tray_supported=True,clip_on_table=True,contacts=[['binder_clip','table']],card_flip_step=1,card_release_step=15,clip_return_step=20)
    else: raise AssertionError(task)
    return o




def progress_example(task,variant):
    """Synthetic predicates for unit tests; never native-physics acceptance."""
    o=evidence(task,variant);i='ABC'.index(variant)
    identities=set(str(x) for x in range(1,6))
    def collect(x):
        if isinstance(x,str):identities.add(x)
        elif isinstance(x,dict):
            for k,v in x.items():collect(k);collect(v)
        elif isinstance(x,(list,tuple)):
            for v in x:collect(v)
    collect(o);identities.update(['cup','card','binder_clip','upper','lower','cap_yellow','cap_white','cap_red'])
    o['progress_physical']={n:dict(released=True,stable=True,supported=True) for n in identities}
    initial=None
    if task=='E03':o['outer_supported']=[o['outside_to_inside'][0]];o['progress_nested_pairs']=list(o['nested_pairs'])
    if task=='E07':
        o['nonoverlap_pairs']={f'{a}|{b}':True for a in range(1,6) for b in range(1,6) if a!=b}
        initial=deepcopy(o);initial['far_to_near']=o['far_to_near'][::-1]
    if task=='E09':initial=deepcopy(o);initial['groups']=[[],[],[]]
    if task=='E11':o['object_cells']={n:[r,c] for r,row in enumerate(o['final_grid']) for c,n in enumerate(row)}
    if task=='E18':o.update(drawer_opened_for_access=True,drawer_closed_after_delivery=True)
    if task=='E22':o['object_sides']={n:s for s,n in o['car_sides'].items()}
    if task=='E29':o['pending_strikes']=[]
    if task=='E37':o['screw_progress']={n:True for n in o['separated']}
    if task=='E39':o['reference_changed']=False
    if task=='E41':o['extension_object_ids']={row:obj for row,obj in o['extensions'].items()};o['progress_supported_rows']=list(o['supported'])
    if task=='E43':
        o['release']['release_id']='release-1';o['launcher_moved']=False
        for s in o['trajectory']:s['release_id']='release-1'
    objects={'E28':list(o.get('in_plate',[])),'E42':list(o.get('ball_ids',[])),'E45':list(o.get('initial_in_cup',[])),'E46':['yellow_block'],'E50':['card']}.get(task,[])
    if objects:o['progress_causal']={n:dict(transport_achieved=True,delivery_chain_valid=True,poured_exit_valid=True,clip_grip_achieved=True,clip_return_after_delivery=True) for n in objects}
    return o,initial
