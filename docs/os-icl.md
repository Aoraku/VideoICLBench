# OS-ICL 团队任务

平台入口为 http://127.0.0.1:18765/ ，使用团队平台访问密钥登录后选择 **OS · 36 题**。沿用平台的 SSH 隧道，无需额外转发端口。

## 人工录制

1. 选择题目与 A/B/C。卡片顶部的 **Demo 操作** 是本次示范使用的应用；**Inference 执行应用** 是完整业务使用的应用，两者可以不同。
2. 阅读 **在哪里操作**。每组给出应用图标、菜单、按钮、输入文件完整路径和保存位置。所有操作在浏览器里的 OS 模拟桌面完成，不修改自己电脑的系统。
3. 点击 **预览示范环境** 试做。应用均可从桌面左下角 **Start** 找到；文件夹双击进入。Notepad 使用 **Open… → Document 选择完整路径 → OK** 打开文件，**Save** 保存。默认选中的 Unrelated note.txt 是范围外文件，不要修改。
4. 正式录制点击 **开始录制**，在分享弹窗选择 OS 应用标签页。保留从桌面进入应用的导航，连续展示同一方法的多个输入与保存结果。不要录工作台的规则卡或整条 inference 流程。
5. 多组示范在应用右下角点击 **下一组**，最后点击 **完成练习**。回工作台等待上传与自动检查，回放后填写审核人并确认审核通过。服务器录像可以回放、下载，切题后保留。

各题共用桌面外观和应用图标，任务材料由所选题目独立加载。同题 A/B/C 共用初始材料、使用不同处理方法。一个 inference 是一个持续环境，跨应用通过 Start 或底部任务栏切换；示范中的组间切换不用于 inference。

例如 **OS-M-02**：桌面单击 **Notepad → Open…**，在 Document 中选 `/Projects/Project-1001/Workspace/Example input.json` 查看两条变更；再打开 `/Projects/Project-1001/Output/Example result.txt`，按所选版本格式编辑并 Save。其余组以卡片里的实际路径为准。

完整规则、分级和逐题示范内容见 [36 题设计与人工录制手册](os-task-design.md)。

## 任务与评分契约

来源为 [peilin717/OS-ICL](https://github.com/peilin717/OS-ICL)，固定提交 `97a47cf491f8d8793b7b78aa4b814b77e246cac8`，配套平台适配由 `scripts/prepare_os_release.py` 和 `scripts/os_refinement.py` 构建。目录为 `tasks/os/catalog.json`。

36 个独立任务族分为 Easy、Medium、Hard 各 12 题，每题 A/B/C。Easy 在一个环境中重复应用方法；Medium 将方法嵌入主要应用内的长程业务；Hard 加上多个现有桌面应用之间的内容或状态依赖。各档 demo 都只教局部方法，用多个清晰例子展示。

评测核对实际保存状态、来源关联、必要业务依赖和禁止副作用。AI 参考视频不计入人工示范；Agent inference 必须配有经过自动检查与人工审核的匹配录像。录像保存在平台持久卷，使用设计指纹及 SHA-256 校验。

## 原生 Agent 执行

Codex 与 Claude Code 管理模型调用、上下文和自动压缩。共享 MCP 只提供示范抽帧、实时截图、坐标键鼠与结束声明。模型无法使用 DOM、语义动作 API、源码、隐藏规则或评分接口。控制器负责创建环境、分配同规则视频及最终评测。

在配置有原生 CLI、模型网关私有凭证及平台密钥的机器上运行：

```bash
python -m vic_sdk.native_agent codex --model gpt-5.5 --code-mode \
  --os-case OS-E-01 --variant A --seed 4201 \
  --control-url http://127.0.0.1:18765 \
  --admin-token-file .local/agentlab-admin-token \
  --timeout 3600 --max-actions 800 --evaluate

python -m vic_sdk.native_agent claude --model claude-sonnet-4-6 \
  --os-case OS-E-01 --variant A --seed 4201 \
  --control-url http://127.0.0.1:18765 \
  --admin-token-file .local/agentlab-admin-token \
  --timeout 3600 --max-actions 800 --max-budget-usd 1.5 --evaluate
```

匹配的已审核人工 demo 自动下载并校验；执行 seed 必须与示范 seed 不同。模型仅得到任务目标和视频，不获得版本对应的规则文字。正式运行使用原生默认压缩策略；私有凭证中的 `claude.compact_percent` 应省略，压缩压力测试阈值不适合正式图片任务。

输出目录包含 `manifest.json`、`result.json`、原生 CLI 日志、截图与输入记录。`outcome` 为原始 evaluator 的 success/fail。`execution_status=completed` 表示正常结束，且应有 `agent_finished=true`；`budget_exhausted` 表示达到原生费用或轮次上限，控制器仍提交实际环境评分，并保留原生退出码和预算原因。网关或环境错误单独报告，不伪装成模型答错。

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

## 部署与维护（管理员）

准备固定版本资源：

```bash
python scripts/prepare_os_release.py --destination /home/qingle/services/os-icl-human36-97a47cf
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
