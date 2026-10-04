"""Versioned fixtures and private outcome evaluation for scoped work."""
from copy import deepcopy
from itertools import combinations
from datetime import datetime, timedelta, timezone
import json
from . import business, application_eval
from vic_apps.domain import initialize
from vic_apps import worksets

TASKS = worksets.TASKS


def generate(task_id, seed, spec):
    kind, names, extra_filter, collection = worksets.CONFIG[task_id]
    initial = business.generate(task_id, seed)
    items = []; scopes = []
    for index, name in enumerate(names + ['其他资料']):
        requested = index < len(names)
        if task_id == 48 and requested:
            extra_filter = ('specification','规格','500ml','350ml') if index==0 else ('specification','规格','104键','87键')
        group = business.generate(task_id, seed + 137 * index)
        rows = group['items']
        if task_id==2 and requested:rows=rows[:5]
        if task_id in (6,14) and requested:
            rows=deepcopy(rows)
            for offset,title in enumerate(['Chris Bell','Sky Rhys'] if task_id==6 else ['项目验收','客户回访']):
                extra=deepcopy(rows[offset]);extra['id']+='-extra';extra['name']=title
                extra['surname']=title.split(' ')[-1]
                extra['name_length']=len(title);rows.append(extra)
        if task_id == 63 and requested:
            topic_titles=[
                ['两数之和','合并有序数组','区间合并','旋转数组','乘积最大子数组','窗口最大值'],
                ['最短路径','地图着色','课程安排','拓扑排序','航班路线规划','岛屿数量'],
                ['字符串压缩','编辑距离','字母异位词','子序列匹配','前缀树查询','最长回文子串'],
            ][index]
            # Keep the independent attribute winners while giving each topic
            # an appropriate, distinct problem library with real statements.
            longest=max(range(len(rows)),key=lambda i:len(rows[i]['name']))
            title=max(topic_titles,key=len);topic_titles.remove(title)
            for position,item in enumerate(rows):
                item['name']=title if position==longest else topic_titles.pop(0)
                item['name_length']=len(item['name'])
        if task_id == 22 and requested:
            for subset in combinations(rows,3):
                candidate=dict(group,items=list(subset))
                effects=[business.expected_effect(task_id,v,candidate) for v in 'ABC']
                if len({json.dumps(e,sort_keys=True) for e in effects})==3:
                    rows=list(subset);break
            else:raise ValueError('三首歌曲未区分三种分类条件')
        if task_id == 57 and requested:
            for subset in combinations(rows, 4):
                candidate = dict(group, items=list(subset))
                effects = [business.expected_effect(task_id, v, candidate) for v in 'ABC']
                if len({json.dumps(e, sort_keys=True) for e in effects}) == 3 and all(e['actions'] for e in effects):
                    rows = list(subset); break
            else: raise ValueError('四个账户未覆盖三个不同提醒条件')
        scope = dict(id=f'scope-{index+1}', name=name, kind=kind, requested=requested,
                     filters={extra_filter[0]:extra_filter[2]} if extra_filter else {},
                     filter_label=extra_filter[1] if extra_filter else '', collection=collection)
        scopes.append(scope)
        if task_id==9:
            scope['notification']=f'{name}通知：请于 2026 年 1 月 {20+index} 日 14:00 参加项目说明会，地点为 {index+1} 号会议室。'
        for n, original in enumerate(rows):
            item = deepcopy(original)
            item.update(id=f's{index}-{item["id"]}', scope_id=scope['id'], scope_name=name,
                        record_code=f'{task_id:03d}-{index+1}{n+1:02d}')
            if extra_filter: item[extra_filter[0]] = extra_filter[2]
            if task_id == 16:
                item['receipt_sender_id'] = 1000 + index * 10 + n
                item['created_at'] = f'2026-01-15T{8 + n // 2:02d}:{(n % 2) * 20 + index:02d}:00+00:00'
                item['text'] = (f'收到，{name}通知已核对，我负责的材料正在整理。' if '收到' in item['text']
                    else [f'{name}的会议地点需要再次确认。',f'{name}的材料清单在哪里查看？',
                          f'{name}的负责人联系方式已更新。',f'{name}的进度表将在下午更新。'][n % 4])
            if task_id==8:
                item['group_members']=[dict(user_id=1 if j==0 else 10000+index*1000+n*20+j,username=person,role='owner' if j==0 else 'member')
                    for j,person in enumerate(['周予安','林若宁','陈以安','许知遥','沈沐言','陆星河','宋清越','季云舟','方明远'][:item['members']])]
            if task_id in (61,63):
                item['number'] += 1000 * index
                item['samples'] = 3
            if task_id == 61:
                item['problem_number'] = 101 + index
                item['problem_title'] = name if requested else '合并有序数组'
                item['submission_number'] = 1000 + 100 * index + n
                submission_fixture(item)
            if task_id == 48 and requested:
                product='不锈钢保温杯' if index==0 else '便携机械键盘'
                item['name']=product+' · '+['星河','远山','青木','拾物','简行','杉川'][n%6]
                item['supplier']=['星河办公用品','远山器材商行','青木生活用品','拾物办公商行','简行设备供应','杉川用品中心'][n%6]
                item['supplier_contact']=f'sales-{index+1}{n+1}@example.test'
            if task_id == 34:
                item['progress_seconds']=item['duration'] if item['completed'] else max(1,int(item['duration']*(0.15+0.1*(n%5))))
            if task_id in (23,33,49, 53):
                if task_id in (49,53):item['account'] = f'62220226000000{index+1:02d}'
                item['created_at'] = '2026-01' + item['created_at'][7:]
            if task_id == 47:
                item.update(travel_date=name if requested else '2026-02-20', origin='北京南', destination='上海虹桥')
            if task_id == 57: item['reminder_channel'] = '短信'
            if task_id in (50,57): item['account']=f'6222{task_id:02d}{index+1:02d}{n+1:02d}{seed%1000000:06d}'
            if task_id == 50:
                end=datetime.fromisoformat(initial['source']['transaction_window']['end']).replace(hour=12,tzinfo=timezone.utc)
                history=[dict(id=f'{item["record_code"]}-TX-{j+1:03d}',occurred_at=(end-timedelta(days=j%30,hours=j//30)).isoformat(),amount=(j*13+seed)%97+1) for j in range(item['transactions'])]
                item['transaction_history']=sorted(history,key=lambda tx:tx['occurred_at'],reverse=True)
                item['recent_transactions']=item['transaction_history'][:2]
            items.append(item)
        # Same-title records with the wrong specification or month remain in
        # the same category/account, so the secondary filter has real meaning.
        if extra_filter and requested:
            for n, original in enumerate(items[-len(rows):][:2]):
                other = deepcopy(original)
                other.update(id=original['id']+'-other', record_code=original['record_code']+'R')
                other[extra_filter[0]] = extra_filter[3]
                if task_id == 16: other['created_at'] = '2025-12-20' + other['created_at'][10:]
                if task_id in (23,33,49, 53): other['created_at'] = '2025-12'+other['created_at'][7:]
                items.append(other)
    initial['items'] = items
    if task_id == 16:
        for item in items:
            item['notification_number'] = item['notification_batch'] + '-' + item['record_code']
            item['text'] = f"通知 {item['notification_number']}\n{item['text']}"
    state = initialize(initial)
    state.update(v2_worksets=True, scopes=scopes,
        execution=dict(assignment=spec['assignment'], instructions=spec['inference']['instructions'], delivery=spec['delivery']))
    if task_id == 57: state['source']['notification_channel'] = '电子邮件'
    state['public_parameters']={
        2:'春季发布组的五位成员已各自发来姓名。请从群成员名单确认身份，按视频格式修改各人的备注昵称；成员账号用于区分同名人员，群外人员不变。',
        6:'只整理研发部的八位联系人。姓名长度不计空格；元音为 a/e/i/o/u，不区分大小写。非命中联系人保持未分组，其他部门不变。',
        7:'每个部门独立比较并标注一个高优先级会话；以任务开始时的未读数和最近消息时间为准，并列保持初始顺序。',
        8:'只整理星桥计划的六个项目群；打开群资料核对名称与实际成员，群号用于区分同名群。非命中群不加大型标签。',
        9:'每个部门独立选择一名收件人，各发送一次对应部门通知；比较使用初始未读数和联系时间，姓氏按英文字母排序，并列保持初始顺序。',
        12:'在产品协作、客户交付两个工作区分别排序；采用任务开始时的未读数、最近消息时间及会话名称，并列保持初始相对顺序。每次调整自动保存。',
        14:'只处理星桥交接的八个会话。时间基准 2026-01-15 12:00 UTC，严格超过 3 天才满足时间条件；已读与未读采用任务开始快照。',
        16:f'检查产品验收、官网发布、客户培训、运营交接四个项目会话；只处理通知批次 N2026-0115，历史批次和其他资料不变。每条回执对应正文中的通知编号；固定回复为“{state["source"]["fixed_reply"]}”，应关联原消息且每条只回复一次。',
        22:f'只处理两张专辑的录音室版，共六首歌曲；时长以秒计，播放量阈值为 {state["source"]["threshold"]} 次。',
        23:f'发布日期范围：2026-01-01 至 2026-01-31（UTC）；指定媒体：{state["source"]["publisher"]}；相同标题以文章编号区分。',
        26:'每个栏目独立比较，保存两项推荐；并列保持资料列表的初始顺序。',
        31:'每个课程主题独立选择一项；时长按秒、点赞率按百分比、发布时间按 UTC 比较，并列保持初始顺序。',
        33:f'发布日期范围：2026-01-01 至 2026-01-31（UTC）；标题指定词：{state["source"]["keyword"]}。',
        34:'完成状态和进度以已有观看记录为准，无需等待播放。',
        38:f'正文长度阈值 {state["source"]["threshold"]} 字，包含标点和空格，不包含标题。',
        47:'北京南至上海虹桥；每个日期独立比较全程耗时、票价或换乘次数，并列保持初始顺序。',
        48:f'评分阈值 {state["source"]["threshold"]}/100；销量阈值 {state["source"]["threshold"]}；只整理各类目指定规格。',
        49:f'金额单位为整数元；备注长度阈值 {state["source"]["threshold"]} 个字符（包含标点和空格）。',
        50:'每个账户组独立比较；最近 30 天的日期范围在账户页明确列出，并列保持初始顺序。',
        53:'每个账户的 2026 年 1 月交易独立比较；金额以元、日期以 UTC 为准，并列保持初始顺序。',
        57:f'余额阈值 {state["source"]["threshold"]} 元；日期判断只比较每个账户最近两笔交易的 UTC 日期；应开启账户的通知渠道设为电子邮件。',
        61:'分别审核两数之和（101）与区间合并（102）的提交记录；每道题独立比较运行时间，单位为毫秒，并列保持初始顺序。所有提交均已判题完成。',
        63:'课程专题顺序：数组与区间 → 图与路径 → 字符串；每个专题选择一道题，按该顺序排列并保存课程练习列表。并列选择专题列表中靠前的题目。',
    }[task_id]
    if task_id == 63: state['domain']['orders']['course'] = []
    if collection:
        for scope in scopes: state['domain']['collections']['scope:'+scope['id']] = []
    from vic_apps.workset_delivery import attach
    return attach(state)


def submission_fixture(item):
    """Historical submissions contain source consistent with their verdict.

    Fixed judge records are part of the exercise input, not fresh executions.
    Correct solutions and failing outputs are checked against real OJ samples.
    """
    from vic_apps.oj_resources import samples
    title=item['problem_title'];verdict=item['verdict']
    solutions={
        '两数之和':'n, target = map(int, input().split())\nvalues = list(map(int, input().split()))\nseen = {}\nfor j, value in enumerate(values):\n    if target - value in seen:\n        print(seen[target - value], j)\n        break\n    seen[value] = j\n',
        '区间合并':'n = int(input())\nintervals = sorted(list(map(int, input().split())) for _ in range(n))\nmerged = []\nfor left, right in intervals:\n    if merged and left <= merged[-1][1]:\n        merged[-1][1] = max(merged[-1][1], right)\n    else:\n        merged.append([left, right])\nfor interval in merged:\n    print(*interval)\n',
        '合并有序数组':'n, m = map(int, input().split())\na = list(map(int, input().split()))\nb = list(map(int, input().split()))\nprint(*sorted(a + b))\n',
    }
    item['code']={'AC':solutions[title], 'WA':'print(0)\n',
                  'RE':'values = []\nprint(values[0])\n',
                  'TLE':'total = 0\nfor i in range(10**12):\n    total += i\nprint(total)\n'}[verdict]
    item['lines']=len(item['code'].splitlines())
    if verdict=='TLE':item['runtime_ms']=1000
    item['test_results']=[dict(name=f'测试点 {j+1}',status=verdict,input=case['input'],expected=case['output'],
        actual=case['output'] if verdict=='AC' else '0' if verdict=='WA' else '',
        detail={'AC':'通过','WA':'输出不匹配','RE':'IndexError: list index out of range','TLE':'超过 1000 ms 限制'}[verdict])
        for j,case in enumerate(samples(title,5))]


def scope_effect(initial, variant, scope):
    subset = worksets.members(initial, scope)
    view = dict(initial, items=subset, labels={x['id']:'' for x in subset}, order=[x['id'] for x in subset])
    return business.expected_effect(initial['task_id'], variant, view)


def reference_commands(initial, variant, include_delivery=True):
    """Private reference for evaluator and offline QA; never served to clients."""
    t = initial['task_id']; commands = [];order=list(initial['domain']['orders']['main'])
    for scope in initial['scopes']:
        if not scope['requested']: continue
        if t==2:
            for item in worksets.members(initial,scope):
                view=dict(initial,source={**initial['source'],'text':item['name']})
                commands.append(('contact.nickname',item['id'],business.transform(2,'ABC'.index(variant),view),[]))
            continue
        effect = scope_effect(initial, variant, scope)
        if 'labels' in effect:
            chosen = []
            for target, label in effect['labels'].items():
                if label:
                    chosen.append(target); commands.append(('label', target, label, []))
            if t in worksets.SNAPSHOT_TASKS: commands.append(('workset.collect', scope['id'], '', chosen))
        elif 'order' in effect:
            eligible=set(effect['order']);positions=[i for i,key in enumerate(order) if key in eligible]
            for i,key in zip(positions,effect['order']):order[i]=key
            commands.append(('order','','',list(order)))
        elif 'selection' in effect:
            if t == 9:commands.append(('message.send',effect['selection'][0],scope['notification'],[]))
            elif t == 63: commands.append(('course.add', effect['selection'][0], '', []))
            else: commands.append(('workset.collect', scope['id'], '', effect['selection']))
        else:
            for target, action in effect['actions']:
                commands.append(('action', target, action, []))
                if t == 57: commands.append(('reminder.channel', target, initial['source']['notification_channel'], []))
    if t == 63: commands.append(('course.save', '', '', []))
    if include_delivery and initial.get('workset_delivery'):
        commands.extend(delivery_commands(initial,variant,commands))
    return commands


def evaluate(initial, final, variant, events):
    expected = deepcopy(initial)
    for op, target, value, ids in reference_commands(initial, variant, include_delivery=False):
        expected = worksets.apply(expected, op, target, value, ids)
    checks = []
    def check(name, passed): checks.append(dict(id=name, passed=bool(passed)))
    for key in ('items','source','scopes','execution','public_parameters'):
        check('input:'+key, initial[key] == final.get(key))
    actual_domain=deepcopy(final['domain'])
    for publication in final.get('workset_delivery',{}).get('publications',[]):
        actual_domain.get('files',{}).pop(publication['id'],None)
    want = application_eval.canonical(expected['domain']); got = application_eval.canonical(actual_domain)
    for key in want: check('business:'+key, got.get(key) == want[key])
    for scope in initial['scopes']:
        if not scope['requested']:continue
        for item in worksets.members(initial,scope):
            key=item['id'];check(scope['id']+':'+item['record_code'],got['objects'].get(key)==want['objects'][key])
        if scope['collection']:
            key='scope:'+scope['id'];check(scope['id']+':delivery',got['collections'].get(key)==want['collections'][key])
    if initial.get('workset_delivery'):
        from vic_apps.workset_delivery import checks as delivery_checks
        checks.extend(delivery_checks(initial,final,delivery_objects(initial,variant)))
    violations = [] if events else ['no_action']
    return dict(success=all(c['passed'] for c in checks) and not violations,
                completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,
                violations=violations+[c['id'] for c in checks if not c['passed']])


def delivery_objects(initial,variant,commands=None):
    commands=commands if commands is not None else reference_commands(initial,variant,include_delivery=False)
    result=[]
    eligible={x['id'] for scope in initial['scopes'] if scope['requested'] for x in worksets.members(initial,scope)}
    for op,target,value,ids in commands:
        if op=='order':result=[key for key in ids if key in eligible]
        elif op=='workset.collect':
            result.extend(key for key in ids if key not in result)
        elif op in ('contact.nickname','label','action','message.send','course.add') and target not in result:result.append(target)
    return result


def delivery_commands(initial,variant,commands):
    return document_commands(initial,delivery_objects(initial,variant,commands))


def document_commands(initial,objects):
    w=initial['workset_delivery'];request=max(w['requests'],key=lambda r:r['revision'])
    recipient=next(r for r in w['directory'] if r['id']==request['recipient'])
    result=[('assignment.draft','',json.dumps(dict(request=request['id'],title=request['title'],deadline=request['deadline'],address=recipient['address'],summary='本文件汇总已完成的业务处理结果及后续工作所需资料。'),ensure_ascii=False),[])]
    for target in objects:
        ref=next(r for r in w['references'] if r['object']==target)
        result.append(('assignment.row',target,json.dumps(dict(reference=ref['id'],detail=ref['detail']),ensure_ascii=False),[]))
    result.append(('assignment.publish','','',[]))
    return result
