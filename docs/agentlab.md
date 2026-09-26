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

1. 查看 [逐题索引](task-evaluation-map.md)，选择分配的题号和 A/B/C 版本。
2. 阅读任务卡的规则与操作说明，点击“开始录制”直接进入应用首页，导航并完成操作。返回任务卡结束录制，录像自动保存并检查任务结果。
3. 需要重录时点击任务卡的“重置环境”。错误规则测试应使用独立记录，避免覆盖要保留的录像。
4. 按 [录制指南](recording-guide.md) 选择实际应用窗口录制，检查视频能播放，首页、导航、文字和鼠标可辨认。
5. 提交反馈时包含题号、版本、种子、run_id、预期行为、实际行为及截图；反馈中不包含访问密钥。

任务 1–75 可参与应用基准验收；系统任务 76–100 暂缓。自动化测试的视频属于工程证据，正式教程需要人工录制和审核。

两个本地端口都必须转发。工作台使用 18765，独立应用使用 18766；应用页通过单次运行凭证读写隔离数据，不接触工作台管理密钥。人工操作不受 Agent 的五分钟与 120 次输入限制。完成任务后回到任务卡点击“结束并保存录像”；保存成功后自动检查任务结果。

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

[应用界面与验收范围](native-frontends.md) 提供来源、首页预览和任务流程说明。`check_native_ui.py` 检查应用任务路径；`check_application_ui.py` 的 225 个诊断用例只证明诊断控件与业务接口可运行。正式录制仍需逐题人工视觉验收。

[独立应用入口验收](direct-application-acceptance.md) 提供 Computer Use 的 13 个模块、15 个代表性任务记录，以及录像与浏览器兼容性边界。
