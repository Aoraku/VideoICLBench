"""Procurement business records and commands, with no task-rule knowledge."""
from copy import deepcopy
import json
import random


def fixture(seed):
    rng = random.Random(seed)
    products = [
        dict(id='cup-white', name='不锈钢保温杯', spec='白色 / 500ml', price=89, stock=60),
        dict(id='cup-black', name='不锈钢保温杯', spec='黑色 / 350ml', price=79, stock=60),
        dict(id='keyboard-blue', name='便携机械键盘', spec='青轴 / 87 键', price=239, stock=60),
        dict(id='keyboard-red', name='便携机械键盘', spec='红轴 / 87 键', price=249, stock=60),
        dict(id='lamp', name='桌面阅读灯', spec='白色 / USB-C', price=129, stock=60),
        dict(id='bag', name='帆布通勤背包', spec='藏青 / 20L', price=159, stock=60),
    ]
    departments = [dict(id='design', name='设计部', address='海棠路 18 号 3 楼，林若宁收'),
                   dict(id='research', name='研发部', address='海棠路 18 号 5 楼，陈嘉树收'),
                   dict(id='operations', name='运营部', address='海棠路 26 号 2 楼，周予安收')]
    requests = []
    for idx, dep in enumerate(departments):
        skus = rng.sample([p['id'] for p in products], 2)
        number = f'CG-{idx+1:03}'
        requests.append(dict(id=number+'-r1',number=number,revision=1,department=dep['id'],
                             date='2026-09-28',lines=[dict(sku=s,quantity=rng.randint(1,3)) for s in skus]))
        requests.append(dict(id=number+'-r2',number=number,revision=2,department=dep['id'],
                             date='2026-09-29',lines=[dict(sku=s,quantity=rng.randint(2,4)) for s in skus]))
        requests.append(dict(id=number+'-add',number=number+'-追加',revision=1,department=dep['id'],
                             date='2026-09-30',lines=[dict(sku=skus[0],quantity=rng.randint(1,3))]))
    rng.shuffle(requests)
    return dict(task_id=45,app='shop',type='T',title='部门采购',seed=seed,workflow='procurement',
                world=dict(products=products,departments=departments,requests=requests,orders={},
                    brief='请为设计部、研发部和运营部各保存一张采购订单草稿。同一申请编号只采用最高版本；追加申请单独累计。每个部门内相同商品编号合并数量，不跨部门合并。按部门通讯录填写收货地址。每行备注使用视频中的格式，数量取本行合并后的最终数量，商品名不包含规格，数量与商品名之间不加空格。只保存草稿，无需付款。'))


def apply(state, op, target, value):
    state = deepcopy(state)
    w = state['world']
    try:
        data = json.loads(value) if value else {}
    except (ValueError, TypeError) as exc:
        raise ValueError('操作内容必须为有效 JSON') from exc
    if not isinstance(data, dict):
        raise ValueError('操作字段无效')
    fields = {'order.create': {'department'}, 'order.address': {'address'},
              'order.line': {'sku','quantity','note'}, 'order.remove': {'sku'},
              'order.save': set(), 'order.delete': set()}
    if op not in fields or set(data) != fields[op]:
        raise ValueError('未知操作或缺少必要字段')
    if op == 'order.create':
        if data['department'] not in [d['id'] for d in w['departments']]:
            raise ValueError('请选择有效部门')
        order_id = f'PO-{state.get("next_order",1):03d}'
        state['next_order'] = state.get('next_order',1)+1
        w['orders'][order_id] = dict(id=order_id,department=data['department'],address='',lines={},status='draft')
        return state
    if target not in w['orders']:
        raise ValueError('订单不存在')
    order = w['orders'][target]
    if op == 'order.delete':
        del w['orders'][target]
        return state
    if op == 'order.address':
        if not isinstance(data['address'],str) or not 1 <= len(data['address']) <= 300:
            raise ValueError('请填写收货地址')
        order['address'] = data['address']
    elif op == 'order.line':
        product = next((p for p in w['products'] if p['id'] == data['sku']), None)
        if product is None or type(data['quantity']) is not int or not 1 <= data['quantity'] <= product['stock']:
            raise ValueError('请选择商品并输入库存范围内的整数数量')
        if not isinstance(data['note'],str) or len(data['note']) > 500:
            raise ValueError('备注不能超过 500 字')
        order['lines'][data['sku']] = dict(quantity=data['quantity'],note=data['note'])
    elif op == 'order.remove':
        if data['sku'] not in order['lines']:
            raise ValueError('订单中没有此商品')
        del order['lines'][data['sku']]
    elif op == 'order.save':
        if not order['address'] or not order['lines']:
            raise ValueError('请先填写收货地址并添加商品')
        order['status'] = 'saved'
        return state
    order['status'] = 'draft'
    return state
