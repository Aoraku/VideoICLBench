"""News research and editable Blog documents; learned selection rules stay private."""
from copy import deepcopy
from datetime import datetime,timezone
import json
import random
from vic import business
from .domain import initialize

TASKS={29,30}


def fixture(task_id,seed,spec):
    state=business.generate(task_id,seed);items=[];scopes=[]
    themes=['城市交通','公共文化','社区服务','绿色生活'] if task_id==29 else ['通勤改善','阅读推广','街区更新']
    for i,name in enumerate(themes):
        scope=dict(id=f'topic-{i+1}',name=name,number=i+1,date_from='2026-01-01',date_to='2026-01-31',sources=[])
        scopes.append(scope);base=business.generate(task_id,seed+197*i)['items']
        rng=random.Random(seed+197*i);positions=list(range(6 if task_id==29 else 8));rng.shuffle(positions)
        even=set(rng.sample(range(6),2+i))
        for position,n in enumerate(positions):
            item=deepcopy(base[n%6])
            title=[f'{name}观察',f'追踪{name}的新变化',f'走访六个街区：{name}服务如何回应居民日常需求与长期期待',f'{name}一线记录',f'{name}项目进展',f'从居民问卷看{name}的下一步行动'][n%6]
            date=f'2026-01-{[28,2,18,21,10,7][n%6]:02d}' if n<6 else ('2025-12-28' if n==6 else '2026-02-02')
            summary=f'{name}调研记录 {n+1}：整理现场访谈与服务数据，列出可供项目组讨论的具体发现及后续事项。'
            item.update(id=f'{i}-{n}',scope_id=scope['id'],scope_name=name,record_code=f'N{i+1}-{position+1:03d}',name=title,name_length=len(title),
                text=summary,summary=summary,created_at=date+'T09:00:00+00:00',timestamp=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()),
                publisher=['Echo','North','Orbit','Sky','Echo','North','AtlasNews','Daily'][n],tag_count=n if n<6 else 9,
                tags=['城市','观察','专题','公共','调研','周报','服务','资料','更新'][:n if n<6 else 9],comments=([2,3,6,9,8,11,14,17][n] if task_id==29 else 2*(n+1)+(0 if n in even else 1)))
            if n>=6:item.update(name=title+' · 跨月资料',name_length=len(title+' · 跨月资料'))
            items.append(item)
    extra=deepcopy(items[0]);extra.update(id='personal',scope_id='personal',scope_name='私人剪报',name='周末散步札记',record_code='PERSONAL-01')
    items.append(extra);state['items']=items;state=initialize(state)
    sources=[]
    for scope in scopes:
        rows=[x['id'] for x in state['items'] if x['scope_id']==scope['id']]
        groups=[rows] if task_id==29 else [rows[:5],rows[4:]]
        for n,group in enumerate(groups,1):
            key=f'{scope["id"]}-source-{n}';scope['sources'].append(key)
            sources.append(dict(id=key,name=scope['name']+f' · 来源清单 {n}',scope=scope['id'],members=group))
        scope['document_title']=scope['name']+' · 阅读资料'
    personal=dict(id='personal',scope='personal',title='私人剪报',sections={'personal':dict(heading='随手记',rows=[])})
    personal['saved']=deepcopy({k:v for k,v in personal.items() if k!='saved'})
    state.update(workflow='editorial_projects',linked_apps=['news','blog'],
        execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),
        world=dict(scopes=scopes,sources=sources,selections={s['id']:[] for s in scopes},documents={'personal':personal},directory={},
            report_title='城市观察 · 本周专题简报',
            brief=('按活动资料中的专题次序，每个专题选一篇文章；同一来源全简报最多两篇，已经达到配额的来源不再参与后续专题比较。按视频标准在剩余候选中选择，并列按文章编号升序。将所选文章的原文链接与给定摘要放入简报对应章节，保存“城市观察 · 本周专题简报”。'
                if task_id==29 else '为三个项目分别汇总指定来源清单。仅采用 2026-01-01 至 2026-01-31（含首尾两日）的文章，按文章编号去重，再在每个项目的候选范围中应用视频筛选规则。最大或最小值并列时全部保留；偶数条件保留全部命中项。用活动资料中的名称建立项目资料页，每篇包含原文链接与给定摘要。保存后在资料目录中登记三个页面的链接及实际文章数。')))
    return state


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];objects=state['domain']['objects']
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容需要有效 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    scope_ids={s['id'] for s in w['scopes']}
    if op=='reading.select':
        articles=data.get('articles')
        if target not in scope_ids or set(data)!={'articles'} or not isinstance(articles,list) or not all(isinstance(a,str) and a in objects and objects[a]['scope_id']==target for a in articles):raise ValueError('请选择属于当前专题或项目的文章')
        w['selections'][target]=list(dict.fromkeys(articles));return state
    if op=='document.create':
        allowed={'weekly'} if state['task_id']==29 else scope_ids
        if set(data)!={'scope','title'} or data['scope'] not in allowed or not isinstance(data['title'],str) or not data['title'].strip() or len(data['title'])>160:raise ValueError('请选择文档范围并填写标题')
        index=state.get('next_document',1);state['next_document']=index+1;key=f'doc-{index:03d}'
        sections={s['id']:dict(heading=s['name'],rows=[]) for s in w['scopes'] if data['scope']=='weekly' or s['id']==data['scope']}
        w['documents'][key]=dict(id=key,scope=data['scope'],title=data['title'].strip(),sections=sections,saved=None)
        return state
    if op=='directory.entry':
        if target not in scope_ids or set(data)!={'document','link','count'} or data['document'] not in w['documents'] or type(data['count']) is not int or data['count']<0 or not isinstance(data['link'],str) or len(data['link'])>300:raise ValueError('请填写有效的资料页、链接与文章数')
        w['directory'][target]=deepcopy(data);return state
    if op=='directory.remove':
        if target not in w['directory']:raise ValueError('目录条目不存在')
        del w['directory'][target];return state
    document=w['documents'].get(target)
    if not document:raise ValueError('文档不存在')
    if op=='document.delete':
        if any(entry['document']==target for entry in w['directory'].values()):raise ValueError('请先移除此文档的目录条目')
        del w['documents'][target];return state
    if op=='document.title':
        if set(data)!={'title'} or not isinstance(data['title'],str) or not data['title'].strip() or len(data['title'])>160:raise ValueError('请填写文档标题')
        document['title']=data['title'].strip()
    elif op=='document.article':
        if set(data)!={'section','article','link','summary'} or data['section'] not in document['sections'] or data['article'] not in objects or not all(isinstance(data[k],str) for k in ('link','summary')) or not data['link'] or not data['summary'] or len(data['link'])>300 or len(data['summary'])>4000:raise ValueError('请填写章节、原文链接和摘要')
        section=document['sections'][data['section']]
        row={k:data[k] for k in ('article','link','summary')}
        prior=next((i for i,r in enumerate(section['rows']) if r['article']==row['article']),None)
        if prior is None:section['rows'].append(row)
        else:section['rows'][prior]=row
    elif op=='document.remove':
        if set(data)!={'section','article'} or data['section'] not in document['sections']:raise ValueError('请选择章节中的文章')
        section=document['sections'][data['section']];section['rows']=[r for r in section['rows'] if r['article']!=data['article']]
    elif op=='document.save':
        if not all(s['rows'] for s in document['sections'].values()):raise ValueError('每个章节至少需要一篇文章')
        document['saved']=deepcopy({k:v for k,v in document.items() if k!='saved'})
    else:raise ValueError('未知资料整理操作')
    return state
