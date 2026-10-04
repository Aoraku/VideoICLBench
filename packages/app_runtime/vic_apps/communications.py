"""Project communications and document delivery; ordinary business commands only."""
from copy import deepcopy
import base64
import hashlib
import json
import random
from vic import business
from .domain import initialize

TASKS = {11, 13, 15}


def file_record(name, text):
    content = text.encode('utf-8')
    return dict(name=name, content=base64.b64encode(content).decode(),
                size=len(content), sha256=hashlib.sha256(content).hexdigest())


def fixture(task_id, seed, spec):
    rng = random.Random(seed)
    base = business.generate(task_id, seed)
    names = ['春季发布', '客户培训', '园区导览', '产品验收'][:3 if task_id == 15 else 4]
    people = ['林若宁', '陈以安', '许知遥', '沈沐言']
    projects = []; items = []; requests = []; conversations = []
    for index, name in enumerate(names):
        project = dict(id=f'P-{index+1:03d}', name=name, requester=10+index,
                       conversation=20+index, request_conversation=10+index)
        projects.append(project)
        conversations += [dict(id=10+index, name=people[index], user_id=10+index, project=project['id']),
                          dict(id=20+index, name=name+' · 项目资料', user_id=20+index, project=project['id'])]
        group = business.generate(task_id, seed + 137 * index)
        for n, original in enumerate(group['items']):
            item = deepcopy(original)
            item.update(id=f'{index}-{n}', project=project['id'], project_name=name,
                        conversation=project['conversation'], record_code=f'{task_id:03d}-{index+1}{n+1:02d}')
            if task_id == 11:
                # Three eligible files have independent extrema. Other files
                # exercise version/type/project filtering before the rule.
                item['name'] = ['完整交付说明.txt', '详细项目背景资料.txt', '摘要.txt', '摘要.txt', '预算.csv', '旧版说明.txt'][n]
                item['file_type'] = 'CSV' if n == 4 else 'TXT'
                item['version'] = '草案' if n == 3 else '历史版' if n == 5 else '审定版'
                item['file_text'] = f'{name}\n编号：{item["record_code"]}\n{item["name"]} · {item["version"]}\n' + ('项目资料。' * [8, 70, 28, 2, 10, 120][n])
                item['size'] = len(item['file_text'].encode('utf-8'))
                item['name_length'] = len(item['name'])
            elif task_id == 13:
                item['batch'] = '晚班-0115'
                item['text'] = f'[{item["record_code"]}] {name} · 批次 {item["batch"]}\n' + (
                    [f'紧急：{name}今晚的入场名单缺少两位讲师，请早班联系会务补全后再发给门岗。',
                     f'紧急：{name}演示投影无法连接电脑，请设备值班员在明早彩排前检查转接线。',
                     f'紧急：{name}签到材料还未送达，请联系印务确认送达时间并通知接待组。',
                     f'紧急：{name}客户补充了无障碍通行需求，请场地负责人确认电梯入口。',
                     f'紧急：{name}最新议程的讲师时段有冲突，请项目协调员联系双方确认。',
                     f'紧急：{name}供应商申请更换到货入口，请仓库值班员确认卸货安排。'][n % 6]
                    if '紧急' in item['text'] else
                    [f'{name}的饮水和纸杯已补齐，数量登记在物资表，不需要追加采购。',
                     f'{name}场地照片已经归档，可供下次活动布置参考。',
                     f'{name}的参会反馈问卷下周汇总，暂时没有待跟进事项。'][n % 3])
                item['created_at'] = f'2026-01-15T{6+n:02d}:00:00+00:00'
            else:
                item['account'] = f'EMP-{index+1}{n+1:03d}'
                item['conversation'] = 2
            items.append(item)
        if task_id == 13:
            old = deepcopy(items[-6])
            old.update(id=old['id']+'-old', record_code=old['record_code']+'H', batch='早班-0115')
            old['text'] = f'[{old["record_code"]}] {name} · 批次 早班-0115\n紧急：上午的资料需要留档。'
            old['created_at'] = '2026-01-15T03:00:00+00:00'; items.append(old)
        request_id = f'REQ-{index+1:03d}'
        requests.append(dict(id=request_id, project=project['id'], requester=10+index,
            conversation=10+index, message_id=5000+index, file_type='TXT', version='审定版',
            body=f'请求 {request_id}：请从“{name} · 项目资料”会话查找项目 {project["id"]} 的 TXT 审定版附件，按视频标准选一份，回复给我并关联本请求。'))
    if task_id == 11:
        rng.shuffle(items)
    if task_id == 13:
        extra = deepcopy(items[-1]); extra.update(id='outside',conversation=50,project='P-999',project_name='其他项目',record_code='013-999')
        extra['text']='[013-999] 其他项目 · 批次 晚班-0115\n紧急：旧项目的文件需归档。';items.append(extra)
    base['items'] = items
    state = initialize(base)
    for index, item in enumerate(state['items']):
        item['message_id'] = 100 + index
        state['domain']['objects'][item['id']]['message_id'] = 100 + index
    conversations += [dict(id=2,name='程知夏 · 早班负责人',user_id=2,project=''),dict(id=50,name='其他项目',user_id=50,project='P-999')]
    state.update(workflow='communications',execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']))
    state['world'] = dict(projects=projects, requests=requests, conversations=conversations,
        handover=dict(title='晚班消息交接单', rows={}, sent=False), documents={}, groups={},
        brief={11:'处理四位项目负责人的资料请求。先按项目号、文件类型及版本限定候选，再按视频标准选文件；每条请求只交付一次，须关联原请求并发回请求人。文件体积按字节、名称长度包含扩展名，并列选资料列表中靠前的文件。',
               13:'你负责晚班消息交接。只处理春季发布、客户培训、园区导览、产品验收四个项目中“晚班-0115”批次的消息。按视频方式处理含“紧急”的消息，转发收件人为程知夏。交接单只列本次应处理消息，包含任务编号、原消息链接和实际处理结果；发送给程知夏，历史批次与其他项目不变。',
               15:'为三个项目各创建一个工作群。每项目独立选三位成员，比较任务开始时的姓名长度、最近联系时间与未读数；并列按候选名单初始顺序。核对账号，使用通知中的群名和公告，把对应资料链接发入群。'}[task_id])
    state['source']['recipient'] = '程知夏'
    if task_id == 15:
        for project in projects:
            project.update(group_name=project['name']+'工作群',announcement=f'{project["name"]}启动会：2026-01-20 14:00，会议室 {project["id"][-1]}。请于会前阅读项目资料。',
                material_link='/native-assets/im/projects?project='+project['id'],
                material=f'{project["id"]}-brief.txt',material_text=f'{project["name"]}项目资料\n目标：完成{project["name"]}的准备与交付。\n资料编号：{project["id"]}-brief\n联系人：{people[projects.index(project)]}')
    state['linked_apps'] = ['studio']
    if task_id == 11:
        state['world']['materials'] = deepcopy(state['domain']['files'])
        state['domain']['files'] = {}
        for request in state['world']['requests']:
            request['body'] = request['body'].replace('会话查找', '对应的 Studio 项目资料库查找') + ' 请将所选原文件导入 Chat 后回复附件，不能只发文件名。'
        state['world']['brief'] += ' 原文件保存在 Studio 项目资料库；先按项目号查找并导入所选文件，再回 Chat 交付。'
    elif task_id == 13:
        state['world']['brief'] += ' 消息在 Chat 处理，交接清单在 Studio 项目文档编制并保存，再回 Chat 发送已保存的真实交接文件。'
    else:
        state['world']['brief'] += ' 建群后到 Studio 为每个项目编制含实际群成员账号的项目简报，再把该简报入口发入对应群。群成员变化后须重新保存简报。'
    return state


def message_link(item):
    return f'/chat?open={item["conversation"]}&msg={item["message_id"]}'


def handover_text(doc):
    return '# '+doc['title']+'\n\n'+'\n'.join(f'- {row["task_number"]} · {row["project"]} · {row["status"]} · 原消息索引：{row["link"]}' for row in doc['rows'].values())


def project_brief(state, project, group):
    """Snapshot of the actual project roster, not a rule-derived answer."""
    people = {item['id']: item for item in state['items']}
    roster = [dict(id=key, name=people[key]['name'], account=people[key]['account']) for key in group['members']]
    body = project['material_text'] + '\n\n' + group['announcement'] + '\n\n项目组：' + group['name'] + '\n' + '\n'.join(f"- {p['name']} · {p['account']}" for p in roster)
    return dict(project=project['id'], group=str(group['id']), name=group['name'], announcement=group['announcement'], roster=roster, body=body)


def apply(state, op, target='', value='', ids=None):
    state = deepcopy(state); w=state['world']; d=state['domain']; t=state['task_id']
    if op=='action' and t==13:
        obj=d['objects'].get(target)
        if not obj or target not in {x['id'] for x in state['items']} or value not in ('转发','收藏','归档'):
            raise ValueError('请选择消息与有效操作')
        if value=='转发':
            d['messages'].append(dict(id=f'sent-{len(d["messages"])+1}',sender='self',recipient='2',
                body=obj['text'],reference=target,attachment=None))
        elif value=='收藏':
            obj['starred']=True
            if target not in d['collections']['favorites']:d['collections']['favorites'].append(target)
        else:obj['archived']=True
        return state
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('请提供有效操作内容') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='document.import' and t==11:
        if data or target not in w['materials']:
            raise ValueError('请选择项目资料库中的原文件')
        d['files'][target]=deepcopy(w['materials'][target])
    elif op=='file.send' and t==11:
        if set(data)!={'file','recipient','request'}:raise ValueError('请选择附件、收件人和原请求')
        if data['file'] not in d['files'] or data['recipient'] not in {c['user_id'] for c in w['conversations']} or data['request'] not in {r['id'] for r in w['requests']}:
            raise ValueError('附件、收件人或请求不存在')
        d['messages'].append(dict(id=f'sent-{len(d["messages"])+1}',sender='self',recipient=str(data['recipient']),
            body='资料回复 · '+data['request'],reference=data['request'],attachment=data['file']))
    elif op=='handover.line' and t==13:
        if set(data)!={'status'} or target not in {x['id'] for x in state['items']} or data['status'] not in ('待处理','已转发','已收藏','已归档'):
            raise ValueError('请选择原消息和处理结果')
        if w['handover']['sent']:raise ValueError('交接单已经发送')
        item=d['objects'][target]
        w['handover']['rows'][target]=dict(message=target,task_number=item['record_code'],project=item['project'],link=message_link(item),status=data['status'])
    elif op=='handover.remove' and t==13:
        if w['handover']['sent']:raise ValueError('交接单已经发送')
        if target not in w['handover']['rows']:raise ValueError('交接项不存在')
        del w['handover']['rows'][target]
    elif op=='handover.save' and t==13:
        if data or not w['handover']['rows'] or w['handover']['sent']:
            raise ValueError('请先编制未发送的交接清单')
        doc=w['handover'];body=handover_text(doc);key='handover-001'
        w['documents'][key]=dict(id=key,title=doc['title'],rows=deepcopy(doc['rows']),body=body)
        d['files'][key]=file_record(doc['title']+'.md',body)
    elif op=='handover.send' and t==13:
        if set(data)!={'recipient'} or data['recipient'] not in {c['user_id'] for c in w['conversations']}:
            raise ValueError('请选择有效收件人')
        doc=w['handover']
        if not doc['rows'] or doc['sent']:raise ValueError('请添加交接项；已发送的交接单不可重复发送')
        body=handover_text(doc)
        saved=w['documents'].get('handover-001')
        if not saved or saved.get('body')!=body or saved.get('rows')!=doc['rows']:
            raise ValueError('请到 Studio 保存最新交接文档后再发送')
        key='handover-001';record=dict(id=key,title=doc['title'],rows=deepcopy(doc['rows']),body=body,recipient=data['recipient'])
        w['documents'][key]=record;d['files'][key]=file_record(doc['title']+'.md',body)
        d['messages'].append(dict(id=f'sent-{len(d["messages"])+1}',sender='self',recipient=str(data['recipient']),
            body=doc['title'],reference=key,attachment=key))
        doc['sent']=True
    elif op=='group.create' and t==15:
        if set(data)!={'name','members'} or not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>80:
            raise ValueError('请填写群名称并选择成员')
        members=data['members']
        if not isinstance(members,list) or not members or len(members)!=len(set(members)) or not set(members)<={x['id'] for x in state['items']}:
            raise ValueError('请选择有效且不重复的群成员')
        key=100+state.get('next_group',0);state['next_group']=state.get('next_group',0)+1
        w['groups'][str(key)]=dict(id=key,name=data['name'].strip(),members=list(members),announcement='',messages=[])
    elif op=='project.brief' and t==15:
        project=next((p for p in w['projects'] if p['id']==target),None)
        group=w['groups'].get(str(data.get('group','')))
        if set(data)!={'group'} or not project or not group or not group['announcement']:
            raise ValueError('请选择项目与已填写公告的工作群')
        doc=project_brief(state,project,group);key='brief-'+project['id']
        w['documents'][key]=doc;d['files'][key]=file_record(project['name']+'项目简报.md',doc['body'])
    elif op in ('group.name','group.announcement','group.message','group.members','group.delete') and t==15:
        group=w['groups'].get(target)
        if not group:raise ValueError('群聊不存在')
        if op=='group.delete':del w['groups'][target]
        elif op=='group.members':
            members=data.get('members')
            if set(data)!={'members'} or not isinstance(members,list) or not members or len(members)!=len(set(members)) or not set(members)<={x['id'] for x in state['items']}:raise ValueError('请选择有效成员')
            group['members']=list(members)
        else:
            if set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请填写有效内容')
            if op=='group.name':group['name']=data['text']
            elif op=='group.announcement':group['announcement']=data['text']
            else:
                project=next((p for p in w['projects'] if p['material_link']==data['text']),None)
                if project and w['documents'].get('brief-'+project['id'])!=project_brief(state,project,group):
                    raise ValueError('请先在 Studio 保存与当前群成员、公告一致的项目简报')
                group['messages'].append(dict(id=len(group['messages'])+1,body=data['text']))
    else:raise ValueError('此操作不适用于当前工作区')
    return state
