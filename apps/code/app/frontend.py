import os
import streamlit as st
import requests
import json
import time
import pandas as pd
import datetime
import benchmark_bridge as benchmark

# 配置
st.set_page_config(
    page_title="在线评测系统",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_URL = os.environ.get("VIC_API_URL", "http://127.0.0.1:8000")

# 会话状态管理
def init_session_state():
    defaults = {
        "logged_in": False,
        "username": "",
        "user_id": "",
        "role": "",
        "current_page": "login",
        "current_problem_id": None,
        "cookies": None
    }
    if benchmark.ACTIVE:
        defaults.update(logged_in=True, username="周予安", user_id="1", role="user", current_page="problems")
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# API请求封装
def api_request(method, endpoint, data=None, params=None, files=None, cookies=None):
    if benchmark.ACTIVE:
        return benchmark.api_request(method, endpoint, data=data, params=params, files=files, cookies=cookies)
    url = f"{BASE_URL}{endpoint}"
    if cookies is None and st.session_state.cookies:
        cookies = st.session_state.cookies
    
    headers = {"Accept": "application/json"}
    if files:
        # 自动设置Content-Type为multipart/form-data
        pass
    else:
        headers["Content-Type"] = "application/json"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=params, cookies=cookies, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, files=files, cookies=cookies, headers=headers, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(url, json=data, cookies=cookies, headers=headers, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(url, cookies=cookies, headers=headers, timeout=30)
        else:
            return {"code": 400, "msg": f"不支持的方法: {method}"}, None

        if response.cookies:
            st.session_state.cookies = response.cookies

        try:
            result = response.json() if response.content else {"code": response.status_code, "msg": "响应为空"}
            return result, response.cookies
        except json.JSONDecodeError:
            return {"code": response.status_code, "msg": "解析JSON失败", "raw": response.text}, response.cookies

    except requests.exceptions.RequestException as e:
        st.error(f"请求错误: {e}")
        return {"code": 500, "msg": f"请求错误: {e}"}, None

# 页面导航
def navigate_to(page, problem_id=None):
    st.session_state.current_page = page
    st.session_state.current_problem_id = problem_id

# 组件：题目详情
def render_problem_details(problem):
    st.title(f"题目: {problem.get('title', '未知')}")
    st.caption(f"ID: {problem.get('id', 'N/A')}")

    st.markdown("### 题目描述")
    st.markdown(problem.get("description", "无"))

    st.markdown("### 输入描述")
    st.markdown(problem.get("input_description", "无"))

    st.markdown("### 输出描述")
    st.markdown(problem.get("output_description", "无"))
    
    st.markdown("### 数据范围")
    st.markdown(problem.get("constraints", "无"))

    st.markdown("### 样例")
    samples = problem.get("samples", [])
    if isinstance(samples, str):
        try:
            samples = json.loads(samples)
        except json.JSONDecodeError:
            samples = []
    for i, sample in enumerate(samples, 1):
        with st.expander(f"样例 {i}"):
            st.code(sample.get("input"), "text")
            st.code(sample.get("output"), "text")
            
    if problem.get("hint"):
        st.markdown("### 提示")
        st.warning(problem.get("hint"))

# 页面：登录/注册
def render_login_page():
    st.title("用户登录与注册")
    tab1, tab2 = st.tabs(["登录", "注册"])
    with tab1:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录"):
                res, _ = api_request("POST", "/api/auth/login", data={"username": username, "password": password})
                if res and res.get("code") == 200:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_id = res.get("data", {}).get("user_id")
                    st.session_state.role = res.get("data", {}).get("role")
                    st.success("登录成功！")
                    navigate_to("problems")
                    st.rerun()
                else:
                    st.error(f"登录失败: {res.get('msg', '未知错误')}")
    with tab2:
        with st.form("register_form"):
            username = st.text_input("用户名", key="reg_user")
            password = st.text_input("密码", type="password", key="reg_pass")
            if st.form_submit_button("注册"):
                res, _ = api_request("POST", "/api/users/", data={"username": username, "password": password})
                if res and res.get("code") == 200:
                    st.success("注册成功！请前往登录。")
                else:
                    st.error(f"注册失败: {res.get('msg', '未知错误')}")

# 页面：题目列表
def render_problems_page():
    st.title("题目列表")
    res, _ = api_request("GET", "/api/problems/")
    if res and res.get("code") == 200:
        problems = res.get("data", [])
        if problems:
            # 难度映射
            difficulty_map = {
                "easy": "入门", "easy-medium": "普及-", "medium": "普及/提高-",
                "medium-hard": "普及+/提高", "hard": "提高+/省选-",
                "hard-expert": "省选/NOI-", "expert": "NOI/NOI+"
            }
            for problem in sorted(problems, key=lambda x: x.get('id', '')):
                with st.container(border=True):
                    # 题号和标题
                    c1, c2 = st.columns([0.8, 4])
                    with c1:
                        st.subheader(f"`{problem.get('id', 'N/A')}`")
                    with c2:
                        st.subheader(problem.get('title', '未知题目'))

                    # 新增信息: 难度, 作者, 来源
                    info_cols = st.columns(3)
                    difficulty_val = problem.get('difficulty', '')
                    info_cols[0].markdown(f"**难度:** {difficulty_map.get(difficulty_val, '未分类')}")
                    info_cols[1].markdown(f"**作者:** {problem.get('author', 'N/A')}")
                    info_cols[2].markdown(f"**来源:** {problem.get('source', 'N/A')}")
                    
                    if benchmark.ACTIVE:
                        benchmark.extra_problem(problem)
                    st.markdown("") # 增加一些间距

                    if st.button("进入题目", key=f"view_{problem.get('id')}", use_container_width=True):
                        navigate_to("problem_detail", problem_id=problem.get('id'))
                        st.rerun()
        else:
            st.info("暂无题目")
    else:
        st.error("加载题目列表失败")

# 页面：题目详情
def render_problem_detail_page():
    problem_id = st.session_state.current_problem_id
    res, _ = api_request("GET", f"/api/problems/{problem_id}")
    if res and res.get("code") == 200:
        problem_data = res.get("data", {})
        
        st.title(f"题目: {problem_data.get('title', '未知')}")
        st.caption(f"ID: {problem_id}")

        st.markdown("### 题目信息")
        info_cols = st.columns(4)
        info_cols[0].metric("时间限制", f"{problem_data.get('time_limit', 1000)} ms")
        info_cols[1].metric("内存限制", f"{problem_data.get('memory_limit', 128)} MB")
        info_cols[2].metric("评测模式", f"{problem_data.get('judge_mode', 'standard')}")
        
        difficulty_map = {
            "easy": "入门", "easy-medium": "普及-", "medium": "普及/提高-",
            "medium-hard": "普及+/提高", "hard": "提高+/省选-",
            "hard-expert": "省选/NOI-", "expert": "NOI/NOI+"
        }
        difficulty_val = problem_data.get('difficulty', 'easy')
        info_cols[3].metric("难度", difficulty_map.get(difficulty_val, "未知"))

        meta_cols = st.columns(4)
        meta_cols[0].markdown(f"**作者:** {problem_data.get('author', 'N/A')}")
        meta_cols[1].markdown(f"**来源:** {problem_data.get('source', 'N/A')}")
        
        tags = problem_data.get('tags', [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else ""
        meta_cols[2].markdown(f"**标签:** {tags_str or '无'}")
        
        st.markdown("### 题目描述")
        st.markdown(problem_data.get("description", "无"))
        st.markdown("### 输入描述")
        st.markdown(problem_data.get("input_description", "无"))
        st.markdown("### 输出描述")
        st.markdown(problem_data.get("output_description", "无"))
        st.markdown("### 约束")
        st.markdown(problem_data.get("constraints", "无"))
        
        if problem_data.get("hint"):
            st.markdown("### 提示")
            st.info(problem_data.get("hint"))

        st.markdown("---")
        st.subheader("样例")
        samples = problem_data.get("samples", [])
        if isinstance(samples, str):
            try: samples = json.loads(samples)
            except json.JSONDecodeError: samples = []
        
        if not samples:
            st.info("该题目没有提供样例。")
        else:
            for i, sample in enumerate(samples, 1):
                c1, c2 = st.columns(2)
                c1.markdown(f"**样例输入 {i}**")
                c1.code(sample.get("input", ""), language="text")
                c2.markdown(f"**样例输出 {i}**")
                c2.code(sample.get("output", ""), language="text")
        
        st.markdown("---")
        
        c1, c2 = st.columns(2)
        if c1.button("提交代码", use_container_width=True, type="primary"):
            navigate_to("submit_code", problem_id=problem_id)
            st.rerun()
        if c2.button("我的本题提交", use_container_width=True):
            st.session_state.view_submissions_tab = "我的提交"
            st.session_state.submission_filter = {"problem_id": problem_id, "user_id": st.session_state.user_id}
            navigate_to("view_submissions")
            st.rerun()
            
    else:
        st.error("加载题目详情失败")
        
# 页面：添加/编辑题目
def render_add_problem_page():
    st.title("添加新题目")
    with st.form("add_problem_form"):
        st.info("请为新题目填写详细信息。对于列表类型字段，请使用JSON格式。")
        
        c1, c2 = st.columns(2)
        # 必填
        with c1:
            st.subheader("必填字段")
            id = st.text_input("题目ID (e.g., P1001)")
            title = st.text_input("标题")
            description = st.text_area("题目描述 (Markdown)", height=150)
            input_description = st.text_area("输入描述 (Markdown)", height=150)
            output_description = st.text_area("输出描述 (Markdown)", height=150)
            constraints = st.text_area("约束 (Markdown)", height=100)
        with c2:
            st.subheader("可选字段")
            hint = st.text_area("提示", height=100)
            source = st.text_input("来源")
            tags = st.text_input("标签 (用英文逗号,分隔)")
            time_limit = st.number_input("时间限制 (ms)", value=1000)
            memory_limit = st.number_input("内存限制 (MB)", value=128)
            author = st.text_input("作者", value=st.session_state.username)
            difficulty_map = {
                "easy": "入门", "easy-medium": "普及-", "medium": "普及/提高-",
                "medium-hard": "普及+/提高", "hard": "提高+/省选-",
                "hard-expert": "省选/NOI-", "expert": "NOI/NOI+"
            }
            difficulty = st.selectbox(
                "难度",
                options=list(difficulty_map.keys()),
                format_func=lambda x: difficulty_map.get(x, "未知"),
                index=0
            )
        
        st.subheader("样例和测试用例 (JSON格式)")
        samples = st.text_area("样例", height=100, value='[{"input": "1 1", "output": "2"}]', help='格式: [{"input": "...", "output": "..."}, ...]')
        testcases = st.text_area("测试用例", height=200, value='[{"input": "1 1", "output": "2"}]', help='格式: [{"input": "...", "output": "..."}, ...]')

        submitted = st.form_submit_button("创建题目")
        if submitted:
            try:
                problem_data = {
                    "id": id, "title": title, "description": description,
                    "input_description": input_description, "output_description": output_description,
                    "samples": json.loads(samples), "constraints": constraints, 
                    "testcases": json.loads(testcases),
                    "hint": hint, "source": source, "tags": [t.strip() for t in tags.split(',')] if tags else [],
                    "time_limit": time_limit, "memory_limit": memory_limit,
                    "author": author, "difficulty": difficulty
                }
                if not all([id, title, description, input_description, output_description, constraints]):
                    st.error("请填写所有必填字段！")
                else:
                    res, _ = api_request("POST", "/api/problems/", data=problem_data)
                    if res and res.get("code") == 200:
                        st.success(f"题目 {id} 创建成功！")
                    else:
                        st.error(f"创建失败: {res.get('msg', '未知错误')}")
            except json.JSONDecodeError:
                st.error("样例或测试用例的JSON格式不正确")
            except Exception as e:
                st.error(f"发生错误: {e}")

# 页面：提交代码
def render_submit_code_page():
    problem_id = st.session_state.current_problem_id
    st.title(f"提交代码到题目 {problem_id}")
    
    languages = []
    lang_res, _ = api_request("GET", "/api/languages/")
    if lang_res and lang_res.get("code") == 200:
        data = lang_res.get("data")
        if isinstance(data, list):
            languages = [lang.get('name') for lang in data if lang.get('name')]
        elif isinstance(data, dict) and "name" in data and isinstance(data.get("name"), list):
            languages = data["name"]

    if not languages:
        st.warning("无法加载可用语言列表，请确保后端服务正常且已配置语言。")
        languages = ["python"] # Fallback

    if benchmark.ACTIVE:
        current = benchmark.business()["state"]
        st.caption("待整理的代码草稿")
        st.code(current["source"]["text"], language="python")
    with st.form("submission_form"):
        language = st.selectbox("选择语言", languages)
        code = st.text_area("代码", height=400)
        if st.form_submit_button("提交"):
            data = {"problem_id": problem_id, "language": language, "code": code}
            res, _ = api_request("POST", "/api/submissions/", data=data)
            if res and res.get("code") == 200:
                submission_id = res.get('data', {}).get('submission_id')
                st.success(f"提交成功！提交ID: {submission_id}")
                if benchmark.ACTIVE:
                    st.info("代码已存入提交记录。")
                else:
                    st.info("评测任务已在后台运行，请稍后在“查看提交”页面手动查询结果。")
            else:
                st.error(f"提交失败: {res.get('msg', '未知错误')}")

# 页面：查看提交
def render_view_submissions_page():
    st.title("查看提交记录")

    tab_options = ["我的提交", "筛选查询", "按ID查询"]
    default_tab = st.session_state.pop('view_submissions_tab', '我的提交')
    try:
        default_index = tab_options.index(default_tab)
    except ValueError:
        default_index = 0
    
    my_submissions_tab, filter_tab, id_query_tab = st.tabs(tab_options)

    def render_submission_list(submissions):
        if not submissions:
            st.info("没有符合条件的提交记录。")
            return
        for sub in submissions:
            if sub is None: 
                continue
            with st.container():
                st.markdown("---")
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.markdown(f"**提交 ID:** `{sub.get('submission_id', 'N/A')}`")
                c2.markdown(f"**题目 ID:** `{sub.get('problem_id', 'N/A')}`")
                status = sub.get('status', 'N/A')
                color = "green" if status == "success" else "orange" if status == "pending" else "red"
                c3.markdown(f"**状态:** <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
                score = sub.get('score', 0)
                counts = sub.get('counts', 10)
                c4.metric("分数", f"{score}/{counts}")
                if benchmark.ACTIVE:
                    benchmark.extra_submission(sub)

    with my_submissions_tab:
        st.subheader("我的提交")
        pre_filter = st.session_state.pop('submission_filter', {})
        
        if "my_submissions_data" not in st.session_state or st.button("刷新我的提交", key="my_submissions_btn") or pre_filter:
            my_params = {"user_id": st.session_state.user_id}
            if pre_filter.get("problem_id"):
                 my_params['problem_id'] = pre_filter.get("problem_id")
            
            res, _ = api_request("GET", "/api/submissions/", params=my_params)
            if res and res.get("code") == 200:
                st.session_state.my_submissions_data = res.get("data", {})
            else:
                st.session_state.my_submissions_data = {"total": 0, "submissions": []}
                st.error(f"加载提交记录失败: {res.get('msg', '未知错误')}")
        
        data = st.session_state.get("my_submissions_data", {"total": 0, "submissions": []})
        st.write(f"共找到 {data.get('total', 0)} 条记录")
        render_submission_list(data.get("submissions", []))

    with filter_tab:
        st.subheader("筛选查询")
        with st.form("filter_form"):
            user_id_input = st.text_input("用户ID (可选)")
            problem_id_input = st.text_input("题目ID (可选)")
            status_input = st.selectbox("状态 (可选)", ["", "success", "pending", "error", "AC", "WA", "TLE", "MLE", "RE", "CE"])
            
            c1, c2 = st.columns(2)
            page_input = c1.number_input("页码", min_value=1, value=1)
            page_size_input = c2.number_input("每页数量", min_value=1, value=20)
            
            if st.form_submit_button("查询"):
                params = {k: v for k, v in {
                    "user_id": user_id_input, "problem_id": problem_id_input, "status": status_input,
                    "page": page_input, "page_size": page_size_input
                }.items() if v}
                
                if not params:
                    st.warning("请输入至少一个筛选条件。")
                else:
                    res, _ = api_request("GET", "/api/submissions/", params=params)
                    if res and res.get("code") == 200:
                        st.session_state.filtered_submissions_data = res.get("data", {})
                    else:
                        st.session_state.filtered_submissions_data = {"total": 0, "submissions": []}
                        st.error(f"加载提交记录失败: {res.get('msg', '未知错误')}")
        
        if "filtered_submissions_data" in st.session_state: # 只有查询后才显示
            filtered_data = st.session_state.get("filtered_submissions_data", {})
            st.write(f"共找到 {filtered_data.get('total', 0)} 条记录")
            render_submission_list(filtered_data.get("submissions", []))
    
    with id_query_tab:
        st.subheader("按ID查询提交")
        submission_id = st.text_input("输入提交ID", key="id_query_input")
        if st.button("查询状态", key="id_query_btn"):
            if submission_id:
                res, _ = api_request("GET", f"/api/submissions/{submission_id}")
                if res and res.get("code") == 200:
                    data = res.get("data", {})
                    st.success("查询成功！")
                    
                    # 显示题目ID和状态
                    st.markdown(f"**题目 ID:** `{data.get('problem_id', 'N/A')}`")
                    status = data.get('status', 'N/A')
                    color = "green" if status == "success" else "orange" if status == "pending" else "red"
                    st.markdown(f"**状态:** <span style='color:{color}; font-weight:bold;'>{status}</span>", unsafe_allow_html=True)

                    st.metric(label="分数", value=f"{data.get('score', 'N/A')} / {data.get('counts', 'N/A')}")
                else:
                    st.error(f"查询失败: {res.get('msg', '未知错误')}")

# 页面：语言列表
def render_languages_page():
    st.title("支持的语言")
    res, _ = api_request("GET", "/api/languages/")
    if res and res.get("code") == 200:
        st.dataframe(res.get("data", []), use_container_width=True, hide_index=True)

    # 移除管理员权限判断，让普通用户也能添加新语言
    with st.expander("添加新语言"):
        with st.form("add_lang_form"):
            st.subheader("必填字段")
            name = st.text_input("语言名称 (e.g., cpp)")
            file_ext = st.text_input("文件扩展名 (e.g., .cpp)")
            run_cmd = st.text_input("执行命令", placeholder="{executable_file} {input_file}")

            st.subheader("可选字段")
            compile_cmd = st.text_input("编译命令", placeholder="gcc {source_file} -o {executable_file}")
            source_template = st.text_area("代码模板")
            time_limit = st.number_input("默认时间限制 (s)", value=1.0, step=0.1, format="%.1f")
            memory_limit = st.number_input("默认内存限制 (MB)", value=128)

            if st.form_submit_button("添加"):
                if not all([name, file_ext, run_cmd]):
                    st.error("请填写所有必填字段！")
                else:
                    data = {
                        "name": name, "file_ext": file_ext, 
                        "compile_cmd": compile_cmd, "run_cmd": run_cmd,
                        "source_template": source_template, 
                        "time_limit": time_limit * 1000, # 后端单位为ms
                        "memory_limit": memory_limit
                    }
                    add_res, _ = api_request("POST", "/api/languages/", data=data)
                    if add_res and add_res.get("code") == 200:
                        st.success("语言添加成功！")
                        st.rerun()
                    else:
                        st.error(f"添加失败: {add_res.get('msg', '未知错误')}")
                            
# 页面：查看日志
def render_submission_log_page():
    st.title("查看评测日志")
    submission_id = st.text_input("请输入提交ID", key="log_sub_id")
    if st.button("查询日志", key="log_btn"):
        if submission_id:
            log_res, _ = api_request("GET", f"/api/submissions/{submission_id}/log")
            if log_res and log_res.get('code') == 200:
                data = log_res.get('data', {})
                st.success(f"日志获取成功 (提交ID: {submission_id})")
                
                st.metric("总分", f"{data.get('score', 0)} / {data.get('counts', 100)}")
                
                details = data.get('details', [])
                if not details:
                    st.warning("该提交仍在评测中或没有详细的测试点信息。")
                else:
                    st.markdown("---")
                    st.subheader("测试点详情")
                    for detail in details:
                        result = detail.get("result", "UNK")
                        color = "green" if result == "AC" else "red"
                        with st.container():
                            c1, c2, c3, c4 = st.columns(4)
                            c1.markdown(f"**测试点 #{detail.get('id', '?')}**")
                            c2.markdown(f"**结果: <span style='color:{color}; font-weight:bold;'>{result}</span>**", unsafe_allow_html=True)
                            c3.metric("耗时(s)", f"{detail.get('time', 0):.3f}")
                            c4.metric("内存(MB)", f"{detail.get('memory', 0):.2f}")
            else:
                st.error(f"获取日志失败: {log_res.get('msg', '未知错误')}")
        else:
            st.warning("请输入提交ID")

# 管理员面板
def render_admin_page():
    st.title("管理员面板")
    tabs = st.tabs(["题目管理", "用户管理", "提交管理", "SPJ管理", "系统管理"])

    with tabs[0]: # 题目管理
        st.subheader("所有题目")
        prob_res, _ = api_request("GET", "/api/problems/")
        if prob_res and prob_res.get("code") == 200:
            problems = prob_res.get("data", [])
            df = pd.DataFrame(problems, columns=["id", "title"])
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            if problems:
                selected_id = st.selectbox("选择题目进行操作", [p['id'] for p in problems])
                col1, col2 = st.columns(2)
                if col1.button("删除题目", type="primary"):
                    del_res, _ = api_request("DELETE", f"/api/problems/{selected_id}")
                    if del_res and del_res.get("code") == 200:
                        st.success(f"题目 {selected_id} 删除成功！")
                        st.rerun()
                
                with col2.expander("设置日志可见性"):
                    visibility_options = {"public": "对所有用户可见", "private": "对本人和管理员可见"}
                    visibility_choice = st.selectbox(
                        "选择可见性",
                        options=list(visibility_options.keys()),
                        format_func=lambda x: visibility_options[x]
                    )
                    if st.button("更新可见性"):
                        vis_res, _ = api_request("PUT", f"/api/problems/{selected_id}/log_visibility", data={"log_visibility": visibility_choice})
                        if vis_res and vis_res.get("code") == 200:
                            st.success("可见性更新成功！")

    with tabs[1]: # 用户管理
        st.subheader("所有用户")
        user_res, _ = api_request("GET", "/api/users/")
        if user_res and user_res.get("code") == 200:
            users = user_res.get("data", {}).get("users", [])
            st.dataframe(users, use_container_width=True, hide_index=True)
            
            if users:
                selected_user = st.selectbox("选择用户", users, format_func=lambda u: f"{u['username']} ({u['user_id']})")
                new_role = st.selectbox("设置新角色", ["user", "admin", "banned"], index=["user", "admin", "banned"].index(selected_user['role']))
                if st.button("更新角色"):
                    role_res, _ = api_request("PUT", f"/api/users/{selected_user['user_id']}/role", data={"role": new_role})
                    if role_res and role_res.get("code") == 200:
                        st.success(f"用户 {selected_user['username']} 的角色已更新！")
                        st.rerun()
        
        with st.expander("创建管理员账户"):
            with st.form("create_admin_form"):
                username = st.text_input("新管理员用户名")
                password = st.text_input("密码", type="password")
                if st.form_submit_button("创建"):
                    admin_res, _ = api_request("POST", "/api/users/admin", data={"username": username, "password": password})
                    if admin_res and admin_res.get("code") == 200:
                        st.success(f"管理员 {username} 创建成功！")
                        st.rerun()
                    else:
                        st.error(f"创建失败: {admin_res.get('msg', '未知错误')}")

    with tabs[2]: # 提交管理
        st.subheader("重新评测提交")
        with st.form("rejudge_form"):
            submission_id = st.text_input("输入要重新评测的提交ID")
            if st.form_submit_button("执行重判", type="primary"):
                if submission_id:
                    rejudge_res, _ = api_request("PUT", f"/api/submissions/{submission_id}/rejudge")
                    if rejudge_res and rejudge_res.get('code') == 200:
                        st.success(f"已将提交 {submission_id} 加入重判队列！")
                    else:
                        st.error(f"重判失败: {rejudge_res.get('msg', '未知错误')}")

    with tabs[3]: # SPJ管理
        st.subheader("SPJ管理")
        prob_res_spj, _ = api_request("GET", "/api/problems/")
        if prob_res_spj and prob_res_spj.get("code") == 200:
            problems = prob_res_spj.get("data", [])
            if problems:
                problem_id = st.selectbox("选择题目进行SPJ配置", [p['id'] for p in problems])
                
                languages = []
                lang_res, _ = api_request("GET", "/api/languages/")
                if lang_res and lang_res.get("code") == 200:
                    data = lang_res.get("data")
                    if isinstance(data, dict) and "name" in data and isinstance(data.get("name"), list):
                        languages = data["name"]

                language = st.selectbox("SPJ语言", languages)
                uploaded_file = st.file_uploader("上传SPJ脚本 (e.g., .py, .cpp)")
                
                if st.button("上传SPJ"):
                    if uploaded_file and language:
                        # 注意：文件上传时，参数需要通过URL传递
                        endpoint = f"/api/problems/{problem_id}/spj?language={language}"
                        files = {'file': (uploaded_file.name, uploaded_file.getvalue(), "text/plain")}
                        res, _ = api_request("POST", endpoint, files=files)
                        if res and res.get("code") == 200:
                            st.success("SPJ上传成功！")
                        else:
                            st.error(f"上传失败: {res.get('msg') if res else '请求失败'}")
                    else:
                        st.warning("请选择SPJ脚本和语言。")

                if st.button("删除SPJ", type="primary"):
                    del_spj_res, _ = api_request("DELETE", f"/api/problems/{problem_id}/spj")
                    if del_spj_res and del_spj_res.get("code") == 200:
                        st.success("SPJ删除成功！")

    with tabs[4]: # 系统管理
        st.subheader("数据管理")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("导出全部数据"):
                res, _ = api_request("GET", "/api/export")
                if res:
                     st.download_button("下载导出文件 (export.json)", json.dumps(res, indent=2), "export.json")
        with col2:
            uploaded_import_file = st.file_uploader("导入数据 (.json)")
            if st.button("执行导入"):
                if uploaded_import_file:
                    files = {'file': uploaded_import_file}
                    res, _ = api_request("POST", "/api/import", files=files)
                    if res and res.get("code") == 200:
                        st.success("数据导入成功！请刷新页面查看。")
                    else:
                        st.error(f"导入失败: {res.get('msg', '未知错误')}")
        
        st.subheader("危险区域")
        st.warning("以下操作不可逆，请谨慎操作！")
        if st.checkbox("我确认要进行危险操作"):
            if st.button("重置系统", type="primary"):
                reset_res, _ = api_request("POST", "/api/reset")
                if reset_res and reset_res.get("code") == 200:
                    st.success("系统重置成功！会话已失效，请重新登录。")
                    time.sleep(2)
                    # 登出并清理会话
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    init_session_state()
                    st.rerun()
                else:
                    st.error(f"重置失败: {reset_res.get('msg', '未知错误')}")

# 页面：日志审计
def render_log_auditing_page():
    st.title("日志审计 (Access Log)")
    if st.button("刷新访问日志"):
        log_res, _ = api_request("GET", "/api/logs/access")
        if log_res and log_res.get("code") == 200:
            st.dataframe(log_res.get("data", []))
        else:
            st.error(f"获取日志失败: {log_res.get('msg', '未知错误')}")

# 侧边栏和主路由
def render_sidebar():
    with st.sidebar:
        st.title("Liugu OJ")
        st.title("导航")
        if not st.session_state.logged_in:
            if st.button("登录/注册", use_container_width=True):
                navigate_to("login")
        else:
            st.success(f"欢迎, {st.session_state.username} ({st.session_state.role})")
            if st.button("题目列表", use_container_width=True): navigate_to("problems")
            if st.button("添加题目", use_container_width=True): navigate_to("add_problem")
            if st.button("查看提交", use_container_width=True): navigate_to("view_submissions")
            if benchmark.ACTIVE and st.button("我的代码与笔记", use_container_width=True): navigate_to("files")
            if st.button("查看日志", use_container_width=True): navigate_to("submission_log")
            if st.button("支持的语言", use_container_width=True): navigate_to("languages")
            
            if st.session_state.role == "admin":
                st.divider()
                st.subheader("管理员")
                if st.button("日志审计", use_container_width=True): navigate_to("log_auditing")
                if st.button("管理面板", use_container_width=True): navigate_to("admin")
            
            st.divider()
            if st.button("登出", use_container_width=True):
                api_request("POST", "/api/auth/logout")
                # 清理会话
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                init_session_state()
                st.rerun()

def main():
    init_session_state()
    render_sidebar()
    
    page = st.session_state.current_page
    
    if not st.session_state.logged_in:
        render_login_page()
    elif page == "files" and benchmark.ACTIVE: benchmark.render_files()
    elif page == "problems": render_problems_page()
    elif page == "problem_detail": render_problem_detail_page()
    elif page == "add_problem": render_add_problem_page()
    elif page == "submit_code": render_submit_code_page()
    elif page == "view_submissions": render_view_submissions_page()
    elif page == "submission_log": render_submission_log_page()
    elif page == "languages": render_languages_page()
    elif page == "admin" and st.session_state.role == "admin": render_admin_page()
    elif page == "log_auditing" and st.session_state.role == "admin": render_log_auditing_page()
    else:
        render_problems_page()

if __name__ == "__main__":
    main()
