#!/usr/bin/env python3
"""Generate the author inventory from the current catalog, including metric props."""
import json
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
tasks=json.loads((repo/'simulator/benchmark/tasks.json').read_text())['tasks']
lines=['# 50题桌面作者清单','','全部为非厨房桌面改编题，RoboTwin / RoboCasa 各25个设计来源。运行平台为 robosuite 双 Panda。来源名称保留上游原名；本套件道具、任务名和目标以本表为准。','','作者材料：目标、尺寸图和成功录像不可额外提供给 demo-only agent。所有非抬举题终态须经真实接触链支撑在桌面，不能把盒子勾在空中算成功。','','尺寸为完整 X×Y×Z，单位毫米；圆柱／圆形底座的 X 为直径。开口容器壁厚与底板均8毫米。A布局图标出初态；姿态题的卧放方向见 tasks.json。','','| ID | 桌面任务 | 来源 | 判分关系 | 主要道具尺寸 | A布局 |','| --- | --- | --- | --- | --- | --- |']
for t in tasks:
 source=t['source'];props='；'.join(o['display_name']+' '+'×'.join(str(round(v*2000)) for v in o['size']) for o in t['objects'])
 lines.append(f'| {t["id"]} v{t["task_revision"]} | {t["title"]} | [{source["project"]}/{source["task"]}]({source["url"]}) | '+', '.join(g['type'] for g in t['goals'])+f' | {props} | [比例图](filming/{t["id"]}-A.svg) |')
(repo/'simulator/benchmark/TASKS.md').write_text('\n'.join(lines)+'\n')
