# OS-ICL 团队任务

平台入口为 http://127.0.0.1:18765/ ，使用团队平台访问密钥登录后选择 **OS · 36 题**。沿用平台的 SSH 隧道，无需额外转发端口。

选择题目和 A/B/C 版本，观看示范视频，然后点击“打开执行环境”。任务在独立标签页直接显示 Vibe OS。完成后点击应用里的 **Finish and evaluate**，或回到任务卡点击“检查最终结果”。“重置并打开”创建独立的执行环境。

## 任务与评分契约

来源为 [peilin717/OS-ICL](https://github.com/peilin717/OS-ICL)，固定提交 `e6c805094eade3ee391d89ad19dbbefc5bc76e11`。包含 36 题、108 个规则上下文及 108 段配套 WebM 视频，版本为 1.0.0。视频使用上游 manifest 的 SHA-256 校验。

任务运行在浏览器 OS 模拟器中，不操作宿主操作系统。桌面、应用、生成器和 evaluator 来自上游仓库。恢复类任务的公共执行要求为：按可见的 **Index 升序**处理异常对象，完成一个对象的两个步骤后再处理下一个。具体恢复策略由示范教授。该公共要求和 Index 列由 `patches/os-icl-visible-recovery-order.patch` 提供，评分函数使用上游原实现。

跨应用题按轨迹评分：进入来源应用、点击需要检查的来源记录、进入目标应用、执行对应操作。看到正确结果不等于轨迹符合要求。

## 原生 Agent 执行

Codex 与 Claude Code 管理模型调用、上下文和自动压缩。共享 MCP 只提供示范抽帧、实时截图、坐标键鼠与结束声明。模型无法使用 DOM、语义动作 API、源码、隐藏规则或评分接口。控制器负责创建环境、分配同规则视频及最终评测。

在配置有原生 CLI、模型网关私有凭证及平台密钥的机器上运行：

```bash
python -m vic_sdk.native_agent codex --model gpt-5.5 --code-mode \
  --os-case OS-SEL-01 --variant A --seed 20261005 \
  --control-url http://127.0.0.1:18765 \
  --admin-token-file .local/agentlab-admin-token \
  --timeout 1200 --max-actions 100 --evaluate

python -m vic_sdk.native_agent claude --model claude-sonnet-4-6 \
  --os-case OS-SEL-01 --variant A --seed 20261005 \
  --control-url http://127.0.0.1:18765 \
  --admin-token-file .local/agentlab-admin-token \
  --timeout 1200 --max-actions 100 --max-budget-usd 1.5 --evaluate
```

匹配的 canonical demo 自动下载并校验；执行 seed 必须与示范 seed 不同。模型仅得到任务目标和视频，不获得版本对应的规则文字。正式运行使用原生默认压缩策略；私有凭证中的 `claude.compact_percent` 应省略，压缩压力测试阈值不适合正式图片任务。

输出目录包含 `manifest.json`、`result.json`、原生 CLI 日志、截图与输入记录。`outcome` 为 evaluator 的 success/fail 时，还须核对 `execution_status=completed`、`agent_finished=true`。网关或环境错误单独报告，不伪装成模型答错。

## API 与访问边界

| 接口 | 权限 | 用途 |
|---|---|---|
| `GET /os-api/cases` | 平台管理密钥 | 36 题目录 |
| `GET /os-api/cases/{case_id}/demo?variant=A` | 平台管理密钥 | 对应示范视频 |
| `POST /os-api/runs` | 平台管理密钥 | 创建人类或 Agent 环境 |
| `GET /os-api/runs/{id}/demo` | 管理或该运行的 actor 凭证 | 校验后的对应示范 |
| `GET /os-api/runs/{id}/observation` | 管理或该运行的 actor 凭证 | 1280×720 实时像素 |
| `POST /os-api/runs/{id}/actions` | 管理或该运行的 actor 凭证 | 帧编号校验的坐标键鼠输入 |
| `POST /os-api/runs/{id}/eval` | 平台管理密钥 | 幂等提交与上游评分 |

应用地址携带单运行 capability，进入后转换为作用域受限的 HttpOnly cookie。应用代理只能访问本运行及白名单静态资源；不开放录制后台、源码或其他运行。原始 OS 服务没有宿主端口映射，仅在 Docker 网络内访问。

## 部署与维护

准备固定版本资源：

```bash
python scripts/prepare_os_release.py --destination /home/qingle/services/os-icl-e6c8050
```

目标目录应为空。部署主机可直接下载，或在联网机器准备后传输完整目录。完整平台镜像应由包含 OS 适配的本仓库构建。执行以下命令时保留 OS Compose 层：

```bash
sudo docker compose --env-file .local/docker.env \
  -f infra/compose.yaml -f infra/compose.os.yaml up --build -d
sudo docker compose --env-file .local/docker.env \
  -f infra/compose.yaml -f infra/compose.os.yaml ps
```

`VIC_OS_SOURCE_HOST` 可指定资源目录。OS episode 保存在 `os_data` 持久卷，平台的 OS 运行元数据保存在 `run_data` 持久卷。服务采用 `unless-stopped`，容器退出会重启。浏览器进程中断的 Agent 运行需要重新创建环境，不能无声地当作续跑。

界面与评分链路检查（不录制视频）：

```bash
python scripts/check_os_ui.py --token-file .local/agentlab-admin-token
```
