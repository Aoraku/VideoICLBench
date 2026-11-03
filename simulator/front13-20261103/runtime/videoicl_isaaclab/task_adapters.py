"""Task-specific physical recipes. No fallback template is a completed task.

Dimensions below are half extents, matching the native USD recipe schema.
These adapters are separate from the frozen eight anchor recipes.
"""
import copy
import math
import random
from .task_recipes import RECIPES, adapt as adapt_remaining


IMPLEMENTED = {'F02', 'F03', 'F04', 'F05', 'F07', 'F12'} | set(RECIPES)


def box(size, pos=(0., 0., 0.)):
    return dict(type='box', size=list(size), pos=list(pos), quat=[1., 0., 0., 0.])


def adapt(spec):
    if spec['id'] in RECIPES:
        return adapt_remaining(spec)
    spec = copy.deepcopy(spec)
    if spec['id'] not in IMPLEMENTED:
        return spec
    if spec['id'] == 'F02':
        _cup(spec)
    elif spec['id'] == 'F05':
        _ranking(spec)
    elif spec['id'] in ('F03', 'F07'):
        _sorting(spec)
    elif spec['id'] == 'F04':
        _egg_holder(spec)
    elif spec['id'] == 'F12':
        _cards(spec)
    spec.update(status='task-specific-pending-physx', task_revision=2,
                task_adapter='native-compound-v1', demo_status='pending_recording')
    spec.pop('variant_permutation',None)
    spec['scene_template'].update(object_count=len(spec['objects']),
                                  zone_count=len(spec['zones']))
    return spec


def _cup(spec):
    # A genuinely hollow square cup: separate floor, four walls and three
    # handle bars. Nothing caps the cavity or attaches the cup to its pad.
    obj = copy.deepcopy(spec['objects'][0])
    hx, hy, hz, wall = .027, .027, .034, .004
    shapes = [box([hx, hy, .003], [0, 0, -hz+.003]),
              box([wall/2, hy, hz], [-hx+wall/2, 0, 0]),
              box([wall/2, hy, hz], [hx-wall/2, 0, 0]),
              box([hx-wall, wall/2, hz], [0, -hy+wall/2, 0]),
              box([hx-wall, wall/2, hz], [0, hy-wall/2, 0]),
              box([.008, .003, .003], [hx+.006, 0, .016]),
              box([.008, .003, .003], [hx+.006, 0, -.016]),
              box([.003, .003, .019], [hx+.014, 0, 0])]
    obj.update(id='cup', kind='cup', role='movable', size=[.044, hy, hz],
               inner_size=[hx-wall, hy-wall, hz-.006],
               collision_shapes=shapes, density=450, label='square cup')
    obj['xy'] = [-.055 if spec['seed'] == 0 else -.025, .18]
    spec['objects'] = [obj]
    spec['zones'] = [dict(id=f'target{i}', xy=[x, .075],
                          half_size=[.050, .050], marker=i, kind='marked_zone')
                     for i, x in enumerate((-.105, 0., .105))]
    chosen = 'ABC'.index(spec['variant'])
    spec['goals'] = [dict(type='place', object='cup', target=f'target{chosen}',
                          require_upright=True, minimum_up_cos=.97)]
    spec['scene_template']['asset_family'] = 'hollow_square_cup'
    spec['scene_template']['goal_adapter'] = 'place'


def _ranking(spec):
    # Five genuinely different sizes, with one neutral material. Size (not
    # color or a hidden ID) is the visible rank to transfer from the demo.
    rng = random.Random(502 + spec['seed'])
    source_columns = [-.16, -.08, 0., .08, .16]
    rng.shuffle(source_columns)
    objects = []
    for rank in range(5):
        half = .017 + rank*.003
        obj = copy.deepcopy(spec['objects'][0])
        obj.update(id=f'block{rank}', kind='box', label=f'size rank {rank+1}',
                   role='movable', size=[half]*3,
                   xy=[source_columns[rank], .205+rng.uniform(-.006, .006)],
                   rgba=[.12, .30, .85, 1.],
                   collision_shapes=[box([half]*3)])
        objects.append(obj)
    spec['objects'] = objects
    spec['zones'] = [dict(id=f'slot{i}', xy=[x, .075], half_size=[.036, .040],
                          marker=None, kind='ordered_slot')
                     for i, x in enumerate((-.16, -.08, 0., .08, .16))]
    order = {'A': [0, 1, 2, 3, 4], 'B': [4, 3, 2, 1, 0],
             'C': [2, 1, 3, 0, 4]}[spec['variant']]
    spec['goals'] = [dict(type='place', object=f'block{rank}', target=f'slot{slot}')
                     for slot, rank in enumerate(order)]
    spec['action_budget'] = 1600
    spec['expert_action_budget'] = 1200
    spec['scene_template']['asset_family'] = 'five_size_ranking'
    spec['scene_template']['goal_adapter'] = 'place'


def _sorting(spec):
    """Three open bins; six shape pieces or a full 3x3 attribute cross."""
    arx=spec['embodiment']=='arx_x5'
    sign=-1 if arx else 1
    rng=random.Random(307+spec['seed'])
    # Fixtures are genuinely hollow compounds: the base is one collider,
    # followed by four walls. The floor contact is required by the evaluator.
    fixtures=[];zones=[]
    for i,x in enumerate((-.15,0.,.15)):
        y=sign*.075;hx,hy=.067,.063
        parts=[([hx,hy,.003],[x,y,.803]),
               ([.003,hy,.025],[x-hx+.003,y,.825]),
               ([.003,hy,.025],[x+hx-.003,y,.825]),
               ([hx-.006,.003,.025],[x,y-hy+.003,.825]),
               ([hx-.006,.003,.025],[x,y+hy-.003,.825])]
        for size,pos in parts:
            fixtures.append(dict(type='box',size=size,xy=pos[:2],z=pos[2]))
        zones.append(dict(id=f'bin{i}',xy=[x,y],half_size=[hx-.006,hy-.006],
                          marker=i,kind='open_bin',surface_z=.806))
    objects=[];assignments=[]
    count=9 if spec['id']=='F07' else 6
    columns=[-.10,0.,.10]
    colors=([.85,.12,.1,1.],[.12,.7,.22,1.],[.12,.3,.85,1.])
    for i in range(count):
        shape=i%3;color=i//3 if count==9 else 0
        obj=copy.deepcopy(spec['objects'][0])
        h=.016
        if shape==0:
            collision=[dict(type='cylinder',size=[h,h],pos=[0,0,0],quat=[1,0,0,0])]
        elif shape==1:
            vertices=[]
            for z in (-h,h):
                for k in range(3):vertices.extend([h*math.cos(k*2*math.pi/3),h*math.sin(k*2*math.pi/3),z])
            faces=[0,2,1,3,4,5,0,1,4,0,4,3,1,2,5,1,5,4,2,0,3,2,3,5]
            collision=[dict(type='mesh',mesh_data=dict(vertices=vertices,faces=faces),
                            pos=[0,0,0],quat=[1,0,0,0])]
        else:collision=[box([h,h,h])]
        cross=(color+shape)%3
        obj.update(id=f'piece{i}',kind=('cylinder','triangle','box')[shape],
                   role='movable',label=f'color {color}; shape {shape}',
                   size=[h,h,h],xy=[columns[i%3]+rng.uniform(-.004,.004),
                                   sign*(.19+(i//3)*.075)],
                   rgba=colors[color] if count==9 else [.85,.85,.85,1.],
                   collision_shapes=collision,density=450)
        if count==9:obj['marker']=cross
        objects.append(obj)
        if count==6:
            target=(shape+'ABC'.index(spec['variant']))%3
        else:
            target={'A':color,'B':shape,'C':cross}[spec['variant']]
        assignments.append(target)
    used=[0,0,0];goals=[]
    for obj,target in zip(objects,assignments):
        slot=used[target];used[target]+=1
        x,y=zones[target]['xy']
        offset=([-.025,.025][slot] if count==6 else [-.035,0.,.035][slot])
        goals.append(dict(type='place',object=obj['id'],target=f'bin{target}',
                          required_support=f'fixture{target*5}',
                          placement_xy=[x+offset,y],surface_z=.806))
    spec.update(objects=objects,zones=zones,fixtures=fixtures,goals=goals,
                expert_action_budget=1600,action_budget=1600,
                attribute_member_table={f'bin{i}':[o['id'] for o,t in zip(objects,assignments) if t==i]
                                        for i in range(3)})
    spec['scene_template']['asset_family']='open_bin_shape_sorting' if count==6 else 'color_shape_cross_sorting'
    spec['scene_template']['goal_adapter']='place'


def _egg_holder(spec):
    """Three eggs and a physical 2x3 holder with six open recesses."""
    angle=0. if spec['seed']==0 else .18
    origin=[0.,.095] if spec['seed']==0 else [.012,.10]
    def xy(x,y):
        return [origin[0]+x*math.cos(angle)-y*math.sin(angle),
                origin[1]+x*math.sin(angle)+y*math.cos(angle)]
    fixtures=[];zones=[]
    for row,y in enumerate((-.037,.037)):
        for col,x in enumerate((-.072,0.,.072)):
            center=xy(x,y);base=len(fixtures)
            fixtures.append(dict(type='cylinder',size=[.027,.003],xy=center,z=.805))
            # A segmented circular wall preserves a real hole. No convex
            # hull of the entire holder fills the six cavities.
            for k in range(16):
                a=k*2*math.pi/16
                fixtures.append(dict(type='box',size=[.004,.0055,.014],
                                     xy=xy(x+.025*math.cos(a),y+.025*math.sin(a)),
                                     z=.822,quat=[math.cos((a+angle)/2),0,0,math.sin((a+angle)/2)]))
            zones.append(dict(id=f'cell{row}{col}',xy=center,half_size=[.023,.023],
                              marker=None,kind='egg_recess',surface_z=.808,
                              floor_fixture=f'fixture{base}'))
    # The tray's near-side direction mark is visible in both seeds.
    zones.append(dict(id='holder_direction',xy=xy(0.,-.078),half_size=[.018,.012],
                      marker=1,kind='direction_marker'))
    vertices=[];faces=[];slices=24;bands=12
    for j in range(bands+1):
        lat=-math.pi/2+j*math.pi/bands
        radius=.0175*math.cos(lat)*(1-.12*math.sin(lat))
        for k in range(slices):
            a=k*2*math.pi/slices
            vertices.extend([radius*math.cos(a),radius*math.sin(a),.025*math.sin(lat)])
    for j in range(bands):
        for k in range(slices):
            a=j*slices+k;b=j*slices+(k+1)%slices;c=a+slices;d=b+slices
            faces.extend([a,b,d,a,d,c])
    objects=[]
    for i,x in enumerate((-.075,0.,.075)):
        obj=copy.deepcopy(spec['objects'][0])
        obj.update(id=f'egg{i}',kind='egg',role='movable',label='egg',
                   size=[.018,.018,.025],xy=[x,.235 if spec['seed']==0 else .245],
                   rgba=[.85,.85,.85,1.],density=600,
                   collision_shapes=[dict(type='mesh',mesh_data=dict(vertices=vertices,faces=faces),
                                          pos=[0,0,0],quat=[1,0,0,0])])
        objects.append(obj)
    chosen={'A':['cell00','cell01','cell02'],
            'B':['cell10','cell11','cell12'],
            'C':['cell00','cell02','cell11']}[spec['variant']]
    goals=[]
    for obj,cell in zip(objects,chosen):
        zone=next(z for z in zones if z['id']==cell)
        goals.append(dict(type='place',object=obj['id'],target=cell,
                          required_support=zone['floor_fixture'],
                          require_upright=True,minimum_up_cos=.90))
    spec.update(objects=objects,zones=zones,fixtures=fixtures,goals=goals,
                holder_frame=dict(origin=origin,yaw=angle),
                expert_action_budget=1000)
    spec['scene_template']['asset_family']='three_eggs_six_open_recesses'
    spec['scene_template']['goal_adapter']='place'


def _cards(spec):
    """Three thick cards and ordinary open-groove name-card holders."""
    fixtures=[];zones=[];objects=[]
    colors=([.85,.12,.10,1.],[.12,.70,.22,1.],[.12,.30,.85,1.])
    columns=(-.085,0.,.085)
    offset=0. if spec['seed']==0 else .009
    for i,x in enumerate(columns):
        floor=len(fixtures)
        parts=[([.034,.040,.004],[x+offset,.075,.804]),
               ([.012,.040,.015],[x+offset-.020,.075,.823]),
               ([.012,.040,.015],[x+offset+.020,.075,.823])]
        fixtures.extend(dict(type='box',size=size,xy=p[:2],z=p[2]) for size,p in parts)
        zones.append(dict(id=f'holder{i}',xy=[x+offset,.075],
                          half_size=[.008,.038],marker=None,
                          surface_z=.808,floor_fixture=f'fixture{floor}',kind='card_slot'))
        obj=copy.deepcopy(spec['objects'][0])
        obj.update(id=f'card{i}',kind='card',role='movable',label=('red','green','blue')[i],
                   size=[.006,.032,.043],xy=[x,.205 if spec['seed']==0 else .22],
                   rgba=colors[i],density=450,collision_shapes=[box([.006,.032,.043])])
        objects.append(obj)
    order={'A':[0,1,2],'B':[1,2,0],'C':[2,0,1]}[spec['variant']]
    goals=[dict(type='place',object=f'card{color}',target=f'holder{slot}',
                require_upright=True,minimum_up_cos=.985,
                required_support=zones[slot]['floor_fixture'],
                clearance_margin=.0005,bottom_tolerance=.004)
           for slot,color in enumerate(order)]
    spec.update(objects=objects,zones=zones,fixtures=fixtures,goals=goals,
                expert_action_budget=1000)
    spec['scene_template']['asset_family']='thick_cards_open_groove_holders'
    spec['scene_template']['goal_adapter']='place'
