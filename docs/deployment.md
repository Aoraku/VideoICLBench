# 部署与运行

## 本机

安装依赖并构建前端后，执行 `python scripts/start_platform.py`。控制服务监听 `127.0.0.1:8765`，应用 Worker 监听 `127.0.0.1:8771`。共享启动器检查端口和服务启动情况，退出时清理两个子进程。

开发入口也可以分别启动：`scripts/dev_apps.py` 和 `scripts/dev.py`。本机管理凭证为 `.local/admin-token`；Worker 凭证由其派生，模型不会获得这两个凭证。

## 实验室容器

```bash
python3 scripts/bootstrap.py
docker compose --env-file .local/docker.env -f infra/compose.yaml up --build -d
```

部署包含控制服务、应用 Worker 和 PostgreSQL。控制数据库、运行证据和应用数据分别位于持久卷。应用 Worker 无公开主机端口；只有控制服务的 8765 端口发布到主机回环地址。可以通过 SSH 隧道访问门户。

`VIC_PORT=8766` 可调整主机端口。`VIC_ROOT=/app` 指向任务、前端和应用资源。`VIC_APPLICATION_BASE=http://applications:8771` 是控制服务访问应用的内部地址。浏览器使用 `application.localhost`，并在独立进程内将其解析到 Worker 容器地址，使剪贴板等安全上下文 API 可用。用户通过门户操作远程画面。

每个应用运行拥有独立 Chromium 进程与独立 SQLite 文件。判分后浏览器进程释放，最终画面和录像保留。控制服务和应用 Worker 均使用一个 Uvicorn 进程；不能直接通过增加 `--workers` 共享会话状态。

正式远程入口需要实验室的 SSH 地址、部署目录和可访问端口。公网入口应另行配置 TLS 和成员身份认证；共享管理员密钥适用于受控实验室部署。

## 六个来源应用的普通模式

`infra/compose.native.yaml` 提供 chat、im、music、news、code、gomoku profiles。它们与用于任务录制的 benchmark 模式分别运行。

| 应用 | 主机端口 |
|---|---|
| Chat 后端／前端 | 8801／8811 |
| IM 后端／前端 | 8802／8812 |
| Music | 8803 |
| News | 8804 |
| Code | 8805 |
| Gomoku noVNC | 8806 |

普通 Code 模式默认禁用不受隔离的程序执行；应用基准中的 OJ 任务使用独立数据、静态语法检查、代码规则及提交记录。

## 系统执行池

Windows 76–90、Linux 92–98、Android 91／99／100 暂缓执行。`scripts/preflight.py` 检查 Linux/KVM、libvirt、ADB 和镜像配置，`runtimes/profiles.example.json` 定义可允许的执行 profile。

Worker 可管理 qcow2 写入层和 transient domain，以及单个独占 Android AVD。Windows UEFI 需要实例级 NVRAM／TPM 隔离，Android 并发需要 AVD 与端口分配；系统输入、逐题初始化和采集适配必须齐备后才可启用录制。

## Docker 官方镜像的备用仓库

基础镜像可通过 `VIC_NODE_IMAGE`、`VIC_PYTHON_IMAGE` 和 `VIC_POSTGRES_IMAGE` 指定。当执行主机无法连接 Docker Hub 时，可在 `.local/docker.env` 中配置 Docker 官方镜像的 ECR Public 地址：

```dotenv
VIC_NODE_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
VIC_PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
VIC_POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres:17-bookworm
```

这些变量仅选择基础镜像来源。服务、端口、应用数据卷及认证配置由同一份 Compose 文件管理。[Docker 官方镜像在 ECR Public 的发布说明](https://aws.amazon.com/blogs/containers/docker-official-images-now-available-on-amazon-elastic-container-registry-public/)。

## Agentlab

团队执行主机的访问、验收及维护步骤见 [Agentlab 使用说明](agentlab.md)。
