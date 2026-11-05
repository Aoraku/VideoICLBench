# 安装与外部依赖

本目录是独立 harness 源码，SDK 与原测试源码逐字节复制。包根的
`process_launcher.py` 与 `VideoICLBench/packages/sdk/vic_sdk/process_identity.py`
保持原层级，因此无需修改原 SDK 的 launcher 路径。

## GUI / CLI Python

使用 Python 3.11 或更新版本，在本目录的 `VideoICLBench` 内执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/harbor/run_embodied_pool.py --help
.venv/bin/python scripts/harbor/run_embodied.py --help
```

这会安装 Python harness 依赖和浏览器；不会安装 IsaacLab、模型 CLI 或数据。
`pyproject.toml` 是本独立包的依赖元数据，SDK 文件本身没有修改。
版本范围沿用源项目，`setproctitle==1.3.6` 是进程身份 launcher 的精确要求。

## 原生仿真 Python

`--native-python` 指向已有、与资产兼容的 IsaacLab/IsaacSim Python。
该环境也必须能够 `import setproctitle` 且版本为 `1.3.6`；安装到该独立环境，
或由部署者提供兼容的 release-local vendor，不能修改他人的共享环境。
Linux `/proc`、Kit/IsaacLab、CUDA/驱动和 native runtime 由部署方提供。
纯 Python GUI 依赖不能替代这些运行条件。

## 外部路径合同

| 参数/文件 | 必须由运行方提供的内容 |
| --- | --- |
| `--runtime-root` | 已验收 runtime，含 `scripts/serve_realworld_room_pool.py` 和 `videoicl_isaaclab/`，保持其 USD/碰撞/机制源依赖完整 |
| `--cases` | 该 runtime 的完整已验证 cases，含固定 episode/task/variant/seed、robot profile、bindings；其中绝对路径在本机部署时解析 |
| `--task-root` | 每个 `embodied-eXX-c` 任务包；instruction/native 元数据/rule/demo SHA 与 runtime provenance 一致 |
| `--binary` | 已固定版本的真正 Codex CLI；当前新测试固定 0.163.0 |
| `--codex-model-catalog` | 对应模型的完整原生 catalog 与 SHA，支持 262144 窗口及 direct/serial GUI 工具政策 |
| `--credentials` | 本机私有 provider 配置，仅文件路径进入启动命令；不要提交 Git |
| `--provider-ca-bundle` | 验证 provider HTTPS 的 CA bundle |
| `--api-concurrency-config` | 本机私有共享并发策略与可写 gate 路径 |

本包不含 runtime、任务、视频、USD/纹理资产、运行配置、keys、profile 或私有日志。
迁移外部路径时必须保持原材料 SHA，不能用缺失演示片段或不同物体替代。
原生环境的 `isaaclab` / `videoicl_isaaclab` 是明确的外部 ABI，不是 pip 包漏项。

## 本地回归

```bash
.venv/bin/python -m pytest tests/test_embodied_codex_native_tools.py tests/test_native_structured_supervisor.py
.venv/bin/python -m pytest tests/test_tls_relay_request_metadata.py tests/test_tls_relay.py
```

前者使用 fake executor/HTTP mock；后者只访问本机假 TLS 服务。完整 GUI/Chrome
测试需要实际浏览器；真实 CLI + localhost mock 的 opt-in 用例默认跳过。
此处测试不会启动 IsaacLab、真实模型 API 或正式 episode。不要用离线回归替代
真正首图、动作反馈、缓存、原生 compact 与终态验证。运行流程和 CLI 模板见包根 README。
