#!/usr/bin/env python3
"""Generate the human recording checklist from the private author catalog."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from simulator.tabletop50.families import FAMILIES, REVISION

lines = ["# 第一人称友好的桌面双臂50任务", "", f"版本：`{REVISION}`。2026-10-09。", "",
         "这是50个候选任务族、150个视频规则条件。文档存在不代表仿真已通过或视频已录好；逐题状态以验收清单为准。真人视频尚未录制，道具易得与可录性是设计判断，仍需实物试录。", "",
         "## 统一要求", "",
         "- 普通桌面、坐姿、头戴或胸前相机；所有目标与操作区域须同时入镜。",
         "- 用大件、浅盒、开放支架、宽松接口；不使用锅具、液体、细绳、小螺丝、精密齿轮、强力卡扣。",
         "- A/B/C共享道具、可见初态、公共委托、权限和预算；视频教授规则，三版终态互斥。",
         "- 示范与执行用不同布局和实例；固定颜色选择只作为简单基线。关系规则需要足够示例排除竞争解释。",
         "- 主指标是成功率。物理接触、释放、稳定支撑是完成条件，不是动作细节积分。",
         "- 双臂平台不意味着每题都必须同时用两手；允许其他正确动作路径。F47单独明确包含空中交接事件。",
         "- 本套有共享技能，不宣称50种独立操作。新增族必须有不同的规则学习内容、约束或工作目标；只换颜色和道具不计新族。",
         "- 容量、通道、锁闭等约束必须真实存在；不可仅用文字禁止桌面暂存、越障或合法解法。",
         "- 仿真示范是有状态权限的作者控制器记录，不是独立agent成绩，也不是已录真人视频。", "",
         "## 道具包", "",
         "优先共用：大积木与长条、圆柱、厚塑料片、两三个浅盒和松盖、杯垫、托盘、箭头和图形贴纸。扩展包：儿童形状盒、木环短柱、宽槽架、粗杆与L形钩、宽铲、桌刷、大木珠、玩具级插销和宽松套筒。没有采购链接与价格承诺。", "",
         "## 50族总表", "",
         "| ID | 任务 | 分组 | 需要理解或规划的内容 |", "| --- | --- | --- | --- |"]
for f in FAMILIES:
    lines.append(f'| {f["id"]} | {f["title"]} | {f["group"]} | {f["challenge"]} |')
lines += ["", "## 逐题录制卡", ""]
for f in FAMILIES:
    lines += [f'### {f["id"]} {f["title"]}', "", f'- 道具：{f["props"]}。',
              f'- 操作难点：{f["challenge"]}。',
              *[f'- 视频{k}：{v}。' for k, v in f["rules"].items()],
              f'- 第一人称摆台：{f["camera_note"]}。', f'- 复位：{f["reset"]}。',
              f'- 初始实现状态：`{f["status"]}`；真人录制：`{f["human_recording_status"]}`。', ""]
lines += ["## 录制验收", "", "每段连续拍摄，无剪辑、规则字幕或私有目标叠字。开始时完整展示初态，结束时双手撤开展示终态。顶面标记不要被夹持点遮住。模拟第一人称视角只能检查构图，不代替实物试录。", "",
          "仿真验收至少检查：同seed三版初态一致、三版终态互斥、未执行初态不成功、作者通过合法控制动作完成、视频覆盖完整执行和成功终态、示范与执行实例分离。插孔另检查真实孔壁、错误件不能穿入、悬空和穿模不能通过。", ""]
(ROOT/"simulator/tabletop50/TASKS_50.md").write_text("\n".join(lines))
(ROOT/"simulator/tabletop50/families.json").write_text(json.dumps(dict(revision=REVISION, family_count=50, condition_count=150, families=FAMILIES), ensure_ascii=False, indent=2)+"\n")
