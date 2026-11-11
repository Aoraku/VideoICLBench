# VideoICL 具身仿真与评测

## 从这里开始

| 要做的事 | 入口 |
| --- | --- |
| 接手最新实验，了解配置、数据格式与复现步骤 | [具身评测交接](HANDOFF.md) |
| 下载题目、QA 和实际输入视频 | [HF Benchmark](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Demos50) |
| 下载六个模型的原生终态、逐步动作和观察回放 | [HF 评测轨迹](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Evaluation-Trajectories-Public) |
| 安装新版同池并发 Harness | [异步多房间 Harness](harness/coalesced/README.md) |
| 下载 Astra 和 Opus 当次实验的完整归档 | [GitHub Release 与恢复说明](trajectories/astra-opus-20261107/README.md) |

HF Benchmark 提供评测输入。HF 评测轨迹用于分析结果。GitHub Release 保留 Astra 和 Opus 的完整归档。

## 代码目录

| 目录 | 内容 |
| --- | --- |
| [harness/](harness/README.md) | 当前同池并发 Harness，以及历史 Codex 和 GUI 入口导航。 |
| [astra-iclworld-20261106/](astra-iclworld-20261106/README.md) | Astra 的固定实验配置、运行时装配、任务准备和独立 QA。 |
| [native-codex-20261106/](native-codex-20261106/README.md) | Astra 归档对应的原生 Codex SDK 与 GUI 协议。 |
| [trajectories/](trajectories/README.md) | HF 轨迹字段和归档下载入口。 |
| [handoff/](handoff/HANDOFF.md) | 早期原型交接记录。当前交接从 [HANDOFF.md](HANDOFF.md) 进入。 |

## 使用最新统一 Harness 运行 IsaacLab 实验

1. 从 [统一 Harness](harness/coalesced/README.md) 安装依赖，准备匹配的 IsaacLab/IsaacSim 与原生 CLI。
2. 从 [数据交接](HANDOFF.md) 下载固定题目、输入与资产，核对 R/I/E、A/B/C、seed 和输入条件。
3. 全部模型使用 `harness/coalesced/pool_verified.py`，通过 `--engine`、`--model` 和 CLI/provider 参数选择模型。默认短窗口并发调度，各房间独立请求模型。

`native-codex-20261106/` 等目录保留历史实验版本；历史轨迹的原始设置保持不变。新评测统一使用上述入口。

## 历史 MuJoCo 套件

| 目录或入口 | 内容 |
| --- | --- |
| [`tabletop50/`](tabletop50/README.md) | 50 个桌面任务族，含录像、实现进度和部署说明。[视频索引](tabletop50/VIDEOS.md) |
| [`delivery8/`](delivery8/README.md) | 八题 HTTP agent、控制面板和 24 段 A/B/C 演示。[任务列表](delivery8/TASKS.md) |
| [`benchmark/`](benchmark/README.md) | 早期 robosuite 改编任务，使用 `rt/rc` 编号。 |
| [`embodied_icl/`](embodied_icl/README.md) 与 [`simulation_b01/`](simulation_b01/) | 双 Panda 桌面 GUI 原型、场景生成和 Panda 资源。 |
| [`run_hosted.py`](run_hosted.py) 与 [`launch.py`](launch.py) | 历史 Hosted VLM 入口。网页显示仿真画面与运行面板，模型走视觉 Chat Completions 接口。[服务器说明](SERVER_AGENT.md) |
| [`backends/robocasa/`](backends/robocasa/) 与 [`handoff/`](handoff/HANDOFF.md) | 微波炉单题后端与 10 月原型交接记录。 |

### 启动双 Panda GUI 原型

从仓库根目录执行，需要 Python 3.11+。

```bash
cd simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py --variant C --seed 31 --port 18621
```

打开 <http://127.0.0.1:18621/>。启动器会重建场景，使用本机资源路径。无显示器 Linux 可配置 EGL。本原型可以在 CPU 上运行。

在 `simulator/` 内可执行以下验证。

```bash
python simulation_b01/build_scene.py
python embodied_icl/test_contract.py
```

GUI 提供相机、操作说明、步长、夹爪命令、执行状态和动作计数。SUBMIT 后锁定当前回合，判分写入 `embodied_icl/private_runs/<episode>/`。正式运行时应在服务端隔离任务变体、物理真值和判分目录，只给参测模型公开的 GUI 或动作接口。[操作与判分协议](embodied_icl/README.md)

浏览器录屏由标签页导出 WebM。后端生成的 `execution.mp4` 记录仿真相机画面。示范重录属于作者侧操作，命令和保存位置见协议说明。
