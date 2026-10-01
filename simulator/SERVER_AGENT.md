# 服务器部署与 Agent 界面路线（2026-10-01）

基线提交：`2c25e7f`。当前目录是 MuJoCo + GUI + 私有判分原型，尚不包含独立模型运行器或右侧 Agent 面板。历史开发者点击验收不能称为独立 demo-only ICL 成绩。

## Show-Harness 实际提供的两条路线

1. **浏览器 Agent**：把 `prompts/web_operator_dual.txt` 交给 Computer Use Agent，由其截图、点击按钮并检查步数。示例里的 Claude 右栏来自 Claude 浏览器扩展，非 GUMI 服务自带聊天侧栏。上游 `gumi/gpt_operator/operator.py` 模块说明明确区分 Claude 扩展点击与 HTTP operator。
2. **Hosted VLM operator**：`gumi/gpt_web_operator.py --target-url http://localhost:8620` 读取状态及相机 JPEG，请模型输出结构化动作，再调用 `/api/step`。8630 端口提供独立监督面板，包含 Run/Pause/Step once、实际输入帧、当前 prompt 和决策事件。这条路径不经过浏览器点击，不应标成 Computer Use。

来源：
- https://github.com/showlab/Show-Harness/blob/main/gumi/README.md
- https://github.com/showlab/Show-Harness/blob/main/prompts/web_operator_dual.txt
- https://github.com/showlab/Show-Harness/blob/main/gumi/gpt_operator/operator.py
- https://github.com/showlab/Show-Harness/blob/main/gumi/gpt_operator/static/index.html

## 本项目应做的改动

正式主模式采用 GUI Computer Use：demo/统一抽帧 + 通用按钮说明 + 当前网页截图，模型输出屏幕点击或按键。运行器不得获得场景坐标、任务版本、源码或判分状态。HTTP token 模式可保留为独立对照，明确记录模式，不混报分数。

左侧为演示和机器人 GUI，右侧为 Agent 运行事件面板。面板展示：运行模式、模型名称、实际输入 demo/抽帧、最近观察、模型公开响应摘要、工具调用、执行反馈、延迟、预算和开始/暂停/单步/停止。不伪造模型思考过程。展示给人的监督面板不纳入 Agent 截图，避免递归观察和额外信息泄漏。

上游 `compact_model_state` 当前白名单含 `ee_pos`、`holding`、`picked`、`placed`、`task_done`、`can_stop`；不应直接复制。我们只允许图片、通用命令/步数反馈，判分结果提交后服务端保存。上游示例 prompt 中 TASK 是文字任务，也必须换为通用 demo-only 指令，不能写入颜色层序。

服务器组件应分开：MuJoCo 进程（EGL/OSMesa）→ 环境 HTTP 服务 → 隔离浏览器与 Agent worker → 人类监督界面。密钥只在 worker 的服务端环境中，不能返回前端。每个 episode 使用独立状态/进程与输出目录；暂停阻止新动作，不能撤销已执行动作。

## 当前版本的服务器运行方式

先在服务器建立独立 venv、安装 requirements，运行 `python run.py --variant C --seed 31 --port 18631`。无桌面 NVIDIA 服务器设置 `MUJOCO_GL=egl`（需可用 EGL 驱动）；CPU 软件渲染可选择已安装 OSMesa 的环境。

服务目前仅绑定 127.0.0.1，推荐先用同端口 SSH 隧道访问：

```bash
ssh -N -L 127.0.0.1:18631:127.0.0.1:18631 ubuntu-descfly
```

浏览器打开 http://127.0.0.1:18631/ 。原服务 Origin 检查只认可 localhost/127.0.0.1 加服务端口，因此不同本地端口、域名反代不能直接照搬。域名部署需增加显式 allowed-origin 配置、反向代理与 HTTPS；网页 getDisplayMedia 录屏也需要安全上下文。暂不要仅把监听地址改成 0.0.0.0 就当成完成部署。

下一版交付应包含 Linux 环境锁定、容器/启动脚本、健康检查、GPU/软件渲染 smoke test、固定 prompt、Agent worker、右侧事件面板以及一局独立 Agent 的输入/动作/判分记录。模型凭据及一次真实调用验证属于 Agent 接入验收，当前版尚未实现。
