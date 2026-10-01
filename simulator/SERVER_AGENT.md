# Hosted VLM operator：服务器部署

按当前选择，本项目实现 **Hosted HTTP operator**。模型通过视觉观察输出基础动作 token，运行器调用 `/api/step`；不依赖浏览器扩展，也不声称是 Computer Use 点击。右侧显示模型实际输入、公开动作说明、执行反馈和运行控制。

## 启动（Linux NVIDIA 服务器）

```bash
cd simulator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export MUJOCO_GL=egl
# 使用支持图片输入的 Chat Completions 兼容服务；不自动选择模型/提供商。
export VLM_BASE_URL=https://YOUR_PROVIDER/v1
export VLM_MODEL=YOUR_VISION_MODEL
read -rsp 'VLM API key: ' VLM_API_KEY; export VLM_API_KEY; echo
python run_hosted.py --variant C --seed 31 --environment-port 18631 --port 18632
```

API key 只在运行器环境内，不能填写到网页、提交到 Git 或发送给仿真进程。自托管无鉴权的兼容服务可设占位 key。没有配置时面板仍可查看仿真，但 Run/Step once 禁用；不会虚构模型运行记录。仅实现 `/chat/completions` 图片消息协议，并非所有厂商 API 的通用适配器。

本地建立同端口隧道：

```bash
ssh -N -L 127.0.0.1:18632:127.0.0.1:18632 ubuntu-descfly
```

访问 http://127.0.0.1:18632/ 。不需要服务器安装浏览器或桌面环境。MuJoCo 使用 EGL，页面在本地浏览器渲染。两项服务均只绑定 localhost，不是开放公网的多用户产品。生产域名接入需要额外的 HTTPS、身份认证和明确 Origin 配置，不要直接暴露端口。

已有独立仿真服务时也可只运行：

```bash
python hosted/hosted_operator.py --target-url http://127.0.0.1:18631 --port 18632
```

`run_hosted.py` 监督两个子进程，任一退出则清理另一项；SIGINT/SIGTERM 同样清理。需要常驻可由 systemd 管理这条命令，密钥通过权限受限的 EnvironmentFile 注入。每次启动创建新 episode；Stop 后重新启动运行器才能再次调用模型，新的正式评测须同时重启环境。

## 模型究竟读到什么

每次调用包含固定 `hosted/prompt.txt`、12 张按时间排序的 demo JPEG、四路同一动作边界的当前图片、状态/步数/预算/夹爪开合命令，以及最近 8 次有效决策和执行反馈。演示目前是**脚本生成的仿真机器人**，并非真实人手；目前输入是 **12 帧采样**，不是原视频全帧。面板原视频供人检查，模型收到的图片另行展示。

模型不读网页 DOM、源码、文件系统、TCP、物体位姿、抓取成功真值、规则文字、A/B/C 版本、demo 元数据或判分结果。运行器通过独立白名单组装请求，提交结果保存在环境私有目录。相对移动步长是动作参数，不是当前世界坐标。GRASP 只闭合夹爪，不自动找物体。

每轮只允许一对同时执行的左右臂 token，步长 5/10/20 mm；旋转目前只有绕竖直轴 10°。模型必须自己根据图像对齐和调整。返回 JSON 经过严格字段、token、类型及范围校验；无代码执行、对象级技能、额外工具或任意 URL 请求。

`/api/observe` 在仿真主线程排队，返回动作结束后的同步图片和不透明观察标识；执行时用该标识防止人工操作或环境变化后执行旧决策。标识不发送给模型。

## 控制与记录

- **Run**：持续观察 → 调用模型 → 验证 → 执行 → 再观察。
- **Step once**：一轮。首次运行会自动 START 环境。
- **Pause**：阻止新动作，丢弃尚未执行的模型回复；不能撤销已经下发的动作。
- **Stop**：终止该运行器。环境保持当前状态，不自动宣布完成。
- 模型 `finish=true`：提交环境，锁定 episode，私有判分；前端不展示成功真值。

请求超时、非法回复、预算耗尽、过期观察都会停止继续执行；模型请求不自动重试。检查后可在预算允许时手动 Run。模型调用预算与物理动作预算独立。右侧 summary 是模型公开的简短动作说明，不是内部思维链。

`hosted/runs/<id>/` 保存固定 prompt、逐次完整请求（含实际图片）以及决策/执行事件 JSONL；不会保存 key 或提供商的 reasoning_content。失败响应不保存原文，防止提供商回显凭据。环境在 `embodied_icl/private_runs/` 保存私有物理状态、评分及相机执行视频。两个目录均 gitignore。部署包有源码和作者 demo 元数据，正式参测模型只能获得运行器规定输入，不能拥有服务器 shell。

## 验证与边界

```bash
python hosted/test_operator.py
python simulation_b01/build_scene.py
python embodied_icl/test_contract.py
```

协议测试使用假模型验证 16 张图片输入、隐藏字段过滤、非法动作拒绝、暂停取消、观察过期、提交、错误不重试和调用预算。假模型测试**不是 ICL 成绩**。必须配置有效视觉模型，再用 Run 获得独立 Agent 的真实轨迹与私有评分，才能评估模型成功率。历史开发者操作和脚本 demo 均不能算盲测成绩。

## 上游依据

Show-Harness 同时有浏览器扩展控制和 Hosted HTTP 模式。这里采用后者的观察→决策→动作思路，代码为本项目适配实现；不复制上游状态中的 `ee_pos`、`holding`、`picked`、`placed`、`task_done`、`can_stop`。截图里的 Claude 扩展侧栏无需复刻，提供我们自己的监督面板。

- [Show-Harness GUMI](https://github.com/showlab/Show-Harness/blob/main/gumi/README.md)
- [Hosted operator](https://github.com/showlab/Show-Harness/blob/main/gumi/gpt_operator/operator.py)
- [上游监督面板](https://github.com/showlab/Show-Harness/blob/main/gumi/gpt_operator/static/index.html)
- [图片输入协议](https://developers.openai.com/api/docs/guides/images-vision)
