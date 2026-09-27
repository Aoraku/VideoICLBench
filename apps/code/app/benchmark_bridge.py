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


def business(path="", body=None):
    response = requests.request(
        "POST" if body else "GET",
        os.environ["VIC_NATIVE_SELF_BASE"] + "/api/runs/" + os.environ["VIC_NATIVE_RUN"] + path,
        headers={"Authorization": "Bearer " + os.environ["VIC_NATIVE_TOKEN"]}, json=body, timeout=15,
    )
    if not response.ok:
        raise ValueError(response.json().get("detail", "Application request failed"))
    return response.json()


def command(op, target="", value="", ids=None):
    current = business()
    return business("/commands", dict(op=op, target=target, value=value, ids=ids or [],
                                     epoch=current["epoch"], action_id=uuid.uuid4().hex))


def problem(item):
    from vic_apps.oj_resources import problem_content, samples
    content = problem_content(item["name"])
    return dict(id=str(item["number"]), title=item["name"], difficulty="easy", author="课程组",
                source="算法练习", tags=["基础算法"], time_limit=1000, memory_limit=128,
                description=content["description"], input_description=content["input_description"], output_description=content["output_description"],
                constraints=content["constraints"],
                samples=samples(item["name"], item["samples"]),
                pass_rate=item["pass_rate"], benchmark_object=item["id"], label=item.get("label", ""))


def api_request(method, endpoint, data=None, params=None, **kwargs):
    try:
        state = business()["state"]
        route = endpoint.rstrip("/")
        items = [state["domain"]["objects"][x["id"]] for x in state["items"]]
        value = None
        if method == "GET" and route == "/api/problems":
            value = [problem(x) for x in items]
        elif method == "GET" and route.startswith("/api/problems/"):
            item = next(x for x in items if str(x["number"]) == route.split("/")[-1])
            value = problem(item)
        elif method == "GET" and route == "/api/languages":
            value = [dict(name="python", file_ext=".py", time_limit=1000, memory_limit=128)]
        elif method == "GET" and route.startswith("/api/submissions"):
            rows = [dict(submission_id=str(1000+i), problem_id=str(x["number"]), status=x["verdict"],
                         score=100 if x["verdict"]=="AC" else 0, counts=100, code=x["code"],
                         runtime_ms=x["runtime_ms"], lines=len(x["code"].splitlines()), created_at=x["created_at"],
                         benchmark_object=x["id"], label=x["label"]) for i,x in enumerate(items)]
            rows.extend(dict(submission_id=str(2000+i),problem_id="100",status="saved",score=0,counts=0,
                             code=x["body"]) for i,x in enumerate(state["domain"]["artifacts"]) if x["kind"]=="submission")
            value = dict(total=len(rows), submissions=rows) if route=="/api/submissions" else next(x for x in rows if x["submission_id"] == route.split("/")[-1])
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
    st.caption(f"样例数 {len(problem_data['samples'])} · 通过率 {problem_data['pass_rate']}%")
    if t == 62:
        label = st.radio("难度标签", ["未标注"]+state["options"], index=([""]+state["options"]).index(state["labels"][problem_data["benchmark_object"]]), horizontal=True, key="difficulty_"+problem_data["id"])
        if st.button("保存标签", key="label_"+problem_data["id"]):
            command("label", problem_data["benchmark_object"], "" if label=="未标注" else label)
            st.success("标签已保存")
    if t == 63 and st.button("选择这道题", key="choose_"+problem_data["id"]):
        command("select", ids=[problem_data["benchmark_object"]])
        st.success("已选择题目")


def extra_submission(sub):
    if not sub.get("benchmark_object"):
        return
    state = business()["state"]
    submitted_at = sub['created_at'].replace('T', ' ').removesuffix('+00:00')
    st.caption(f"耗时 {sub['runtime_ms']} ms · 代码 {sub['lines']} 行 · 提交时间 {submitted_at} UTC")
    if state["task_id"] == 61:
        options=[""]+state["options"]
        label=st.radio("结果标签",["未标注"]+state["options"],index=options.index(state["labels"][sub["benchmark_object"]]),horizontal=True,key="sub_label_"+sub["submission_id"])
        if st.button("保存结果标签", key="sub_save_"+sub["submission_id"]):
            command("label",sub["benchmark_object"],"" if label=="未标注" else label);st.success("标签已保存")
    if state["task_id"] == 64 and st.button("查看代码",key="sub_view_"+sub["submission_id"]):
        command("select",ids=[sub["benchmark_object"]]);st.code(sub["code"],language="python")


def render_files():
    state = business()["state"]
    t=state["task_id"]
    st.title("我的代码与笔记")
    if t in (59,60):
        st.subheader("解题笔记" if t==59 else "solution.py")
        st.code(state["source"]["text"],language="text" if t==59 else "python")
        text=st.text_area("编辑答案" if t==59 else "编辑源代码",value=state["outputs"].get("target",state["source"]["text"]),height=320)
        if st.button("保存文件",type="primary"):
            command("save","target",text);st.success("文件已保存")
    else:
        for item in state["items"]:
            with st.expander(item["name"]+" · solution.py"):
                st.code(item["code"],language="python")
                st.caption(f"代码长度：{len(item['code'])} 个字符（包含空格和换行）")
                a,b=st.columns(2)
                if a.button("本地检查",key="check_"+item["id"]):
                    result=command("action",item["id"],"本地检查")
                    passed=result["state"]["domain"]["checks"][-1]["passed"]
                    st.success("语法检查通过") if passed else st.error("语法检查未通过")
                if b.button("提交",key="submit_"+item["id"]):
                    command("action",item["id"],"提交");st.success("已提交")
