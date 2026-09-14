# Agentlab 团队平台

## 代码与执行服务

代码仓库：[Aoraku/VideoICLBench](https://github.com/Aoraku/VideoICLBench)。执行目录：`/home/qingle/services/videoicl`。运行环境为 Docker Compose，包含控制服务、应用 Worker 和 PostgreSQL。

平台入口绑定执行主机的 `127.0.0.1:8765`。应用 Worker 和数据库仅在容器网络内访问。任务数据库、业务数据、录像和证据保存在 Docker 持久卷中。

## 同事访问

具有执行主机 SSH 权限的成员在自己的电脑上保持以下命令运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18765:127.0.0.1:8765 qingle@agentlab
```

`agentlab` 为团队 SSH 别名；未配置该别名的成员向管理员获取实际 SSH 主机地址。若成员使用独立 SSH 账号，将 `qingle` 替换为该账号。

浏览器打开 [团队平台的本地隧道入口](http://127.0.0.1:18765/)，输入管理员单独分发的**平台访问密钥**。此密钥与 GitHub 凭证、SSH 密钥不同。服务器凭证文件位于 `/home/qingle/services/videoicl/.local/admin-token`，不提交到 GitHub。

关闭隧道会断开该成员的访问；执行主机上的服务继续运行。公网域名入口需要独立配置 DNS、HTTPS 和成员认证。

## 验收流程

1. 查看 [逐题索引](task-evaluation-map.md)，选择分配的题号、A/B/C 版本和种子。
2. 进入独立环境，先进行一次符合规则的操作，确认判分通过。
3. 重置该运行，故意使用另一版本的规则，确认判分失败。
4. 按 [录制指南](recording-guide.md) 录制，检查视频能播放、字幕和鼠标可辨认。
5. 提交反馈时包含题号、版本、种子、run_id、预期行为、实际行为及截图；反馈中不包含访问密钥。

任务 1–75 可参与应用基准验收；系统任务 76–100 暂缓。自动化测试的视频属于工程证据，正式教程需要人工录制和审核。

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
