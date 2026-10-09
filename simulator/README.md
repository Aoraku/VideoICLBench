> 当前新版：**[桌面双臂50任务](tabletop50/README.md)** · **[全部视频索引](tabletop50/VIDEOS.md)** · **[部署与网页查看](tabletop50/DEPLOY.md)**。
>
> 50族设计，50族运行配方（F42/F43/F46为未验收原型），99段合格历史视频、33族完整A/B/C；尚未完成全部150条件。新版源码、运行工具、视频与测试全部放在本 `simulator/` 目录，部署不依赖仓库其他目录。下文为保留的旧GUI原型。

# VideoICL 桌面双臂仿真模拟器

Show-Harness / GUMI 风格的 GUI 控制原型，使用真正的 MuJoCo 接触物理和双 Panda 机械臂。Agent 看演示和四路相机，通过移动、旋转、夹爪开合按钮排队，再点击 COMMIT。底层实现 IK 和关节控制，不自动选择或对齐物体。

## Hosted VLM operator（服务器）

已增加左侧仿真画面 + 右侧模型运行面板。使用 `python run_hosted.py` 启动；模型通过图片与 HTTP 基础动作交互，不需要浏览器扩展。部署、模型配置、输入边界与 Run/Pause/Step once/Stop 见 [服务器说明](SERVER_AGENT.md)。当前仅支持视觉 Chat Completions 兼容接口。

## 原 GUI 启动

在仓库根目录执行（Python 3.11+；依赖版本见 requirements.txt）：

```bash
cd simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py --variant C --seed 31 --port 18621
```

打开 http://127.0.0.1:18621/ 。`run.py` 每次根据当前目录重新生成场景，避免迁移后仍引用原机器的资源路径。默认仅监听本机；参数见 `python embodied_icl/server.py --help`。macOS 使用本地图形环境；无显示器 Linux 需配置可用的 EGL（例如 `MUJOCO_GL=egl`）。不需要 GPU 才能运行本地原型。

## 内容与复现

- `embodied_icl/`：GUI 服务、物理动作适配、私有判分、前端和 A/B/C demo。
- `simulation_b01/`：双臂场景生成、基础控制与 Panda 资源。
- 已附 A/B/C 演示 MP4 和每段 12 张时间采样图；这些是脚本驱动的仿真机器人演示，不是真人手部 demo。
- 已附约 33 MB Panda 模型资源及上游 LICENSE、下载清单；来自 Google DeepMind MuJoCo Menagerie，遵循所附 Apache-2.0 许可。
- 不包含开发虚拟环境、历史私有运行日志和网页验收录屏。

基础验证：

```bash
python simulation_b01/build_scene.py
python embodied_icl/test_contract.py
```

如需重新生成演示，先备份并移走需要重生成的 `embodied_icl/demos/<版本>/demo.mp4`，再运行 `python embodied_icl/make_demos.py`。已有视频会保留，抽帧会重新生成。此步骤是作者侧工作，不提供给参测 Agent。

## 观察边界与限制

网页公开相机图像、通用操作说明、步长、夹爪开合命令、执行状态和动作计数，不提供 TCP 或物体世界坐标。夹爪开合命令不等于抓取成功真值。内部控制和判分仍需要仿真真值。SUBMIT 后锁定当前局，判分写入 `embodied_icl/private_runs/<episode>/`。

正式评测必须将源码、demo 元数据、任务版本和 private_runs 隔离在 Agent 无权访问的服务端；仅开放规定的图片与动作接口或 GUI。本目录本身是开发者包，不构成权限隔离沙箱。已有开发者成功操作不能当作独立盲测 ICL 成绩。当前旋转仅 yaw，位置分布有限，demo 是仿真输入；详细动作语义和限制见 [协议说明](embodied_icl/README.md)。

“开始网页录屏”使用浏览器标签页录制，需要选择当前网页并授权。停止后下载 WebM；录制保存在浏览器内存中，刷新或关闭前应停止并保存。后端自动生成的 `execution.mp4` 仅含仿真相机画面，不是网页录屏。
