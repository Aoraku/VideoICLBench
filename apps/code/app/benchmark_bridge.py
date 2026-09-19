"""Original OJ API shape backed by isolated business records."""

import os
import uuid
import requests
import streamlit as st

ACTIVE = bool(os.environ.get("VIC_NATIVE_RUN"))


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
    descriptions = {
        "两数之和": ("给定整数数组和目标值，找出和等于目标值的两个元素，输出它们的下标。每组输入保证恰有一个解，不能重复使用同一元素。", "首行 n 与目标值，次行 n 个整数。", "输出两个从 0 开始的下标。", "4 9\n2 7 11 15", "0 1"),
        "合并有序数组": ("给定两个非递减整数数组，将它们合并为一个有序数组。", "首行两个数组长度，随后两行给出数组。", "输出合并后的有序数组。", "3 3\n1 3 5\n2 4 6", "1 2 3 4 5 6"),
        "括号匹配": ("判断只包含圆括号、方括号和花括号的字符串是否正确配对并嵌套。", "一行括号字符串。", "正确配对输出 YES，否则输出 NO。", "([]{})", "YES"),
        "二叉树遍历": ("给定二叉树的层序表示，输出它的前序遍历结果。空节点使用 null 表示。", "一行空格分隔的层序节点。", "按根、左、右的顺序输出节点。", "1 2 3 null 4", "1 2 4 3"),
        "最短路径": ("给定非负权有向图，从指定起点出发计算到各个节点的最短距离。", "首行 n m s，随后 m 行给出起点、终点与边权。", "输出起点到各节点的最短距离，不可达输出 -1。", "3 3 1\n1 2 4\n2 3 2\n1 3 9", "0 4 6"),
        "区间合并": ("给定若干闭区间，合并所有相交区间并按起点排序输出。", "首行为区间数量，随后每行一个区间的左右端点。", "每行输出一个合并后的区间。", "3\n1 3\n2 6\n8 10", "1 6\n8 10"),
    }
    description,inputs,outputs,example,answer=descriptions[item["name"]]
    return dict(id=str(item["number"]), title=item["name"], difficulty="easy", author="课程组",
                source="算法练习", tags=["基础算法"], time_limit=1000, memory_limit=128,
                description=description, input_description=inputs, output_description=outputs,
                constraints="整数输入；数据规模不超过 100000。",
                samples=[dict(input=example,output=answer) for _ in range(item["samples"])],
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
                         runtime_ms=x["runtime_ms"], lines=x["lines"], timestamp=x["timestamp"],
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
    st.caption(f"耗时 {sub['runtime_ms']} ms · 代码 {sub['lines']} 行 · 时间序号 {sub['timestamp']}")
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
                a,b=st.columns(2)
                if a.button("本地检查",key="check_"+item["id"]):
                    result=command("action",item["id"],"本地检查")
                    passed=result["state"]["domain"]["checks"][-1]["passed"]
                    st.success("语法检查通过") if passed else st.error("语法检查未通过")
                if b.button("提交",key="submit_"+item["id"]):
                    command("action",item["id"],"提交");st.success("已提交")
