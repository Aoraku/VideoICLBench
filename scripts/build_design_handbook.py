"""Generate the team's final task handbook from executable task contracts."""
import argparse
import ast
from collections import Counter
import html
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from vic.main import create_app
from vic.config import ROOT
from vic.task_review import os_catalog
from vic.execution_prompts import RELATION

FAMILIES={
 'selection':'对象属性与入选条件', 'selection_set':'对象属性与集合筛选条件',
 'mapping':'对象特征与操作或目标位置的对应关系', 'ordering':'比较字段与处理优先顺序',
 'state_machine':'可见状态与下一步动作的对应关系', 'recovery':'异常类型与两步恢复动作的对应关系',
 'cross_app':'来源面板信息与目标对象的匹配关系',
}
EMBODIED_DEMOS={
'F01':'完整展示三种颜色积木的支撑关系与自下而上的叠放结果。',
'F11':'展示圆、三角、方柱标记各自对应的圆环颜色，以及圆环实际套入柱子的结果。',
'F10':'同时呈现参照板与目标框，展示相对位置经变换后的对应关系。',
'F08':'呈现多套不同颜色的形状件，展示所选颜色套件及各形状对应的孔位。',
'F22':'呈现上下托盘、下层物件尺寸、被取走物件及恢复后的托盘关系，明确尺寸选择原则。',
'F17':'呈现堆叠的层次、从底部计数的目标层，以及取件后剩余物件的相对次序。',
'F39':'呈现三类区域标记、示范收集区与木球聚拢的结果，明确收集目标的对应关系。',
'F44':'呈现盒标记、导向板、挡球件和球的最终去向，明确所选标记与目标盒的对应关系。',
}


def collect(os_source):
    with TemporaryDirectory() as tmp:
        secret='handbook-local-read-only'
        app=create_app(database_url=f'sqlite:///{tmp}/db',data_dir=Path(tmp),secret=secret)
        with TestClient(app) as client:
            response=client.get('/v2/tasks',headers={'Authorization':'Bearer '+secret});response.raise_for_status()
            web=response.json()['tasks']
    rows=[]
    for t in web:
        demo=t['demo']; count=demo['episode_count']
        rows.append(dict(id=f"{t['id']:03d}",kind='web',title=t['title'],platform=' / '.join(t['platforms']),difficulty={'low':'低','medium':'中','hard':'高'}[t['difficulty']],type=t['type'],relation=RELATION[t['id']],
            demo=f"从应用默认首页进入操作页，展示{RELATION[t['id']]}，保留输入、操作及保存后的可见结果。示范包含 {count} 组规则案例。"+('本题只保存多行答案草稿，不提交判题答案。' if t['id']==59 else '')+('示范所需的移动过程用于呈现首次达到停止条件的时刻，复盘文档不属于示范。' if t['id']==69 else '')+('每组只示范一个落点，连续六回合和复盘交付属于 inference。' if t['id']==74 else ''),
            rules={v:demo.get('rule_explanations',{}).get(v) or t['variants'][v] for v in 'ABC'},inference=t['inference']['instructions'],delivery=t['delivery'],recording='同事录制的规则示范',review=f"/review?kind=web&task={t['id']}"))
    release=json.loads((os_source/'videoicl-catalog.json').read_text())
    for t in release['cases']:
        rows.append(dict(id=t['id'],kind='os',title=t['title'],platform='OS-ICL / '+t['app'],difficulty=t['difficulty'],type=t['difficulty_reason'],relation=t['relation'],
            demo=t['demo_description'],rules=t['rules'],inference=t['task']+'\n公共交付约束与实例范围：'+t['query_example'],delivery=t['evaluation'],recording='同事人工录制并审核的局部方法示范',review=f"/review?kind=os&task={t['id']}"))
    manifest=json.loads((ROOT/'simulator/delivery8/release.private.json').read_text())
    for t in manifest['tasks']:
        rows.append(dict(id=t['id'],kind='embodied',title=t['title'],platform='Tabletop8 双臂桌面仿真',difficulty=t['difficulty']+' / '+t['length'],type='物理交互',relation=t['challenge'],demo=EMBODIED_DEMOS[t['id']],rules=t['rules'],inference=t['challenge']+'。在新的初始布局中完成对应操作；以真实接触、支撑、插入或物体位置关系为准，结束任务后保存执行结果。',delivery='满足本题目标物理状态的执行结果与自动保存的执行录像。',recording='仿真作者控制器示范，非真人录制',review=f"/review?kind=embodied&task={t['id']}"))
    assert len(rows)==119
    return rows


def render(rows):
    esc=lambda value:html.escape(str(value))
    paragraphs=lambda text:''.join('<p>'+esc(line)+'</p>' for line in text.split('\n') if line.strip())
    output=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VideoICL 任务设计手册</title><style>
:root{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#202c33;background:#fff;line-height:1.8}body{margin:0}main{max-width:1040px;margin:0 auto;padding:52px 42px}h1{font-size:34px;margin:0 0 12px;color:#000}h2{font-size:25px;margin-top:46px;color:#000}h3{font-size:21px;color:#000;margin:0 0 10px}h4{font-size:16px;margin:20px 0 6px;color:#000}p{margin:8px 0 14px}a{color:#256451}small,.meta{color:#52636b}.meta{font-size:14px}table{width:100%;border-collapse:collapse;margin:20px 0 28px;font-size:14px}th,td{border:1px solid #d9d9d9;padding:11px 14px;vertical-align:top;text-align:left}th{background:#e8eff2;color:#000}tbody tr:nth-child(even){background:#f7f9fa}.controls{position:sticky;top:0;z-index:2;display:flex;gap:12px;flex-wrap:wrap;background:#fff;padding:15px 0;border-bottom:1px solid #cbd5db}input,select,button{font:inherit;font-size:14px;padding:9px 12px;background:#fff;border:1px solid #b8c5c9;border-radius:5px}input{flex:1;min-width:220px}.task{border-top:1px solid #b8c5c9;margin-top:36px;padding-top:24px;scroll-margin-top:100px}.rule{margin:6px 0}.rule b{display:inline-block;min-width:30px}.task p{white-space:pre-wrap}.task[hidden]{display:none}.index td:first-child{white-space:nowrap}.index td:nth-child(3){width:22%}.toplinks{display:flex;gap:22px;margin:22px 0}.note{font-size:14px;color:#52636b}@media(max-width:700px){main{padding:28px 20px}table{font-size:12px}td,th{padding:8px}h1{font-size:29px}}@media print{main{max-width:none;padding:0}.controls,.toplinks,.review-link{display:none}a{color:#000;text-decoration:none}h2,h3,h4{break-after:avoid}.task{break-before:auto}.rule,p{orphans:3;widows:3}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4;margin:20mm}}
</style><main><header><h1>VideoICL 任务设计手册</h1><p class="meta">设计原则 难度体系 逐题示范与执行规范</p><p>本手册面向任务设计者、视频录制同事与评测维护者，覆盖 75 道 Web 任务、36 道 OS 任务和 8 道具身任务，共 119 个任务族与 357 个 A/B/C 条件。评测的核心是从清晰的视频示范中学会可迁移的方法，再在独立的新实例中完成目标。执行难度由业务依赖、状态变化和物理交互决定。</p><p class="note">本手册包含完整 A/B/C 规则，供团队设计与审阅使用，不作为 agent 的 inference prompt。</p></header>
<nav class="toplinks"><a href="#principles">设计原则</a><a href="#levels">难度分级</a><a href="#index">任务索引</a><a href="#tasks">逐题规范</a></nav>
<section id="principles"><h2>设计原则</h2>
<p><b>视频教会明确的方法。</b>示范应清晰呈现输入、处理动作和结果。文本题明确整段、逐词、逐字符或逐行的作用范围；分类题同时呈现命中与未命中对象；阈值题覆盖边界；选择题让竞争属性对应不同候选；排序题说明稳定性与并列约定。视频长度以足以辨认关系为准，不能通过信息缺失或歧义提高难度。</p>
<p><b>Demo 与 inference 职责独立。</b>Web 各难度的 demo 均只展示方法及必要操作，从默认首页保留进入操作页的自然导航。资料汇总、跨模块办理、跨平台交付等完整业务链属于 inference。停止判断等依赖动态过程的示范须保留触发条件前后的必要过程。视频与执行应用可以不同，但字段和动作的对应关系必须明确。OS 配套示范呈现局部交互关系；具身示范呈现关系及其必要物理实现过程，不以轨迹长度冒充额外规则。</p>
<p><b>Prompt 是目标加约束。</b>执行者获得需要完成的成果、处理范围、限制条件及必要公共参数，且明确应从视频学习哪一种对应关系、选择顺序或转换格式。Prompt 不给 A/B/C 的答案，不提供按钮级路线。软件显示联系人、文件、业务通知、来源资料与已保存状态；评测目标和教程说明由外部 prompt 提供。</p>
<p><b>一个 episode 对应一个持续环境。</b>同一应用内的多份消息、文章、歌曲或答案是同一资料库里的对象，操作按对象编号保存。应用导航只改变查看位置。涉及多平台时，应用切换入口连接同一个 run 的共享数据与真实文件；切换不重置状态、不替换任务实例，也不显示解题进度。</p>
<p><b>A/B/C 是反事实对照。</b>同一任务在相同 seed 下保持输入环境和业务目标一致，三个条件分别提供对应版本的视频，使用独立的模型上下文与运行状态。三个版本是三次独立评测，不是一次 inference 中要完成的三个清单项。Demo 的实例与 inference 的实例分开，避免直接复制对象编号或答案。</p>
<p><b>依据真实结果判分。</b>评测器读取实际保存的文本、标签、集合、顺序、消息、提交记录和物理状态，同时检查未命中对象、来源关联与接收对象。严格成功要求所有必要条件满足；检查项完成度用于诊断部分成功，不代替严格成功。多对象题不得因最后一项正确而覆盖前面错误。需要交付文件的任务检查文件内容与实际业务状态一致。</p>
<p><b>规则理解与执行能力分别分析。</b>可在观看视频后用独立 QA 测量关系理解，再观察在线执行结果。无视频、错配视频和正确视频构成有用的对照。任务级成功率、检查项完成度与失败类型应一起报告，人工难度标签不能替代实测模型成功率。</p></section>
<section id="levels"><h2>难度分级</h2><p>Web 的低中高按执行结构划分，各 25 题。所有等级使用同样清晰的示范要求。</p>
<table><thead><tr><th>等级</th><th>执行结构</th><th>必要判分依据</th></tr></thead><tbody><tr><td>Web 低</td><td>在同一应用数据库中处理多个对象。文本题通常有三份资料，生成内容分类有十二条；棋盘题在同一棋谱库保存三份不同棋盘，逐一分类或作局部决策。</td><td>逐对象结果和未命中对象的保持；三份棋谱分别核对合法操作及条件，并提供部分完成度。</td></tr><tr><td>Web 中</td><td>围绕一个交付目标完成同平台多模块业务，关联独立资料、制作成果并交付。视频方法是其中的一个环节。</td><td>有效请求、范围、实际处理结果、资料关联、可下载成果及接收地址。</td></tr><tr><td>Web 高</td><td>跨两个或多个平台的完整业务流程，后续操作消耗前序真实结果或文件。</td><td>源数据、实际保存状态、跨平台内容一致性、正确接收人和可追溯交付。</td></tr></tbody></table>
<p>棋盘选点基线可能只需一次决策，不能据其标签宣称具备长程难度。长度、难度与规则复杂度是不同维度：重复次数增加执行负担，状态依赖与跨应用资料关联增加规划负担，物理接触增加控制负担；含糊规则、等待时间和无意义点击不构成设计难度。</p>
<p>OS 分为 Easy、Medium、Hard，各 12 题。Easy 在一个持续桌面中对多个新对象重复应用同一方法；Medium 在一个主要应用中完成长程业务，视频方法只是其中一个模块；Hard 在此基础上要求 File Explorer、Notepad、Settings、Task Scheduler 等桌面应用之间有真实内容或状态依赖。应用切换不重置环境。Demo 由人录制，覆盖同一规则的多次实现，不演示完整长程 query。三档都是执行结构标签，不代表模型实测成功率。</p>
<p>具身任务分别保留长度和难度：简单 2 题，中等 3 题，困难 3 题；短程 3 题，中程 3 题，长程 2 题。难点来自重排、遮挡下取件、结构恢复、真实套入和非抓取接触控制。配套视频来自仿真作者控制器；难度标签不表示独立 VLM 已验证的成功率。</p></section>
<h2 id="index">任务索引</h2><div class="controls"><input id="search" aria-label="搜索任务" placeholder="搜索题号 任务名 平台或内容"><select id="kind" aria-label="任务类型"><option value="">全部类型</option><option value="web">Web</option><option value="os">OS</option><option value="embodied">具身</option></select><span id="count">119 题</span></div><table class="index"><thead><tr><th>编号</th><th>任务</th><th>平台</th><th>难度</th></tr></thead><tbody>''']
    for t in rows:output.append(f'<tr data-kind="{t["kind"]}" data-task="{t["id"]}"><td><a href="#task-{t["id"]}">{t["id"]}</a></td><td>{esc(t["title"])}</td><td>{esc(t["platform"])}</td><td>{esc(t["difficulty"])}</td></tr>')
    output.append('</tbody></table><h2 id="tasks">逐题规范</h2><p class="note">Web 条目给出完整执行请求。实例化时人物、项目或资料名称以该 run 返回的 inference_task 为准。OS 条目给出目标、公共交付约束与需要学习的具体关系。具身条目以八题交付定义为准。录像和实例启动入口由任务审阅页提供。</p>')
    for t in rows:
        output.append(f'<article class="task" id="task-{t["id"]}" data-kind="{t["kind"]}" data-task="{t["id"]}"><h3>{t["id"]} {esc(t["title"])}</h3><p class="meta">{esc(t["platform"])} · 难度 {esc(t["difficulty"])} · 类型 {esc(t["type"])}</p><h4>Demo 呈现什么</h4>{paragraphs(t["demo"])}<p class="meta">视频来源：{esc(t["recording"])}</p>')
        for v in 'ABC':output.append(f'<p class="rule"><b>{v}</b>{esc(t["rules"][v])}</p>')
        output.append(f'<h4>Inference 执行什么</h4>{paragraphs(t["inference"])}<p><b>学习关系：</b>{esc(t["relation"])}</p><p><b>最终成果：</b>{esc(t["delivery"])}</p><a class="review-link" href="{t["review"]}">审阅视频与打开执行环境</a></article>')
    output.append('''<h2>规范来源</h2><p>Web 任务目录及运行生成器、录制指导、独立评测器；OS-ICL tasks36.py / judge36.py 与 tasks/os/catalog.json；Tabletop8 八题交付规则与任务定义。视频资料、录像审核状态和审阅意见由平台后端独立保存。</p></main><script>
const tasks=[...document.querySelectorAll('article.task')],index=[...document.querySelectorAll('.index tbody tr')];function filter(){const q=document.querySelector('#search').value.toLowerCase(),kind=document.querySelector('#kind').value;let n=0;tasks.forEach((t,i)=>{const hide=(kind&&t.dataset.kind!==kind)||!t.textContent.toLowerCase().includes(q);t.hidden=!!hide;index[i].hidden=!!hide;if(!hide)n++});document.querySelector('#count').textContent=n+' 题'}document.querySelector('#search').oninput=filter;document.querySelector('#kind').onchange=filter;
</script></html>''')
    return ''.join(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--os-source',type=Path,required=True);args=parser.parse_args()
    rows=collect(args.os_source)
    (ROOT/'docs/task-design-catalog.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs/task-design.html').write_text(render(rows))
    print('Generated handbook:',dict(Counter(t['kind'] for t in rows)))
