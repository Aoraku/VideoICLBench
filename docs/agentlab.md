# Agentlab 团队平台

## 代码与执行服务

代码仓库：[Aoraku/VideoICLBench](https://github.com/Aoraku/VideoICLBench)。执行目录：`/home/qingle/services/videoicl`。运行环境为 Docker Compose，包含控制服务、应用 Worker 和 PostgreSQL。

平台入口绑定执行主机的 `127.0.0.1:8765`。应用入口绑定执行主机的 `127.0.0.1:8771`，数据库仅在容器网络内访问。任务数据库、业务数据、录像和证据保存在 Docker 持久卷中。

## 同事访问

具有执行主机 SSH 权限的成员在自己的电脑上保持以下命令运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18765:127.0.0.1:8765 \
  -L 127.0.0.1:18766:127.0.0.1:8771 qingle@agentlab
```

`agentlab` 为团队 SSH 别名；未配置该别名的成员向管理员获取实际 SSH 主机地址。若成员使用独立 SSH 账号，将 `qingle` 替换为该账号。

浏览器打开 [团队平台的本地隧道入口](http://127.0.0.1:18765/)，输入管理员单独分发的**平台访问密钥**。此密钥与 GitHub 凭证、SSH 密钥不同。服务器凭证文件位于 `/home/qingle/services/videoicl/.local/admin-token`，不提交到 GitHub。

关闭隧道会断开该成员的访问；执行主机上的服务继续运行。公网域名入口需要独立配置 DNS、HTTPS 和成员认证。

### macOS 自动连接

具备免交互 SSH 登录权限的成员可安装登录后自动运行的后台连接。先关闭占用 18765、18766 端口的手动隧道，再在仓库目录运行：

```bash
python3 scripts/install_macos_tunnel.py --host qingle@agentlab
```

安装后直接访问 [平台入口](http://127.0.0.1:18765/)，无需打开终端。macOS 登录后自动连接；连接进程退出后由 launchd 自动拉起。SSH 每 15 秒检查服务器响应，连续三次无响应会退出并重连。电脑断网、关机或休眠期间无法访问，联网并唤醒后会重新连接；服务器本身不可用时需等待服务器恢复。

配置位于 `~/Library/LaunchAgents/com.videoicl.agentlab-tunnel.plist`，日志位于 `~/Library/Logs/VideoICL/`。该配置仅保存连接参数，不保存平台密钥或 SSH 私钥。检查状态：

```bash
launchctl print gui/$(id -u)/com.videoicl.agentlab-tunnel
curl --fail http://127.0.0.1:18765/healthz
curl --fail http://127.0.0.1:18766/healthz
```

卸载自动连接：

```bash
launchctl bootout gui/$(id -u)/com.videoicl.agentlab-tunnel
rm ~/Library/LaunchAgents/com.videoicl.agentlab-tunnel.plist
```

## 验收流程

1. 在主页选择 **v2 list**，找到分配的题号和 A/B/C 版本。列表表头可按任务序号、难度或平台排序，再次点击切换升降序；支持搜索和平台筛选。完整规格见 [75 题设计表](../VideoICL_75_web_tasks.md)。
2. 任务卡提供 **示范 · demo** 和 **执行 · inference** 两个入口。示范页显示该版本的完整规则解释和逐步录制说明，“预览示范环境”不请求录屏。执行页说明工作目标、步骤和交付物，“打开执行环境”从应用首页进入独立的执行数据。完成工作后回任务卡点击“检查最终交付”；检查会提交本次结果，修改重试需重置。
3. 需要重做时，点击“重置执行环境”并重新打开应用。旧应用页面的访问凭证会失效，须使用新打开的页面。
4. 人工录制时，在示范页阅读该版本的规则和操作清单，按 [录制指南](recording-guide.md) 点击“开始录制”；录制自动从示范初态开始。保留应用首页和自然导航，按页面显示的案例数完成教学；连续练习每组结束点击“下一组”，最后点击“完成练习”。预览和执行验证均无需录屏。
5. 提交反馈时包含题号、版本、预期行为、实际行为及截图；有运行编号时附上 run_id。反馈中不包含访问密钥。

任务 1–75 可参与应用基准验收；系统任务 76–100 暂缓。自动化验收检查界面操作、持久化结果和接口，不录制教程视频；正式教程由同事录制并审核。

低、中、高各 25 题。低难度在一批新对象或多个独立局面中多次应用视频规则；中难度完成有资料来源、必要前置依赖和真实交付物的完整长程任务；高难度在多个应用和模块之间处理更长的依赖链。题目的业务目标、处理范围、信息来源和交付去向均明确给出。Demo 只教授规则，不要求录制执行阶段的完整流程。

姓名、项目与业务资料按任务及初态确定，重置可复现相同资料；示范和执行使用不同姓名池。真实使用体验、教学清晰度和难度感受由同事按题试用反馈，接口验证负责检查业务结果。

两个本地端口都必须转发。工作台使用 18765，独立应用使用 18766；应用页通过单次运行凭证读写隔离数据，不接触工作台管理密钥。人工操作不受 Agent 的五分钟与 120 次输入限制。录像保存成功后自动检查任务结果；停止所有录屏后才能返回规则说明。

## Agent 连接

Agent runner 使用同一隧道入口 `http://127.0.0.1:18765`。管理凭证负责初始化与调用逐题 eval；模型仅获得该运行的 actor 凭证，用于截图和键鼠输入。模型推理可在其他机器上运行。

## 服务维护

在执行主机上运行：

```bash
cd /home/qingle/services/videoicl
sudo docker compose --env-file .local/docker.env -f infra/compose.yaml ps
curl --fail http://127.0.0.1:8765/healthz
```

服务使用 `unless-stopped` 重启策略。更新代码应安排在没有录制或评测任务运行的时段；更新过程会替换应用进程：

```bash
cd /home/qingle/services/videoicl
git pull --ff-only
python3 scripts/bootstrap.py
sudo docker compose --env-file .local/docker.env -f infra/compose.yaml up --build -d
```

停止或更新服务时保留数据卷；`down -v` 会删除持久数据，不用于常规维护。备份需同时覆盖 PostgreSQL、应用数据库、运行证据及凭证文件。

服务属于受控团队平台，使用共享管理凭证；任务执行状态隔离不等于成员权限隔离。个人账号、任务归属权限和公网身份接入为独立功能。

## 验收记录

[v2 平台验收记录](reviews/v2-agentlab-release.json) 覆盖服务器上的 225 个执行条件、225 个示范条件（共 990 组连续练习），以及最终交付、文件下载、重置和凭证更新。原生界面流程的逐平台记录与 Code／五子棋连续练习记录位于同目录。验收不录制教程视频。

[应用界面与验收范围](native-frontends.md) 提供来源、首页预览和任务流程说明。`check_native_ui.py` 检查应用任务路径；`check_application_ui.py` 的 225 个诊断用例只证明诊断控件与业务接口可运行。正式录制仍需逐题人工视觉验收。

[独立应用入口验收](direct-application-acceptance.md) 提供 Computer Use 的 13 个模块、15 个代表性任务记录，以及录像与浏览器兼容性边界。

## OS-ICL 任务

主页 **OS · 36 题** 提供 36 个 OS 模拟任务和 108 段配套示范视频，使用同一平台密钥和现有隧道。操作步骤、原生 Agent 命令、API 和带 OS 服务的维护命令见 [OS-ICL 团队任务](os-icl.md)。维护这台服务器时需同时指定 `-f infra/compose.yaml -f infra/compose.os.yaml`，以保留 OS 资源挂载和服务。

### Mac 上验证 inference

在实际运行浏览器或 Agent 的 Mac 上建立上述双端口隧道，然后访问 `http://127.0.0.1:18765/`，在 v2 任务卡选择“执行 · inference”。独立应用使用 `http://127.0.0.1:18766`；两个端口都要保持可用。录制与 inference 共用平台访问密钥，分别创建独立任务环境。

`127.0.0.1` 指当前电脑。若 Agent 的浏览器运行在另一台机器，应在那台机器上建立隧道，而不是将 Mac 的本地地址直接发给远程浏览器。
