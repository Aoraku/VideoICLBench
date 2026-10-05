# 具身 VideoICL 交接（2026-10-06）

交接对象：AgentLab 评测框架维护者。代码入口为本仓库 `simulator/`。这是**现有可运行原型、素材和实验记录的交接包**，不是 50 题全部完成或所有平台全部接入的声明。

## 交付状态先看这里

| 项目 | 实际状态 | 接手入口 |
|---|---|---|
| 自建 MuJoCo 双 Panda 桌面 | 已实现；不是 RoboTwin | `../run.py`、`../embodied_icl/` |
| RoboCasa v0.2 杯子／微波炉 | 已实现；单臂 PandaOmron | `../backends/robocasa/` |
| RoboTwin、ManiSkill、RLBench | 尚未实现本项目适配；无可交付运行证据 | `catalog.json` 中明确标为未接入 |
| Hosted HTTP VLM | 两后端都有图像输入、动作白名单、运行面板 | `../launch.py --mode hosted` |
| GUI Agent | 截图与实际按钮点击；可复用现有浏览器 Agent | `../harness/gui_driver.py` |
| 真人第一人称素材 | EPIC-KITCHENS 的真实人手；已有配对杯子素材 | `../backends/robocasa/media/human_demo.mp4` |
| 真实机器人／真机实测 | 没有；不能把人手或仿真录像称为真机结果 | 待采集 |
| 50 题 | 设计稿，非 50 个可运行环境 | `design/` |

会议纪要中的“三类 MuJoCo 环境已搭建”不能作为验收证据。目前代码与运行记录仅支持上表的两种后端。后续每接一个平台，需有 reset → observe → action → submit → 私有判分 → 整窗录像的验收链。

## 难度、素材和评测矩阵

难度是暂定标签，应分别记录规则推断复杂度与控制复杂度，不能按按钮次数直接宣称 ICL 更难。

| 层级 | 案例／规则 | 演示 | 判分与证据 | 尚缺 |
|---|---|---|---|---|
| 低规则复杂度，操作不止一步 | 三色积木 A/B/C 不同层序；演示推断底到顶颜色 | `../embodied_icl/demos/{A,B,C}/demo.mp4` | 接触、层高、对齐、垫内、直立、稳定、机器人撤离；独立 GUI Agent 单次 219 步成功 | 真人对应 A/B/C；更多布局与种子；按会议“同对象多次操作”口径也可标中等，不能称单步任务 |
| 中等（待实现） | 同物体按演示连续翻转／放入，最终布局相同但过程规则不同 | 尚无独立配对素材 | 需事件顺序判分；设计库可作为选题起点 | 环境、两域演示、判分与实测均未交付，不计入已完成题数 |
| 高操作复杂度／规则复杂度尚低 | 开微波炉→杯子入炉→关门→启动 | 人手 10.1 秒；仿真 38.25 秒，见下方 | 工程控制成功；人手 demo Agent 0/1，仿真 demo Agent 0/1 | 自定义 A/B/C、跨初态、过程判分、多次试验 |

微波炉的高层操作目标匹配，但真人是下翻门、仿真是侧开门，液体与加热未建模，不能宣称物理机制完全相同。自然行为视频也不自动证明存在充分可辨识的“自定义规则”。因此**尚未满足每档真人／真机与仿真各 1–2 条的完整收集目标**；本包是可承接基线及缺口清单。

## 视频与实际结果

以下视频、逐步日志和作者标注仅随独立本地／服务器资源包提供，**不在 GitHub 代码分支中**。下列相对路径是资源包内路径；只 clone 代码时需另外取得资源包。

- [真人杯子 demo](../backends/robocasa/media/human_demo.mp4)：输入素材，真实第一人称人手。
- [仿真杯子 demo](../backends/robocasa/media/sim_demo.mp4)：输入素材，录制控制轨迹驱动的物理仿真。
- [工程验证整窗录像](evidence/mug_engineering_full_browser.mp4)：763 步成功，`agent_run=false`，不是 VLM 成绩。
- [人手 demo 条件 Agent 整窗录像](evidence/trial_a_full_browser.mp4)：245 基础动作，失败。
- [仿真 demo 条件 Agent 整窗录像](evidence/trial_b_full_browser.mp4)：305 基础动作，失败。
- [积木历史执行回顾](evidence/stack_agent_review.mp4)：历史证据，不能冒充本次的完整浏览器录屏；配套 [私有判分摘要](evidence/stack_result.json)。
- [本次实验记录](evaluation.json)：两次独立上下文 Codex Agent，gpt-6-astra；每段 demo 均匀抽 16 帧含首尾。没有给文字任务答案、TCP 或物体世界坐标。输入／工具审计未发现违规读取；不是操作系统级隔离。

这些是 **1 次试验／条件**，只报原始计数 1/1、0/1、0/1，不宣称总体正确率。积木与微波炉协议不同，不应合并平均。微波炉预先完成控制器校准，旧失败预检排除；正式运行中有截图超时，未重发不确定动作。为及时交付，两条件同时追加剩余 8 分钟收尾时限，未耗尽原 120 次提交／1000 基础动作上限。

正式接手应复验：明确规则诊断、demo-only、无 demo、错误 demo，在相同种子与预算下运行；模型只收到正式条件规定的内容。每次创建新 Agent 上下文和新环境实例。

## 启动与服务器

详细命令见 [RUNBOOK](RUNBOOK.md)。所有命令从 `simulator/` 执行。两套物理依赖使用独立虚拟环境，不要混装 NumPy／MuJoCo 版本。

- 桌面环境：AgentLab 的原部署 `/home/qingle/services/videoicl-simulator`，18641 环境、18642 Hosted；保留不覆盖。
- GPU 环境：ubuntu-descfly 的既有 RoboCasa 环境 `/home/descfly/VideoICL/robocasa-0.2/.venv/bin/python`。本包可用该解释器启动，需原 1.4GB `microwave.hdf5` 及资产树。
- SSH 别名／账号由接手人自己的 SSH 配置解析。仓库不含密码、API key、账号 token 或会议内部附件。
- 本包由新分支发布，不自动合并主分支；检查 GitHub 分支与 commit 后再接入任务调度。部署目录／验收信息见 `deployment.json`。

## Harness 接口及 AgentLab 对接

| 操作 | 环境接口 | 谁调用 |
|---|---|---|
| 初始化 | 启动独立进程，每次创建新私有运行目录 | 调度器 |
| 观察 | POST `/api/observe`，返回 RGB、白名单状态、opaque/revision observation_id | Hosted 运行器；GUI Agent 用网页截图 |
| 开始 | POST `/api/start` | Hosted 运行器或 GUI 的 START |
| 动作 | POST `/api/step`；left/right token 列表、step_m、expected_observation | Hosted；GUI 通过按钮排队及 COMMIT |
| 提交 | POST `/api/stop` | Hosted finish 或 GUI SUBMIT |
| 判分 | 读取服务端私有 `result.json` | 仅评测器；不返给 Agent |

两种 track 分开记：**Hosted HTTP** 输出 token 后调用动作 API；**GUI** 驱动浏览器实际点击。不可把前者描述成 Computer Use。右侧 Hosted 面板展示模型公开短说明，不是内部思维链。已有按钮前端保留；无需浏览器扩展。

桌面后端支持双臂与 yaw；RoboCasa 当前只有右臂，left 必须 STILL，支持 yaw/roll/pitch。相对步长 5/10/20mm，GRASP 只闭合夹爪；不存在选对象、自动对齐或 pick-and-place。`harness/gui_driver.py` 当前针对单右臂页面，不是所有桌面双臂动作的完整 runner。

GUI CDP 驱动只读按钮位置／公开反馈并截图，但 CDP 连接本身权限很大：它必须由可信运行器持有，模型只能发有界动作请求。开发者仓库、manifest、源代码、作者标注与评测目录均含任务答案，**不能挂到 Agent 的文件系统或提供目录遍历**。public URL 不含任务名／版本；模型 prompt 不注入本文件内容。

已有 AgentLab 部署是独立服务，并未实现原工作台任务列表与评分调度注册。接手需要：进程隔离／端口分配、模型调用包装、任务资产映射、私有评分收集、超时取消和 artifact 上传。用 `catalog.json` 做作者侧任务发现，不将 catalog 送给模型。

## 验收与移交顺序

1. 校验 `sha256.json` 和 `deployment.json`；素材来源与权限见 [THIRD_PARTY](THIRD_PARTY.md)。
2. 运行两组 Hosted 协议测试；在目标机器完成物理契约／RoboCasa冒烟验收。
3. 只开放白名单观察／动作能力；确认截图和 prompt 没有文字答案或真值。
4. 录制**实际 Agent 操作的整个浏览器窗口**，含地址栏、所有可见按钮与面板；相机视频不是替代品。
5. 新上下文运行，提交后由调度器读私有判分。超时动作先观察，不能自动重试。
6. 收集每种难度缺失的真人／真机素材与 A/B/C 对照后再进入正式榜单。失败记录保留。

RoboCasa 干净机器的全资产下载安装尚未验收：本次验收复用了既有 GPU 资产环境。不要把“代码能迁移”写成“任意空服务器一键复现成功”。
