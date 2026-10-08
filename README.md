# VideoICL-Bench

具身任务新增入口：[50题桌面双臂任务与运行说明](simulator/benchmark/README.md)（RoboTwin／RoboCasa 来源，统一 robosuite）。

VideoICL-Bench 为人类录制者和 GUI Agent 提供统一的应用、任务、截图输入、录像和状态评测平台。

应用界面预览与来源见 [应用界面](docs/native-frontends.md)。

团队成员访问共享执行服务，请阅读 [Agentlab 访问与验收说明](docs/agentlab.md)。任务问题可在本仓库 Issues 中选择“任务验收反馈”提交。

OS 任务入口为主页 **OS · 36 题**：包含同事提供的 108 段规则示范、独立执行环境与原始 evaluator，支持原生 Codex / Claude Code。访问、部署和运行命令见 [OS-ICL 使用说明](docs/os-icl.md)。

## 录制前就绪范围

- **75 个软件／游戏任务，225 个 A/B/C 规则版本**：具有业务状态与 eval 实现；应用任务路径的自动检查与人工视觉验收分别记录。
- **13 个应用模块**：六个来源仓库的 benchmark 模式，六个新增业务应用和一个游戏集合。
- **100 份逐题 eval 契约**：任务 1–75 有执行实现；76–100 的系统模拟器与系统执行适配暂缓。
- 每个运行使用独立应用数据库和独立 Chromium 进程，隔离 Cookie、页面和剪贴板。
- 录制支持规则字幕、鼠标指示、点击标记、15 FPS MP4；停止录制即封存输入。帧率可通过 `VIC_RECORDING_FPS` 设置为 5–30，默认单段上限 120 秒，配置范围 30–180 秒。
- 通过判分的教程可提交人工审核。正式数据集仍需要人工录制和审核的视频，因此运行结果中的 `official` 为 `false`。

软件／游戏的执行表面为 `native-task-workspace`。应用保留各自的首页与导航，通过适配器连接独立业务数据。Code 使用独立 Streamlit 进程，五子棋使用 Linux 容器里的原 SDL 程序；浏览器统一呈现画面和接收输入。

## 启动

```bash
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock.txt -e '.[test]'
.venv/bin/python -m playwright install chromium
npm --prefix apps/portal ci
npm --prefix apps/portal run build
npm --prefix apps/chat/frontend/frontend ci
VITE_BASE_PATH=/native-assets/chat/ npm --prefix apps/chat/frontend/frontend run build
npx --yes pnpm@10.4.1 --dir apps/im/Frontend install --frozen-lockfile
NEXT_PUBLIC_VIC_BENCHMARK=1 npx --yes pnpm@10.4.1 --dir apps/im/Frontend build
.venv/bin/python scripts/start_platform.py
```

打开 [本地平台](http://127.0.0.1:8765/)。访问密钥位于 `.local/admin-token`，权限 0600。应用 Worker 在本机 8771 端口运行。两个服务分别对应 `scripts/dev.py` 和 `scripts/dev_apps.py`，统一启动器负责启动检查和退出清理。

包含原 SDL 五子棋的完整环境使用 Linux 容器。容器版构建全部前端，并使用 PostgreSQL 和独立应用数据卷：

```bash
python3 scripts/bootstrap.py
docker compose --env-file .local/docker.env -f infra/compose.yaml up --build -d
```

端口 8765 已占用时可在命令前设置 `VIC_PORT=8766`。容器访问密钥为 `.local/docker.env` 中的 `VIC_ADMIN_TOKEN`；凭证生成器不覆盖既有值。

## 应用与任务

录制与试用入口为主页的 **v2 list** 标签页，包含低、中、高难度各 25 题。选择任务与 A/B/C 版本后，任务卡展示录制规则、示范内容、执行目的、工作要求和最终交付。

- 人工录制：点击“重置示范”，再点击“开始录制”，直接进入应用首页。
- 试用执行任务：点击“打开执行环境”；完成业务操作后回到任务卡，点击“检查最终交付”。无需录视频即可试用。
- 重做执行任务：点击“重置执行环境”，再打开应用；重置会使旧应用页面的访问凭证失效。

完整任务规格见 [75 题设计表](VideoICL_75_web_tasks.md)。示范使用小样本教学初态，执行环境使用对应难度的独立业务初态。

| 应用 | 路径 | 任务 |
|---|---|---|
| 通讯 A | `apps/chat/benchmark` | 1–14 |
| 通讯 B | `apps/im/benchmark` | 15–16 |
| 音乐 | `apps/music/benchmark` | 17、18、22、27、28、32 |
| 新闻 | `apps/news/benchmark` | 19、20、23、24、29、30、33 |
| 视频／信息流 | `apps/media/benchmark` | 21、25、26、31、34、35 |
| 博客 | `apps/blog/benchmark` | 36、38、40、42 |
| 内容工作室 | `apps/studio/benchmark` | 37、39、41、43 |
| 旅游 | `apps/travel/benchmark` | 44、47、51、54 |
| 购物 | `apps/shop/benchmark` | 45、48、52、55 |
| 银行 | `apps/bank/benchmark` | 46、49、50、53、56、57 |
| 编程 | `apps/code/benchmark` | 58–65 |
| 五子棋 | `apps/gomoku/benchmark` | 66–67 |
| 2048／数独／扫雷／黑白棋 | `apps/games/benchmark` | 68–75 |

## 每题 eval API

v2 的契约接口为 `GET /v2/tasks/{task_id}/contract`。创建运行时向 `POST /v1/runs` 传入 `suite: "v2"`、题号、版本及 `mode: "demo"` 或 `"eval"`；连续示范另传 `teaching: true`。最终交付使用 `POST /v2/tasks/{task_id}/eval`，请求体为 `{"run_id": "..."}`。重置接口为 `POST /v1/runs/{run_id}/reset`。这些管理接口均需要平台访问密钥。

以下示例为基础任务接口；v2 运行须使用上述 v2 契约与交付接口，不能混用不同任务集的判分接口。

管理凭证创建并结束任务，Agent 凭证只允许该运行的截图和键鼠输入。

```python
from vic_sdk import Client

runner = Client('http://127.0.0.1:8765', manager_token)
contract = runner.task_contract(1)
run = runner.create(task_id=1, variant='A', seed=10001, runtime='browser')
actor = Client('http://127.0.0.1:8765', run['actor_token'])
shot = actor.observation(run['id'])
# Agent 根据截图发出 actor.act(...)；不接触规则、业务 API 或判分接口。
result = runner.evaluate_task(1, run['id'])
```

对应 HTTP 接口：

```text
GET  /v1/tasks/{task_id}/contract
POST /v1/runs
GET  /v1/runs/{run_id}/observation
POST /v1/runs/{run_id}/actions
POST /v1/tasks/{task_id}/eval       {"run_id": "..."}
POST /v1/runs/{run_id}/reset
GET  /v1/runs/{run_id}/evidence
```

判分封存输入，检查业务结果、过程约束和额外操作，返回 `success`、`completion`、`checks`、`violations` 和证据引用。重复判分返回同一结果，任务编号不匹配会被拒绝。

[逐题应用与评测索引](docs/task-evaluation-map.md) 汇总全部任务、规则与读取字段。逐题契约位于 `tasks/contracts/001.json` 至 `100.json`。系统题返回明确的未接入错误，不生成模拟成功结果。

任务定义由 `VideoICL_100_tasks.md` 和 `tasks/catalog-overrides.json` 共同生成。审阅后的规则、版本及参数写入 overrides；`original_rules` 保留清单原文，问答答案与生效规则一致。运行 `python scripts/build_catalog.py && python scripts/build_contracts.py && python scripts/build_app_modules.py` 生成目录、契约及应用索引，并将输入与生成文件一起提交。CI 校验这些文件可重复生成。

## 验证

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/check_native_ui.py 1,5,17,23,31,38,43,48,57,68 A
.venv/bin/python scripts/check_application_ui.py
.venv/bin/python scripts/smoke_application_pixels.py
.venv/bin/python scripts/smoke_application_concurrency.py
```

`check_native_ui.py` 从应用入口导航并操作原应用或新增产品界面；`check_application_ui.py` 仅检查开发诊断控件，不能证明原应用录制可用。模型执行协议为截图与键鼠输入。界面与验收范围见 [应用界面](docs/native-frontends.md)，操作说明见 [录制指南](docs/recording-guide.md)，架构见 [业务模型](docs/implementation-scope.md)。

## 原生 Codex / Claude Code 执行

`scripts/native_agent.py` 启动本机安装的原生 `codex exec` 或 `claude -p`。模型请求、历史维护、工具循环、自动压缩和 session 恢复均由原生 CLI 负责。共享的 `vic-computer` MCP 只提供平台截图、坐标键鼠操作、指定视频抽帧和结束声明。

```bash
.venv/bin/python -m pip install -e '.[agents,test]'

# 密钥通过指定环境变量读取；不要将真实密钥写入命令历史或版本库。
.venv/bin/python scripts/native_agent.py codex \
  --base-url https://your-responses-gateway.example/v1 \
  --api-key-env VIC_CODEX_KEY --model your-model-id \
  --control-url http://127.0.0.1:8765 --admin-token-file .local/admin-token \
  --task 29 --variant A --seed 10001 --demo /absolute/path/demo.mp4 --evaluate

.venv/bin/python scripts/native_agent.py claude \
  --base-url https://your-messages-gateway.example \
  --api-key-env VIC_CLAUDE_KEY --model your-model-id \
  --control-url http://127.0.0.1:8765 --admin-token-file .local/admin-token \
  --task 29 --variant A --seed 10001 --demo /absolute/path/demo.mp4 --evaluate
```

也可将两组连接配置保存在 Git 忽略的 `.local/native-agents/credentials.json`，权限设为 `0600`；顶层键为 `codex`、`claude`，每组包含 `base_url`、`api_key` 和可选 `model`。使用该文件时可以省略 `--base-url`、`--api-key-env`。模型必须支持对应原生 CLI 的协议：Codex 使用 Responses，CC 使用 Anthropic Messages；网关需同时支持图像、工具调用和流式输出。配置任意模型 ID 不代表已验证其兼容性。不会自动回退到另一模型。

Codex Remote 网关可在 `codex` 配置组设置 `"native_auth": true`，使用原生 `auth.json` API-key 认证和 WebSocket 配置；通用 Responses 网关默认使用环境变量认证。`--binary /absolute/path/codex` 或配置组的 `binary` 字段可指定原生 CLI 版本。

每次运行使用独立的原生配置目录和空白工作目录，不修改个人 Codex/CC 配置。MCP 只持有该实例的截图/键鼠凭证，管理员凭证留在外层启动器。运行资料保存在 `.local/native-agents/runs/`：原生事件流、原生 session、逐步截图、键鼠日志、视频读取时间点、结果摘要，以及显式请求的最终评测。不会录制执行视频。

`--demo` 提供带时间戳的视频帧，不提供音轨、DOM、点击轨迹或人工规则答案；这属于视频帧输入条件。`--evaluate` 会封存平台实例；不指定时可以使用原生恢复命令继续：

```bash
.venv/bin/python scripts/native_agent.py codex --resume /absolute/path/run-directory \
  --model original-model-id --prompt '继续核对刚才的页面'
# Claude Code 同样使用 --resume；由 CLI 恢复原 session，不由启动器重放历史。
```

`--compaction-smoke` 仅用于压缩验证：启用一次性的无业务含义文本工具，并降低原生阈值。Codex 默认测试阈值为 6000 tokens，CC 为 5%；可用 `--compact-threshold` 指定。正式运行不设置这些覆盖值，使用 CLI 的原生默认策略。压缩证据来自 Codex 的原生 rollout 事件和 CC 的 `compact_boundary`，不能以模型自称压缩或退出码为证明。

CC 可通过 `--claude-compact-percent 5` 或私有配置 `claude.compact_percent` 指定原生自动压缩阈值（1–95）；该选项不会启用诊断工具，也不会创建自定义摘要。阈值和原生压缩事件写入运行资料。较低阈值会增加压缩调用次数和时延，应在实验中固定并报告。

`--max-budget-usd` 是 CC 的原生估算费用上限，并非第三方网关的账单保证。Codex 网关若不报告用量，结果保留其原始零值，不将零值解释为免费。启动器默认预算为 1800 秒、120 次输入；创建实例时将输入上限和含启动宽限的服务端时限写入 manifest。预算由管理端设定，Agent 无权自行修改。恢复原生 session 不会扩大服务端实例预算。

CLI 的工具限制用于限定实验接口，不是面向恶意模型的完整安全隔离。正式批量评测应在不挂载源码、答案或个人凭证的隔离执行机/容器中运行。

启动器在调用模型前检查真实浏览器截图。终止性的环境错误会停止推理；`result.json` 的 `outcome` 区分 `success`、`fail`、`incomplete`、`agent_error`、`environment_error` 和 `evaluation_error`，并单独保留原生退出码、超时及模型输出。任务判分失败不等于程序异常；达到时间预算后仍会封存可用环境并评分。视频信息工具提供时长，截图工具提供剩余操作时间。

`execution_status` 区分显式结束、缺少结束声明、超时、环境错误与模型接入错误；`agent_finished` 单独记录是否调用 `finish`。模型接入异常返回 `agent_error`，没有调用 `finish` 的普通退出返回 `incomplete`；两者保留未封存实例，支持使用原生 `--resume` 恢复，不能计为正常结束的模型任务失败。Codex 和 CC 使用原生 Stop hook 检查显式结束声明，最多提醒三次，并受原始时间预算约束；hook 不读取任务答案、不总结历史、不调用模型 API。[Claude Code Stop hook 文档](https://code.claude.com/docs/en/hooks#stop)、[Codex hooks 文档](https://learn.chatgpt.com/docs/hooks)。Codex 仅为本次生成的独立 hook 配置使用原生 hook 信任选项，不扩大键鼠接口或 shell 权限。工具日志记录真实 HTTP 与抽帧耗时，`outside_tool_io_seconds` 包含模型请求、传输和 CLI 开销，不能全部解释为纯模型计算时间。

Codex 的 `--code-mode` 是原生 CLI 功能开关，供需要该工具封装的网关使用；它不替换模型循环。CLI 可能提示该功能处于开发阶段，必须按实际模型验证工具调用，不能仅凭普通文本回复认定接入成功。

使用 `--rule-file /absolute/path/rule.txt` 可运行文字规则诊断，与 `--demo` 互斥。该条件只提供通用规则和公开任务，不应包含指定实例的目标文件 ID 或答案。比较视频条件与文字规则条件时，保持模型、任务、版本、种子、界面和预算一致。

对于无法识别 `tool_result` 内图片的 Anthropic 兼容网关，可显式启用 `--lift-tool-images`。本机回环代理将原始图片块移至同一条用户消息的顶层，保持像素、时间顺序、工具编号、文本、模型参数及响应流不变；不做 OCR、规则注入、历史裁剪或重试。该配置在 manifest 中标记，正常支持工具图片的提供商应直接连接。若网关丢失并行工具调用，`--serial-tools` 使用 CC 原生 `--append-system-prompt` 要求每次调用一个工具。两项都可在私有 credentials JSON 的 `claude` 配置中设为 `true`。

```bash
# 对有上述兼容问题的网关，沿用所选模型及私有凭证。
.venv/bin/python scripts/native_agent.py claude \
  --lift-tool-images --serial-tools --claude-compact-percent 5 \
  --control-url http://127.0.0.1:18765 --admin-token-file .local/agentlab-admin-token \
  --task 11 --variant A --seed 10001 --demo /absolute/path/11-A.mp4 \
  --timeout 1800 --max-actions 120 --max-budget-usd 3 --evaluate
```


[Task 11/A 端到端验证](docs/reviews/gui-harness-task11.json) 使用种子 10001、同事提供的 72 秒 demo，以及独立的通用文字规则输入。四项结果均调用 `finish` 并正常结束，eval API 均为 `success`，每个实例的四条交付全部通过。Agent 只通过截图和坐标键鼠操作任务界面。

| 原生框架 / 所请求的模型 | 文字规则 | Demo 视频 |
|---|---|---|
| Codex 0.147.0 / GPT-5.5 | success，46 次输入，628 秒 | success，44 次输入，644 秒 |
| CC 2.1.117 / Sonnet 4.6 | success，94 次输入，1548 秒，无人工恢复 | success，使用原生 session 恢复和原生自动压缩 |

这些结果用于证明集成可用，不是模型成功率对比。CC 视频轮包含网关错误恢复和压缩阈值诊断干预；完整尝试记录保存在验收 JSON。CC 的自动压缩具有原生 `compact_boundary` 证据。Codex 0.147.0 / GPT-5.5 的独立文本会话验证通过原生手动压缩、轮次开始前的自动压缩及压缩后标记回忆。GUI 长工具输出压力测试仍因网关工具目录续接冲突失败，未出现压缩开始或完成事件；不能将该错误认定为压缩请求被拒绝，GUI 操作中的自动压缩可靠性仍未验证。Codex 网关返回零 token 用量，不能据此推断费用。


实测记录见 [原生接入验证](docs/reviews/native-agents.json)。2026-10-02 的结果如下；这些是接入测试，不是任务成功率测评。

| 原生框架 / 模型 | 实时截图与真实点击 | 原生 session 恢复 | 原生自动压缩 |
|---|---|---|---|
| Codex / `gpt-5.6-luna` | 通过 | 通过 | 未验证成功：长工具结果的续接被网关拒绝；未产生压缩事件 |
| Claude Code / `claude-sonnet-4-6` | 通过 | 通过 | 通过：自动压缩事件报告 9185 → 884 tokens，随后完成点击并保留测试标记 |

CC 验证版本为 2.1.117。Codex 基础操作验证版本为 0.154.0-alpha.6.2；长工具结果续接在该版本和 0.159.3 均失败，不能据此断言失败发生在压缩请求本身。Codex 网关返回的用量不足以确认压缩阈值是否触发。网关未提供可核实的价格表，因此这些模型是低成本候选，不保证为绝对最低价；CC 网关模型列表未提供 Haiku，测试使用 Sonnet，没有使用 Opus。

## 桌面双臂50题（RoboTwin / RoboCasa 改编）

统一 robosuite 双 Panda 场景、任务定义、私有判分、GUI 和实验 harness 见 [运行说明](simulator/benchmark/README.md) 与 [50题清单](simulator/benchmark/TASKS.md)。包含独立 Agentlab CPU / OSMesa 部署入口。六题 pilot 的作者验收和仿真示范见 [pilot 说明](simulator/benchmark/PILOT.md)；人手示范与逐题 agent 实验仍需采集和验收；历史微波炉杯子实验保留在 embodied handoff 中。
