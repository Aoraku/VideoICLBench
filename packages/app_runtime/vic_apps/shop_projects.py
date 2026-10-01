"""Department shopping, inventory, order receipts and procurement handovers."""
from copy import deepcopy
import json
import random
from vic import business
from .domain import initialize
from .communications import file_record

TASKS={52,55}


def fixture(task_id,seed,spec):
    base=business.generate(task_id,seed);rng=random.Random(seed);items=[]
    kinds=[('便携机械键盘','红轴 / 87 键'),('不锈钢保温杯','白色 / 500ml'),('桌面阅读灯','白色 / USB-C'),('帆布通勤背包','藏青 / 20L'),('无线静音鼠标','蓝牙 / 黑色'),('旅行收纳包','灰色 / 三件套')]
    departments=[dict(id='design',name='设计部',address='海棠路 18 号 3 楼，林若宁收'),dict(id='research',name='研发部',address='海棠路 18 号 5 楼，陈嘉树收'),dict(id='operations',name='运营部',address='海棠路 26 号 2 楼，许清和收')]
    people=[dict(id=10+i,name=name,department=dep['id']) for i,(name,dep) in enumerate(zip(['林若宁','陈嘉树','许清和'],departments))]
    needs=[];requests=[]
    def product(code,kind,specification,price,stock,rating,tags=()):
        item=deepcopy(base['items'][len(items)%6])
        item.update(id=code,record_code=code,name=kinds[kind][0],category='category-'+str(kind),spec=specification,price=price,stock=stock,rating=rating,tags=list(tags),vendor=['青禾自营','山岚商贸','常青优品'][len(items)%3],text='日常办公用品。请核对商品编号、规格及销售方。')
        items.append(item)
    if task_id==52:
        for i,(name,configuration) in enumerate(kinds):
            quantity=rng.randint(2,4);price=60+i*20
            needs.append(dict(id=f'NEED-{i+1:03d}',department=departments[i//2]['id'],category='category-'+str(i),name=name,spec=configuration,quantity=quantity,budget=price+40))
            for j,(premium,stock,rating,configuration_) in enumerate([(0,quantity+12,4.9,configuration),(30,quantity+14,4.7,configuration),(10,quantity+1,4.2,configuration),(15,quantity+20,5.0,'其他规格'),(90,quantity+20,5.0,configuration),(20,quantity-1,5.0,configuration)]):
                product(f'F{i+1}-{j+1:02d}',i,configuration_,price+premium,stock,rating)
    else:
        for i in range(8):
            group=i//4;label=['本期采购','会场备用'][group]
            product(f'P{i+1:03d}',i%6,kinds[i%6][1],60+i*20,30,4.3+i%3*.2,[label] if i%4!=2 else ['常备物资'])
        for i in range(2):
            requests.append(dict(id=f'LIST-{i+1:03d}',title=['设计部活动用品整理','研发部培训用品整理'][i],department=departments[i]['id'],recipient=10+i,label=['本期采购','会场备用'][i],codes=[f'P{j+1:03d}' for j in range(i*4,i*4+4)],quantities={f'P{j+1:03d}':[2,3,4,1][j%4] for j in range(i*4,i*4+4)}))
    product('U-001',1,'黑色 / 350ml',79,30,4.6,['本期采购'])
    product('U-002',0,'青轴 / 87 键',239,30,4.8,['会场备用'])
    rng.shuffle(items);base['items']=items;state=initialize(base)
    codes={x['record_code']:x['id'] for x in state['items']}
    cart={codes['U-001']:2};favorites=[codes['U-002']]
    if task_id==55:
        for r in requests:
            r['products']=[codes[c] for c in r.pop('codes')];r['quantities']={codes[c]:q for c,q in r['quantities'].items()}
            for index,id in enumerate(r['products']):
                if index in (0,2):cart[id]=r['quantities'][id]
                if index==3:favorites.append(id)
    brief={52:'为三个部门各购买两类办公用品。先核对需求中的类别、规格、数量和单价上限，再在合格商品中按视频标准选择；比较使用商品页标明的初始库存，并列按商品编号升序。把选中商品按需求数量加入购物车，按部门地址分别确认三张模拟订单并保存订单回执。购物车和收藏中的其他商品保留原状。订单可取消后重做；本环境不发生实际扣款。',55:'你负责给下一班采购人员交接两份用品清单。先从团队消息核对每份清单的范围与指定标签，再按视频方式处理清单内命中标签的商品。新增入车使用清单数量，已在车内的商品不重复添加；不改动其他商品。每份交接单按清单顺序列出全部商品的最终购物车数量、收藏状态与商品链接，保存后发送给该清单的联系人。变更商品状态后须重新核对交接单；无需下单或付款。'}[task_id]
    state.update(workflow='shop_projects',linked_apps=['shop'] if task_id==52 else ['shop','im'],execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),world=dict(departments=departments,people=people,needs=needs,requests=requests,cart=cart,favorites=favorites,stock={x['id']:x['stock'] for x in state['items']},orders={},handovers={},receipts=[],discussion=[],brief=brief))
    return state


def request_rows(state,request):
    w=state['world']
    return [dict(sku=id,cart_quantity=w['cart'].get(id,0),favorite=id in w['favorites']) for id in request['products']]


def order_text(state,order):
    department=next(d for d in state['world']['departments'] if d['id']==order['department'])
    lines=[f'# {order["id"]} · 模拟订单回执',f'采购部门：{department["name"]}',f'收货地址：{order["address"]}',f'确认号：{order["confirmation"]}','']
    total=0
    for id,quantity in sorted(order['lines'].items()):
        p=state['domain']['objects'][id];total+=p['price']*quantity
        lines.append(f'{p["record_code"]} · {p["name"]} · {p["spec"]} · {p["vendor"]} · {quantity} 件 × {p["price"]} 元 = {quantity*p["price"]} 元')
    return '\n'.join(lines+['',f'合计：{total} 元','本订单为隔离环境中的模拟订单，不发生实际扣款。'])+'\n'


def handover_text(state,request,rows):
    body=[f'# {request["title"]} · 采购交接单',f'清单编号：{request["id"]}',f'指定标签：{request["label"]}','','| 商品编号 | 商品与规格 | 购物车数量 | 已收藏 | 商品链接 |','| --- | --- | --- | --- | --- |']
    for row in rows:
        p=state['domain']['objects'][row['sku']]
        body.append(f'| {p["record_code"]} | {p["name"]} · {p["spec"]} | {row["cart_quantity"]} | {"是" if row["favorite"] else "否"} | [查看商品](?product={row["sku"]}) |')
    return '\n'.join(body)+'\n'


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];objects=state['domain']['objects']
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容须为 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='message.send':
        if target not in [str(p['id']) for p in w['people']] or set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请选择联系人并填写消息')
        w['discussion'].append(dict(id=len(w['discussion'])+1,recipient=int(target),body=data['text'].strip()));return state
    if op in ('cart.set','cart.remove','favorite.add','favorite.remove'):
        if target not in w['stock']:raise ValueError('商品不存在')
        if op=='cart.set':
            if set(data)!={'quantity'} or type(data['quantity']) is not int or not 1<=data['quantity']<=w['stock'][target]:raise ValueError('请输入当前库存范围内的整数数量')
            w['cart'][target]=data['quantity']
        elif op=='cart.remove':w['cart'].pop(target,None)
        elif op=='favorite.add':w['favorites']=sorted(set(w['favorites'])|{target})
        else:w['favorites']=[id for id in w['favorites'] if id!=target]
        return state
    if op=='order.place':
        if state['task_id']!=52 or set(data)!={'department','address','lines'} or data['department'] not in {d['id'] for d in w['departments']} or not isinstance(data['address'],str) or not 1<=len(data['address'])<=300 or not isinstance(data['lines'],dict) or not data['lines']:raise ValueError('请选择部门、商品并填写收货地址')
        for id,q in data['lines'].items():
            if id not in w['stock'] or type(q) is not int or not 1<=q<=min(w['stock'][id],w['cart'].get(id,0)):raise ValueError('采购数量超过库存或购物车数量')
        key=f'ORDER-{state.get("next_order",1):03d}';state['next_order']=state.get('next_order',1)+1
        order=dict(id=key,department=data['department'],address=data['address'],lines=deepcopy(data['lines']),status='confirmed',confirmation='SIM-'+key)
        w['orders'][key]=order
        for id,q in data['lines'].items():
            w['stock'][id]-=q;w['cart'][id]-=q
            if not w['cart'][id]:del w['cart'][id]
        state['domain']['files']['order-'+key]=file_record(key+'-订单回执.md',order_text(state,order));return state
    if op=='order.cancel':
        if target not in w['orders']:raise ValueError('订单不存在')
        for id,q in w['orders'][target]['lines'].items():w['stock'][id]+=q;w['cart'][id]=w['cart'].get(id,0)+q
        del w['orders'][target];state['domain']['files'].pop('order-'+target,None);return state
    if op=='receipt.withdraw':
        if target not in {r['id'] for r in w['receipts']}:raise ValueError('交接通知不存在')
        w['receipts']=[r for r in w['receipts'] if r['id']!=target];return state
    request=next((r for r in w['requests'] if r['id']==target),None)
    if state['task_id']!=55 or not request:raise ValueError('请选择采购清单')
    if op in ('handover.save','handover.delete') and any(r['request']==target for r in w['receipts']):raise ValueError('请先撤回已发送交接单，再修改或删除')
    if op=='handover.save':
        if set(data)!={'rows'} or not isinstance(data['rows'],list) or not data['rows']:raise ValueError('请填写交接明细')
        seen=set()
        for row in data['rows']:
            if not isinstance(row,dict) or set(row)!={'sku','cart_quantity','favorite'} or row['sku'] not in w['stock'] or row['sku'] in seen or type(row['cart_quantity']) is not int or row['cart_quantity']<0 or type(row['favorite']) is not bool:raise ValueError('交接明细字段无效或商品重复')
            seen.add(row['sku'])
        body=handover_text(state,request,data['rows']);w['handovers'][target]=dict(rows=deepcopy(data['rows']),body=body)
        state['domain']['files']['handover-'+target]=file_record(target+'-采购交接单.md',body)
    elif op=='handover.delete':w['handovers'].pop(target,None);state['domain']['files'].pop('handover-'+target,None)
    elif op=='handover.send':
        if set(data)!={'recipient'} or data['recipient'] not in {p['id'] for p in w['people']}:raise ValueError('请选择收件人')
        handover=w['handovers'].get(target)
        if not handover or handover['rows']!=request_rows(state,request):raise ValueError('请按清单顺序核对全部商品的实际状态，并保存最新交接单')
        if any(r['request']==target for r in w['receipts']):raise ValueError('此交接单已经发送')
        key=f'receipt-{state.get("next_receipt",1):03d}';state['next_receipt']=state.get('next_receipt',1)+1
        w['receipts'].append(dict(id=key,request=target,recipient=data['recipient'],body=handover['body']))
    else:raise ValueError('未知采购操作')
    return state
