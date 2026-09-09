# 实验室部署

## 控制服务

`infra/compose.yaml` 部署控制服务和 PostgreSQL。每个控制实例使用单个 Uvicorn 进程：生命周期锁及浏览器上下文由此进程持有，不支持直接把 `--workers` 提高。多节点执行池应使用独立 Worker 服务，不能用多个控制进程共享同一会话。

```bash
python3 scripts/bootstrap.py
docker compose --env-file .local/docker.env -f infra/compose.yaml up --build -d
```

容器端口仅发布到服务器的 `127.0.0.1:8765`。实验室成员可通过 SSH 隧道访问；正式公网入口需要 TLS、独立应用来源、身份服务及输入网关。

本地端口已有开发服务时，可以设置 `VIC_PORT=8766` 启动容器版。`VIC_ROOT=/app` 指定容器内的任务、前端和判分资源；启动检查要求这些资源完整。

`VIC_PUBLIC_BASE` 在控制容器中使用其回环地址，这是浏览器 Worker 的内部导航地址。公网入口与内部导航地址应在完成独立网关接入时分别配置。

## 原应用

`infra/compose.native.yaml` 提供可选 profile：chat、im、music、news、code、gomoku。

```bash
docker compose --env-file .local/docker.env -f infra/compose.native.yaml --profile music up --build -d
```

每个评测运行应使用不同 Compose 项目名和数据卷。该文件用于原应用开发验证，不代表控制平台已能给原应用分配任务。

| 应用 | 本机端口 | 配置 |
|---|---:|---|
| Chat 后端 / 前端 | 8801 / 8811 | 独立 SQLITE_PATH、ASGI、HTTP/WebSocket 代理 |
| IM 后端 / 前端 | 8802 / 8812 | ASGI、可配置后端地址、HTTP/WebSocket 代理 |
| Music | 8803 | 独立 SQLite、非调试服务 |
| News | 8804 | 本地新闻快照 |
| Code | 8805 | 独立数据库，默认禁用不受隔离的代码执行 |
| Gomoku | 8806 | SDL/Xvfb/noVNC，服务退出可见 |

Code 的 `VIC_JUDGE_MODE=isolated-worker` 只允许用于已配置独立隔离边界的执行实例；该开关本身不建立沙箱。控制服务不得挂载 Docker socket 或直接运行提交代码。

## 系统 Worker

运行 `scripts/preflight.py` 检查 KVM、libvirt、ADB、模拟器和镜像配置。复制 `runtimes/profiles.example.json` 到服务器配置目录，填写已有镜像与 domain 模板。

```bash
export VIC_WORKER_PROFILES=/etc/videoicl/profiles.json
export VIC_WORKER_DATA=/srv/videoicl/instances
export VIC_WORKER_TOKEN='独立随机凭证，至少 32 字符'
uvicorn runtimes.worker:create_app --factory --host 127.0.0.1 --port 8770 --workers 1
```

Worker 只接受预定义 profile，创建真实 qcow2 写入层和 transient domain。支持销毁、重置和截图，不提供自动降级的仿真环境。模板限定为单个可写系统盘；共享 NVRAM 的 UEFI 模板会被拒绝，必须补齐实例级 NVRAM/TPM 隔离后才能接入相应 Windows 镜像。

Android 生命周期工具只允许单个配置 AVD 独占使用；并发需要 AVD 克隆、端口分配和各自的快照目录。客体任务初始化、输入转发、Guacamole 网关和控制服务调度连接仍是正式运行的必要接入项。

## 正式环境门槛

1. 固定操作系统镜像、浏览器、字体和输入法版本。
2. 每个运行使用独立数据库、浏览器、磁盘与网络访问范围。
3. 评测服务、凭证、答案和初始状态证据位于客体之外。
4. 所有任务完成 GUI 参考流程，并通过反事实及副作用检查。
5. 通过 15 会话混合运行测试及故障恢复测试。
6. 教程具有人工审核记录，且与冻结的任务及环境版本一致。
