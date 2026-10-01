"""Isolated invoice payments, double-entry balances, receipts and reconciliation."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
import random
from vic import business
from .domain import initialize
from .communications import file_record

TASKS={46,56}


def money(cents):return f'{cents//100}.{cents%100:02d}'


def fixture(task_id,seed,spec):
    base=business.generate(task_id,seed);rng=random.Random(seed);items=[]
    names=['Avery Lin','Blake Chen','Riley Xu','Morgan He','Elliot Wu','Robin Zhou','Avery Lin']
    for i,name in enumerate(names):
        length=[12,16,19,10,14,18,12][i]
        account=str(6101+i)+''.join(str(rng.randrange(10)) for _ in range(length-8))+str(7302+i)
        item=deepcopy(base['items'][i%6]);item.update(id=f'SUP-{i+1:03d}',record_code=f'SUP-{i+1:03d}',name=name,account=account,company=['青禾设计咨询','星桥技术服务','云帆活动服务','山岚培训中心','白鹭设备维护','远川资料整理','青禾设计咨询（其他供应商）'][i],bank='青禾模拟银行');items.append(item)
    rng.shuffle(items);base['items']=items;state=initialize(base);objects=state['domain']['objects']
    codes={p['record_code']:p['id'] for p in state['items']}
    accounts=[dict(id='own-research',name='研发项目账户',number='990000010826'),dict(id='own-operations',name='运营项目账户',number='990000020827'),dict(id='own-reserve',name='备用账户',number='990000030828')]
    people=[dict(id=10,name='林若宁',role='财务负责人'),dict(id=11,name='陈嘉树',role='项目协调员'),dict(id=12,name='许清和',role='项目协调员')]
    bills=[];count=4 if task_id==46 else 6
    for i in range(count):
        bills.append(dict(id=f'INV-{i+1:03d}',project=['青禾设计','星桥研发','云帆运营'][i//2],purpose=['设计服务费','资料整理费','设备维护费','项目培训费','会场服务费','研究协作费'][i],payee=codes[f'SUP-{i+1:03d}'],payer=accounts[i%2]['id'],cents=[12005,45050,25000,20000,60025,8099][i],batch='2026-10',initial_status='pending',coordinator=10+i//2,note=f'账单 INV-{i+1:03d}'))
    batch=[b['id'] for b in bills]
    bills.append(dict(id='INV-HISTORY',project='过往项目',purpose='九月资料整理',payee=codes['SUP-006'],payer='own-research',cents=12500,batch='2026-09',initial_status='paid',coordinator=10,note='历史付款'))
    bills.append(dict(id='INV-NEXT',project='下期项目',purpose='十一月协作费',payee=codes['SUP-007'],payer='own-reserve',cents=9000,batch='2026-11',initial_status='pending',coordinator=12,note='下期账单'))
    balances={a['id']:1500000 if i<2 else 800000 for i,a in enumerate(accounts)}
    balances.update({p['id']:50000 for p in state['items']})
    historical=dict(id='PAY-H001',bill='INV-HISTORY',payer='own-research',payee=codes['SUP-006'],cents=12500,memo='历史付款',status='posted',occurred_at='2026-09-29T09:00:00+08:00')
    state['domain']['balances']=deepcopy(balances)
    state['domain']['ledger']=[dict(transfer=historical['id'],account=historical['payer'],cents=-12500,counterparty=historical['payee']),dict(transfer=historical['id'],account=historical['payee'],cents=12500,counterparty=historical['payer'])]
    brief={46:'财务已授权支付本期付款清单中的四张账单。请先在团队通知和账单中核对批次、供应商编号、付款账户及金额，再以收款名册中的完整账号生成视频规定的备注。备注仅填写格式化后的账号，不加其他文字。逐笔确认模拟转账，将实际付款编号回填对应账单，保留可下载回执。历史与下期账单不处理。',56:'审核本期六张账单，按视频条件决定付款集合。指定字母为 a，姓名判断不区分大小写；金额阈值为 250.00 元。根据每张账单指定的付款账户、供应商编号和金额完成模拟转账，附言使用账单中给出的文字。将实际付款编号回填账单，再按本期清单顺序保存已付与未付明细，发送给财务负责人林若宁。未付款原因填写“未达到视频规定的付款条件”。历史与下期账单不处理。'}[task_id]
    brief+=' 本环境不连接真实资金，不收手续费；确认前可返回编辑，确认后不能撤销付款。同一账单只能付款一次，填错并已确认时须重置本轮。'
    state.update(workflow='payment_projects',linked_apps=['bank','im'],execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),world=dict(accounts=accounts,people=people,bills=bills,batch_bills=batch,batch='2026-10',letter='a',threshold=25000,reference_time='2026-10-02T09:00:00+08:00',opening_balances=balances,transfers={historical['id']:historical},bill_links={'INV-HISTORY':historical['id']},report=None,receipts=[],discussion=[],report_recipient=10,unpaid_reason='未达到视频规定的付款条件',brief=brief))
    state['domain']['files']['transfer-'+historical['id']]=file_record(historical['id']+'-付款回执.md',receipt_text(state,historical))
    return state


def receipt_text(state,transfer):
    w=state['world'];account=next(a for a in w['accounts'] if a['id']==transfer['payer']);payee=state['domain']['objects'][transfer['payee']]
    return '\n'.join([f'# {transfer["id"]} · 模拟付款回执',f'账单编号：{transfer["bill"]}',f'付款账户：{account["name"]} · {account["number"]}',f'供应商编号：{payee["record_code"]}',f'收款人：{payee["name"]} · {payee["company"]}',f'收款账号：{payee["account"]}',f'金额：{money(transfer["cents"])} 元',f'备注：{transfer["memo"]}',f'入账时间：{transfer["occurred_at"]}','手续费：0.00 元','状态：已入账','本回执来自隔离的模拟账户，不发生实际资金转移。'])+'\n'


def report_rows(state):
    w=state['world']
    return [dict(bill=id,transfer=w['bill_links'].get(id,''),reason='' if w['bill_links'].get(id) else w['unpaid_reason']) for id in w['batch_bills']]


def report_text(state,rows):
    w=state['world'];bills={b['id']:b for b in w['bills']};paid=0;unpaid=0
    lines=['# 十月付款对账清单','','| 账单 | 项目 | 供应商 | 金额（元） | 状态 | 付款回执 | 未付款原因 |','| --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        bill=bills[row['bill']];payee=state['domain']['objects'][bill['payee']]
        if row['transfer']:paid+=bill['cents']
        else:unpaid+=bill['cents']
        link=f'[查看回执](?transfer={row["transfer"]})' if row['transfer'] else '—'
        lines.append(f'| {bill["id"]} | {bill["project"]} | {payee["record_code"]} · {payee["name"]} | {money(bill["cents"])} | {"已付" if row["transfer"] else "未付"} | {link} | {row["reason"]} |')
    lines+=['',f'已付合计：{money(paid)} 元',f'未付合计：{money(unpaid)} 元','','## 付款账户核对']
    for account in w['accounts']:
        opening=w['opening_balances'][account['id']];current=state['domain']['balances'][account['id']]
        lines.append(f'{account["name"]} · {account["number"]}：本轮期初 {money(opening)} 元，期末 {money(current)} 元，本轮支出 {money(opening-current)} 元')
    return '\n'.join(lines)+'\n'


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];d=state['domain'];bills={b['id']:b for b in w['bills']};payees={p['id'] for p in state['items']}
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容须为 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='message.send':
        if target not in [str(p['id']) for p in w['people']] or set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请选择联系人并填写消息')
        w['discussion'].append(dict(id=len(w['discussion'])+1,recipient=int(target),body=data['text'].strip()));return state
    if op=='transfer.execute':
        if set(data)!={'bill','payer','payee','cents','memo'} or data['bill'] not in bills or data['payer'] not in {a['id'] for a in w['accounts']} or data['payee'] not in payees or type(data['cents']) is not int or not 1<=data['cents']<=d['balances'][data['payer']] or not isinstance(data['memo'],str) or not 1<=len(data['memo'])<=200:raise ValueError('请核对账单、账户、金额及备注；金额不得超过可用余额')
        if any(t['bill']==data['bill'] for t in w['transfers'].values()):raise ValueError('此账单已经付款，不能重复支付')
        index=state.get('next_transfer',1);key=f'PAY-{index:04d}';state['next_transfer']=index+1
        time=(datetime.fromisoformat(w['reference_time'])+timedelta(seconds=index)).isoformat()
        transfer=dict(id=key,**deepcopy(data),status='posted',occurred_at=time);w['transfers'][key]=transfer
        d['balances'][data['payer']]-=data['cents'];d['balances'][data['payee']]+=data['cents']
        d['ledger']+=[dict(transfer=key,account=data['payer'],cents=-data['cents'],counterparty=data['payee']),dict(transfer=key,account=data['payee'],cents=data['cents'],counterparty=data['payer'])]
        d['files']['transfer-'+key]=file_record(key+'-付款回执.md',receipt_text(state,transfer));return state
    if op=='bill.link':
        if target not in w['batch_bills'] or set(data)!={'transfer'} or data['transfer'] not in w['transfers']:raise ValueError('请选择本期账单和有效付款回执')
        w['bill_links'][target]=data['transfer'];return state
    if op=='bill.unlink':
        if target not in w['batch_bills']:raise ValueError('只能修改本期账单回填')
        w['bill_links'].pop(target,None);return state
    if op=='receipt.withdraw':
        if target not in {r['id'] for r in w['receipts']}:raise ValueError('对账通知不存在')
        w['receipts']=[r for r in w['receipts'] if r['id']!=target];return state
    if state['task_id']!=56:raise ValueError('未知付款操作')
    if op in ('report.save','report.delete') and w['receipts']:raise ValueError('请先撤回已发送对账清单，再编辑或删除')
    if op=='report.save':
        if set(data)!={'rows'} or not isinstance(data['rows'],list) or not data['rows']:raise ValueError('请填写对账明细')
        seen=set()
        for row in data['rows']:
            if not isinstance(row,dict) or set(row)!={'bill','transfer','reason'} or row['bill'] not in bills or row['bill'] in seen or not isinstance(row['transfer'],str) or (row['transfer'] and row['transfer'] not in w['transfers']) or not isinstance(row['reason'],str) or len(row['reason'])>300:raise ValueError('对账行无效或账单重复')
            seen.add(row['bill'])
        body=report_text(state,data['rows']);w['report']=dict(rows=deepcopy(data['rows']),body=body)
        d['files']['payment-report']=file_record('十月付款对账清单.md',body)
    elif op=='report.delete':w['report']=None;d['files'].pop('payment-report',None)
    elif op=='report.send':
        if set(data)!={'recipient'} or data['recipient'] not in {p['id'] for p in w['people']}:raise ValueError('请选择财务联系人')
        report=w['report']
        if not report or report['rows']!=report_rows(state) or report['body']!=report_text(state,report['rows']):raise ValueError('请核对账单回填与余额，保存最新对账清单后再发送')
        if w['receipts']:raise ValueError('对账清单已经发送')
        key=f'receipt-{state.get("next_receipt",1):03d}';state['next_receipt']=state.get('next_receipt',1)+1
        w['receipts'].append(dict(id=key,recipient=data['recipient'],body=report['body']))
    else:raise ValueError('未知付款操作')
    return state
