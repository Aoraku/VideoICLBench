# VideoICL Embodied 50

50 个可编译到 **robosuite 1.5.1 双 Panda 桌面环境**的改编任务：RoboTwin 25 题、RoboCasa v0.2 25 题。MuJoCo 3.2.6 是物理引擎，机器人、夹爪和 OSC 控制器来自 robosuite；这不是裸 MuJoCo 控制器项目，也不是原平台官方 benchmark 的复现。

所有任务的具体来源、固定上游 commit、物体、目标区域、私有成功条件、拍摄指引均在 [tasks.json](tasks.json)。完整题目表见 [TASKS.md](TASKS.md)。每题有 A/B/C 三种布局，共 150 个任务／布局组合。A 为示范布局，B 左右镜像、C 前后镜像；seed 在初始物体布局上施加 ±4 mm 共同平移，保留容器内初始关系。它们不是额外计数的任务。

**实现与验收状态分开记录：**场景、动作、相机、私有判分、GUI、runner 已实现；人手／仿真示范均需要外部采集；50 题还没有逐题独立 agent 成功率或全部可解性验收。`verify` 检查真实物理加载与未完成场景不能成功，不代表 agent 解题。`probe` 是作者写的固定动作夹杯工程检查，不是 agent 结果。

## 任务适配边界

- 全部桌面、两台固定 Panda。4 题通过交接／同时夹持规则强制双臂协作；其余题提供双臂操作，但可能单臂可完成。不要把所有题称作“强制双臂任务”。
- RoboTwin 提供叠放、交接、双臂抬举、摆放与姿态设计；RoboCasa 提供整理、备餐、容器转移与物体关系。每题明确被删去的原平台阶段。
- 用彩色物理代理道具统一视觉和可制作性：方形开口杯／碗／篮、瓶、长条、块、圆盘、手机片。开口容器有真实底板和四壁；没有把实心方块当容器。物体语义由人手示范建立，不依赖逼真食物材质。
- 厨房导航、抽屉门、液体、加热、电子秤等没有移植。既有“夹杯放入微波炉”实验仍在 `simulator/backends/robocasa`，原始结果保存在 handoff；新 `rt12` 仅为桌面夹杯摆放，不能替换或混用其分数。
- 这是 **VideoICL 改编套件**。上游给出任务设计来源；执行后端单列为 robosuite，不冒称原生 RoboTwin 或原生 RoboCasa 的结果。

## 本地运行

Python 3.11。Linux CPU 离屏渲染需要系统 OSMesa（Debian 包 `libosmesa6`），无需 GPU。

```bash
python3.11 -m venv .local/embodied-env
.local/embodied-env/bin/pip install -r simulator/benchmark/requirements.txt
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa  # 仅 Linux；macOS 不设置这两项
export EMBODIED_DATA="$PWD/.local/embodied50-data"
.local/embodied-env/bin/python -m uvicorn simulator.benchmark.server:app --host 127.0.0.1 --port 18660 --workers 1
```

macOS 离屏渲染需要正常图形上下文；沙盒内可能中止。一个服务只允许一个活动物理世界，模型初始化期间 CPU 会有开销。服务只监听 loopback，经 SSH 转发访问；不要把包含 author 管理接口的进程直接公开。

启动后 author token 位于 `$EMBODIED_DATA/admin.token`，权限 0600。作者创建轮次（此 token 不给 agent）：

```python
from pathlib import Path
import httpx
url = 'http://127.0.0.1:18660'
auth = {'Authorization': 'Bearer ' + Path('.local/embodied50-data/admin.token').read_text().strip()}
r = httpx.post(url + '/admin/sessions', headers=auth, timeout=360,
    json={'task':'rt12', 'variant':'A', 'seed':0, 'condition':'no_demo'})
r.raise_for_status()
print(url + r.json()['actor_url'])
```

打开返回 URL，即可通过三路相机、左右臂按钮和双臂同时执行操作。每次动作推进 0.4 s；移动 2 cm／旋转 10°；夹爪命令保持。提交后不能继续操作。作者用 `GET /admin/results/{session}` 读取最终结果。服务重启会关闭现有轮次；已落盘结果仍可读。

## Actor 与私有 evaluator

Actor 仅持有不可猜的轮次 capability，可使用：

| Endpoint | 内容 |
| --- | --- |
| `GET /actor/{session}/observe` | 三路 RGB JPEG、动作余量、时间余量 |
| `GET /actor/{session}/demo` | 对应实验条件的示范；无任务名称和目标坐标 |
| `POST /actor/{session}/action` | `{"left":"UP","right":"STILL"}` 等白名单动作 |
| `POST /actor/{session}/submit` | 只返回 ended，不返回成功／失败 |
| `/s/{session}` | 同一动作集的可视化操作台 |

Actor 没有 TCP／物体坐标、深度、目标规则、密集奖励、成功标记或 author token。`text` baseline 有显式任务指令，其余条件没有。未知 JSON 字段、非法动作、超额操作被拒绝。达到动作预算仍可提交；超过墙钟预算自动结束且判为失败。每轮 manifest、动作日志、相机帧、worker 日志、最终私有结果分开落盘。

成功要求最终关系全部满足，位置稳定至少 0.5 s；非抬举题必须松开夹爪。叠放需要接触与高度支持，装入需要完整 XY 边界和底部落在容器底板，瓶子倒立不算扶正。交接记录左臂离桌夹持到右臂离桌夹持的历史，桌面中转不算。双臂抬举检查同时夹持，不用“曾经碰过”替代。

这是一条**接口隔离边界**，不是同一 Unix 账号下的恶意代码安全沙箱。正式 agent 只能连接 actor capability 或 GUI，不能给它服务器 shell、仓库／catalog 读取权限、服务数据目录或作者凭证。客户端策略进程和 author orchestrator 应使用不同权限或不同主机。

## 示范采集与条件

支持 `no_demo`、`text`、`human_video`、`human_frames`、`sim_video`、`sim_frames`。完整视频与 16 帧是不同条件，不能自动互换。缺失示范时返回 409，不能悄悄降级到无示范。

按 TASKS.md 准备道具，在 A 布局录完整人手操作（双手在固定斜俯视镜头内；起止静置、无剪辑、无字幕／目标提示）；另录同任务 A 仿真成功操作。作者检查目标满足、相机映射、初终态一致性，之后导入：

```bash
.local/embodied-env/bin/python -m simulator.benchmark.demos rt12 human /absolute/path/cup.mp4 --author-verified
.local/embodied-env/bin/python -m simulator.benchmark.demos rt12 sim /absolute/path/sim-cup.mp4 --author-verified
```

导入脚本转码、提取 16 个均匀时间点帧、记录媒体 SHA256。`--author-verified` 是作者实际审阅后的声明，不会自动证明成功。媒体存在外部数据目录，不进 Git。历史微波炉杯子视频不能自动标成新桌面夹杯示范。一个任务只有导入相应示范后，该条件才可运行。

## Harness

API runner 负责创建轮次、预算、随机种子、示范条件、运行 manifest 和最终私有结果；策略是独立持续 JSON-lines 进程，仅接收相机、示范与动作规则，不接收 task ID 或 evaluator。stdout 每行输出 `{"left":"...","right":"...","submit":false}`；stderr 存日志。不要把 author 输出目录开放给 agent。

```bash
.local/embodied-env/bin/python -m simulator.benchmark.run \
  --admin-token-file .local/embodied50-data/admin.token \
  --task rt12 --variant B --seed 0 --condition human_frames \
  --policy '.local/embodied-env/bin/python -m simulator.benchmark.hosted_policy' \
  --output .local/runs/rt12-B-human-0
```

示例 hosted policy 从环境读取 `POLICY_BASE_URL`、`POLICY_API_KEY`、`POLICY_MODEL`，使用兼容 Chat Completions 的多模态图像协议；没有绑定某一模型。完整视频条件需要策略端原生视频支持，示例图像适配器会明确拒绝。服务不会自行调用模型或产生费用。

GUI-only agent 使用 `gui_driver`：先启动带 CDP 的 Chromium 打开 actor URL，再将 JSON 输入 driver。它只查询可见按钮位置／状态、发送浏览器鼠标键盘事件并截屏，不调用 actor API。例：

```bash
printf '%s' '{"op":"act","left":"GRASP","right":"STILL"}' | \
.local/embodied-env/bin/python -m simulator.benchmark.gui_driver \
  --cdp-port 9222 --page-url http://127.0.0.1:18660/s/SESSION \
  --audit-log .local/gui-actions.jsonl
```

`observe` 截屏，`submit` 点击提交。GUI-only 与 API-image 两种动作界面必须分组报告，不能把控制接口差异算成视频效果。两者单次物理动作、步长、时间推进与预算相同。

## 验证与研究验收

```bash
.local/embodied-env/bin/python -m pytest tests/embodied50 -q
.local/embodied-env/bin/python -m simulator.benchmark.verify --output .local/smoke.json
.local/embodied-env/bin/python -m simulator.benchmark.verify --render --output .local/render-smoke.json
.local/embodied-env/bin/python -m simulator.benchmark.probe
```

`verify` 对 50×3 个真实环境执行 reset、双臂动作、未完成提交判分和有限状态检查；`--render` 另检查三相机。物理正例测试验证真实叠放支持接触；夹杯 probe 验证动作到物理夹取再到终态评估的完整链路。

先做六题 pilot：`rt12` 夹杯、`rt07` 交接、`rt02` 三层塔、`rc10` 锅间转移、`rc22` 瓶子互换、`rc11` 食材分类。每题首先由作者通过同一动作接口完成至少一次，再审定示范，之后用 fresh-context agent 跑匹配 seed／布局。优先比较人手16帧 vs 仿真16帧，并加 no-demo／text 两个基线；全视频另开实验。A 测模仿，B/C 测布局迁移；至少5个 seed、报告成功率与置信区间、动作数、墙钟时间、失败类别。原始手递手／抬举等困难题可能需要修改道具尺寸或规则，必须版本化后重跑。

扩展至50题前逐题确认：真实动作接口可解、初态不满足目标、没有越界／掉桌、失败场景不能过关、示范确实完成目标、可在人桌面复现。当前没有把这些未来验收伪装成已完成实验。

## Agentlab

隔离目录 `/home/qingle/services/videoicl-embodied-50`；服务名 `videoicl-embodied-50.service`，loopback 端口18660，保留现有 simulator 服务与端口。CPU + OSMesa，不依赖 ubuntu-descfly 的 GPU。部署脚本：

```bash
# 在 Agentlab as qingle，仓库已经放到服务目录的 repo/ 下
bash scripts/embodied50/deploy-agentlab.sh
systemctl --user status videoicl-embodied-50.service
journalctl --user -u videoicl-embodied-50.service -n 50
```

首次环境准备需 Python3.11 venv；可用 uv 安装。`requirements-agentlab.lock` 固定经过验收的完整 Linux 依赖。离线包部署可以设置 `PIP_NO_INDEX=1 PIP_FIND_LINKS=/absolute/wheels`。访问：

```bash
ssh -N -L 18660:127.0.0.1:18660 qingle@agentlab
```

Author token 只保留服务器，或通过受控 SSH 读取；不要贴到 GitHub／agent prompt。运行数据默认权限仅用户可读。停止新服务使用 `systemctl --user stop videoicl-embodied-50.service`；不会影响旧服务。

## 来源与许可证

任务设计链接逐题列在 tasks.json；生成代码没有复制上游任务实现或分发上游资源。

- [RoboTwin](https://github.com/RoboTwin-Platform/RoboTwin)：任务设计来源，具体 commit 见 catalog。
- [RoboCasa v0.2](https://github.com/robocasa/robocasa/tree/v0.2)：厨房任务关系来源。
- [robosuite v1.5.1](https://github.com/ARISE-Initiative/robosuite/tree/v1.5.1)：通过依赖安装提供机器人、控制器、桌面和基础对象，遵循其 MIT 许可证。
- [MuJoCo](https://github.com/google-deepmind/mujoco)：通过依赖安装，Apache-2.0。

上游任务来源不意味着本适配套件通过上游官方评测认证。

Agentlab 首次部署额外提供 `rt12` 的作者固定动作仿真示范（58次动作、2.5fps采样；外部数据目录），用于验证媒体导入和流程。它不是独立 agent 成绩，也不能充当人手示范。其他示范仍需逐题采集。
