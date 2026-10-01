"""Project configuration, deterministic outputs and concrete delivery artifacts."""
from copy import deepcopy
import ast
import hashlib
import json
import random
from vic import business
from .domain import initialize
from .communications import file_record

TASKS={41,43}


def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fixture(task_id,seed,spec):
    base=business.generate(task_id,seed);items=[];projects=[];templates=[];documents=[]
    people=[dict(id=10+i,name=name) for i,name in enumerate(['林若宁','陈嘉树','程知夏'])]
    names=['客户反馈摘要','迭代会议纪要','运行巡检报告']
    records=[['客户希望导入表格时保留列名，并在格式错误时指出具体行。','试用团队建议将首次配置步骤集中到同一页，减少来回切换。','支持人员希望在工单详情中查看最近一次处理记录。'],
             ['陈嘉树负责导入向导，周三前提交交互稿。','林若宁负责回归样本，周四前完成边界数据整理。','程知夏负责发布说明，周五下午与支持团队核对。'],
             ['资料导出队列在九点出现积压，十点恢复正常。','定时备份校验全部通过，恢复演练计划安排在周六。','两台测试节点需要更新证书，负责人已登记维护窗口。']]
    for i,name in enumerate(names):
        p=dict(id=f'project-{i+1}',name=name,recipient=people[i]['id'],task_prefix=f'S{i+1}',outputs=[],min_context=[32,64,128][i],available_models=[],template=f'template-{i+1}-v2',document=f'document-{i+1}-v2')
        projects.append(p)
        for version in (1,2):
            templates.append(dict(id=f'template-{i+1}-v{version}',project=p['id'],name=name+'模板',version=f'v{version}',heading=['反馈要点','行动事项','巡检记录'][i],limit=2 if version==1 else 10,
                text=f'将“{name}”资料逐条整理成有序清单。保留原资料中的负责人、时间与具体事项。'+('仅取前两条。' if version==1 else '覆盖全部资料条目。')))
            documents.append(dict(id=f'document-{i+1}-v{version}',project=p['id'],name=name+'资料',version=f'v{version}',records=records[i] if version==2 else [text.replace('周三','上周三').replace('九点','昨天九点') for text in records[i][:2]],
                updated_at=f'2026-02-{9+version:02d}T09:00:00+08:00'))
    if task_id==41:
        prototypes=[('Atlas Long',128,12),('Cedar Economy',64,2),('R3',32,7),('Boreal Wide',256,15),('Orchid Lite',128,3),('P4',64,9),('Summit Ultra',512,18),('Maple Saver',256,4),('Q5',128,11),('Z',8,0.1),('Aurora Max',1024,0.5)]
        for n,(name,context,price) in enumerate(prototypes):
            item=deepcopy(base['items'][n%6]);item.update(id=f'model-{n}',model_code=f'M-{n+1:02d}',name=name,name_length=len(name),context=context,price=price);items.append(item)
        random.Random(seed).shuffle(items)
    else:
        for i,p in enumerate(projects):
            codes=[f'def {"summarize" if i==0 else "meeting" if i==1 else "inspect"}_records(records):\n    return [str(record).strip() for record in records]\n',
                   'def count_items(items):\n    return len(items)\n',
                   'def normalize_name(name)\n    return name.strip()\n',
                   'def first_record(records):\n    return records[0\n']
            order=list(range(4));random.Random(seed+307*i).shuffle(order)
            for position,n in enumerate(order):
                code=f'# {p["name"]} / GEN-{i+1}{position+1:02d}\n'+codes[n]
                item=deepcopy(base['items'][n]);item.update(id=f'{i}-{n}',project=p['id'],project_name=p['name'],record_code=f'GEN-{i+1}{position+1:02d}',name=['记录整理.py','条目计数.py','名称标准化.py','首条记录.py'][n],code=code,text=code,batch='2026-W06');items.append(item)
        extra=deepcopy(items[0]);extra.update(id='historical',project='historical',project_name='历史项目',record_code='GEN-OLD',batch='2026-W05');items.append(extra)
    base['items']=items;state=initialize(base)
    for i,p in enumerate(projects):
        if task_id==41:p['available_models']=[item['id'] for item in state['items'] if item['model_code'] in [f'M-{n+1:02d}' for n in range(i*3,i*3+3)]+['M-10']]
        else:p['outputs']=[item['id'] for item in state['items'] if item.get('project')==p['id']]
    state.update(workflow='studio_projects',linked_apps=['studio','im'] if task_id==43 else ['studio'],
        execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),
        world=dict(projects=projects,people=people,templates=templates,documents=documents,configs={},generations={},archives={},checks={},saved={},copies={},receipts=[],discussion=[],delivery=dict(rows={},saved=None),
            brief=('为三个项目分别保存模型配置：先满足项目的上下文下限与可用模型名单，再按视频标准选模型。上下文单位为 K，价格为每百万 token 的人民币价格，名称长度包含空格；并列按模型编号升序。绑定项目要求的 v2 模板与 v2 资料，运行后将结果归档到对应项目，保留一份最终归档。相同配置和资料可重复生成相同内容。'
                if task_id==41 else '只处理三个项目本期输出清单中的文件，逐项运行 Python 语法检查；检查只解析语法，不执行程序。按视频方式交付通过项，失败项只保留检查报告。保存方式须将实际文件加入交付清单；复制方式须把复制的完整代码粘贴到该文件的交付栏；发送方式须发给项目指定联系人，并把对应回执加入清单。最后保存完整的交付清单。历史项目文件不交付。')))
    return state


def generate_text(state,project,config):
    w=state['world'];model=state['domain']['objects'][config['model']]
    template=next(x for x in w['templates'] if x['id']==config['template'])
    document=next(x for x in w['documents'] if x['id']==config['document'])
    header=f'# {project["name"]}\n\n模型：{model["name"]}\n模板：{template["name"]} / {template["version"]}\n资料：{document["name"]} / {document["version"]}\n\n## {template["heading"]}\n\n'
    return header+'\n'.join(f'{i+1}. {record}' for i,record in enumerate(document['records'][:template['limit']]))+'\n'


def check_output(text):
    try:ast.parse(text);return dict(passed=True,digest=digest(text),message='Python 语法检查通过')
    except (SyntaxError,ValueError,TypeError) as exc:return dict(passed=False,digest=digest(text),message=f'语法检查未通过：{getattr(exc,"msg",str(exc))}'+(f'（第 {exc.lineno} 行）' if getattr(exc,'lineno',None) else ''))


def manifest_text(state,rows):
    lines=['# 生成结果交付清单','']
    for project in state['world']['projects']:
        entries=[(target,row) for target,row in rows.items() if state['domain']['objects'][target]['project']==project['id']]
        if not entries:continue
        lines+=['## '+project['name'],'']
        for target,row in entries:
            item=state['domain']['objects'][target]
            lines += [f'### {item["record_code"]} · {item["name"]}',f'方式：{dict(saved="保存",copied="复制",sent="发送")[row["kind"]]}',f'关联记录：{row["reference"]}']
            if row['kind']=='copied':lines+=['```python',row['body'].rstrip('\n'),'```']
            lines.append('')
    return '\n'.join(lines)+'\n'


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];objects=state['domain']['objects'];item_ids={item['id'] for item in state['items']}
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容需要有效 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    projects={p['id']:p for p in w['projects']}
    if op=='config.save':
        if state['task_id']!=41 or target not in projects or set(data)!={'model','template','document'} or data['model'] not in item_ids or data['template'] not in [x['id'] for x in w['templates']] or data['document'] not in [x['id'] for x in w['documents']]:raise ValueError('请选择项目、模型、模板和资料')
        if data['model'] not in projects[target]['available_models'] or objects[data['model']]['context']<projects[target]['min_context']:raise ValueError('模型不满足本项目的可用范围或上下文下限')
        w['configs'][target]=deepcopy(data);return state
    if op=='generation.run':
        if state['task_id']!=41 or target not in w['configs']:raise ValueError('请先保存项目配置')
        config=w['configs'][target];body=generate_text(state,projects[target],config)
        key=f'generation-{state.get("next_generation",1):03d}';state['next_generation']=state.get('next_generation',1)+1
        w['generations'][key]=dict(id=key,project=target,config=deepcopy(config),body=body,digest=digest(body));return state
    if op=='generation.archive':
        if target not in w['generations'] or set(data)!={'project'} or data['project'] not in projects:raise ValueError('请选择生成结果和归档项目')
        generation=w['generations'][target];key=f'archive-{state.get("next_archive",1):03d}';state['next_archive']=state.get('next_archive',1)+1
        file='file-'+key
        state['domain']['files'][file]=file_record(projects[data['project']]['name']+'.md',generation['body'])
        w['archives'][key]=dict(id=key,generation=target,project=data['project'],file=file,config=deepcopy(generation['config']),link='files/'+file);return state
    if op=='archive.remove':
        if target not in w['archives']:raise ValueError('归档记录不存在')
        archive=w['archives'].pop(target);state['domain']['files'].pop(archive['file'],None);return state
    if op=='message.send':
        if target not in [str(p['id']) for p in w['people']] or set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请填写消息并选择联系人')
        w['discussion'].append(dict(id=len(w['discussion'])+1,recipient=int(target),body=data['text'].strip()));return state
    if op=='delivery.save':
        if state['task_id']!=43 or not w['delivery']['rows']:raise ValueError('请先完成交付清单')
        state['domain']['files']['delivery-manifest']=file_record('生成结果交付清单.md',manifest_text(state,w['delivery']['rows']))
        w['delivery']['saved']=deepcopy(w['delivery']['rows']);return state
    if state['task_id']!=43 or target not in item_ids:raise ValueError('生成结果不存在')
    item=objects[target]
    if op=='output.check':w['checks'][target]=check_output(item['code']);return state
    if op=='output.clear':
        if target in w['saved']:state['domain']['files'].pop(w['saved'].pop(target),None)
        w['copies'].pop(target,None);w['receipts']=[r for r in w['receipts'] if r['target']!=target];w['delivery']['rows'].pop(target,None);return state
    if op=='delivery.remove':w['delivery']['rows'].pop(target,None);return state
    checked=w['checks'].get(target)
    if not checked or not checked['passed'] or checked['digest']!=digest(item['code']):raise ValueError('请先运行检查；只有通过的结果可以交付')
    if op=='output.save':
        key='output-'+target
        state['domain']['files'][key]=file_record(item['record_code']+'-'+item['name'],item['code']);w['saved'][target]=key
    elif op=='output.copy':w['copies'][target]=dict(body=item['code'],digest=digest(item['code']))
    elif op=='output.send':
        if set(data)!={'recipient'} or data['recipient'] not in [p['id'] for p in w['people']]:raise ValueError('请选择交付联系人')
        key=f'receipt-{state.get("next_receipt",1):03d}';state['next_receipt']=state.get('next_receipt',1)+1
        w['receipts'].append(dict(id=key,target=target,recipient=data['recipient'],name=item['name'],record_code=item['record_code'],body=item['code'],digest=digest(item['code']),link='outputs/'+target))
    elif op=='delivery.line':
        if set(data)!={'kind','reference'} or data['kind'] not in ('saved','sent') or not isinstance(data['reference'],str):raise ValueError('请选择交付方式及实际记录')
        allowed=['files/'+file for file in w['saved'].values()] if data['kind']=='saved' else ['receipts/'+r['id'] for r in w['receipts']]
        if data['reference'] not in allowed:raise ValueError('交付记录不存在')
        w['delivery']['rows'][target]=dict(kind=data['kind'],reference=data['reference'])
    elif op=='delivery.paste':
        if target not in w['copies'] or set(data)!={'body'} or not isinstance(data['body'],str) or len(data['body'])>16000:raise ValueError('请先复制本项结果，再粘贴到对应交付栏')
        w['delivery']['rows'][target]=dict(kind='copied',reference='copies/'+target,body=data['body'])
    else:raise ValueError('未知项目操作')
    return state
