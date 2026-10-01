"""Draft scheduling, published articles and editor/author deliveries."""
from copy import deepcopy
from datetime import datetime
import json
import random
from vic import business
from .domain import initialize

TASKS={40,42}


def fixture(task_id,seed,spec):
    state=business.generate(task_id,seed);items=[]
    columns=[dict(id=f'column-{i+1}',name=name) for i,name in enumerate(['城市观察','生活方式','技术札记'])]
    authors=[dict(id=10+i,name=name,account=f'author-{i+1:02d}') for i,name in enumerate(['林若宁','陈嘉树','苏念','程知夏','许知远','唐清越'])]
    projects=[];letter=state['source']['letter']
    texts=[
        ['南门公交站增设了候车雨棚，早高峰还增加了两班区间车。乘客可以在站牌查看到站时间，绕行期间的换乘指引也已贴出。街道将收集一周反馈，再决定晚高峰是否采用同样的安排。',
         '社区图书馆把周末开放时间延长到晚上八点，并增设了儿童阅读区。借阅台旁可以报名参加周六的共读活动，每场活动限二十人。',
         '街角饮水点已开放，居民可自带水杯取用。',
         '旧市场外的步道完成照明维修，入口增设了无障碍坡道。施工结束后，沿街商户恢复了正常营业。夜间巡查会持续到月底，发现灯具故障可向服务站报修。',
         '街道公布了本季度公共空间改造名单，居民可以查阅设计草图并填写意见。首轮反馈将围绕休息座椅、树荫和自行车停放区域展开，汇总结果会在下月议事会上公开。',
         '周末市集调整了摊位分区，手作、餐饮与二手交换各有独立区域。主办方同时增加垃圾分类点，并给摊主发放了收摊检查表。试行两周后将根据通行情况调整布局。'],
        ['我们把一周菜单按现有食材重新安排，先使用保鲜期较短的蔬菜，再补充主食和蛋白质。购物清单分为必需与可替换两栏，可以减少临时采购。周末复盘时记录实际剩余量，为下周提供依据。',
         '阳台花盆按日照时长重新摆放，喜阴植物移到靠墙的位置。浇水记录写在小卡片上，出差时家人也能按同一份记录照顾植物，避免重复浇水。',
         '玄关增加钥匙托盘，出门前更容易找到随身物品。',
         '换季衣物先按使用频率分类，常穿的放在容易拿取的位置。暂时不用的衣物清洁后装入收纳袋，标签写明类别与季节。整理结束后预留一层空格，方便后续取放。',
         '一次步行计划从家附近的公园开始，路线包含休息点与饮水处。同行者提前约定集合时间，并根据天气准备雨具。实际走完后记录耗时，下一次可据此缩短或延长路线。',
         '家庭阅读角采用可调节台灯与矮书架，孩子能自己选择读物。晚间共读不追求读完一本书，而是轮流描述最感兴趣的画面。每周更换一部分书目，让阅读保持新鲜感。'],
        ['项目把每天的构建结果归档到独立目录，并在日志中保留版本号与执行时间。发生失败时，维护者可以先查看最早的错误，再决定是否重试。清理策略只删除超过保留期限的产物，近期结果始终可追溯。',
         '我们给配置文件增加了字段说明，并准备了一份最小可运行示例。新成员可以先运行示例验证环境，再替换自己的参数。示例使用固定输入，方便比较每次修改的结果。',
         '下载文件后校验摘要，可以发现传输损坏。',
         '文档索引按读者要完成的工作组织，每个入口都链接到可运行的示例。维护者在发布时检查链接，并注明示例适用的版本。这样读者可以从操作步骤追溯到接口说明。',
         '数据导入前先检查列名、编码和必填字段，发现问题时保留原始文件并生成错误清单。修正文件后只重试失败批次，成功批次不会重复写入，减少了人工核对的工作量。',
         '测试环境使用固定的参考数据，运行结束后保存关键输出与日志。每个测试案例有独立编号，报告可以直接关联到输入样本。团队每周审查失败案例，确认问题来自实现还是数据变化。']]
    titles=['一周服务观察','把改变记录下来','一则现场短记','日常工作中的小调整','从反馈到下一步行动','试行两周后的复盘']
    for i,column in enumerate(columns):
        project=dict(id=f'project-{i+1}',name=column['name']+'编辑计划',column=column['id'],batch='2026-W06',candidates=[])
        projects.append(project);rng=random.Random(seed+211*i);order=list(range(6));rng.shuffle(order)
        base=business.generate(task_id,seed+211*i)['items']
        for position,n in enumerate(order):
            item=deepcopy(base[n]);name=f'{column["name"]}：{titles[n]}'
            if task_id==42 and n in (0,2,4):name=letter+' 版｜'+name
            item.update(id=f'{i}-{n}',project=project['id'],project_name=project['name'],batch=project['batch'],record_code=f'D{i+1}-{position+1:03d}',
                name=name,name_length=len(name),text=texts[i][n],created_at=f'2026-02-{[9,1,5,7,3,6][n]:02d}T09:00:00+08:00',
                author=authors[2*i+n%2]['id'],tag_count=[0,1,2,3,4,0][n],tags=['观察','记录','专题','实践'][:[0,1,2,3,4,0][n]],
                default_cover=f'cover-{i}',summary=texts[i][n].split('。')[0]+'。',plan_column=columns[(i+n)%3]['id'] if task_id==42 else column['id'],
                plan_time=f'2026-02-{12+i:02d}T{9+n:02d}:00')
            item['updated_at']=item['created_at'];items.append(item)
        old=deepcopy(items[-1]);old.update(id=f'{i}-old',name=letter+' 版｜上期备用稿',batch='2026-W05',record_code=f'D{i+1}-OLD',text='上期短记。',tag_count=4,tags=['观察','记录','专题','实践'],created_at='2026-02-10T09:00:00+08:00',updated_at='2026-02-10T09:00:00+08:00')
        items.append(old)
    private=deepcopy(items[0]);private.update(id='personal',project='personal',project_name='个人随笔',batch='私人',record_code='PRIVATE-01',name='周末随手记')
    items.append(private);state['items']=items;state=initialize(state)
    covers=[dict(id=f'cover-{i}',name=['通勤时刻','街区散步','窗边阅读','周末市集','绿色日常','工作笔记'][i],url=f'/native-assets/blog/cover-{i}.svg') for i in range(6)]
    plan=[]
    for i,project in enumerate(projects):
        project['candidates']=[x['id'] for x in state['items'] if x['project']==project['id'] and x['batch']==project['batch']]
        project.update(cover=f'cover-{i+3}',summary=['记录城市公共服务的具体变化与居民反馈。','整理可在日常生活中尝试的小方法。','分享团队工作中可重复使用的技术实践。'][i],publish_at=f'2026-02-{12+i:02d}T10:00')
        for item in state['items']:
            if item['id'] in project['candidates']:
                plan.append(dict(draft=item['id'],project=project['id'],column=item['plan_column'],publish_at=item['plan_time'],cover=item['default_cover'],summary=item['summary']))
    state.update(workflow='publishing',linked_apps=['blog','im'] if task_id==42 else ['blog'],
        execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),
        world=dict(projects=projects,columns=columns,covers=covers,authors=authors,plan=plan,edits={},publications={},index={},notifications=[],discussion=[],reference_time='2026-02-28T12:00:00+08:00',
            brief=('三个栏目各发布一篇：只从对应编辑计划列出的本期草稿中选择，比较依据为最初的更新时间或正文字数；字数包含正文标点与空格，不含标题。填写编辑计划给出的封面、摘要及发布时间，发布后将文章链接加入对应栏目索引。并列时按稿件编号升序选择第一篇，勿发布上期备用稿或私人随笔。'
                if task_id==40 else f'只处理本周排期表列出的本期草稿。按视频规则判断发布集合；标题匹配字符为“{letter}”，区分大小写，标签数按稿件实际标签计算。保留稿件原封面与摘要，为命中项填写排期表指定的栏目和时间，发布并加入对应栏目目录，再把实际文章链接发给稿件作者。未命中稿件、上期备用稿与私人随笔保持未发布。')+' 所有发布时间使用北京时间，精确到分钟。'))
    return state


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];objects=state['domain']['objects'];draft_ids={item['id'] for item in state['items']}
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容需要有效 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='post.metadata':
        if target not in draft_ids or set(data)!={'column','cover','summary','publish_at'} or data['column'] not in [c['id'] for c in w['columns']] or data['cover'] not in [c['id'] for c in w['covers']] or not isinstance(data['summary'],str) or not 1<=len(data['summary'])<=500 or not isinstance(data['publish_at'],str):raise ValueError('请填写栏目、封面、摘要和发布时间')
        try:parsed=datetime.fromisoformat(data['publish_at'])
        except (ValueError,TypeError) as exc:raise ValueError('发布时间无效') from exc
        if parsed.strftime('%Y-%m-%dT%H:%M')!=data['publish_at']:raise ValueError('请按北京时间填写日期和时分')
        if any(p['draft']==target for p in w['publications'].values()):raise ValueError('请先撤下文章再修改发布资料')
        w['edits'][target]=deepcopy(data);return state
    if op=='post.publish':
        if target not in draft_ids or target not in w['edits']:raise ValueError('请先保存发布资料')
        if any(p['draft']==target for p in w['publications'].values()):raise ValueError('此稿件已经发布')
        item=objects[target];key=f'post-{state.get("next_publication",1):03d}';state['next_publication']=state.get('next_publication',1)+1
        w['publications'][key]=dict(id=key,draft=target,title=item['name'],body=item['text'],author=item['author'],**w['edits'][target],link='posts/'+key)
        return state
    if op in ('index.add','index.remove'):
        if target not in [c['id'] for c in w['columns']] or set(data)!={'publication'} or data['publication'] not in w['publications']:raise ValueError('请选择栏目及已发布文章')
        key=data['publication'];entries=w['index'].setdefault(target,[])
        if op=='index.add' and not any(entry['publication']==key for entry in entries):entries.append(dict(publication=key,link=w['publications'][key]['link']))
        if op=='index.remove':
            w['index'][target]=[entry for entry in entries if entry['publication']!=key]
            if not w['index'][target]:del w['index'][target]
        return state
    if op=='notice.withdraw':
        if target not in [n['id'] for n in w['notifications']]:raise ValueError('通知不存在')
        w['notifications']=[n for n in w['notifications'] if n['id']!=target];return state
    if op=='message.send':
        if target not in [str(a['id']) for a in w['authors']] or set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请填写消息并选择作者')
        w['discussion'].append(dict(id=len(w['discussion'])+1,recipient=int(target),body=data['text'].strip()));return state
    post=w['publications'].get(target)
    if not post:raise ValueError('已发布文章不存在')
    if op=='post.withdraw':
        if any(e['publication']==target for rows in w['index'].values() for e in rows) or any(n['publication']==target for n in w['notifications']):raise ValueError('请先移除目录条目并撤回作者通知')
        del w['publications'][target]
    elif op=='post.notify':
        if set(data)!={'recipient'} or data['recipient'] not in [a['id'] for a in w['authors']]:raise ValueError('请选择通知收件人')
        key=f'notice-{state.get("next_notice",1)}';state['next_notice']=state.get('next_notice',1)+1
        w['notifications'].append(dict(id=key,recipient=data['recipient'],publication=target,title=post['title'],summary=post['summary'],link=post['link'],publish_at=post['publish_at']))
    else:raise ValueError('未知发布操作')
    return state
