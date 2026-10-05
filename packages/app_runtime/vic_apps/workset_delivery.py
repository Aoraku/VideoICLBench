"""Editable operational documents built from native app work and source records.

No rule or variant is known here. Users choose the rows and join the supplied
business reference data; publication captures the actual saved application state.
"""
from copy import deepcopy
import base64
import hashlib
import json

# title, source document, row meaning, reference column, concrete reference values
CONFIG = {
2:('参会人员名册','会务席位表','参会成员','席位与职责',['A区讲师席','B区嘉宾席','C区会务席','A区演示席','B区合作方席','C区记录席']),
6:('客户联络名单','联系渠道登记表','联络对象','联系邮箱',['events@example.test','design@example.test','research@example.test','service@example.test']),
7:('值班响应安排','部门值班表','优先响应会话','值班负责人',['张文琪 / 上午班','郑晓岚 / 下午班','杨文博 / 夜间班']),
8:('项目群支持清单','群管理员登记表','需要重点支持的项目群','管理员工号',['OPS-102','OPS-205','OPS-308','OPS-411']),
9:('会议通知交付单','会议议程登记表','收到通知的联络人','会议资料编号',['AGENDA-采购评审','AGENDA-需求走查','AGENDA-交付沟通']),
12:('客服班次交接表','会话工单关联表','依次处理的会话','关联工单',['CASE-登录问题','CASE-账单咨询','CASE-安装支持','CASE-权限申请']),
14:('会话交接记录','项目责任登记表','本次处理的会话','后续负责人',['张文琪 / 客户服务','郑晓岚 / 技术支持','杨文博 / 交付协调']),
16:('项目通知回执台账','通知责任登记表','已处理回执','通知责任人',['陈乐然 / 发布联络','杜思齐 / 现场协调','何书涵 / 文档交付']),
22:('音乐节目单','节目解说资料','入选歌曲','播报介绍',['器乐开场，主持人介绍活动主题','来宾入场背景曲，保持低音量','中场交流曲，提醒观众自由交流','闭场致谢曲，主持人宣布结束']),
23:('专题编辑分工单','编辑轮值表','已分类文章','责任编辑',['周文静 / 城市报道','汪瑞晨 / 文化报道','罗静宜 / 社区报道']),
26:('栏目上架排期','视频版权与排期表','推荐视频','获准播放时段',['周六 09:00 首播','周六 14:00 复播','周日 10:00 首播','周日 15:00 复播']),
31:('课程教学安排','教学大纲','课程视频','教学目标',['识别观察对象并记录三个特征','比较两个镜头的叙事作用','解释公共文化空间的用途']),
33:('新闻值班跟进单','采访联系簿','需要跟进的文章','采访联系人',['城市服务站 / 010-55550101','社区活动室 / 010-55550202','文化中心 / 010-55550303']),
34:('学习资料复盘单','课程要求表','本次整理的视频','对应作业',['提交观察记录一页','完成镜头分析一页','整理主题要点一页']),
38:('内容编辑分工表','项目编辑安排','待编辑文章','负责编辑',['周文静 / 校对','汪瑞晨 / 编辑','罗静宜 / 终审']),
47:('差旅路线比较表','出差会议通知','候选行程','到达后会议地点',['虹桥会议中心 301','滨江研发中心 208']),
48:('采购询价清单','采购需求附件','优选商品','需求数量',['12 件','8 件','6 件','15 件']),
49:('月度支出分类台账','报销凭证索引','分类交易','原始凭证号',['RCPT-交通-012','RCPT-会务-023','RCPT-办公-034','RCPT-材料-045']),
50:('家庭账户安排表','账户用途登记表','已标注账户','本月资金用途',['住房与水电支出','学习与图书支出','出行与交通支出','医疗与备用金']),
53:('月度对账凭证包','财务归档目录','选定交易凭证','归档目录',['2026/01/日常费用','2026/01/项目经费']),
57:('账户提醒交接表','账户联系渠道表','开启提醒的账户','通知接收邮箱',['finance@example.test','treasury@example.test','billing@example.test']),
61:('课程代码讲评计划','教学进度安排','已分类提交','讲评重点',['边界输入与空集合','循环与终止条件','输出格式与测试样例','异常原因与修复建议']),
63:('课程作业发布单','课程教学大纲','课程练习','提交要求',['附复杂度分析','附边界样例说明','附思路与测试记录']),
69:('2048 训练复盘','学员训练计划','练习结果','学员与训练目标',['学员 S-069：练习识别何时停止操作']),
74:('黑白棋训练复盘','学员训练计划','对局结果','学员与训练目标',['学员 S-074：练习连续回合保持选点策略']),
}


PURPOSE = {
2:'为活动现场制作可直接用于签到和座位安排的参会名册：每人的备注姓名需符合统一格式，并对应本人席位和职责。',
6:'为部门联络员准备可直接使用的分组联系名单：规则确定入选人员，再关联登记邮箱，避免联系同名或无关人员。',
7:'为下一班安排优先响应人员：各部门选出的优先会话必须关联其值班责任人，接班人能据此开始处理。',
8:'安排项目群的协作支持：找出需要支持的群，将实际群号和管理员工号交给运营同事，避免在同名群中联系错人。',
9:'完成部门会议通知与资料交接：每部门通知指定收件人，再关联该部门会议议程，让会务确认通知与资料一致。',
12:'让接班客服按正确顺序接手工作：整理两个工作区会话队列，将每个会话关联实际工单，交接表按队列顺序排列。',
14:'向后续负责人交接项目会话：根据规则整理会话，记录真实归档、置顶或免打扰状态，并明确每项后续负责人。',
16:'完成项目通知回执核对：将实际回复关联通知编号与通知责任人，形成能供项目协调员追踪的回执台账。',
22:'为主持人准备可直接使用的音乐节目单：按规则分类歌曲，给入选曲目关联播报介绍，保留曲名、版本和时长。',
23:'完成专题文章编辑分工：分类当期文章，将文章编号、类别和责任编辑对应起来，交给编辑组开展加工。',
26:'为视频栏目准备上架排期：选择推荐内容并核对每个视频的获准播放时段，交付可据此安排播放的排期单。',
31:'为授课教师准备教学安排：按规则选择课程视频，结合教学大纲填写对应目标，让教师明确每节课看什么和教什么。',
33:'为新闻值班员安排后续采访：按规则标记文章后，将实际跟进文章关联采访联系人，形成可执行的采访清单。',
34:'整理个人课程学习与作业安排：依据观看记录处理视频，再对应课程要求列出后续作业，不重复学习已处理资料。',
38:'为项目组分派文章编辑工作：按规则标记需编辑内容，再关联编辑安排中的负责人，形成可据此分工的编辑表。',
47:'为出差同事准备可用的路线比较表：按日期筛选行程，将入选路线与到达后的会议地点关联，方便确认交通与会务安排。',
48:'为采购同事准备询价清单：选出指定规格的优选商品，关联实际需求数量，避免只询问单价却遗漏采购数量。',
49:'完成月度支出分类与凭证交接：分类当月交易，将每笔入选支出关联原始凭证号，供财务复核与归档。',
50:'为家庭记账人交接账户用途：按规则标注账户，再对照用途登记表写明资金用途，防止同类账户混淆。',
53:'为财务整理月度对账凭证包：各账户选出规定交易，生成真实凭证，关联正确月份与账户的归档目录。',
57:'为出纳完成账户提醒配置与接收人交接：规则决定哪些账户需提醒，设置渠道后关联负责接收提醒的邮箱。',
61:'为授课教师准备代码讲评计划：根据提交判题结果与视频规则分类，再关联各提交的讲评重点，保留题目及提交编号。',
63:'为学生发布结构完整的课程作业：按规则逐专题选题并保存顺序，给每题补充大纲中的提交要求，形成可发布作业单。',
69:'为学员完成一次停止判断训练及复盘：核对训练计划，实际进行2048练习，到视频指定条件首次出现时停止，将真实过程交给教练。',
74:'为学员完成连续选点训练及复盘：核对训练计划，连续六回合按示范策略落子，将实际双方走法交给教练分析。',
}


def attach(state, spec=None):
    out=deepcopy(state);t=out['task_id'];title,source,row,detail,values=CONFIG[t]
    if t in (69,74):
        out['domain']=dict(objects={},messages=[],collections={},memberships={},ledger=[],balances={},settings={},artifacts=[],checks=[],orders={},clipboard_history=[],files={})
    scopes=[s for s in out.get('scopes',[]) if s['requested']]
    rows=out.get('items') or [dict(id='practice-result',name='本次训练',scope_id='training',record_code=f'COACH-{t:03d}')]
    references=[]
    for i,item in enumerate(rows):
        references.append(dict(id=f'REF-{t:03d}-{i+1:03d}',object=item['id'],object_code=item.get('record_code',item['id']),
            name=item['name'],scope=item.get('scope_id','training'),detail=values[i%len(values)],
            supplier=item.get('supplier',''),supplier_contact=item.get('supplier_contact','')))
    # The request revision and destination address come from separate records.
    # An obsolete request is intentionally retained as normal inbox history.
    batch=f'WORK-{t:03d}-{out.get("seed",0)%10000:04d}'
    scope_instruction=(spec or {}).get('inference',{}).get('scope_instruction') or '仅列入本次命中、处理或入选的对象，未命中及范围外对象不列入；排序任务按保存顺序编排。联系人改名任务列出全部指定成员。'
    current=dict(id=batch+'-R2',revision=2,title=title+' · 十月执行批次',
        deadline='2026-10-16 17:00',recipient='TEAM-'+str(t),reference_register=source,
        body=PURPOSE[t]+f' 请采用本请求的最新修订，并根据《{source}》补齐每条{row}的“{detail}”。先完成应用中的规则操作，再编制《{title}》，交付给责任团队。{scope_instruction}文件中保留对象编号、真实保存结果和关联资料，便于接收人直接开展后续工作。',
        scope_ids=[s['id'] for s in scopes] or ['training'])
    previous=dict(current,id=batch+'-R1',revision=1,deadline='2026-10-12 12:00',recipient='TEAM-ARCHIVE',title=title+' · 筹备预案归档',body=f'这是筹备阶段的历史预案，仅供查阅。原计划将资料归档至历史资料归档组，不作为本次执行与交付依据。本次处理范围、截止时间及接收团队请查看《{title} · 十月执行批次》。')
    out['workset_delivery']=dict(title=title,purpose=PURPOSE[t],source_title=source,row_title=row,detail_label=detail,
        request_number=batch,requests=[previous,current],references=references,
        directory=[dict(id='TEAM-ARCHIVE',name='历史资料归档组',address='archive@example.test'),
                   dict(id='TEAM-'+str(t),name=title.replace('表','').replace('单','')+'接收组',address=f'work-{t:03d}@example.test'),
                   dict(id='TEAM-OTHER',name='其他项目协作组',address='other@example.test')],
        draft=None,publications=[],next_publication=1,training_opening=deepcopy(out.get('board')) if t in (69,74) else None)
    return out


def business_snapshot(state):
    if state['task_id'] in (69,74):
        return {k:deepcopy(state.get(k)) for k in ('board','score','moves','turns','stopped','selection')}
    d=state['domain']
    return {k:deepcopy(v) for k,v in d.items() if k!='files'}


def row_snapshot(state,target):
    if target=='practice-result':
        return business_snapshot(state)
    d=state['domain'];item=d['objects'][target]
    return dict(object=deepcopy(item),messages=[deepcopy(m) for m in d['messages'] if m.get('recipient')==target or m.get('reference')==target],
        collections=[key for key,values in d['collections'].items() if target in values],
        artifacts=[deepcopy(a) for a in d['artifacts'] if a.get('transaction')==target or target in a.get('items',[])],
        orders={key:values.index(target)+1 for key,values in d['orders'].items() if target in values})


def result_description(snapshot,task_id):
    if 'object' not in snapshot:
        turns=snapshot.get('turns') or snapshot.get('moves') or []
        return f'总分 {snapshot.get("score",0)}；完成 {len(turns)} 个回合；练习'+('已停止' if snapshot.get('stopped') else '进行中')+'。操作记录：'+json.dumps(turns,ensure_ascii=False)+'\n结束棋盘：\n'+board_text(snapshot.get('board') or [])
    obj=snapshot['object'];parts=[]
    columns={
        7:[('unread','初始未读数')],8:[('members','成员数')],12:[('unread','初始未读数')],
        22:[('artist','歌手'),('edition','版本'),('duration','时长（秒）')],23:[('publisher','来源'),('created_at','发布日期')],
        26:[('duration','时长（秒）'),('like_rate','点赞率')],31:[('duration','时长（秒）'),('like_rate','点赞率')],
        33:[('publisher','来源'),('created_at','发布日期')],34:[('progress_seconds','已观看秒数'),('duration','总秒数')],
        38:[('words','正文字数')],47:[('origin','出发站'),('destination','到达站'),('travel_date','日期'),('price','票价'),('duration','耗时（分钟）'),('transfers','换乘数')],
        48:[('specification','规格'),('supplier','供应商'),('supplier_contact','询价邮箱'),('price','参考单价'),('rating','评分')],49:[('account','账户'),('amount','金额'),('text','交易备注')],
        50:[('account','账号'),('balance','余额'),('transactions','近期交易数')],53:[('account','账户'),('amount','金额'),('created_at','交易时间')],
        57:[('account','账号'),('balance','余额')],61:[('problem_title','题目'),('submission_number','提交号'),('verdict','判题结果'),('runtime_ms','运行时间（毫秒）')],
        63:[('number','题号'),('samples','样例数')],
    }
    if task_id==47:
        def clock(total):
            day,minute=divmod(total,1440)
            return (f'{day}天后 ' if day else '')+f'{minute//60:02d}:{minute%60:02d}'
        start=360+obj['departure']*10
        parts.extend(['出发：'+clock(start),'到达：'+clock(start+obj['duration'])])
    for key,label in columns.get(task_id,[]):
        if key in obj:parts.append(label+'：'+str(obj[key]))
    for key,label in [('nickname','备注姓名'),('label','分类'),('reminder_channel','通知渠道')]:
        if obj.get(key):parts.append(label+'：'+str(obj[key]))
    for key,label in [('read','已读'),('starred','已收藏'),('archived','已归档'),('pinned','已置顶'),('muted','已免打扰'),('hidden','已隐藏'),('deleted','已删除'),('reminder','提醒已开启')]:
        if obj.get(key):parts.append(label)
    if snapshot.get('messages'):parts.append('发送记录：'+'；'.join(m['body'] for m in snapshot['messages']))
    if snapshot.get('collections'):parts.append('已保存到业务集合')
    for artifact in snapshot.get('artifacts',[]):
        if artifact.get('number'):parts.append('凭证号：'+artifact['number'])
        elif artifact.get('title'):parts.append('成果：'+artifact['title'])
    if snapshot.get('orders'):parts.append('列表位置：'+'、'.join(str(v) for v in snapshot['orders'].values()))
    return '；'.join(parts) or '已列入本次业务资料'


def board_text(board):
    return '\n'.join(' '.join(str(cell) for cell in row) for row in board)


def document_text(state,draft):
    w=state['workset_delivery'];lines=['# '+draft['title'],'',f'请求：{draft["request"]}',f'交付截止：{draft["deadline"]}',f'接收邮箱：{draft["address"]}','',draft['summary'],'']
    if w.get('training_opening'):
        lines+=['## 训练初态',board_text(w['training_opening']),'']
    for i,row in enumerate(draft['rows'],1):
        ref=next(r for r in w['references'] if r['object']==row['object'])
        lines += [f'## {i}. {ref["object_code"]} · {ref["name"]}',f'{w["detail_label"]}：{row["detail"]}',
                  f'关联资料：{row["reference"]}','保存结果：'+result_description(row['snapshot'],state['task_id']),'']
    return '\n'.join(lines)


def apply(state,op,target='',value='',ids=None):
    out=deepcopy(state);w=out['workset_delivery']
    try:data=json.loads(value or '{}')
    except (ValueError,TypeError) as exc:raise ValueError('请填写有效的文档内容') from exc
    if not isinstance(data,dict):raise ValueError('文档字段应为对象')
    if op=='assignment.draft':
        if set(data)!={'request','title','deadline','address','summary'} or not all(isinstance(x,str) and x.strip() for x in data.values()):raise ValueError('请填写请求编号、标题、截止时间、接收邮箱和交付说明')
        if data['request'] not in {r['id'] for r in w['requests']}:raise ValueError('请选择已有的业务请求')
        if any(len(x)>4000 for x in data.values()):raise ValueError('文档字段过长')
        rows=w['draft']['rows'] if w['draft'] else []
        w['draft']=dict(data,rows=rows)
    elif op=='assignment.row':
        if not w['draft']:raise ValueError('请先新建业务文档')
        if target not in {r['object'] for r in w['references']} or set(data)!={'reference','detail'} or not all(isinstance(v,str) and v.strip() for v in data.values()):raise ValueError('请选择对象，填写关联资料编号和业务信息')
        rows=w['draft']['rows'];row=dict(object=target,**data,snapshot=row_snapshot(out,target))
        old=next((i for i,r in enumerate(rows) if r['object']==target),None)
        if old is None:rows.append(row)
        else:rows[old]=row
    elif op=='assignment.remove':
        if not w['draft']:raise ValueError('请先新建业务文档')
        w['draft']['rows']=[r for r in w['draft']['rows'] if r['object']!=target]
    elif op=='assignment.order':
        if not w['draft']:raise ValueError('请先新建业务文档')
        rows={r['object']:r for r in w['draft']['rows']}
        if len(ids or [])!=len(rows) or set(ids or [])!=set(rows):raise ValueError('请保留全部文档条目且不重复')
        w['draft']['rows']=[rows[key] for key in ids]
    elif op=='assignment.publish':
        draft=w['draft']
        if not draft or not draft['rows']:raise ValueError('请完成文档正文后交付')
        if any(row['snapshot']!=row_snapshot(out,row['object']) for row in draft['rows']):raise ValueError('应用数据已变动，请逐条刷新文档中的保存结果再交付')
        body=document_text(out,draft);key=f'delivery-{w["next_publication"]:03d}';w['next_publication']+=1
        record=dict(id=key,document=deepcopy(draft),body=body,business_snapshot=business_snapshot(out))
        w['publications'].append(record)
        raw=body.encode();out.setdefault('domain',{}).setdefault('files',{})[key]=dict(name=w['title']+'.md',content=base64.b64encode(raw).decode(),size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    else:raise ValueError('未知业务文档操作')
    return out


def checks(initial,final,objects):
    w=final['workset_delivery'];start=initial['workset_delivery'];checks=[]
    def check(name,yes):checks.append(dict(id='delivery:'+name,passed=bool(yes)))
    for field in ('requests','references','directory','request_number','training_opening'):
        check('source:'+field,w[field]==start[field])
    check('published',bool(w['publications']))
    if not w['publications']:return checks
    record=w['publications'][-1];draft=record['document'];request=max(start['requests'],key=lambda r:r['revision'])
    recipient=next(r for r in start['directory'] if r['id']==request['recipient'])
    for key,wanted in dict(request=request['id'],deadline=request['deadline'],address=recipient['address']).items():check(key,draft.get(key)==wanted)
    check('document_title',isinstance(draft.get('title'),str) and bool(draft['title'].strip()))
    check('document_saved',draft==w['draft'])
    actual_objects=[r['object'] for r in draft['rows']]
    check('objects_and_order',actual_objects==objects if initial['task_id'] in (12,63) else len(actual_objects)==len(objects) and set(actual_objects)==set(objects))
    check('fresh_business_result',record['business_snapshot']==business_snapshot(final))
    for row in draft['rows']:
        ref=next((r for r in start['references'] if r['object']==row['object']),None)
        check(row['object']+':reference',ref and row['reference']==ref['id'] and row['detail']==ref['detail'])
        check(row['object']+':snapshot',row['snapshot']==row_snapshot(final,row['object']))
    check('readable_file',record['body']==document_text(final,draft))
    raw=record['body'].encode();file=final.get('domain',{}).get('files',{}).get(record['id'],{})
    check('file_bytes',file.get('content')==base64.b64encode(raw).decode() and file.get('sha256')==hashlib.sha256(raw).hexdigest() and file.get('size')==len(raw))
    return checks
