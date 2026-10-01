"""Native Liugu OJ course workspace for multi-file, history and delivery tasks."""
import base64,json
import streamlit as st
import benchmark_bridge as bridge
from vic_apps.code_projects import latest_check,delivery_rows


def go(page,entry=None):
    st.session_state.current_page=page
    if entry:st.session_state.course_entry_id=entry
    st.rerun()


def command(op,target='',data=None):
    try:
        bridge.command(op,target,json.dumps(data or {}));st.rerun()
    except ValueError as exc:st.error(str(exc))


def download(state,id,label):
    file=state['domain']['files'].get(id)
    if file:st.download_button(label,base64.b64decode(file['content']),file_name=file['name'],mime='application/zip' if file['name'].endswith('.zip') else 'text/markdown',key='download_'+id)


def sidebar(state):
    st.success('欢迎，周予安 · 课程交付')
    tabs=[('题目列表','problems'),('课程清单','course_overview'),('项目工作区','course_editor'),('检查记录','course_checks'),('查看提交','course_submissions'),('交付中心','course_delivery')]
    if state['task_id']==64:tabs.insert(2,('历史版本','course_history'))
    for label,page in tabs:
        if st.button(label,use_container_width=True,key='nav_'+page):go(page)
    st.divider();st.caption('Python · 项目内运行')
    st.caption('题目提供全部测试和源代码；从课程清单查看工作要求。')
    if st.button('运行说明',use_container_width=True):go('course_help')


def choose_entry(w):
    keys=[e['id'] for e in w['entries']];current=st.session_state.get('course_entry_id',keys[0])
    if current not in keys:current=keys[0]
    id=st.selectbox('课程条目',keys,index=keys.index(current),format_func=lambda id:id+' · '+next(e['title'] for e in w['entries'] if e['id']==id))
    st.session_state.course_entry_id=id
    return next(e for e in w['entries'] if e['id']==id)


def check_result(checked):
    if not checked:return
    st.subheader(checked['id'])
    a,b=st.columns(2);a.metric('本地语法检查',checked['syntax']['status']);b.metric('测试运行结果',checked['tests']['status'])
    st.caption(checked['syntax']['detail'])
    if checked['tests']['detail']:st.code(checked['tests']['detail'],language='text')
    if checked['tests']['cases']:
        st.dataframe([{'测试点':r['name'],'输入':json.dumps(r['input'],ensure_ascii=False),'预期输出':json.dumps(r['expected'],ensure_ascii=False),'实际输出':json.dumps(r['actual'],ensure_ascii=False),'状态':r['status'],'说明':r['detail']} for r in checked['tests']['cases']],hide_index=True,use_container_width=True)


def render(page,state):
    w=state['world'];locked=bool(w['delivery'] and w['delivery']['published'])
    if page=='problems':
        st.info(state['execution']['assignment'])
        if st.button('查看本课程清单',type='primary'):go('course_overview')
        return False
    if page in ('problem_detail','languages'):return False
    if page=='submit_code':
        candidates=[e for e in w['entries'] if e['problem']==str(st.session_state.current_problem_id)]
        go('course_editor',candidates[0]['id'] if candidates else None)
    if page in ('files','view_submissions'):page='course_editor' if page=='files' else 'course_submissions'
    if page=='course_overview':
        st.title('课程清单');st.info(w['brief'])
        for e in w['entries']:
            with st.container(border=True):
                st.subheader(e['id']+' · '+e['title']);st.caption('指定题号：'+e['problem']+' · 文件：'+', '.join(e['files']))
                a,b=st.columns(2)
                if a.button('打开 '+e['id'],key='entry_'+e['id']):go('course_editor',e['id'])
                if b.button('查看题目 '+e['id'],key='problem_'+e['id']):
                    st.session_state.current_problem_id=e['problem'];go('problem_detail')
        download(state,'course-readme','下载课程说明')
    elif page=='course_editor':
        st.title('项目工作区');e=choose_entry(w);id=e['id'];files=w['drafts'][id]
        st.caption('指定题号：'+e['problem']+' · 入口：'+e['entry_file']+' / solve')
        with st.expander('课程要求'):st.write(w['brief'])
        if not files:
            st.info('请先从历史版本恢复本模块代码。')
            if st.button('选择历史版本'):go('course_history',id)
            return True
        if state['task_id']==60:st.info('重命名范围：pricing.py、invoice.py 中的 tax_rate、total、tax。保留 app.py、函数接口、字典键和字符串。')
        if state['task_id']==65:st.info('候选源代码保持不变。本地检查为语法检查，测试运行结果另行记录。')
        edited={}
        for name,tab in zip(files,st.tabs(list(files))):
            with tab:
                with st.expander('给定源代码 · '+name):st.code(e['files'][name],language='python')
                edited[name]=st.text_area('编辑 '+name,value=files[name],height=340,key='editor_'+id+'_'+name,disabled=locked or state['task_id']==65)
                st.caption(f'{len(edited[name])} 个字符 · {len(edited[name].splitlines())} 行')
                if state['task_id']==58:bridge.whitespace_view(edited[name])
        dirty=edited!=files
        a,b=st.columns(2)
        if a.button('保存全部文件',disabled=locked or state['task_id']==65,type='primary'):command('code.save',id,{'files':edited})
        if b.button('运行本地检查与测试',disabled=locked or dirty):command('code.check',id)
        if dirty:st.warning('编辑内容尚未保存，请保存后再运行检查或提交。')
        checked=latest_check(w,id);check_result(checked)
        if state['task_id']!=64:
            st.divider();st.subheader('提交判题')
            pids=[p['id'] for p in w['problems']]
            problem=st.selectbox('提交题号',pids,index=pids.index(e['problem']),format_func=lambda p:p+' · '+next(x['title'] for x in w['problems'] if x['id']==p),key='submit_problem_'+id)
            existing=next((s for s in w['submissions'].values() if s['entry']==id),None)
            if st.button('提交当前代码',disabled=locked or dirty or not checked or bool(existing),type='primary'):command('code.submit',id,{'problem':problem})
            if existing:
                st.success(existing['id']+' · 题目 '+existing['problem']+' · '+existing['tests']['status'])
                if existing['files']!=files:st.warning('提交快照与当前代码不同，请撤回并重新提交。')
                if st.button('撤回此提交',disabled=locked):command('code.withdraw',existing['id'])
                download(state,'submission-'+existing['id'],'下载此提交代码包')
        if st.button('前往交付中心'):go('course_delivery')
    elif page=='course_history':
        st.title('历史版本');e=choose_entry(w)
        st.info('按照视频选择版本，恢复后运行检查。不要求修复历史代码的错误。')
        for h in w['history']:
            if h['entry']!=e['id']:continue
            with st.container(border=True):
                st.subheader(h['id']);st.caption(h['created_at']+' · '+str(sum(len(c.splitlines()) for c in h['files'].values()))+' 行 · 题目 '+h['problem'])
                for name,code in h['files'].items():
                    with st.expander('查看 '+h['id']+' / '+name):st.code(code,language='python',line_numbers=True)
                if st.button('恢复 '+h['id'],disabled=locked):
                    try:
                        bridge.command('code.restore',e['id'],json.dumps({'version':h['id']}))
                        for name,code in h['files'].items():st.session_state['editor_'+e['id']+'_'+name]=code
                        go('course_editor',e['id'])
                    except ValueError as exc:st.error(str(exc))
    elif page=='course_checks':
        st.title('检查记录')
        if not w['checks']:st.info('尚无检查记录。请在工作区保存并运行代码。')
        for c in reversed(list(w['checks'].values())):
            with st.expander(c['id']+' · '+c['entry']+' · '+c['tests']['status']):
                check_result(c)
                for name,code in c['files'].items():st.caption(name);st.code(code,language='python')
                if st.button('打开条目 '+c['id']):go('course_editor',c['entry'])
    elif page=='course_submissions':
        st.title('查看提交记录')
        if not w['submissions']:st.info('尚无本课程提交。')
        for sub in reversed(list(w['submissions'].values())):
            with st.container(border=True):
                st.subheader(sub['id']);st.caption(sub['entry']+' · 题目 '+sub['problem']+' · 检查 '+sub['check']);st.write('判题结果：'+sub['tests']['status'])
                for name,code in sub['files'].items():
                    with st.expander(sub['id']+' / '+name):st.code(code,language='python')
                download(state,'submission-'+sub['id'],'下载 '+sub['id'])
                a,b=st.columns(2)
                if a.button('打开 '+sub['id']):go('course_editor',sub['entry'])
                if b.button('撤回 '+sub['id'],disabled=locked):command('code.withdraw',sub['id'])
    elif page=='course_delivery':render_delivery(state)
    else:
        st.title('课程运行说明');st.write(w['brief']);st.markdown('运行入口为题目给出的 Python 函数。每个测试点使用独立的模块状态。支持项目内 `from … import …`、函数、循环、条件判断、基本算术及 `sum`、`len`、`range` 等常用函数。单次运行限时 2 秒 CPU 时间，Linux 环境内存限制 256 MB。')
        st.markdown('**结果含义**：AC 测试通过；WA 输出不符；RE 运行错误；CE 代码无法运行；TLE 超时。本地语法检查 PASS/FAIL 与判题结果分别记录。')
    return True


def render_delivery(state):
    w=state['world'];saved=w['delivery'];locked=bool(saved and saved['published']);st.title('课程交付中心')
    st.caption('按课程清单核对来源、实际检查编号与提交编号，再保存并发布可下载代码包。')
    default=saved['rows'] if saved else [dict(entry=e['id'],problem=e['problem'],source='',check='',submission='',reason='') for e in w['entries']]
    if st.button('读取当前记录',disabled=locked):
        for r in delivery_rows(state):
            for key in ('problem','source','check','submission','reason'):st.session_state['delivery_'+r['entry']+'_'+key]=r[key]
        st.rerun()
    rows=[]
    for e in w['entries']:
        id=e['id'];old=next((r for r in default if r['entry']==id),dict(entry=id,problem=e['problem'],source='',check='',submission='',reason=''));r={'entry':id}
        with st.container(border=True):
            st.subheader(id+' · '+e['title']);columns=st.columns(3)
            for index,(key,label,options) in enumerate([
                ('problem','题号',[p['id'] for p in w['problems']]),
                ('check','检查编号',['']+[c['id'] for c in w['checks'].values() if c['entry']==id]),
                ('submission','提交编号',['']+[s['id'] for s in w['submissions'].values() if s['entry']==id]),
            ]):
                widget='delivery_'+id+'_'+key
                if st.session_state.get(widget,old[key]) not in options:st.session_state[widget]='' if '' in options else options[0]
                r[key]=columns[index].selectbox(label+' '+id,options,index=options.index(old[key]) if old[key] in options else 0,key=widget,disabled=locked or (key=='submission' and state['task_id']==64))
            if state['task_id']==64:
                opts=['']+[h['id'] for h in w['history'] if h['entry']==id]
                r['source']=st.selectbox('来源版本 '+id,opts,index=opts.index(old['source']) if old['source'] in opts else 0,key='delivery_'+id+'_source',disabled=locked)
            else:r['source']=''
            r['reason']=st.text_input('未提交原因 '+id,value=old['reason'],key='delivery_'+id+'_reason',disabled=locked) if state['task_id']==65 else ''
            if st.button('核对条目 '+id):go('course_editor',id)
        rows.append(r)
    dirty=not saved or rows!=saved['rows'];stale=bool(saved and saved['rows']!=delivery_rows(state))
    a,b,c=st.columns(3)
    if a.button('保存交付清单',disabled=locked,type='primary'):command('delivery.save',data={'rows':rows})
    if b.button('发布交付包',disabled=locked or dirty or stale):command('delivery.publish')
    if c.button('删除交付清单',disabled=locked or not saved):command('delivery.delete')
    if dirty:st.caption('交付行有待保存内容。')
    if stale:st.warning('检查、提交或代码已变化，请读取当前记录并重新保存。')
    if saved:
        st.success('交付包已发布') if locked else st.info('交付包已保存，尚未发布')
        st.markdown(saved['body']);download(state,'course-delivery','下载课程代码交付包');download(state,'course-manifest','下载交付清单')
        if locked and st.button('撤回交付发布'):command('delivery.reopen')
