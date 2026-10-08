"""Original OJ API shape backed by isolated business records."""

import os
import uuid
import requests
import streamlit as st

ACTIVE = bool(os.environ.get("VIC_NATIVE_RUN"))


def whitespace_view(text):
    """A display-only inspection aid; never alters submitted source characters."""
    st.caption("空白字符视图：· 表示一个空格，⇥ 表示一个 Tab。编辑与提交保留原始字符。")
    st.code(text.replace(" ", "·").replace("\t", "⇥   "), language="text", line_numbers=True)
    indents = []
    for number, line in enumerate(text.splitlines(), 1):
        prefix = line[:len(line) - len(line.lstrip(" \t"))]
        if prefix:
            indents.append(f"第 {number} 行：{prefix.count(' ')} 个空格、{prefix.count(chr(9))} 个 Tab")
    if indents:
        st.caption("；".join(indents))


_snapshot = None

def begin_render():
    global _snapshot
    _snapshot = None


def business(path="", body=None):
    global _snapshot
    if not path and body is None and _snapshot is not None:
        return _snapshot
    response = requests.request(
        "POST" if body else "GET",
        os.environ["VIC_NATIVE_SELF_BASE"] + "/api/runs/" + os.environ["VIC_NATIVE_RUN"] + path,
        headers={"Authorization": "Bearer " + os.environ["VIC_NATIVE_TOKEN"]}, json=body, timeout=15,
    )
    if not response.ok:
        raise ValueError(response.json().get("detail", "Application request failed"))
    data = response.json()
    if not path or path == "/commands":
        _snapshot = data
    return data


def command(op, target="", value="", ids=None):
    current = business()
    return business("/commands", dict(op=op, target=target, value=value, ids=ids or [],
                                     epoch=current["epoch"], action_id=uuid.uuid4().hex))


def problem(item):
    from vic_apps.oj_resources import problem_content, samples
    title=item.get('problem_title',item['name'])
    content = problem_content(title)
    return dict(id=str(item.get('problem_number',item["number"])), title=title, difficulty="easy", author="课程组",
                source=item.get('scope_name',"算法练习"), tags=["基础算法"], time_limit=1000, memory_limit=128,
                description=content["description"], input_description=content["input_description"], output_description=content["output_description"],
                constraints=content["constraints"],
                samples=samples(item["name"], item["samples"]),
                pass_rate=item["pass_rate"], benchmark_object=item["id"], label=item.get("label", ""))


def api_request(method, endpoint, data=None, params=None, **kwargs):
    try:
        state = business()["state"]
        route = endpoint.rstrip("/")
        if state.get('workflow')=='code_projects':
            import json
            def course_problem(p):
                return dict(id=p['id'],title=p['title'],difficulty='easy',author='课程组',source=state['world']['course'],tags=['课程交付'],time_limit=2000,memory_limit=256,judge_mode='course-python',description=p['description'],input_description='函数参数见下列公开测试。',output_description='返回与预期输出一致的 JSON 值。',constraints='仅使用课程给出的项目文件；运行说明见侧栏。',samples=[dict(input=json.dumps(t['args'],ensure_ascii=False),output=json.dumps(t['expected'],ensure_ascii=False)) for t in p['tests']],pass_rate=100)
            if method=='GET' and route=='/api/problems':return dict(code=200,data=[course_problem(p) for p in state['world']['problems']]),None
            if method=='GET' and route.startswith('/api/problems/'):
                return dict(code=200,data=course_problem(next(p for p in state['world']['problems'] if p['id']==route.split('/')[-1]))),None
            if method=='GET' and route=='/api/languages':return dict(code=200,data=[dict(name='python',file_ext='.py',time_limit=2000,memory_limit=256)]),None
            raise ValueError('请从课程工作区操作此项目')
        items = [state["domain"]["objects"][x["id"]] for x in state["items"]]
        scope_id=st.session_state.get('workset_scope','') if state.get('v2_worksets') else ''
        scoped=[x for x in items if not scope_id or x.get('scope_id')==scope_id]
        value = None
        if method == "GET" and route == "/api/problems":
            value = list({p['id']:p for p in [problem(x) for x in scoped]}.values())
        elif method == "GET" and route.startswith("/api/problems/"):
            item = next(x for x in items if str(x.get('problem_number',x["number"])) == route.split("/")[-1])
            value = problem(item)
        elif method == "GET" and route == "/api/languages":
            value = [dict(name="python", file_ext=".py", time_limit=1000, memory_limit=128)]
        elif method == "GET" and route.startswith("/api/submissions"):
            rows = [dict(submission_id=str(x.get('submission_number',1000+i)), problem_id=str(x.get('problem_number',x["number"])), status=x["verdict"],
                         score=sum(r['status']=='AC' for r in x['test_results']) if x.get('test_results') else (100 if x["verdict"]=="AC" else 0),
                         counts=len(x['test_results']) if x.get('test_results') else 100, code=x["code"],
                         runtime_ms=x["runtime_ms"], lines=len(x["code"].splitlines()), created_at=x["created_at"],
                         benchmark_object=x["id"], label=x["label"], scope_id=x.get('scope_id'),
                         record_code=x.get('record_code'),test_results=x.get('test_results',[])) for i,x in enumerate(items)]
            rows.extend(dict(submission_id=str(2000+i),problem_id="100",status="saved",score=0,counts=0,
                             code=x["body"]) for i,x in enumerate(state["domain"]["artifacts"]) if x["kind"]=="submission")
            if route=="/api/submissions":
                rows=[x for x in rows if (not scope_id or x.get('scope_id')==scope_id)
                      and all(not (params or {}).get(k) or str(x.get(k))==str(params[k]) for k in ('problem_id','status'))]
                total=len(rows);page=int((params or {}).get('page',1));size=int((params or {}).get('page_size',1000))
                value=dict(total=total,submissions=rows[(page-1)*size:page*size])
            else:value=next(x for x in rows if x['submission_id']==route.split('/')[-1])
        elif method == "POST" and route == "/api/submissions" and state["task_id"] == 58:
            command("save", "target", data["code"])
            value = dict(submission_id="2000")
        else:
            raise ValueError("此独立练习尚未接入该功能")
        return dict(code=200, data=value), None
    except (ValueError, StopIteration, requests.RequestException) as exc:
        return dict(code=422, msg=str(exc) or "对象不存在"), None


def extra_problem(problem_data):
    state = business()["state"]
    t = state["task_id"]
    if state.get('workflow')=='code_projects':
        st.caption('公开测试 '+str(len(problem_data['samples']))+' 组 · 课程条目与题号须对应')
        return
    st.caption(f"样例数 {len(problem_data['samples'])} · 通过率 {problem_data['pass_rate']}%")
    if t == 62:
        label = st.radio("难度标签", ["未标注"]+state["options"], index=([""]+state["options"]).index(state["labels"][problem_data["benchmark_object"]]), horizontal=True, key="difficulty_"+problem_data["id"])
        if st.button("保存标签", key="label_"+problem_data["id"]):
            command("label", problem_data["benchmark_object"], "" if label=="未标注" else label)
            st.success("标签已保存")
    if t == 63:
        if state.get('v2_worksets'):
            st.caption('课程专题：'+problem_data['source'])
            if st.button('加入课程练习',key='course_add_'+problem_data['id']):
                command('course.add',problem_data['benchmark_object']);st.success('已加入课程；可在课程练习列表中排序和保存')
        elif st.button("选择这道题", key="choose_"+problem_data["id"]):
            command("select", ids=[problem_data["benchmark_object"]])
            st.success("已选择题目")


def extra_submission(sub, prefix=''):
    if not sub.get("benchmark_object"):
        return
    state = business()["state"]
    submitted_at = sub['created_at'].replace('T', ' ').removesuffix('+00:00')
    st.caption(f"耗时 {sub['runtime_ms']} ms · 代码 {sub['lines']} 行 · 提交时间 {submitted_at} UTC")
    if state["task_id"] == 61:
        if sub.get('test_results'):
            st.caption('记录编号：'+sub['record_code'])
            with st.expander('测试详情 · '+sub['submission_id']):
                st.caption('历史判题结果 · 单测试点运行时间限制 1000 ms')
                st.table([{'测试点':r['name'],'状态':r['status'],'输入':r['input'],
                           '预期输出':r['expected'],'实际输出':r['actual'],'说明':r['detail']} for r in sub['test_results']])
                st.code(sub['code'],language='python')
        options=[""]+state["options"]
        with st.form(prefix+'submission_label_form_'+sub['submission_id']):
            label=st.radio("结果标签",["未标注"]+state["options"],index=options.index(state["labels"][sub["benchmark_object"]]),horizontal=True,key=prefix+"sub_label_"+sub["submission_id"])
            submitted=st.form_submit_button("保存结果标签")
        if submitted:
            command("label",sub["benchmark_object"],"" if label=="未标注" else label);st.success("标签已保存")
    if state["task_id"] == 64 and st.button("查看代码",key="sub_view_"+sub["submission_id"]):
        command("select",ids=[sub["benchmark_object"]]);st.code(sub["code"],language="python")


def render_scope():
    state=business()['state']
    if not state.get('v2_worksets'): return
    scopes={s['id']:s['name'] for s in state['scopes']}
    st.caption(state['public_parameters'])
    def changed():
        for key in ('my_submissions_data','filtered_submissions_data','submission_filter'):
            st.session_state.pop(key,None)
    st.selectbox(state['scopes'][0]['kind'],['']+list(scopes),format_func=lambda key:scopes.get(key,'全部资料'),
                 key='workset_scope',on_change=changed)


def render_course():
    state=business()['state'];d=state['domain'];order=d['orders']['course']
    st.title('课程练习列表')
    st.info(state['public_parameters'])
    st.caption('每个专题保留一道练习；在题库选择同一专题的其他题目会替换该专题题目。')
    if not order:st.info('请从题目列表选择课程练习。')
    for i,key in enumerate(order):
        item=d['objects'][key]
        with st.container(border=True):
            st.subheader(f"{i+1}. {item['number']} · {item['name']}")
            st.caption('课程专题：'+item['scope_name'])
            a,b,c=st.columns(3)
            if a.button('上移',key='up_'+key,disabled=i==0):
                ids=list(order);ids[i-1],ids[i]=ids[i],ids[i-1];command('course.order',ids=ids);st.rerun()
            if b.button('下移',key='down_'+key,disabled=i==len(order)-1):
                ids=list(order);ids[i],ids[i+1]=ids[i+1],ids[i];command('course.order',ids=ids);st.rerun()
            if c.button('移除',key='remove_'+key):command('course.remove',key);st.rerun()
    if st.button('保存课程练习列表',type='primary'):
        command('course.save');st.rerun()
    saved=next((a for a in d['artifacts'] if a.get('kind')=='course_list'),None)
    if saved:
        st.success('已保存的课程练习列表')
        for i,key in enumerate(saved['items']):
            item=d['objects'][key];st.write(f"{i+1}. {item['scope_name']} · {item['number']} · {item['name']}")
        if saved['items']!=order:st.warning('列表有未保存的调整，请保存后交付。')


def render_files():
    state = business()["state"]
    t=state["task_id"]
    st.title("我的代码与笔记")
    if t in (59,60):
        st.subheader("解题笔记" if t==59 else "solution.py")
        if t == 59:
            st.info('本批目标：三道题的答案均须正式提交。保存文件只保留草稿；每份都需要点击“提交答案”，并核对提交记录。' if state.get('v2_atomic') else '本次只需整理这一份多行笔记并保存文件，不需要提交答案。')
        if t==59 and state.get('v2_atomic'):
            problem=state['source']['answer_problem']
            st.info(f"提交目标题目：{problem['number']} · {problem['name']}")
        if t == 60:
            st.caption("待重命名变量：" + "、".join(state["source"]["rename_targets"]))
            st.caption("只改指定变量的定义与引用；相似名称、字符串和注释保持不变。")
        st.code(state["source"]["text"],language="text" if t==59 else "python")
        text=st.text_area("编辑答案" if t==59 else "编辑源代码",value=state["outputs"].get("target",state["source"]["text"]),height=320)
        if st.button("保存文件",type="primary"):
            command("save","target",text);st.success("文件已保存")
        if t==59 and state.get('v2_atomic'):
            if st.button('提交答案',type='primary'):
                command('answer.submit','target')
                st.rerun()
            submitted=next((a for a in state['domain']['artifacts'] if a.get('kind')=='answer_submission'),None)
            if submitted:
                st.success(f"答案已提交 · 题目 {submitted['problem']} · {submitted['id']}")
                st.code(submitted['body'],language='text')
    else:
        submitted = {record["target"] for record in state["domain"]["artifacts"]
                     if record["kind"] == "submission"}
        checked = {record["target"]: record["passed"] for record in state["domain"]["checks"]}
        st.caption(f"共 {len(state['items'])} 份文件 · 已提交 {len(submitted)} 份")
        if t == 65:
            st.caption("指定函数名：" + state["source"]["function"])
            st.caption(f"长度阈值：{state['source']['code_threshold']} 个字符（包含空格和换行）")
            st.caption("本地检查指 Python 语法检查；提交不额外要求程序运行通过。")
        for item in state["items"]:
            with st.expander(item["name"]+" · solution.py"):
                st.code(item["code"],language="python")
                st.caption(f"代码长度：{len(item['code'])} 个字符（包含空格和换行）")
                if item["id"] in checked:
                    st.success("语法检查通过") if checked[item["id"]] else st.error("语法检查未通过")
                if item["id"] in submitted:
                    st.success("已提交")
                a,b=st.columns(2)
                if a.button("本地检查",key="check_"+item["id"]):
                    command("action",item["id"],"本地检查")
                    st.rerun()
                if b.button("提交",key="submit_"+item["id"],disabled=item["id"] in submitted):
                    command("action",item["id"],"提交")
                    st.rerun()
