"""Generate the OS recording design manual from the deployed task contract."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def task_section(t):
    t={**t,'inference_description':t['inference_description'].replace('新夹具移除旧版 cover/request 中固定纸型与双面答案；三种组合共享同一不泄漏组合的业务请求。','批准封面与公共请求不固定纸型或单双面；三种条件共享同一业务请求。').replace('复用现有 evidence 流程时，导出内容通过 Notepad 写入对应原通道的工作副本，保持后续 redact 已支持的 source 身份；不假设任意新文件自动拥有通道来源。','导出内容通过 Notepad 写入对应原通道的工作副本，保留来源身份，供脱敏流程校验。')}
    parts=[f"### {t['id']} {t['title']}",f"**平台：** {t['app']}",f"**难度：** {t['difficulty']}。{t['difficulty_reason']}",
        '**Demo 要录什么：** '+t['demo_description'],f"**示范组织：** {t['demo_groups']} 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。"]
    for v in 'ABC':parts.append(f"- **{v}：** {t['rules'][v]}")
    parts.append('**Demo 操作应用：** '+' → '.join(t['demo_apps']))
    parts.append('**从哪里进入：** '+t['demo_examples']['A'][0]['guide']['entry'])
    parts.append('完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。')
    parts.extend(['**Inference 目标：** '+t['task'],'**实例资料：** '+t['inference_description'],'**学习关系：** '+t['relation'],'**验收依据：** '+t['evaluation']])
    if t['dependencies']:parts.append('**跨应用必要依赖：**\n\n'+'\n'.join('- '+s for s in t['dependencies']))
    return '\n\n'.join(parts)+'\n'

if __name__=='__main__':
    rows=json.loads((ROOT/'tasks/os/catalog.json').read_text())['cases']
    intro='''# OS 任务设计与人工录制手册

本手册覆盖 36 个独立任务族、108 个 A/B/C 条件。面向任务设计者、录制者和审阅者；完整规则及录制说明属于团队资料，不进入被测 agent 的 prompt 或应用画面。

## 设计原则

- **清楚地教方法。** 每段 demo 在同一 A/B/C 条件下呈现多个输入、处理动作及保存后的结果。阈值覆盖边界，分类覆盖命中和不命中，选择提供竞争属性，排序或冲突处理说明并列约定。录制者在任务卡查看规则和逐组预期内容，无需试错反推判定器。
- **Demo 只呈现局部方法。** 从默认桌面自然进入应用，执行已经准备好材料的小例子。完整资料收集、故障排查、成果制作和交付属于 inference。预置前置状态使 hard 的 demo 无需重做整条业务流程。
- **A/B/C 是三个替代规则。** 同 seed 的三个 inference 环境及业务目标相同，分别使用匹配的一段人工视频、独立上下文和独立运行状态。不同版本不出现在同一段 demo 中。
- **一个 inference，一个持续桌面。** 批量对象同时存在于此环境。桌面任务栏可切换九个应用，共享真实文件、设置和作业状态。示范的“下一组”仅用于连续展示局部例子，不出现在 inference。
- **Prompt 是目标与约束。** 明确从视频学习哪一种选择条件、格式、目录组织或映射关系。交付文件名、字段约束和业务范围公开；所选规则的具体值不在 prompt 中泄漏。应用不展示评测目标或解题步骤。
- **真人录制与审核。** 录像由浏览器捕获人工操作，或上传本次示范的人工 WebM / MP4。服务器保存 MP4、原始示例种子、设计指纹、自动检查结果和审核人。只有所有示范组通过检查且人工审核通过的匹配录像可进入 ICL inference。AI 参考录像不计入人工 demo。
- **判实际结果。** 评测读取服务器持久状态，核对成果、来源和禁止副作用。严格成功是必要条件的合取；检查项得分含保护条件，不能当作业务完成百分比。人工审核另行确认视频可读、示例充分以及录制来源。

## 难度分级

| 档位 | 数量 | 执行结构 | Demo 范围 |
|---|---:|---|---|
| Easy | 12 | 在一个环境中对多个新对象反复执行同一方法 | 多个局部对象，含竞争项、边界或不命中项 |
| Medium | 12 | 一个主要应用内完成有依赖的长程业务；视频方法只占一个模块 | 该模块的多次实现，输入材料就绪 |
| Hard | 12 | Medium 加多个桌面应用之间必要的内容或状态依赖 | 该模块的多次实现，前置状态就绪 |

OS 的跨平台边界按现有功能应用划分，例如 File Explorer → Notepad → Task Scheduler → Device Manager。必须存在后者消耗前者内容或状态的依赖；只多开窗口不算跨平台难度。分级描述任务结构，不代表独立模型实测成功率。

## 录制与审阅

示范在浏览器内的 OS 桌面模拟器完成，不操作录制者电脑的真实系统。各题共用桌面外观和应用图标，但加载不同业务材料；同题 A/B/C 共享初始材料，方法不同。任务卡的「Demo 操作」只列示范所需应用，「Inference 执行应用」列完整业务所需应用。

1. 在工作台选择 **OS · 36 题**，选择题目与 A/B/C，阅读规则卡、示范范围和逐组预期保存内容。
   「在哪里操作」列出当前示范的图标、菜单、按钮和完整文件路径。文件夹双击进入；Notepad 用 Open… 的 Document 下拉框选择完整路径，再点 OK。每次保存用 Save，保存位置由打开的文件决定。
2. 可预览和试做；“重置示范”创建独立环境。点击“开始录制”会准备干净桌面，请在浏览器分享窗口中选择 OS 应用标签页。
3. 从桌面进入应用，执行各局部示例，展示保存结果。多组示范点击应用右下角“下一组”；最后点击“完成练习”。不录工作台规则卡，不演示完整 inference 流程。
4. 结束后自动上传并保存，无需选择本地录像文件。任务卡显示自动检查结果；填写审核人，确认视频覆盖全部同规则示例后提交审核。服务器录像可回放、下载，切题后保留状态。
5. 审阅台按 OS 分类显示平台、难度、A/B/C、demo 内容、同事录像、inference 目标和独立环境入口，可保存评价与修改建议。

## 任务索引

| 编号 | 任务 | 平台 | 难度 | Demo 组数 |
|---|---|---|---|---:|
'''
    index='\n'.join(f"| {t['id']} | {t['title']} | {t['app']} | {t['difficulty']} | {t['demo_groups']} |" for t in rows)
    body='\n\n'.join(task_section(t) for t in rows)
    (ROOT/'docs/os-task-design.md').write_text(intro+index+'\n\n## 逐题规范\n\n'+body)
    # Preserve the Web and embodied parts of the user's local Markdown handbook.
    local=ROOT/'docs/task-design.md'
    if local.exists():
        text=local.read_text()
        text=re.sub(r'OS 使用配套目录的 L1—L4 标签[^\n]*','OS 分为 Easy、Medium、Hard 各 12 题：Easy 批量应用同一方法；Medium 在同一主要应用中完成长程业务，视频方法仅是局部模块；Hard 要求多个桌面应用之间存在必要的内容或状态依赖。Demo 由人录制，清楚呈现同一方法的多次实现。',text)
        lines=text.splitlines();first=next(i for i,l in enumerate(lines) if l.startswith('| OS |'));last=max(i for i,l in enumerate(lines) if l.startswith('| OS |'))
        lines[first:last+1]=[f"| OS | [{t['id']}](#task-{t['id']}) | {t['title']} | {t['app']} | {t['difficulty']} |" for t in rows];text='\n'.join(lines)+'\n'
        start=text.rfind('<a id=',0,text.index('### OS-'))
        if start<0:start=text.index('### OS-')
        end=text.rfind('<a id=',0,text.index('### F01'))
        if end<start:end=text.index('### F01')
        text=text[:start]+'\n\n'.join(f'<a id="task-{t["id"]}"></a>\n\n'+task_section(t) for t in rows)+'\n\n'+text[end:]
        text=text.replace('OS-ICL cases.py 配套任务定义','OS-ICL tasks36.py / judge36.py 与 tasks/os/catalog.json')
        local.write_text(text)
    catalog_path=ROOT/'docs/task-design-catalog.json'
    book=json.loads(catalog_path.read_text())
    by_id={t['id']:t for t in rows}
    for item in book:
        if item['kind']!='os':continue
        t=by_id[item['id']]
        item.update(title=t['title'],platform='OS-ICL / '+t['app'],difficulty=t['difficulty'],
                    type=t['difficulty_reason'],relation=t['relation'],demo=t['demo_description'],rules=t['rules'],
                    inference=t['inference_description']+'\n公共交付约束与实例范围：'+t['query_example'],delivery=t['evaluation'])
    catalog_path.write_text(json.dumps(book,ensure_ascii=False,indent=2)+'\n')
    print('Wrote docs/os-task-design.md (36 tasks)')
