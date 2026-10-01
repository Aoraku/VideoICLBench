"""Course projects, immutable check/submission snapshots and downloadable deliveries."""
from copy import deepcopy
from io import BytesIO
import base64,hashlib,json,random,zipfile
from vic import business
from .domain import initialize
from .communications import file_record
from .code_execution import syntax_check,run_checks

TASKS={58,60,64,65}
SOURCES=[
    'def solve(values):\n   total = 0\n   for value in values:\n      if value > 0:\n         total += value\n   return total\n',
    'def solve(values):\n   count = 0\n   for value in values:\n      if value % 2 == 0:\n         count += 1\n   return count\n',
    'def solve(rows):\n   total = 0\n   for price, quantity in rows:\n      if quantity > 0:\n         total += price * quantity\n   return total\n',
]
PROJECT={
    'pricing.py':'tax_rate = 8\n\ndef subtotal(items):\n    total = 0\n    for price, quantity in items:\n        total += price * quantity\n    return total\n',
    'invoice.py':'from pricing import subtotal, tax_rate\n\ndef invoice(items):\n    total = subtotal(items)\n    tax = total * tax_rate // 100\n    return {"label": "total tax_rate tax", "amount": total + tax}\n',
    'app.py':'from invoice import invoice\n\ndef solve(items):\n    summary = invoice(items)\n    return summary["amount"]\n',
}


def fixture(task_id,seed,spec):
    state=initialize(business.generate(task_id,seed));rng=random.Random(seed);offset=rng.randint(2,12)
    tests=[
        [dict(name='正负混合',args=[[-3,5,0,offset]],expected=5+offset),dict(name='空列表',args=[[]],expected=0),dict(name='全部负数',args=[[-2,-8]],expected=0)],
        [dict(name='奇偶混合',args=[[1,2,4,7,8]],expected=3),dict(name='空列表',args=[[]],expected=0),dict(name='含零与负数',args=[[-2,0,3]],expected=2)],
        [dict(name='采购明细',args=[[[120,2],[55,0],[40,3]]],expected=360),dict(name='空清单',args=[[]],expected=0),dict(name='单项费用',args=[[[offset,3]]],expected=offset*3)],
    ]
    titles=['正数费用合计','偶数编号计数','采购金额计算'];descriptions=['返回输入整数列表中所有正数之和。','返回输入整数列表中偶数的数量，零和负偶数也计数。','输入为 [单价, 数量] 列表，仅累计数量大于零的单价与数量乘积。']
    problems=[dict(id=str(2101+i),title=titles[i],description=descriptions[i],tests=tests[i]) for i in range(3)]
    entries=[];history=[]
    if task_id==60:
        problems=[dict(id='2201',title='含税采购费用',description='输入 [单价（分）, 数量] 明细，返回按 8% 税率向下取整后的含税总额（分）。保留 solve、invoice、subtotal 函数和返回字典的 label、amount 字段。',tests=[dict(name='两种商品',args=[[[100,2],[250,1]]],expected=486),dict(name='空订单',args=[[]],expected=0),dict(name='税额取整',args=[[[101,1]]],expected=109)])]
        entries=[dict(id='PROJECT-01',title='采购费用项目',problem='2201',files=deepcopy(PROJECT),entry_file='app.py')]
    elif task_id==65:
        candidates=['def solve(values):\n    return sum(values)\n','def run(values):\n    return sum(values)\n','def solve(values)\n    return sum(values)\n','def run(values):\n    return len(values)\n','def solve(values)\n    return len(values)\n','def run(values)\n    return len(values)\n']
        for i in (1,4):candidates[i]+='# 课程候选说明：保留此份源代码，不修改内容。\n'*4
        candidates[5]+='#'+'x'*(90-len(candidates[5])-1)
        for i,code in enumerate(candidates):entries.append(dict(id=f'CAND-{i+1:02d}',title=f'候选 {i+1} · '+titles[i%3],problem=problems[i%3]['id'],files={'solution.py':code},entry_file='solution.py'))
    else:
        for i,source in enumerate(SOURCES):
            key=f'EX-{i+1:02d}' if task_id==58 else f'MOD-{i+1:02d}'
            entries.append(dict(id=key,title=titles[i],problem=problems[i]['id'],files={'solution.py':source},entry_file='solution.py'))
            if task_id==64:
                old=source.replace('return total','return total + 1').replace('return count','return count + 1')
                longest=source+('# 历史课程注释\n'*8)
                if i==0:longest=longest.replace('def solve(values):','def solve(values)')
                for j,code in enumerate((old,source,longest)):
                    history.append(dict(id=f'HIST-{i+1}-{j+1}',entry=key,problem=problems[i]['id'],created_at=['2026-09-01T09:00:00+08:00','2026-09-20T09:00:00+08:00','2026-09-10T09:00:00+08:00'][j],files={'solution.py':code}))
        rng.shuffle(history)
    briefs={
        58:'老师需要三道练习的规范代码和判题记录。课程清单给出了每题完整解答，现有每层缩进为 3 个空格；按视频统一缩进，代码其他字符与逻辑保持不变。逐题保存、运行给定测试、提交到清单指定题号，再填写检查编号与实际提交编号，发布课程交付包。无需设计新算法。',
        60:'采购费用项目准备交付。按视频规则重命名 pricing.py 与 invoice.py 中的 tax_rate、total、tax（仅有该名称的位置），同步导入与全部引用。app.py、函数名、参数、字典键、字符串和其他变量保持不变。保存全部文件，通过给定测试后提交至题目 2201，再发布项目交付包。',
        64:'助教需要三个模块的历史版本包。每个模块在其初始历史中按视频标准选择一个版本，恢复原代码到交付工作区，运行给定检查，将来源版本编号、检查编号和实际结果与模块对应，保存并发布版本包。代码行数按 splitlines 计数，空行和注释行计入；无需修复历史版本已有错误，也无需提交判题。',
        65:'助教需要筛出符合视频准入条件的课程代码。依课程清单逐份查看原始候选，不改代码；先运行本地检查，再把合格候选提交到对应题目，发布包含全部候选、实际提交编号和未提交原因的交付包。本地检查指 Python 语法检查；判题测试结果另行展示，不是所有规则版本都要求测试通过。指定函数名为 solve，以源代码中出现该名称为准；长度阈值为 90 个字符，空格与换行均计入。未提交原因填写“不符合视频提交条件”。',
    }
    brief=briefs[task_id]+' 给定测试、题号和课程资料均可查看；练习运行支持函数、循环、条件、算术和项目内导入，不支持文件、网络或外部库。检查和提交保存代码快照，修改代码后须重新检查。交付包发布后需先撤回发布才能调整内容。'
    state.update(workflow='code_projects',execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),world=dict(course='课程代码交付',brief=brief,problems=problems,entries=entries,history=history,threshold=90,function='solve',rename_targets=['tax_rate','total','tax'],unsubmitted_reason='不符合视频提交条件',drafts={e['id']:({} if task_id==64 else deepcopy(e['files'])) for e in entries},restored={},checks={},submissions={},delivery=None))
    for e in entries:
        for name,code in e['files'].items():state['domain']['files']['source-'+e['id']+'-'+name]=file_record(name,code)
    state['domain']['files']['course-readme']=file_record('课程说明.md',brief+'\n')
    return state


def zip_record(name,files):
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for path,content in sorted(files.items()):
            info=zipfile.ZipInfo(path,date_time=(2026,10,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            bundle.writestr(info,content.encode())
    content=stream.getvalue()
    return dict(name=name,content=base64.b64encode(content).decode(),size=len(content),sha256=hashlib.sha256(content).hexdigest())


def latest_check(w,entry):
    return next((c for c in reversed(list(w['checks'].values())) if c['entry']==entry and c['files']==w['drafts'][entry]),None)


def submission_files(sub):
    return {**sub['files'],'submission.json':json.dumps(sub,ensure_ascii=False,sort_keys=True,indent=2)+'\n'}


def delivery_rows(state):
    w=state['world'];rows=[]
    for e in w['entries']:
        checked=latest_check(w,e['id']);sub=next((s for s in w['submissions'].values() if s['entry']==e['id']),None)
        rows.append(dict(entry=e['id'],problem=e['problem'],source=w['restored'].get(e['id'],''),check=checked['id'] if checked else '',submission=sub['id'] if sub else '',reason=w['unsubmitted_reason'] if state['task_id']==65 and not sub else ''))
    return rows


def delivery_artifacts(state,rows):
    w=state['world'];files={};lines=['# 课程代码交付清单','','| 模块 / 候选 | 题号 | 来源版本 | 检查编号 | 语法检查 | 运行测试 | 提交编号 | 未提交原因 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        c=w['checks'].get(r['check']);sub=w['submissions'].get(r['submission'])
        lines.append(f'| {r["entry"]} | {r["problem"]} | {r["source"] or "给定代码"} | {r["check"] or "—"} | {c["syntax"]["status"] if c else "未检查"} | {c["tests"]["status"] if c else "未运行"} | {r["submission"] or "—"} | {r["reason"]} |')
        if c:files[r['entry']+'/check.json']=json.dumps(c,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
        for name,code in w['drafts'].get(r['entry'],{}).items():files[r['entry']+'/'+name]=code
        if sub:files[r['entry']+'/submission.json']=json.dumps(sub,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    body='\n'.join(lines)+'\n';files['交付清单.md']=body;files['manifest.json']=json.dumps(rows,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    return body,zip_record('课程代码交付包.zip',files)


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];entries={e['id']:e for e in w['entries']};problems={p['id']:p for p in w['problems']}
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容须为 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='delivery.reopen':
        if not w['delivery']:raise ValueError('尚无交付清单')
        w['delivery']['published']=False;return state
    if w['delivery'] and w['delivery']['published']:raise ValueError('请先撤回交付发布，再调整代码或记录')
    if op in ('code.save','code.restore','code.check','code.submit') and target not in entries:raise ValueError('课程条目不存在')
    if op=='code.save':
        if set(data)!={'files'} or not isinstance(data['files'],dict) or set(data['files'])!=set(entries[target]['files']) or any(not isinstance(v,str) or len(v)>30000 for v in data['files'].values()):raise ValueError('文件集合须与给定项目一致，每个文件不超过 30000 字符')
        w['drafts'][target]=deepcopy(data['files'])
    elif op=='code.restore':
        if state['task_id']!=64 or set(data)!={'version'}:raise ValueError('请选择历史版本')
        source=next((h for h in w['history'] if h['id']==data['version'] and h['entry']==target),None)
        if not source:raise ValueError('历史版本与模块不匹配')
        w['drafts'][target]=deepcopy(source['files']);w['restored'][target]=source['id']
    elif op=='code.check':
        files=w['drafts'][target]
        if set(files)!=set(entries[target]['files']):raise ValueError('请先恢复完整代码')
        key=f'CHK-{state.get("next_check",1):04d}';state['next_check']=state.get('next_check',1)+1
        w['checks'][key]=dict(id=key,entry=target,files=deepcopy(files),syntax=syntax_check(files),tests=run_checks(files,problems[entries[target]['problem']]['tests'],entries[target]['entry_file']))
    elif op=='code.submit':
        if state['task_id']==64:raise ValueError('本课程交付历史版本，无需提交判题')
        if set(data)!={'problem'} or data['problem'] not in problems:raise ValueError('请选择有效题目')
        check=latest_check(w,target)
        if not check:raise ValueError('当前代码尚未检查，请先保存并检查')
        if any(s['entry']==target for s in w['submissions'].values()):raise ValueError('此候选已有提交，请先撤回再重新提交')
        key=f'SUB-{state.get("next_submission",1):04d}';state['next_submission']=state.get('next_submission',1)+1
        files=deepcopy(w['drafts'][target]);result=run_checks(files,problems[data['problem']]['tests'],entries[target]['entry_file'])
        sub=dict(id=key,entry=target,problem=data['problem'],files=files,check=check['id'],tests=result)
        w['submissions'][key]=sub;state['domain']['files']['submission-'+key]=zip_record(key+'-代码提交.zip',submission_files(sub))
    elif op=='code.withdraw':
        if target not in w['submissions']:raise ValueError('提交记录不存在')
        del w['submissions'][target];state['domain']['files'].pop('submission-'+target,None)
    elif op=='delivery.save':
        if set(data)!={'rows'} or not isinstance(data['rows'],list) or not data['rows']:raise ValueError('请填写课程交付明细')
        seen=set()
        for r in data['rows']:
            if not isinstance(r,dict) or set(r)!={'entry','problem','source','check','submission','reason'} or any(not isinstance(v,str) for v in r.values()) or r['entry'] not in entries or r['entry'] in seen or r['problem'] not in problems or len(r['reason'])>200:raise ValueError('交付行无效或条目重复')
            seen.add(r['entry'])
            if r['check'] and r['check'] not in w['checks']:raise ValueError('检查编号不存在')
            if r['submission'] and r['submission'] not in w['submissions']:raise ValueError('提交编号不存在')
            if r['source'] and r['source'] not in {h['id'] for h in w['history']}:raise ValueError('来源版本不存在')
        body,bundle=delivery_artifacts(state,data['rows']);w['delivery']=dict(rows=deepcopy(data['rows']),body=body,published=False)
        state['domain']['files']['course-delivery']=bundle;state['domain']['files']['course-manifest']=file_record('课程代码交付清单.md',body)
    elif op=='delivery.delete':
        w['delivery']=None
        for id in ('course-delivery','course-manifest'):state['domain']['files'].pop(id,None)
    elif op=='delivery.publish':
        delivery=w['delivery']
        if not delivery or delivery['rows']!=delivery_rows(state) or any(not r['check'] for r in delivery['rows']):raise ValueError('请检查全部条目并保存与当前结果一致的交付清单')
        if any(s['files']!=w['drafts'][s['entry']] for s in w['submissions'].values()):raise ValueError('代码已变动，请撤回过期提交并重新提交')
        body,bundle=delivery_artifacts(state,delivery['rows'])
        if delivery['body']!=body or state['domain']['files'].get('course-delivery')!=bundle:raise ValueError('交付包已过期，请重新保存')
        delivery['published']=True
    else:raise ValueError('未知课程操作')
    return state
