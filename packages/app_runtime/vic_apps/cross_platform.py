"""Team requests and versioned deliveries for native multi-platform workflows.

The inbox carries business requirements and actual source documents. Deliveries
snapshot real files/records; no completion flags or rule answers are accepted.
"""
from copy import deepcopy
import base64
import hashlib
import json
import random

TASKS = {35, 40, 41, 43, 51, 52, 58, 60, 64, 65}


def text_record(name, body):
    content = body.encode('utf-8')
    return dict(name=name, content=base64.b64encode(content).decode(), size=len(content), sha256=hashlib.sha256(content).hexdigest())


def attach(state, seed):
    """Apply to inference states only, after identity contextualization."""
    if state['task_id'] not in TASKS or 'cross_platform' in state:
        return state
    state = deepcopy(state); task = state['task_id']; w = state['world']
    from vic.identity_context import identity_map
    pool=sorted(set(identity_map(task,seed,'eval').values()))
    used=json.dumps(state,ensure_ascii=False)
    pool=[name for name in pool if name not in used]
    names = random.Random(seed * 101 + task * 31).sample(pool, 5)
    scopes = []
    if task == 35:
        e = w['event']
        source = w['brief'] + '\n开场：' + e['starts_at'] + '\n换片：' + str(e['turnaround_seconds']) + ' 秒\n'
        objects = state['domain']['objects']
        source += '\n'.join('排除：'+objects[x['video']]['record_code']+'，'+x['reason'] for x in e['exclude'])
        source += '\n'+'\n'.join('替换：'+objects[x['old']]['record_code']+' → '+objects[x['new']]['record_code']+'，'+x['reason'] for x in e['replacements'])
        source += '\n'+'\n'.join('休息：'+objects[x['after']]['record_code']+' 之后 '+str(x['seconds'])+' 秒，'+x['reason'] for x in e['breaks'])
        scopes.append(('event', e['title']+'放映委托', source, '将最终放映时间表交给现场执行负责人，用于开场、换片和休息安排。'))
    elif task == 40:
        for p in w['projects']:
            column = next(c for c in w['columns'] if c['id']==p['column'])
            source = f"栏目：{column['name']}\n本期批次：{p['batch']}\n候选稿件："+'、'.join(state['domain']['objects'][i]['record_code'] for i in p['candidates'])
            source += f"\n封面编号：{p['cover']}\n摘要：{p['summary']}\n北京时间发布：{p['publish_at']}\n"+w['brief']
            scopes.append((p['id'], p['name'], source, '向本栏目负责人交付已发布正文与栏目索引，负责人据此安排推广。'))
    elif task == 41:
        for p in w['projects']:
            source = f"项目：{p['name']}\n上下文下限：{p['min_context']}K\n允许模型："+'、'.join(state['domain']['objects'][id]['name']+'（'+id+'）' for id in p['available_models'])
            source += f"\n有效模板：{p['template']}\n有效资料：{p['document']}\n"+w['brief']
            docs = [d for d in w['documents'] if d['id']==p['document']]
            source += '\n资料原文：\n'+'\n'.join(d['name']+'（'+d['version']+'）\n'+'\n'.join(d['records']) for d in docs)
            scopes.append((p['id'], p['name']+'生成委托', source, '把按有效模板和资料生成的归档文件交给该项目联系人，用于本周项目会议。'))
    elif task == 43:
        for p in w['projects']:
            source = w['brief']+'\n项目：'+p['name']+'\n本期文件：'+'、'.join(state['domain']['objects'][id]['record_code'] for id in p['outputs'])
            scopes.append((p['id'],p['name']+'结果核验委托',source,'项目会议需要本项目的检查结果及通过项的实际交付记录；请将项目交付清单发回该项目联系人。'))
    elif task == 51:
        source = w['brief']+'\n会议安排：\n'+'\n'.join(leg['name']+'；会议 '+leg['meeting_start']+' 至 '+leg['meeting_end']+'；成本中心 '+leg['cost_center']+'；联系邮箱 '+leg['contact'] for leg in w['legs'])
        person=w['people'][0]
        source += '\n乘客：'+person['id']+' '+person['name']+'；证件 '+person['document']+'；联系邮箱 '+person['contact']
        scopes.append(('trip', '三城客户会面出差安排', source, '将包含三段确认预订的完整行程单交给出差同事，供其按时赴约。'))
    elif task == 52:
        for department in w['departments']:
            source='采购部门：'+department['name']+'\n收货地址：'+department['address']+'\n需求明细：\n'
            source += '\n'.join(n['id']+' · '+n['name']+' · '+n['spec']+' · '+str(n['quantity'])+' 件 · 单价上限 '+str(n['budget'])+' 元' for n in w['needs'] if n['department']==department['id'])
            source += '\n'+w['brief']
            scopes.append((department['id'],department['name']+'采购委托',source,'将本部门确认订单的回执交给部门联系人，用于核对实际采购商品、金额和收货地址。'))
    else:
        title = {58:'课程规范代码与判题记录',60:'采购费用项目交付',64:'历史模块版本交付',65:'课程代码候选验收'}[task]
        source = w['brief']+'\n指定课程条目：\n'+'\n'.join(e['id']+' · '+e['title']+' → 题号 '+e['problem'] for e in w['entries'])
        scopes.append(('course', title, source, '把发布的源代码包和交付清单一起回复给委托人；接收者须能下载源代码、定位题号并核对检查/提交记录。'))
    people = [dict(id=710+i,name=names[i],role=['现场执行负责人','栏目负责人','项目联系人','出差同事','课程委托人'][{35:0,40:1,41:2,51:3}.get(task,4)]) for i in range(len(scopes))]
    # A non-target colleague makes recipient identity a real choice, not a hidden answer.
    if task in (43,52):
        people=deepcopy(w['people'])
        for p in people:p['role']='项目联系人'
    people.append(dict(id=799,name=names[-1],role='其他项目联系人'))
    requests = []
    for i,(scope,title,source,purpose) in enumerate(scopes):
        key = f'REQ-{task:03d}-{i+1:02d}'
        current = dict(id=key, revision=2, scope=scope, title=title, requester=people[i]['id'], recipient=people[i]['id'], body=source+'\n交付目的：'+purpose,
            attachment=text_record(title+'-有效需求-v2.md',source+'\n'+purpose+'\n'), supersedes=key+'-v1')
        obsolete = dict(id=key+'-v1', revision=1, scope=scope, title=title+' · 过期草案', requester=people[i]['id'], recipient=people[i]['id'], body='前期草案已被 '+key+'（版本 2）替代。请以同一会话内的有效需求、附件和收件人为准。', attachment=text_record(title+'-过期草案-v1.md','此草案已撤销；不得按此版本交付。\n'), supersedes='')
        requests.extend([obsolete,current])
    original = deepcopy(state.get('linked_apps'))
    state['linked_apps'] = list(dict.fromkeys([state['app'], *(original or []), 'im']))
    state['cross_platform'] = dict(primary_app=state['app'], original_linked_apps=original, people=people, requests=requests, receipts=[], messages=[], available=[], read={})
    return state


def resources(state):
    """Only genuine saved/published records are available to attach."""
    task=state['task_id'];w=state['world'];files=state['domain']['files'];out=[]
    def add(id,scope,title,file,link='',record=None):
        if file:out.append(dict(id=id,scope=scope,title=title,file=deepcopy(file),link=link,record=deepcopy(record)))
    if task==35 and w['schedule']:
        add('screening-timetable','event','最终放映时间表',files.get('screening-timetable'),record=w['schedule'])
    elif task==40:
        for id,post in w['publications'].items():
            obj=state['domain']['objects'][post['draft']]
            project=next(p for p in w['projects'] if p['id']==obj['project'])
            rows=w['index'].get(project['column'],[])
            body=post['title']+'\n'+post['summary']+'\n'+post['body']+'\n发布时间：'+post['publish_at']+'\n栏目索引：\n'+'\n'.join('文章编号 '+row['publication'] for row in rows)+'\n请通过团队交付消息中的栏目文章链接打开原文。'
            add('publication-'+id,project['id'],post['title'],text_record(post['title']+'.md',body),post['link'],dict(publication=post,index=rows))
    elif task==41:
        for id,archive in w['archives'].items():
            add('archive-'+id,archive['project'],'项目归档 '+id,files.get(archive['file']),archive['link'],archive)
    elif task==43 and w['delivery']['saved'] is not None and files.get('delivery-manifest'):
        from .studio_projects import manifest_text
        for project in w['projects']:
            rows={id:deepcopy(w['delivery']['saved'][id]) for id in project['outputs'] if id in w['delivery']['saved']}
            document=manifest_text(state,rows)
            records={id:dict(check=w['checks'].get(id),delivery=rows.get(id)) for id in project['outputs']}
            # Include actual referenced source bytes, copy bodies, or send receipts.
            for id,row in rows.items():
                records[id]['source']=deepcopy(w['copies'].get(id)) if row['kind']=='copied' else deepcopy(files.get(row['reference'][6:])) if row['kind']=='saved' else deepcopy(next((r for r in w['receipts'] if 'receipts/'+r['id']==row['reference']),None))
            add('project-delivery-'+project['id'],project['id'],project['name']+'交付清单',text_record(project['name']+'交付清单.md',document),'files/delivery-manifest',record=records)
    elif task==51 and w['itinerary']:
        add('travel-itinerary','trip','完整出差行程单',files.get('travel-itinerary'),record=w['itinerary'])
    elif task==52:
        for id,order in w['orders'].items():
            if order['status']=='confirmed':
                add('order-'+id,order['department'],'订单 '+id,files.get('order-'+id),'orders/'+id,order)
    elif task in {58,60,64,65} and w['delivery'] and w['delivery']['published']:
        for id in ('course-delivery','course-manifest'):
            add(id,'course',files[id]['name'],files[id],record=w['delivery'])
    return out


def apply(state, op, target='', value='', ids=None):
    if state['task_id'] not in TASKS or 'cross_platform' not in state:
        raise ValueError('本环境没有团队交付会话')
    state=deepcopy(state);h=state['cross_platform']
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('消息字段需要有效 JSON') from exc
    if not isinstance(data,dict):raise ValueError('消息字段无效')
    if op=='handoff.read':
        if data or str(target) not in {str(p['id']) for p in h['people']}:raise ValueError('会话不存在')
        h.setdefault('read',{})[str(target)]=True;return state
    if op=='handoff.refresh':h['available']=resources(state);return state
    if op=='handoff.withdraw':
        if target not in {r['id'] for r in h['receipts']}:raise ValueError('找不到这条交付消息')
        h['receipts']=[r for r in h['receipts'] if r['id']!=target];return state
    if op=='handoff.message':
        if set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000 or str(target) not in {str(p['id']) for p in h['people']}:raise ValueError('请选择联系人并填写消息')
        h['messages'].append(dict(id=len(h['messages'])+1,recipient=int(target),body=data['text'].strip()));return state
    if op!='handoff.send':raise ValueError('未知团队交付操作')
    if set(data)!={'recipient','resources'} or data['recipient'] not in {p['id'] for p in h['people']} or not isinstance(data['resources'],list) or not data['resources'] or not all(isinstance(x,str) for x in data['resources']) or len(set(data['resources']))!=len(data['resources']):raise ValueError('请选择收件人与不重复的实际成果附件')
    request=next((r for r in h['requests'] if r['id']==target),None)
    if not request:raise ValueError('需求编号不存在')
    available={r['id']:r for r in resources(state)}
    if not set(data['resources'])<=set(available):raise ValueError('附件未保存或已撤回，请重新打开附件列表')
    if any(r['request']==target for r in h['receipts']):raise ValueError('该需求已有交付消息；更新前请先撤回原消息')
    number=max([int(r['id'].split('-')[-1]) for r in h['receipts']]+[0])+1
    h['receipts'].append(dict(id=f'delivery-{number:03d}',request=target,revision=request['revision'],recipient=data['recipient'],attachments=[deepcopy(available[id]) for id in data['resources']]))
    h['available']=resources(state)
    return state


def without_extension(state):
    """For existing workflow evaluators, whose immutable-input checks are strict."""
    state=deepcopy(state);extension=state.pop('cross_platform',None)
    if extension:
        if extension['original_linked_apps'] is None:state.pop('linked_apps',None)
        else:state['linked_apps']=extension['original_linked_apps']
    return state


def evaluate(initial, final):
    start=initial['cross_platform'];end=final.get('cross_platform',{});checks=[]
    def check(id,value):checks.append(dict(id='handoff:'+id,passed=bool(value)))
    check('linked_platforms',final.get('linked_apps')==initial.get('linked_apps'))
    for key in ('primary_app','original_linked_apps','people','requests'):check('source:'+key,end.get(key)==start[key])
    receipts=end.get('receipts',[]);current=[r for r in start['requests'] if r['revision']==2]
    check('delivery_count',len(receipts)==len(current))
    available=resources(final)
    for request in current:
        matches=[r for r in receipts if r.get('request')==request['id']]
        check(request['id']+':one_reply',len(matches)==1)
        expected=[r for r in available if r['scope']==request['scope']]
        check(request['id']+':real_artifacts',len(expected)==(2 if initial['task_id'] in {58,60,64,65} else 1))
        if len(matches)==1:
            receipt=matches[0]
            check(request['id']+':recipient',receipt.get('recipient')==request['recipient'])
            check(request['id']+':revision',receipt.get('revision')==2)
            actual=receipt.get('attachments',[])
            check(request['id']+':current_content',sorted(actual,key=lambda x:x['id'])==sorted(expected,key=lambda x:x['id']))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
