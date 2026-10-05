# 部署与复验

以下从 `VideoICLBench/simulator` 执行。Python 环境和素材只给可信作者／运行器，参测 Agent 不拥有服务器 shell。

## 桌面 MuJoCo

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python simulation_b01/build_scene.py
.venv/bin/python embodied_icl/test_contract.py
.venv/bin/python hosted/test_operator.py
# Linux GPU: export MUJOCO_GL=egl
# AgentLab CPU: export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
.venv/bin/python launch.py --backend mujoco-stack --mode gui --variant C --seed 31 --port 18641
```

双臂 Hosted（另一个 episode，勿与上面占用相同端口的实例同时启动）：

```bash
.venv/bin/python launch.py --backend mujoco-stack --mode hosted --variant C --seed 31 --environment-port 18641 --port 18642
```

兼容视觉 API 配置 `VLM_BASE_URL`、`VLM_MODEL`、`VLM_API_KEY`，通过进程环境或权限 600 的 systemd EnvironmentFile 注入。代码不默认选择供应商；无配置可以看网页，不能运行模型。不要将 key 写入命令行、Git 或截图。完整服务配置见 [SERVER_AGENT](../SERVER_AGENT.md)。

## RoboCasa GPU（已配置资产的服务器）

先从独立资源包复制 `simulator/backends/robocasa/media/`，或通过 `--media-dir` 指定同结构目录（两个 MP4 与两组各 16 张帧）。这些资源不在 GitHub 代码分支中。

依赖：Python 3.10.20，RoboCasa v0.2，robosuite 1.5.1，MuJoCo 3.2.6，NumPy 1.23.5；其他包见后端 requirements。既有解释器无需再次 pip 安装。`microwave.hdf5`、RoboCasa 资产不入 Git。

```bash
export MUJOCO_GL=egl
RC_PY=/home/descfly/VideoICL/robocasa-0.2/.venv/bin/python
RC_DATA=/home/descfly/VideoICL/robocasa_asset_archives/microwave.hdf5
"$RC_PY" launch.py --backend robocasa-mug --mode gui --dataset "$RC_DATA" --demo-kind human --port 18761
```

另一个终端，可选 Hosted 面板：

```bash
"$RC_PY" launch.py --backend robocasa-mug --mode hosted --target-url http://127.0.0.1:18761 --port 18763
```

两个终端需分别设置 `RC_PY`。`--demo-kind sim` 切换仿真 demo；每次评测重启独立进程，不能在旧 episode 继续测另一条件。`--run-root` 可设输出目录；不指定时使用 `backends/robocasa/private_runs/<随机id>`。`--run-label` 必须新目录名，拒绝覆盖结果。`--replay` 仅供工程检查，绝不计为 Agent 成绩。

若资产树在其他位置，设 `ROBOCASA_ASSET_ROOT=/absolute/robocasa/models/assets`。其余 fixture 引用仍需有效 RoboCasa 资产安装；不能仅复制 mug XML。无现成环境时先安装上游固定 [v0.2](https://github.com/robocasa/robocasa/tree/v0.2)，安装本包后端依赖并补齐上游资产。历史使用 haosulab/RoboCasa 旧资源包补齐网格／纹理，再恢复 v0.2 源码自带 XML；没有把 SAPIEN 改写设备 XML 直接当作 MuJoCo 模型。完整资产锁定验收仍是待办，外部来源与 hdf5 哈希见 `external_assets.json`。

## 浏览器录制与 GUI 驱动

Linux 浏览器机安装 Xvfb、Chromium、ffmpeg、中文字体；Python 安装 `harness/requirements.txt`。浏览器与 GPU 不同机时，先配置到 GPU localhost 服务的 SSH 转发。不得公开无鉴权端口。

```bash
python record_browser.py --url http://127.0.0.1:18761/ --output recordings/new_trial.mp4 --duration 0 --display 111 --cdp-port 18759
```

录制器启动真正有头 Chromium，默认 1600×1200，包含地址栏和整页可见区域。GUI 模式在**这同一窗口**上操作：

```bash
printf '%s' '{"op":"observe"}' | python harness/gui_driver.py --cdp-port 18759 --page-url http://127.0.0.1:18761/ --audit-log recordings/gui.jsonl
```

可信模型 runner 读取输出 image 的 base64 JPEG，模型给 `{op:act, token:MV_UP, count:1, step:0.01}` 等受限指令后调用同一工具。允许 observe/start/act/finish；不允许任意 JS、路径、场景查询。示例仅演示调用格式，不是任务行动答案。`finish` 通过 GUI 点击提交；私有评分不返回。截图超时可能发生在动作完成之后，必须 observe 后再决策，不能盲目重试。

Ctrl-C 停止录制器；等出现 SAVED 后再复制 MP4。Hosted 模式录制实际面板响应，不伪造鼠标点击。已有 Codex 盲测用平台原生独立 subagent；仓库不包含 Codex 账号凭据，不能把该账号当成可移交 API 服务。

## 本包测试

```bash
python hosted/test_operator.py
python backends/robocasa/hosted/test_operator.py
python handoff/verify_package.py
```

前两项为假模型的接口测试，不计作模型任务成功。新的物理部署验收和结果见 `deployment.json`。需分别报告服务器环境、实际模型输入帧数、动作预算、超时策略和录像范围。
