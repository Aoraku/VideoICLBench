"""Rebuild the reviewable 50-task catalog from explicit task recipes."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COLORS = {'red':[.85,.12,.1,1], 'green':[.12,.7,.22,1], 'blue':[.12,.3,.85,1],
          'yellow':[.95,.72,.12,1], 'white':[.85,.85,.85,1], 'purple':[.65,.2,.75,1]}
tasks=[]
def obj(name, kind='box', color='red', size=None, xy=None, yaw=0):
    defaults={'box':[.025,.025,.025], 'bar':[.055,.018,.018], 'bottle':[.022,.022,.055],
              'cup':[.034,.034,.042], 'bowl':[.065,.065,.025], 'tray':[.105,.075,.018],
              'plate':[.08,.08,.009], 'phone':[.045,.024,.008]}
    return dict(id=name, kind=kind, rgba=COLORS[color], size=size or defaults[kind],
                xy=xy, yaw=yaw, fixed=False)
def add(project, upstream, title, objects, goals, note='', zones=None):
    n=sum(t['source']['project']==project for t in tasks)+1
    for i,o in enumerate(objects):
        if o['xy'] is None: o['xy']=[-.16+(i//3)*.11, -.22+(i%3)*.22]
    path = f'envs/{upstream}.py' if project=='RoboTwin' else next(
        p.relative_to(ROOT/'.local/upstream/robocasa').as_posix()
        for p in (ROOT/'.local/upstream/robocasa/robocasa/environments').rglob('*.py')
        if f'class {upstream}(' in p.read_text())
    revision=subprocess.check_output(['git','-C',str(ROOT/'.local/upstream'/('RoboTwin' if project=='RoboTwin' else 'robocasa')),'rev-parse','HEAD'],text=True).strip()
    repo='RoboTwin-Platform/RoboTwin' if project=='RoboTwin' else 'robocasa/robocasa'
    tasks.append(dict(id=f'{"rt" if project=="RoboTwin" else "rc"}{n:02}', title=title,
        source=dict(project=project,task=upstream,revision=revision,url=f'https://github.com/{repo}/blob/{revision}/{path}'),
        task_revision=2 if project=='RoboTwin' and upstream=='handover_block' else 1,
        execution_backend='robosuite-1.5.1-dual-panda-tabletop',
        adaptation='Task-design adaptation; original assets, native physics and official score are not reused. '+note,
        objects=objects,zones=zones or [dict(id='target',xy=[.16,0],half_size=[.10,.09])],goals=goals,
        variants=['A','B','C'],action_budget=1000,wall_seconds=1800,
        demo_status='missing',release_status='implemented-unvalidated-agent',
        filming=dict(view='Fixed oblique overhead, full table and both hands visible; no cuts or captions.',
                     instruction=title,props=[o['kind'] for o in objects],
                     split='Record A only; evaluate A imitation and B/C layout transfer separately.',
                     acceptance='Complete all private goals; 2 s stable final state; no visible goal text in agent video.')))
def place(name,target='target'): return dict(type='place',object=name,target=target)
def stack(a,b): return dict(type='stack',object=a,target=b)
def pose(name,yaw=0): return dict(type='yaw',object=name,value=yaw,tolerance=.22)
def row(names): return [dict(type='position',object=n,xy=[.15,-.16+i*.16],tolerance=.035) for i,n in enumerate(names)]
def basic(project,upstream,title,objects,**kw): add(project,upstream,title,objects,[place(o['id']) for o in objects],**kw)
P='RoboTwin'
add(P,'stack_blocks_two','红块叠在蓝块上',[obj('red'),obj('blue',color='blue')],[stack('red','blue')])
add(P,'stack_blocks_three','红绿蓝三层塔（蓝在底）',[obj('red'),obj('green',color='green'),obj('blue',color='blue')],[stack('red','green'),stack('green','blue')])
add(P,'stack_bowls_two','小碗嵌入大碗',[obj('small','bowl',size=[.045,.045,.022]),obj('large','bowl',color='blue',size=[.075,.075,.03])],[dict(type='nest',object='small',target='large')],note='Nesting uses open square bowls rather than upstream round assets.')
add(P,'stack_bowls_three','三只碗按大小嵌套',[obj('small','bowl',size=[.035,.035,.018]),obj('mid','bowl','green',size=[.057,.057,.024]),obj('large','bowl','blue',size=[.085,.085,.03])],[dict(type='nest',object='small',target='mid'),dict(type='nest',object='mid',target='large')])
add(P,'blocks_ranking_rgb','红绿蓝从左至右排列',[obj('red'),obj('green',color='green'),obj('blue',color='blue')],row(['red','green','blue']))
add(P,'blocks_ranking_size','块按小中大排列',[obj('small',size=[.018]*3),obj('mid','box','green'),obj('large','box','blue',size=[.033]*3)],row(['small','mid','large']))
for source,kind in [('handover_block','box'),('handover_mic','bar')]:
    add(P,source,'左臂夹起并交给右臂，再放到目标垫',[obj('item',kind,xy=[-.12,-.22],size=[.022,.14,.025] if kind=='box' else None)],[dict(type='handover',object='item',arms=[0,1]),place('item')],zones=[dict(id='target',xy=[.16,0],half_size=[.1,.17])] if kind=='box' else None,
        note='Airborne transfer from arm 0 to arm 1 must include 0.2 s of exclusive receiving-arm ownership; table relay and simultaneous touching do not count. '+('The handover block is elongated to 44 x 280 x 50 mm to provide separated Panda grasp sites; 50 mm and 130 mm proxies had gripper or wrist-interference failures in author trials. This is an explicit geometry adaptation, not a claim that the original task is impossible.' if kind=='box' else 'An elongated bar replaces the microphone mesh.'))
add(P,'lift_pot','双臂同时抬起托盘',[obj('tray','tray',xy=[-.02,0])],[dict(type='dual_lift',object='tray',height=.08)],note='Open tray replaces pot; simultaneous two-gripper contact and elevation required.')
add(P,'pick_dual_bottles','双臂同时夹起两瓶',[obj('a','bottle',xy=[-.12,-.22]),obj('b','bottle','blue',xy=[-.12,.22])],[dict(type='paired_lift',objects=['a','b'],height=.08)])
add(P,'pick_diverse_bottles','高矮两瓶移入不同垫',[obj('tall','bottle'),obj('short','bottle','blue',size=[.028,.028,.035])],[place('tall','left'),place('short','right')],zones=[dict(id='left',xy=[.16,-.18],half_size=[.08,.07]),dict(id='right',xy=[.16,.18],half_size=[.08,.07])])
basic(P,'place_empty_cup','夹杯并放到目标垫',[obj('cup','cup')],note='Cup has a physical open cavity; no microwave stage. This is a new adapted task, separate from the historical microwave-mug experiment.')
for source,kind,title in [('place_bread_basket','bar','面包放入篮'),('place_can_basket','bottle','罐放入篮'),('place_cans_plasticbox','box','两罐放入盒')]:
    oo=[obj('food',kind),obj('basket','tray','blue',xy=[.15,0])]
    gg=[dict(type='nest',object='food',target='basket')]
    if source=='place_cans_plasticbox':
        oo.insert(1,obj('other','bottle','green',size=[.018,.018,.035])); gg.append(dict(type='nest',object='other',target='basket'))
    add(P,source,title,oo,gg)
add(P,'place_container_plate','容器放到盘上',[obj('cup','cup'),obj('plate','plate','blue',xy=[.15,0])],[stack('cup','plate')])
for source,kind,title in [('place_object_scale','box','物块放到秤台'),('place_object_stand','bottle','瓶放到展示台')]:
    add(P,source,title,[obj('item',kind),obj('stand','box','blue',size=[.065,.065,.035],xy=[.15,0])],[stack('item','stand')],note='Static pedestal models the placement target; no electronic scale readout.')
add(P,'place_phone_stand','手机竖立在支架上',[obj('phone','phone'),obj('stand','tray','blue',size=[.065,.045,.018],xy=[.15,0])],[dict(type='nest',object='phone',target='stand'),dict(type='upright',object='phone',axis=0)],note='Open support tray replaces shaped phone stand; phone long axis must be vertical.')
basic(P,'place_mouse_pad','鼠标移至鼠标垫',[obj('mouse','box',size=[.035,.024,.018])])
add(P,'place_dual_shoes','两只鞋并排朝前',[obj('left','bar'),obj('right','bar','blue')],[dict(type='position',object='left',xy=[.15,-.09],tolerance=.035),dict(type='position',object='right',xy=[.15,.09],tolerance=.035),pose('left'),pose('right')],note='Colored elongated solids replace shoe meshes; pose and pair arrangement retained.')
add(P,'adjust_bottle','把横倒的瓶子扶正',[dict(obj('bottle','bottle'),quaternion=[.70710678,0,.70710678,0])],[dict(type='upright',object='bottle',axis=2)],note='Starts on side; retain upright pose for terminal hold.')
basic(P,'move_stapler_pad','订书机移到垫上',[obj('stapler','bar')],note='Rigid elongated prop replaces stapler; no pressing stage.')
basic(P,'move_pillbottle_pad','药瓶移到垫上',[obj('pill','bottle',size=[.023,.023,.032])])
add(P,'place_a2b_left','右侧物块跨桌放到左侧',[obj('item',xy=[-.12,.23])],[place('item')],zones=[dict(id='target',xy=[.12,-.23],half_size=[.08,.07])])
P='RoboCasa'
def rc(source,title,objects,goals=None,note='',zones=None):
    add(P,source,title,objects,goals or [place(o['id']) for o in objects],note='Kitchen navigation, cabinets and appliances are removed; retain the tabletop object relation. '+note,zones=zones)
rc('BeverageOrganization','饮料瓶排成一排',[obj('a','bottle'),obj('b','bottle','green'),obj('c','bottle','blue')],row(['a','b','c']))
rc('DrinkwareConsolidation','两只杯集中到托盘',[obj('a','cup',size=[.033,.033,.034]),obj('b','cup','green',size=[.033,.033,.034]),obj('tray','tray','blue',xy=[.15,0])],[dict(type='nest',object=n,target='tray') for n in ['a','b']])
rc('BowlAndCup','碗杯分置两个区域',[obj('bowl','bowl'),obj('cup','cup','blue')],[place('bowl','left'),place('cup','right')],zones=[dict(id='left',xy=[.16,-.18],half_size=[.09,.08]),dict(id='right',xy=[.16,.18],half_size=[.09,.08])])
rc('SetBowlsForSoup','两碗分别就位',[obj('a','bowl'),obj('b','bowl','blue')],[dict(type='position',object='a',xy=[.14,-.16],tolerance=.035),dict(type='position',object='b',xy=[.14,.16],tolerance=.035)])
rc('SizeSorting','餐具从小到大排列',[obj('a','plate',size=[.035,.035,.008]),obj('b','plate','green',size=[.055,.055,.008]),obj('c','plate','blue')],row(['a','b','c']))
rc('CondimentCollection','调味瓶集中托盘',[obj('a','bottle',size=[.018,.018,.035]),obj('b','bottle','green',size=[.018,.018,.035]),obj('tray','tray','blue',xy=[.15,0])],[dict(type='nest',object=n,target='tray') for n in ['a','b']])
rc('RestockBowls','碗嵌套归置',[obj('a','bowl',size=[.04,.04,.022]),obj('b','bowl','blue',size=[.075,.075,.03])],[dict(type='nest',object='a',target='b')])
rc('AssembleCookingArray','锅与两份食材排列',[obj('pan','bowl'),obj('a','box','green'),obj('b','bar','yellow')],row(['pan','a','b']))
rc('FryingPanAdjustment','平底锅旋转九十度',[obj('pan','tray',xy=[-.05,0],yaw=1.57)],[place('pan'),pose('pan')])
rc('PanTransfer','将食材从左锅转到右锅',[obj('food','box',size=[.018]*3,xy=[-.12,-.20]),obj('left','bowl','blue',xy=[-.12,-.20]),obj('right','bowl','green',xy=[.15,.16])],[dict(type='nest',object='food',target='right')],note='Food starts inside left pan; no heating physics.')
rc('PlaceFoodInBowls','两份食材分别入碗',[obj('a','box',size=[.018]*3),obj('b','box','yellow',size=[.018]*3),obj('left','bowl','blue',xy=[.15,-.16]),obj('right','bowl','green',xy=[.15,.16])],[dict(type='nest',object='a',target='left'),dict(type='nest',object='b',target='right')])
rc('MakeFruitBowl','两色水果集中碗中',[obj('a','box',size=[.018]*3),obj('b','box','yellow',size=[.018]*3),obj('bowl','bowl','blue',xy=[.15,0])],[dict(type='nest',object=n,target='bowl') for n in ['a','b']])
rc('CerealAndBowl','麦片盒与碗配对摆放',[obj('cereal','box',size=[.025,.035,.055]),obj('bowl','bowl','blue')],[dict(type='position',object='cereal',xy=[.15,-.12],tolerance=.04),dict(type='position',object='bowl',xy=[.15,.12],tolerance=.04)])
rc('BreadAndCheese','奶酪叠到面包上',[obj('cheese','box','yellow',size=[.022,.022,.009]),obj('bread','box',size=[.045,.045,.014])],[stack('cheese','bread')])
rc('DessertAssembly','糕点装盘',[obj('cake','box'),obj('plate','plate','blue',xy=[.15,0])],[stack('cake','plate')])
rc('OrganizeBakingIngredients','烘焙原料分类排列',[obj('flour','box',size=[.03,.025,.045]),obj('sugar','bottle','white'),obj('butter','bar','yellow')],row(['flour','sugar','butter']))
rc('ClearingCleaningReceptacles','清洁用品集中一侧',[obj('soap','bottle'),obj('sponge','box','yellow',size=[.035,.025,.012])])
rc('PrewashFoodAssembly','待洗蔬菜放入清洗盆',[obj('a','bar','green',size=[.035,.014,.014]),obj('b','box','yellow',size=[.018]*3),obj('basin','bowl','blue',xy=[.15,0])],[dict(type='nest',object=n,target='basin') for n in ['a','b']],note='Dry basin; no water or cleanliness state.')
rc('OrganizeVegetables','蔬菜按品类摆放',[obj('carrot','bar','yellow'),obj('cucumber','bar','green')],[dict(type='position',object='carrot',xy=[.15,-.12],tolerance=.04),dict(type='position',object='cucumber',xy=[.15,.12],tolerance=.04),pose('carrot'),pose('cucumber')])
rc('DrainVeggies','蔬菜从盆转入沥水盘',[obj('veg','bar','green',size=[.035,.014,.014],xy=[-.12,-.18]),obj('basin','bowl','blue',xy=[-.12,-.18]),obj('plate','plate','yellow',xy=[.15,.15])],[stack('veg','plate')],note='Dry transfer only; no fluid simulation.')
rc('SnackSorting','两种零食分类归盒',[obj('a','box',size=[.018]*3),obj('b','bar','yellow',size=[.03,.014,.014]),obj('left','bowl','blue',xy=[.15,-.16]),obj('right','bowl','green',xy=[.15,.16])],[dict(type='nest',object='a',target='left'),dict(type='nest',object='b',target='right')],note='Open boxes replace drawers; opening and closing are excluded.')
rc('ShakerShuffle','交换两个调味瓶的位置',[obj('a','bottle',xy=[-.12,-.18]),obj('b','bottle','blue',xy=[-.12,.18])],[dict(type='position',object='a',xy=[-.12,.18],tolerance=.035),dict(type='position',object='b',xy=[-.12,-.18],tolerance=.035)])
rc('PastryDisplay','三份糕点有序展示',[obj('a','box'),obj('b','box','yellow'),obj('c','box','blue')],row(['a','b','c']))
rc('PrepMarinatingMeat','肉块放入腌制碗',[obj('meat','box',size=[.03,.025,.014]),obj('bowl','bowl','blue',xy=[.15,0])],[dict(type='nest',object='meat',target='bowl')],note='No chemical marination state.')
rc('ArrangeBreadBasket','两条面包并排装篮',[obj('a','bar',size=[.045,.015,.015]),obj('b','bar','yellow',size=[.045,.015,.015]),obj('basket','tray','blue',xy=[.15,0])],[dict(type='nest',object=n,target='basket') for n in ['a','b']]+[pose('a'),pose('b')])
assert len(tasks)==50
out=Path(__file__).with_name('tasks.json')
out.write_text(json.dumps(dict(schema_version=1,benchmark='VideoICL-Embodied-50',official_upstream_benchmark=False,tasks=tasks),ensure_ascii=False,indent=2)+'\n')
print(out)
