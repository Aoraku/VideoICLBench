"""Dedicated rigid-body tasks for the remaining taxonomy.

All dimensions are metres in the unchanged task frame. Compounds are built
from convex parts: cavities, handles and slots are never convexified shut.
These are project-authored assets, not claims of imported benchmark assets.
"""
import copy
import math
import random

COLORS = ([.85,.12,.10,1.], [.12,.70,.22,1.], [.12,.30,.85,1.])
NEUTRAL = [.66,.69,.73,1.]


def qaxis(axis, angle):
    q=[math.cos(angle/2),0.,0.,0.];q[axis+1]=math.sin(angle/2);return q


def mul(a,b):
    w,x,y,z=a;v,i,j,k=b
    return [w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v]


def shape(kind, size, pos=(0,0,0), quat=(1,0,0,0), rgba=None):
    d=dict(type=kind,size=list(size),pos=list(pos),quat=list(quat))
    if rgba is not None:d.update(rgba=list(rgba),literal_rgba=True)
    return d


def box(size,pos=(0,0,0),**kw):return shape('box',size,pos,**kw)
def cylinder(radius,half,pos=(0,0,0),**kw):return shape('cylinder',[radius,half],pos,**kw)


def prop(name,kind,size,xy,color=NEUTRAL,parts=None,bottom=.805,yaw=0.,**kw):
    return dict(id=name,kind=kind,role='movable',label=name,rgba=list(color),
                size=list(size),xy=list(xy),yaw=yaw,bottom=bottom,density=450,
                collision_shapes=parts or [box(size)],color_mode='literal',**kw)


def zone(name,xy,half=(.045,.045),marker=None,z=.8):
    return dict(id=name,xy=list(xy),half_size=list(half),marker=marker,surface_z=z)


def pose(name,xy=None,z=None,yaw=None,**kw):
    g=dict(type='pose',object=name,**kw)
    if xy is not None:g['xy']=list(xy)
    if z is not None:g['z']=z
    if yaw is not None:g['yaw']=yaw
    return g


def keep(obj,**kw):return pose(obj['id'],obj['xy'],yaw=obj['yaw'],xy_tolerance=.018,**kw)


def ring(radius,height,wall=.004,z=0.,n=24,**kw):
    return [box([wall,math.pi*radius/n+.0004,height],
                [radius*math.cos(a),radius*math.sin(a),z],quat=qaxis(2,a),**kw)
            for a in [k*2*math.pi/n for k in range(n)]]


def vessel(name,xy,color=NEUTRAL,hx=.06,hy=.055,hz=.035,wall=.004,kind='tray',bottom=.805):
    parts=[box([hx,hy,.003],[0,0,-hz+.003]),
           box([wall,hy,hz],[-hx+wall,0,0]),box([wall,hy,hz],[hx-wall,0,0]),
           box([hx-2*wall,wall,hz],[0,-hy+wall,0]),box([hx-2*wall,wall,hz],[0,hy-wall,0])]
    return prop(name,kind,[hx,hy,hz],xy,color,parts,bottom=bottom,inner_size=[hx-2*wall,hy-2*wall,hz])


def fixed(s,parts,xy=(0,0),z=0.,color=NEUTRAL):
    """Add independently collidable static convex parts; return their IDs."""
    ids=[]
    for part in parts:
        p=copy.deepcopy(part);local=p.pop('pos',[0,0,0]);p['xy']=[xy[0]+local[0],xy[1]+local[1]];p['z']=z+local[2]
        p.setdefault('rgba',list(color));p['literal_rgba']=True;ids.append('fixture'+str(len(s['fixtures'])));s['fixtures'].append(p)
    return ids


def bin_at(s,name,xy,hx=.06,hy=.05,hz=.025,marker=None):
    v=vessel(name,xy,hx=hx,hy=hy,hz=hz,bottom=.8)
    ids=fixed(s,v['collision_shapes'],xy,.8+hz)
    s['zones'].append(zone(name,xy,(hx-.008,hy-.008),marker,.806))
    return ids[0]


def put(name,target,**kw):return dict(type='place',object=name,target=target,**kw)


def sequence(s,order,rules,key='sequence'):
    s.setdefault('event_rules',[]).extend(dict(r,key=key) for r in rules)
    s['goals'].append(dict(type='sequence',object=s['objects'][0]['id'],key=key,expected=list(order)))


def layout(s):
    """Mirror the task strip for the reference X5; retain source/target gap."""
    return -1 if s['embodiment']=='arx_x5' else 1


def _shoes(s):
    # Mirrored toe/instep compounds make left and right feet distinguishable.
    y=.24 if not s['seed'] else .26
    objects=[]
    for i,x in enumerate((-.075,.075)):
        side=-1 if i==0 else 1
        parts=[box([.030,.065,.007],[0,0,-.015]),box([.027,.035,.015],[0,-.022,0]),
               box([.030,.032,.012],[side*.004,.035,-.002]),
               cylinder(.024,.011,[side*.006,.055,-.003])]
        shoe=prop(('left','right')[i]+'_shoe','shoe',[.036,.082,.030],[x,y],NEUTRAL,parts,yaw=.3*(-1 if i else 1))
        shoe['visual_shapes']=[box([.018,.014,.001],[0,-.025,.016],rgba=[.12,.13,.15,1.]),
                              box([.022,.002,.002],[0,.005,.016],rgba=[.95,.95,.95,1.])]
        objects.append(shoe)
    floor=bin_at(s,'shoe_box',[0,.055],.115,.105,.018)
    # The brand tag is visible, independent of ABC, on the +Y edge.
    fixed(s,[box([.026,.007,.001])],[0,.163],.842,[.08,.08,.10,1.])
    yaws={'A':[0,0],'B':[math.pi,math.pi],'C':[0,math.pi]}[s['variant']]
    s['objects']=objects
    s['goals']=[pose(o['id'],[x,.055],yaw=yaw,xy_tolerance=.018,required_support=floor,minimum_up_cos=.96)
                for o,x,yaw in zip(objects,(-.055,.055),yaws)]


def _chargers(s):
    # Two pins enter two real rectangular wells. Socket cover is a grid of
    # separate solids, not a solid box with painted holes.
    parts=[box([.023,.021,.028]),box([.002,.004,.014],[-.009,0,-.041]),box([.002,.004,.014],[.009,0,-.041])]
    s['objects']=[prop('charger'+str(i),'charger',[.023,.021,.055],[x,.23],c,parts,bottom=.805)
                  for i,(x,c) in enumerate(zip((-.10,0,.10),([.04,.04,.05,1.],[.90,.9,.88,1.],COLORS[2])))]
    xy=[.012 if s['seed'] else 0,.065]
    # Wells +/-9mm X, clearance 1mm per side, bottom at .808.
    solids=[box([.050,.040,.003],[0,0,-.022]),
            box([.018,.04,.022],[-.032,0,0]),box([.018,.04,.022],[.032,0,0]),
            box([.006,.04,.022],[0,0,0]),box([.008,.015,.022],[-.009,-.025,0]),
            box([.008,.015,.022],[-.009,.025,0]),box([.008,.015,.022],[.009,-.025,0]),box([.008,.015,.022],[.009,.025,0])]
    floor=fixed(s,solids,xy,.833)[0]
    chosen='ABC'.index(s['variant'])
    s['goals']=[pose('charger'+str(chosen),xy,.866,yaw=0.,xy_tolerance=.0018,z_tolerance=.005,required_support=floor,minimum_up_cos=.995)]
    s['goals'] += [keep(o) for i,o in enumerate(s['objects']) if i!=chosen]


def _phone(s):
    x=.012 if s['seed'] else 0.;angle=math.radians(65)
    phone=prop('phone','phone',[.030,.060,.005],[-.08,.23],[.08,.08,.09,1.])
    phone['visual_shapes']=[box([.027,.053,.0006],[0,0,.0058],rgba=[.15,.35,.52,1.]),
                            box([.010,.0015,.0008],[0,.056,.0065],rgba=[.01,.01,.01,1.])]
    back=box([.075,.065,.004],[x,.065,.870],quat=qaxis(0,angle))
    ledge=box([.080,.010,.008],[x,.036,.811])
    support=fixed(s,[back,ledge])
    s['objects']=[phone]
    q=mul(qaxis(0,angle),qaxis(2,{'A':0,'B':math.pi/2,'C':-math.pi/2}[s['variant']]))
    # Screen faces the viewing side; earpiece moves with the actual phone.
    z=.870 if s['variant']=='A' else .845
    s['goals']=[pose('phone',[x,.049],z,quaternion=q,orientation_tolerance=.16,xy_tolerance=.025,z_tolerance=.018,support_any=support)]


def _tparts(color,scale=1.):
    return [box([scale*v for v in size],[scale*v for v in p],rgba=color)
            for size,p in [([.035,.012,.013],[0,.024,0]),([.012,.033,.013],[0,-.020,0])]]


def _swap(s):
    sign=layout(s);d=.008 if s['seed'] else 0
    starts=[[-.085+d,sign*.13],[.085+d,sign*.23]];yaws=[0.,math.pi/2]
    s['objects']=[prop('t'+str(i),'t_piece',[.035,.053,.013],xy,COLORS[i*2],_tparts(COLORS[i*2]),yaw=yaws[i]) for i,xy in enumerate(starts)]
    s['goals']=[pose(o['id'],starts[1-i] if s['variant'] in 'AC' else starts[i],
                     yaw=yaws[1-i] if s['variant'] in 'BC' else yaws[i],xy_tolerance=.016,minimum_up_cos=.97)
                for i,o in enumerate(s['objects'])]


def _correction(s):
    refs=[[-.12,.055],[0,.055],[.12,.055]];starts=[[-.12,.21],[.025,.21],[.12,.24]]
    intended=[[-.12,.20],[0,.20],[.12,.20]];initial_yaw=[math.pi/2,0.,-math.pi/2]
    s['objects']=[prop('tile'+str(i),'directed_tile',[.035,.053,.013],xy,COLORS[i],_tparts(COLORS[i]),yaw=initial_yaw[i]) for i,xy in enumerate(starts)]
    for i,xy in enumerate(refs):fixed(s,_tparts(COLORS[i]),xy,.812)
    # A visible destination outline, while the reference is a separate area.
    s['zones']=[zone('outline'+str(i),xy,(.035,.045)) for i,xy in enumerate(intended)]
    s['goals']=[pose(o['id'],intended[i] if s['variant'] in 'AC' else starts[i],yaw=0. if s['variant'] in 'BC' else initial_yaw[i],xy_tolerance=.012,minimum_up_cos=.97)
                for i,o in enumerate(s['objects'])]


def _relocation(s):
    sign=layout(s);source=[0,sign*.25];target=[.012 if s['seed'] else 0,sign*.065]
    local=[[-.065,-.015],[0,.025],[.065,-.015]]
    s['objects']=[prop('tile'+str(i),'directed_tile',[.021,.032,.008],[source[0]+p[0],source[1]+p[1]],COLORS[i],_tparts(COLORS[i],.6)) for i,p in enumerate(local)]
    fixed(s,[box([.125,.075,.001])],target,.801,[.24,.26,.28,1.])
    goals=[]
    for i,p in enumerate(local):
        x,y=p
        if s['variant']=='B':x,y=y,-x
        elif s['variant']=='C':x=-x
        goals.append(pose('tile'+str(i),[target[0]+x,target[1]+y],yaw=-math.pi/2 if s['variant']=='B' else 0.,xy_tolerance=.014,minimum_up_cos=.97))
    s['goals']=goals


def _basket(s):
    floor=bin_at(s,'basket',[0,.23],.145,.065,.035)
    s['objects']=[prop('item'+str(i),('bottle','toy','block')[i],[.020,.020,.025],[x,.23],COLORS[i],bottom=.807) for i,x in enumerate((-.09,0,.09))]
    s['zones'] += [zone('target'+str(i),[x,.055],(.048,.045),i) for i,x in enumerate((-.12,0,.12))]
    chosen='ABC'.index(s['variant'])
    s['goals']=[put('item'+str(chosen),'target'+str(chosen))]+[keep(o,required_support=floor) for i,o in enumerate(s['objects']) if i!=chosen]


def _caps(s):
    s['objects']=[];s['goals']=[]
    for i,x in enumerate((-.12,0,.12)):
        bottleparts=[cylinder(.024,.033),cylinder(.014,.010,[0,0,.041])]
        bottle=prop('bottle'+str(i),'bottle',[.024,.024,.051],[x,.075],COLORS[i],bottleparts,bottom=.805)
        # Open lower cap cavity, closed roof. Neck fits with 2mm clearance.
        parts=ring(.019,.012,.003)+[cylinder(.022,.003,[0,0,.012])]
        cap=prop('cap'+str(i),'cap',[.022,.022,.015],[x,.23],COLORS[i],parts,bottom=.805)
        s['objects'] += [bottle,cap]
    for i in range(3):
        j=(i+'ABC'.index(s['variant']))%3
        s['goals'].append(dict(type='relative_pose',object='cap'+str(i),target='bottle'+str(j),offset=[0,0,.042],tolerance=[.004,.004,.007],minimum_up_cos=.97,require_contact=True))
    s['goals'] += [keep(o) for o in s['objects'] if o['kind']=='bottle']


def _food(s):
    parts=[cylinder(.027,.009,[0,0,-.015],rgba=[.8,.43,.15,1.]),cylinder(.026,.005,rgba=[.24,.10,.04,1.]),cylinder(.028,.010,[0,0,.015],rgba=[.9,.62,.26,1.])]
    burger=prop('burger','burger',[.029,.029,.026],[-.11,.24],[.8,.5,.2,1.],parts)
    friesparts=[box([.022,.014,.012],[0,0,-.012],rgba=[.8,.1,.08,1.])]+[box([.003,.004,.024],[x,y,.01],rgba=[.95,.72,.19,1.]) for x,y in [(-.013,0),(0,.004),(.012,-.004)]]
    fries=prop('fries','fries',[.022,.018,.035],[0,.24],COLORS[0],friesparts)
    drink=prop('drink','drink',[.019,.018,.045],[.11,.24],[.3,.6,.9,1.],parts=[box([.019,.018,.039]),box([.003,.003,.02],[0,0,.045],rgba=[.9,.9,.9,1.])])
    floor=bin_at(s,'meal_tray',[0,.06],.125,.065,.016)
    s['objects']=[burger,fries,drink]
    chosen={'A':[0,1],'B':[0,2],'C':[1,2]}[s['variant']]
    s['goals']=[put(s['objects'][i]['id'],'meal_tray',required_support=floor) for i in chosen]
    s['goals'] += [keep(o) for i,o in enumerate(s['objects']) if i not in chosen]


def _car_layout(s):
    sign=layout(s);origin=[.02 if s['seed'] else 0,sign*.12];yaw=.55 if s['seed'] else 0.
    carparts=[box([.025,.050,.013]),box([.021,.022,.012],[0,-.010,.022])]
    car=prop('car','reference_car',[.030,.058,.035],origin,[.8,.65,.16,1.],carparts,yaw=yaw)
    car['visual_shapes']=[box([.023,.012,.001],[0,.032,.015],rgba=[.1,.25,.4,1.])]
    s['objects']=[car]+[prop('item'+str(i),'box',[.018,.018,.018],[x,sign*.29],COLORS[i]) for i,x in enumerate((-.10,0,.10))]
    placements={'front':[0,.11],'left':[-.11,0],'right':[.11,0]}
    rules={'A':['front','left','right'],'B':['right','front','left'],'C':['left','right','front']}[s['variant']]
    s['goals']=[keep(car)]
    for i,key in enumerate(rules):
        x,y=placements[key];xy=[origin[0]+x*math.cos(yaw)-y*math.sin(yaw),origin[1]+x*math.sin(yaw)+y*math.cos(yaw)]
        s['goals'].append(pose('item'+str(i),xy,xy_tolerance=.018))


def utensil(kind,name,xy,length=.12,color=NEUTRAL):
    h=length/2;parts=[box([.008,h*.58,.004],[0,-h*.42,0])]
    if kind=='fork':
        parts += [box([.016,.012,.004],[0,h*.38,0])]+[box([.002,.015,.003],[x,h*.77,0]) for x in (-.013,-.004,.004,.013)]
    elif kind=='knife':parts += [box([.011,h*.45,.003],[.004,h*.50,0])]
    else:parts += [cylinder(.019,.003,[0,h*.64,0])]
    return prop(name,kind,[.021,h,.006],xy,color,parts)


def _alignment(s):
    lengths=[.10,.13,.16] if not s['seed'] else [.11,.145,.17]
    s['objects']=[utensil(kind,kind,[x,.25],length) for kind,x,length in zip(('spoon','fork','knife'),(-.10,0,.10),lengths)]
    # Visible neutral line, no ABC label in the world.
    fixed(s,[box([.19,.001,.0005])],[0,.07],.802,[.15,.15,.15,1.])
    mode={'A':1,'B':-1,'C':0}[s['variant']]
    s['goals']=[pose(o['id'],[x,.07+mode*o['size'][1]],yaw=0.,xy_tolerance=.012,minimum_up_cos=.97)
                for x,o in zip((-.10,0,.10),s['objects'])]


def _lengths(s):
    # Fixed prefixes of different lengths; reusable loose spare bars include
    # every needed length for every rule, so ABC do not change observations.
    starts=(-.10,0,.10);prefixes=(.045,.075,.105)
    for x,length in zip(starts,prefixes):fixed(s,[box([.014,length/2,.009])],[x,.015+length/2],.809,[.45,.30,.16,1.])
    lengths=(.045,.075,.105,.135,.165,.105,.105)
    objects=[]
    for i,length in enumerate(lengths):objects.append(prop('bar'+str(i),'wood_bar',[.014,length/2,.009],[-.21+i*.07,.36],NEUTRAL))
    s['objects']=objects;goals=[]
    totals={'A':(.21,.21,.21),'B':(.15,.18,.21),'C':(.21,.18,.15)}[s['variant']]
    used=set()
    for row,(x,prefix,total) in enumerate(zip(starts,prefixes,totals)):
        needed=round(total-prefix,3);candidates=[i for i,v in enumerate(lengths) if abs(v-needed)<.001 and i not in used]
        if not candidates:raise ValueError('Missing independent spare for length rule')
        i=candidates[0]
        used.add(i);goals.append(pose('bar'+str(i),[x,.015+prefix+needed/2],yaw=0.,xy_tolerance=.008,minimum_up_cos=.97))
    s['goals']=goals


def _dining(s):
    sign=layout(s);center=[.015 if s['seed'] else 0,sign*.10]
    floor=fixed(s,[cylinder(.058,.003)],center,.803,[.90,.90,.86,1.])[0]
    s['objects']=[utensil('spoon','spoon',[-.08,sign*.27]),utensil('fork','fork',[.08,sign*.27])]
    fixed(s,[box([.022,.006,.001])],[center[0],center[1]-sign*.09],.802,[.15,.15,.15,1.])
    placements={'A':[[-.10,0],[.10,0]],'B':[[.10,0],[-.10,0]],'C':[[-.04,.13],[.04,.13]]}[s['variant']]
    s['goals']=[pose(o['id'],[center[0]+p[0],center[1]+sign*p[1]],yaw=0.,xy_tolerance=.015,minimum_up_cos=.97) for o,p in zip(s['objects'],placements)]


def _bowl_plate(s):
    sign=layout(s)
    # An actual concave bowl, expanding segmented wall, and a shallow plate.
    bowlparts=[cylinder(.028,.003,[0,0,-.025])]
    for row in range(5):bowlparts += ring(.029+row*.006,.005,.003,z=-.020+row*.010)
    bowl=prop('bowl','bowl',[.057,.057,.028],[-.09,sign*.25],[.83,.88,.90,1.],bowlparts,inner_size=[.052,.052,.028])
    plateparts=[cylinder(.075,.003,[0,0,-.004])]+ring(.073,.005,.003)
    plate=prop('plate','plate',[.078,.078,.009],[.09,sign*.25],[.93,.92,.87,1.],plateparts)
    s['objects']=[bowl,plate]
    if s['variant']=='A':
        s['goals']=[pose('plate',[0,sign*.075],minimum_up_cos=.97),dict(type='relative_pose',object='bowl',target='plate',offset=[0,0,.030],tolerance=[.016,.016,.012],minimum_up_cos=.97,require_contact=True)]
    elif s['variant']=='B':
        s['goals']=[pose('bowl',[0,sign*.075],minimum_up_cos=.97),dict(type='relative_pose',object='plate',target='bowl',offset=[0,0,.030],tolerance=[.016,.016,.012],maximum_up_cos=-.97,require_contact=True)]
    else:s['goals']=[pose('bowl',[-.09,sign*.075],minimum_up_cos=.97),pose('plate',[.09,sign*.075],minimum_up_cos=.97)]


def bottle(name,xy,color):
    return prop(name,'bottle',[.020,.020,.055],xy,color,[cylinder(.020,.037,[0,0,-.012]),cylinder(.011,.014,[0,0,.038])])


def _clutter(s):
    s['objects']=[bottle('target'+str(i),[x,.21],COLORS[i]) for i,x in enumerate((-.095,0,.095))]
    # Different heights, offsets and neutral distractors partially occlude
    # the candidates; objects retain finger-clear approach corridors.
    rng=random.Random(5100+s['seed'])
    for i,(x,y) in enumerate([(-.13,.29),(-.04,.30),(.05,.31),(.14,.29)]):
        s['objects'].append(prop('distractor'+str(i),'box',[.025,.025,.025+rng.random()*.012],[x,y],NEUTRAL))
    chosen='ABC'.index(s['variant']);s['success_release']=False
    s['goals']=[dict(type='grasp_lift',object='target'+str(chosen),minimum_z=.805+.055+.08)]
    s['goals'] += [keep(o) for o in s['objects'] if o['id']!='target'+str(chosen)]


def _trash(s):
    sign=layout(s)
    floor=bin_at(s,'trash',[0,sign*.055],.075,.060,.065)
    s['objects']=[bottle('bottle'+str(i),[x,sign*.25],COLORS[i]) for i,x in enumerate((-.10,0,.10))]
    chosen='ABC'.index(s['variant']);s['goals']=[put('bottle'+str(chosen),'trash',required_support=floor)]
    s['goals'] += [keep(o) for i,o in enumerate(s['objects']) if i!=chosen]


def _flip_cards(s):
    sign=layout(s);floor=bin_at(s,'collection',[0,sign*.06],.135,.065,.018)
    s['objects']=[];rules=[]
    for i,x in enumerate((-.095,0,.095)):
        o=prop('card'+str(i),'two_sided_card',[.025,.035,.004],[x,sign*.24],COLORS[i])
        o['visual_shapes']=[box([.023,.033,.0005],[0,0,-.0045],rgba=[.09,.10,.13,1.])]
        s['objects'].append(o)
        rules.append(dict(label=o['id'],predicate=pose(o['id'],maximum_up_cos=-.94)))
    order={'A':[0,1,2],'B':[1,2,0],'C':[2,0,1]}[s['variant']]
    s['goals']=[put(o['id'],'collection',required_support=floor) for o in s['objects']]
    s['goals'] += [pose(o['id'],maximum_up_cos=-.97) for o in s['objects']]
    sequence(s,['card'+str(i) for i in order],rules)


def _counting(s):
    floors=[bin_at(s,'bin'+str(i),[x,.07],.055,.055,.020,i) for i,x in enumerate((-.13,0,.13))]
    initial=[0,1,2] if s['seed']==0 else [1,0,2]
    objects=[]
    for b,n in enumerate(initial):
        for k in range(n):objects.append(prop('existing'+str(b)+'_'+str(k),'counter',[.010,.010,.010],[-.13+b*.13+(k-.5)*.024,.07],NEUTRAL,bottom=.807))
    for i in range(9):objects.append(prop('spare'+str(i),'counter',[.010,.010,.010],[-.12+(i%3)*.12,.22+(i//3)*.065],NEUTRAL))
    s['objects']=objects
    count={'A':2,'B':3,'C':4}[s['variant']]
    s['goals']=[dict(type='zone_count',object=objects[0]['id'],target='bin'+str(i),members=[o['id'] for o in objects],count=count,required_support=floors[i]) for i in range(3)]


def _sort_order(s):
    floors=[bin_at(s,'bin'+str(i),[x,.055],.05,.05,.020,i) for i,x in enumerate((-.13,0,.13))]
    s['objects']=[prop('piece'+str(i),'box',[.020,.020,.020],[x,.24],COLORS[i]) for i,x in enumerate((-.13,0,.13))]
    s['goals']=[put(o['id'],'bin'+str(i),required_support=floors[i]) for i,o in enumerate(s['objects'])]
    rules=[dict(label=o['id'],predicate=copy.deepcopy(g),released=True) for o,g in zip(s['objects'],s['goals'])]
    order={'A':[0,1,2],'B':[1,2,0],'C':[2,0,1]}[s['variant']]
    sequence(s,['piece'+str(i) for i in order],rules)


def _hanging_mugs(s):
    sign=layout(s);s['objects']=[];s['goals']=[]
    colors=[COLORS[0],[.95,.75,.10,1.],COLORS[2]]
    for i,x in enumerate((-.145,0,.145)):
        parts=[cylinder(.024,.003,[0,0,-.026])]+ring(.023,.026,.003)
        # A real rectangular handle, its empty opening normal to Y.
        parts += [box([.014,.004,.004],[.036,0,-.017]),box([.014,.004,.004],[.036,0,.017]),box([.004,.004,.021],[.046,0,0])]
        s['objects'].append(prop('mug'+str(i),'mug',[.050,.026,.030],[x,sign*.26],colors[i],parts))
    racks=[]
    for i,x in enumerate((-.145,0,.145)):
        # Hook runs through the handle; the upright post is behind the cup.
        ids=fixed(s,[box([.020,.030,.004],[0,0,.804]),cylinder(.006,.065,[0,0,.87]),
                     cylinder(.003,.032,[0,.026,.925],quat=qaxis(0,math.pi/2)),
                     box([.003,.003,.008],[0,.055,.931])],[x,sign*.035],0.)
        racks.append(ids[2]);s['zones'].append(zone('rack'+str(i),[x,sign*.035],(.025,.025),i))
    for i in range(3):
        target=(i+'ABC'.index(s['variant']))%3;x=(-.145,0,.145)[target]
        s['goals'].append(pose('mug'+str(i),[x-.036,sign*.035+.029],.908,yaw=0.,xy_tolerance=.012,z_tolerance=.012,minimum_up_cos=.96,required_support=racks[target]))


def _lid(s,xy,hx,hy,z):
    parts=[box([hx,hy,.004]),box([.020,.012,.008],[0,0,.012])]
    lid=prop('lid','loose_lid',[hx,hy,.020],[xy[0]+hx+.09,xy[1]+.10],NEUTRAL,parts)
    s['objects'].append(lid)
    return pose('lid',xy,z,yaw=0.,xy_tolerance=.014,z_tolerance=.008,minimum_up_cos=.97)


def _lidded_order(s):
    xy=[0,.06];floor=bin_at(s,'box',xy,.12,.065,.033)
    s['objects']=[prop('bar'+str(i),'long_bar',[.017,.049,.012],[x,.25],COLORS[i]) for i,x in enumerate((-.085,0,.085))]
    goals=[put(o['id'],'box',required_support=floor) for o in s['objects']]
    rules=[dict(label=o['id'],predicate=copy.deepcopy(g),released=True) for o,g in zip(s['objects'],goals)]
    lid_goal=_lid(s,xy,.126,.071,.870);lid_goal['support_any']=['fixture'+str(i) for i in range(1,5)]
    s['goals']=goals+[lid_goal]
    rules.append(dict(label='lid',predicate=copy.deepcopy(lid_goal),released=True))
    order={'A':[0,1,2],'B':[1,2,0],'C':[2,0,1]}[s['variant']]
    sequence(s,['bar'+str(i) for i in order]+['lid'],rules)


def _pouring(s):
    sign=layout(s);source=[0,sign*.26]
    cup=vessel('pour_cup',source,hx=.045,hy=.043,hz=.042,kind='cup')
    s['objects']=[cup]
    for i in range(8):
        x=(i%2-.5)*.022;y=((i//2)%2-.5)*.022;z=.812+(i//4)*.020
        s['objects'].append(prop('bead'+str(i),'sphere',[.009]*3,[source[0]+x,source[1]+y],COLORS[1],[shape('sphere',[.009])],bottom=z))
    floors=[bin_at(s,'receiver'+str(i),[x,sign*.045],.055,.055,.030,i) for i,x in enumerate((-.13,0,.13))]
    chosen='ABC'.index(s['variant'])
    s['goals']=[put('bead'+str(i),'receiver'+str(chosen),required_support=floors[chosen]) for i in range(8)]
    s['goals'] += [pose('pour_cup',minimum_up_cos=.97),dict(type='event_seen',object='pour_cup',key='pour',label='tilted')]
    s['no_direct_touch']=['bead'+str(i) for i in range(8)]
    s['goals'] += [dict(type='never_handled',object=n) for n in s['no_direct_touch']]
    s['event_rules']=[dict(key='pour',label='tilted',predicate=pose('pour_cup',maximum_up_cos=.30),held_tool='pour_cup')]


def _cutlery_box(s):
    sign=layout(s);s['objects']=[utensil(kind,kind,[x,sign*.28],.13) for kind,x in zip(('spoon','fork','knife'),(-.10,0,.10))]
    floors=[bin_at(s,'cell'+str(i),[x,sign*.06],.035,.09,.025) for i,x in enumerate((-.085,0,.085))]
    order={'A':[0,1,2],'B':[1,2,0],'C':[2,0,1]}[s['variant']]
    s['goals']=[put(s['objects'][i]['id'],'cell'+str(slot),required_support=floors[slot],require_upright=True) for slot,i in enumerate(order)]
    lid_goal=_lid(s,[0,sign*.06],.126,.096,.855)
    lid_goal['support_any']=['fixture'+str(i) for i in range(len(s['fixtures'])) if i%5]
    s['goals'].append(lid_goal)


def spatula(name,xy):
    # A 1mm leading edge, then a shallow stepped blade and a real handle.
    parts=[box([.012,.060,.008],[0,-.045,.010]),box([.035,.030,.002],[0,.045,.004]),
           box([.035,.010,.0006],[0,.083,.002])]
    return prop(name,'spatula',[.035,.095,.018],xy,[.63,.64,.66,1.],parts)


def _xylophone(s):
    sign=layout(s);keys=[]
    for i,(x,c) in enumerate(zip((-.09,0,.09),(COLORS[0],[.95,.75,.1,1.],COLORS[2]))):
        fixed(s,[box([.032,.008,.006],[0,-.04,.806]),box([.032,.008,.006],[0,.04,.806])],[x,sign*.06])
        keys.append(fixed(s,[box([.032,.055,.005])],[x,sign*.06],.817,c)[0])
    mallet=prop('mallet','mallet',[.027,.115,.023],[0,sign*.28],[.55,.32,.12,1.],
               [cylinder(.009,.070,[0,-.03,0],quat=qaxis(0,math.pi/2)),cylinder(.023,.027,[0,.065,0],quat=qaxis(1,math.pi/2))])
    s['objects']=[mallet];s['goals']=[]
    order={'A':[0,1,2],'B':[2,0,1],'C':[1,2,0]}[s['variant']]
    rules=[dict(label='key'+str(i),predicate=dict(type='contact',object='mallet',target=f),held_tool='mallet',rearm_seconds=.08) for i,f in enumerate(keys)]
    sequence(s,['key'+str(i) for i in order],rules)


def _joint(s,child,kind,anchor0,anchor1=(0,0,0),parent=None,axis='X',limits=(0,0),spring=None):
    j=dict(child=child,type=kind,parent=parent,anchor0=list(anchor0),anchor1=list(anchor1),axis=axis,limits=list(limits))
    if spring:j['spring']=spring
    s['joints'].append(j)


def clip_pair(s,name,xy,color,scale=1.):
    a=scale;size=[.016*a,.047*a,.007*a]
    lower=prop(name,'spring_clip',size,xy,color,
               [box([.016*a,.043*a,.003*a]),box([.016*a,.008*a,.005*a],[0,.035*a,.002*a])],center_z=.812)
    upper=prop(name+'_jaw','clip_jaw',size,xy,color,
               [box([.016*a,.043*a,.003*a]),box([.016*a,.008*a,.005*a],[0,.035*a,-.002*a])],center_z=.812+.012*a)
    s['objects'] += [lower,upper]
    _joint(s,upper['id'],'revolute',[0,0,.010*a],[0,0,-.002*a],parent=name,axis='X',limits=(0,28),spring=dict(stiffness=.12,damping=.025,max_force=.20))
    return lower,upper


def _clothespins(s):
    s['objects']=[];supports=[]
    for i,x in enumerate((-.12,0,.12)):
        fixed(s,[box([.012,.015,.025])],[x,.055],.825)
        support=fixed(s,[box([.037,.026,.003])],[x,.055],.859)[0];supports.append(support)
        s['zones'].append(zone('board'+str(i),[x,.055],(.030,.018),i,z=.862))
        clip_pair(s,'clip'+str(i),[x,.25],COLORS[i])
    s['goals']=[]
    for i in range(3):
        j=(i+'ABC'.index(s['variant']))%3;x=(-.12,0,.12)[j]
        s['goals'] += [pose('clip'+str(i),[x,.022],.851,yaw=0.,xy_tolerance=.015,z_tolerance=.012,required_support=supports[j]),
                       dict(type='contact',object='clip'+str(i)+'_jaw',target=supports[j])]


def _mobile_plate(s):
    # Three real holes, with a movable frame instead of a fixed target pad.
    parts=[box([.145,.010,.012],[0,-.040,0]),box([.145,.010,.012],[0,.040,0])]
    for x in (-.14,-.048,.048,.14):parts.append(box([.008,.030,.012],[x,0,0]))
    # Slotted interfaces remain physically open down to the tabletop.
    for x in (-.094,0,.094):
        parts += [box([.038,.009,.012],[x,-.021,0]),box([.038,.009,.012],[x,.021,0])]
    plate=prop('mobile_plate','hole_board',[.15,.050,.012],[0,.07],NEUTRAL,parts)
    plate['visual_shapes']=[box([.005,.005,.0005],[x,-.041,.013],rgba=COLORS[i]) for i,x in enumerate((-.094,0,.094))]
    peg=prop('peg','peg',[.016,.012,.035],[0,.25],COLORS[0],
             [box([.010,.010,.025],[0,0,-.008]),box([.024,.018,.005],[0,0,.018])])
    s['objects']=[plate,peg]
    selected='ABC'.index(s['variant']);x=(-.094,0,.094)[selected]
    s['goals']=[dict(type='relative_pose',object='peg',target='mobile_plate',offset=[x,0,.021],tolerance=[.006,.004,.008],require_contact=True,minimum_up_cos=.99),keep(plate),
               dict(type='event_seen',object='peg',key='stabilized_insert',label='both_arms')]
    s['event_rules']=[dict(key='stabilized_insert',label='both_arms',predicate=dict(type='tool_contact',object='peg',target='mobile_plate'),held_tool='peg')]


def _sliding(s):
    # Five blocks and exactly one vacancy in a 2x3 track. Two neutral blocks
    # let the specified end swap remain physically reachable (a 2x2 puzzle
    # with the blank fixed would make that odd permutation impossible).
    centers=[[-.09,.07],[0,.07],[.09,.07],[-.09,.16],[0,.16],[.09,.16]]
    fixed(s,[box([.14,.10,.003])],[0,.115],.803)
    for x in (-.14,.14):fixed(s,[box([.005,.10,.026])],[x,.115],.829)
    for y in (.015,.215):fixed(s,[box([.14,.005,.026])],[0,y],.829)
    # A transparent physical ceiling prevents bypassing the sliding rule by
    # lifting a block out; side access remains available for pushing.
    fixed(s,[box([.145,.105,.003])],[0,.115],.856,[.75,.80,.85,.10])
    s['objects']=[prop('slider'+str(i),'slider',[.041,.041,.017],p,COLORS[i] if i<3 else NEUTRAL,bottom=.807) for i,p in enumerate(centers[:5])]
    mapping={'A':[1,2,0],'B':[2,0,1],'C':[2,1,0]}[s['variant']]
    s['goals']=[pose('slider'+str(i),centers[j],yaw=0.,xy_tolerance=.010,maximum_z=.837,minimum_up_cos=.99) for i,j in enumerate(mapping)]


def _cabinet(s,two=False):
    xy=[0,.18];zs=[.831,.934] if two else [.831]
    # Static cabinet shell leaves the entire front open. Each hollow drawer
    # is a freely pushed/pulled native PhysX prismatic body with hard stops.
    fixed(s,[box([.130,.100,.006],[0,0,.800]),box([.006,.100,.105],[-.130,0,.905]),
             box([.006,.100,.105],[.130,0,.905]),box([.130,.006,.105],[0,.100,.905]),
             box([.13,.10,.006],[0,0,1.01 if two else .91])],xy)
    drawers=[]
    for i,z in enumerate(zs):
        initial_open=(.035 if i==0 else .065) if not s['seed'] else (.065 if i==0 else .020)
        drawer=vessel('drawer'+str(i),[xy[0],xy[1]-initial_open],hx=.118,hy=.090,hz=.025,bottom=z-.025)
        drawer['center_z']=z
        drawer['collision_shapes'] += [box([.045,.012,.008],[0,-.100,.004])]
        drawer['size'][1]=.112;s['objects'].append(drawer);drawers.append(drawer)
        _joint(s,drawer['id'],'prismatic',xy+[z],axis='Y',limits=(-.14,0))
    if two:
        opened={'A':[False,True],'B':[True,False],'C':[True,True]}[s['variant']]
        # Array order lower, upper; rule A upper only, B lower only.
        s['goals']=[pose(d['id'],[xy[0],xy[1]-(.13 if opened[i] else 0)],z=zs[i],xy_tolerance=.012,minimum_up_cos=.99) for i,d in enumerate(drawers)]
    else:
        for i,x in enumerate((-.070,0,.070)):
            s['objects'].append(prop('item'+str(i),'box',[.016,.016,.016],[x,drawers[0]['xy'][1]],COLORS[i],bottom=.813))
        floor=bin_at(s,'plate',[0,-.08],.10,.055,.012)
        chosen='ABC'.index(s['variant'])
        s['goals']=[put('item'+str(chosen),'plate',required_support=floor),pose('drawer0',xy,z=zs[0],xy_tolerance=.012,minimum_up_cos=.99)]
        s['goals'] += [dict(type='relative_pose',object='item'+str(i),target='drawer0',offset=[x,0,-.002],tolerance=[.018,.018,.012],require_contact=True) for i,x in enumerate((-.070,0,.070)) if i!=chosen]


def _drawers(s):_cabinet(s,False)
def _two_drawers(s):_cabinet(s,True)


def _buttons(s):
    n,m=(3,1) if not s['seed'] else (2,3)
    s['quantity_cards']=[n,m];s['objects']=[];s['event_rules']=[]
    for i,(x,count) in enumerate(zip((-.085,.085),(n,m))):
        fixed(s,[box([.032,.04,.002])],[x,.24],.802,[.9,.9,.85,1.])
        for k in range(count):fixed(s,[cylinder(.004,.0005)], [x+(k%3-1)*.013,.24+(k//3-.5)*.014],.805,[.08,.08,.10,1.])
        fixed(s,[cylinder(.029,.008)],[x,.07],.808,[.25,.26,.29,1.])
        o=prop('button'+str(i),'spring_button',[.023,.023,.007],[x,.07],COLORS[i*2],[cylinder(.023,.007)],center_z=.835,disable_gravity=True)
        s['objects'].append(o)
        _joint(s,o['id'],'prismatic',[x,.07,.835],axis='Z',limits=(-.013,0),spring=dict(stiffness=180,damping=2,max_force=6))
        s['event_rules'].append(dict(key='presses',label=o['id'],predicate=pose(o['id'],maximum_z=.825),rearm_predicate=pose(o['id'],minimum_z=.833),rearm_seconds=.04,require_finger_contact=True))
    counts={'A':[n,m],'B':[m,n],'C':[n+m,abs(n-m)]}[s['variant']]
    s['goals']=[dict(type='event_count',object=o['id'],key='presses',label=o['id'],count=counts[i]) for i,o in enumerate(s['objects'])]
    s['goals'] += [pose(o['id'],minimum_z=.833) for o in s['objects']]


def _flip_food(s):
    sign=layout(s);s['objects']=[spatula('spatula',[0,sign*.30])]
    for i,x in enumerate((-.075,.075)):
        o=prop('pancake'+str(i),'rigid_pancake',[.036,.036,.008],[x,sign*.10],[.84,.57,.24,1.],[cylinder(.036,.008)])
        # Different faces are geometry/material, not hidden object IDs.
        o['visual_shapes']=[box([.003,.025,.0005],[dx,0,.0086 if i==0 else -.0086],rgba=[.25,.10,.03,1.]) for dx in (-.016,0,.016)]
        s['objects'].append(o)
    chosen={'A':[0],'B':[1],'C':[0,1]}[s['variant']]
    s['no_direct_touch']=['pancake0','pancake1'];s['goals']=[]
    for i in range(2):
        name='pancake'+str(i)
        s['goals'] += [pose(name,maximum_up_cos=-.97) if i in chosen else pose(name,minimum_up_cos=.97),dict(type='never_handled',object=name)]
        if i in chosen:
            s['goals'].append(dict(type='event_seen',object=name,key='spatula_contact',label=name))
            s['event_rules'].append(dict(key='spatula_contact',label=name,predicate=dict(type='tool_contact',object=name,target='spatula')))


def _spatula_delivery(s):
    s['objects']=[spatula('spatula',[0,.29]),prop('wafer','thin_wafer',[.035,.040,.0015],[0,.15],COLORS[1])]
    # Rigid obstructions surround the wafer at finger height, leaving a low
    # blade-width entrance. It must be supported on the physical thin blade.
    fixed(s,[box([.007,.055,.020])],[-.050,.15],.82)
    fixed(s,[box([.007,.055,.020])],[.050,.15],.82)
    floors=[bin_at(s,'slot'+str(i),[x,-.035],.042,.050,.008,i) for i,x in enumerate((-.11,0,.11))]
    chosen='ABC'.index(s['variant']);s['no_direct_touch']=['wafer']
    s['goals']=[put('wafer','slot'+str(chosen),required_support=floors[chosen]),dict(type='never_handled',object='wafer'),dict(type='event_seen',object='wafer',key='blade_support',label='carried')]
    s['event_rules']=[dict(key='blade_support',label='carried',predicate=dict(type='tool_lift',object='wafer',target='spatula',minimum_z=.85))]


def _tool_clip(s):
    sign=layout(s)
    lower,upper=clip_pair(s,'tool_clip',[0,sign*.32],[.65,.65,.68,1.],1.35)
    s['objects'] += [prop('card'+str(i),'card',[.025,.035,.004],[x,sign*.18],COLORS[i]) for i,x in enumerate((-.09,0,.09))]
    fixed(s,[box([.018,.020,.030])],[-.04,sign*.12],.83)
    fixed(s,[box([.018,.020,.030])],[.04,sign*.12],.83)
    s['zones']=[zone('target'+str(i),[x,-sign*.045],(.045,.045),i) for i,x in enumerate((-.11,0,.11))]
    selected='ABC'.index(s['variant']);name='card'+str(selected)
    s['no_direct_touch']=['card'+str(i) for i in range(3)]
    s['goals']=[put(name,'target'+str(selected)),dict(type='event_seen',object=name,key='clip_grasp',label='lifted')]
    s['goals'] += [keep(o) for o in s['objects'] if o['kind']=='card' and o['id']!=name]
    s['goals'] += [dict(type='never_handled',object=n) for n in s['no_direct_touch']]
    s['event_rules']=[dict(key='clip_grasp',label='lifted',predicate=dict(type='tool_lift',object=name,target='tool_clip',second_contact='tool_clip_jaw',minimum_z=.85))]


def _folding(s):
    a=prop('panel_a','hinged_cardboard',[.075,.055,.004],[-.10,.07],[.72,.53,.31,1.])
    b=prop('panel_b','hinged_cardboard',[.075,.055,.004],[.05,.07],[.72,.53,.31,1.])
    s['objects']=[a,b]
    _joint(s,'panel_b','revolute',[.075,0,0],[-.075,0,0],parent='panel_a',axis='Y',limits=(-175,0))
    # An independent triangular support block, never a scripted latch.
    vertices=[-.05,-.04,-.025,.05,-.04,-.025,-.05,-.04,.025,-.05,.04,-.025,.05,.04,-.025,-.05,.04,.025]
    faces=[0,2,1,3,4,5,0,1,4,0,4,3,1,2,5,1,5,4,2,0,3,2,3,5]
    wedge=prop('support','support_wedge',[.05,.04,.025],[0,.26],[.34,.43,.52,1.],
               [dict(type='mesh',mesh_data=dict(vertices=vertices,faces=faces),pos=[0,0,0],quat=[1,0,0,0])])
    s['objects'].append(wedge)
    angle={'A':math.pi/2,'B':math.pi/3,'C':2*math.pi/3}[s['variant']]
    s['goals']=[dict(type='relative_angle',object='panel_b',target='panel_a',axis=1,angle=angle,tolerance=.10,support='support'),pose('panel_a',minimum_up_cos=.97)]


RECIPES = {'F06':_shoes,'F13':_chargers,'F14':_phone,'F18':_swap,
           'F19':_correction,'F20':_relocation,'F21':_basket,'F25':_caps,
           'F26':_food,'F29':_car_layout,'F32':_alignment,'F33':_lengths,
           'F35':_dining,'F48':_bowl_plate,'F51':_clutter,'F52':_trash,
           'F24':_flip_cards,'F27':_counting,'F28':_sort_order,'F30':_hanging_mugs,
           'F31':_lidded_order,'F40':_pouring,'F45':_xylophone,'F47':_cutlery_box,
           'F09':_clothespins,'F15':_mobile_plate,'F16':_sliding,'F23':_drawers,
           'F34':_buttons,'F37':_flip_food,'F38':_spatula_delivery,'F41':_tool_clip,
           'F46':_two_drawers,'F49':_folding}


def adapt(s):
    if s['id'] not in RECIPES:return s
    s=copy.deepcopy(s);s.update(objects=[],zones=[],fixtures=[],goals=[],event_rules=[],joints=[])
    RECIPES[s['id']](s)
    sign=layout(s)
    # Robotwin's background wall begins at world Y=.4 (task X=.4).
    # Keep the optical centre in front of it on every supported rig.
    s['head_view']=dict(eye_task=[.28,-sign*.50,1.60],target_task=[0,sign*.16,.83],
                        profile='project-fixed-task-camera-v4',
                        note='Project task camera; native reference wrist mounts remain unchanged')
    if s['seed']:
        # A fixed second layout, not a rule-dependent scene cue.
        delta=[.006,-.004]
        for entry in s['objects']+s['zones']+s['fixtures']:
            entry['xy']=[a+b for a,b in zip(entry['xy'],delta)]
        for goal in s['goals']+[r['predicate'] for r in s['event_rules']]:
            if 'xy' in goal:goal['xy']=[a+b for a,b in zip(goal['xy'],delta)]
        for joint in s['joints']:
            if not joint.get('parent'):
                joint['anchor0'][:2]=[a+b for a,b in zip(joint['anchor0'][:2],delta)]
    s.update(status='task-specific-pending-physx',task_revision=3,
             task_adapter='native-task-recipe-v3',demo_status='pending_recording',
             asset_provenance='Project-authored convex compounds; reference native robot rig retained')
    s.pop('variant_permutation',None)
    s['scene_template'].update(asset_family=s['id']+'-dedicated',object_count=len(s['objects']),zone_count=len(s['zones']),goal_adapter='task_specific')
    return s
