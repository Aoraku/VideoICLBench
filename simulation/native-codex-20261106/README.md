# 原生 Codex 具身评测交接

本版使用真正的 Codex CLI 连续会话。Codex 负责模型请求、工具调用与返回、会话历史和自动 compact；宿主负责 GUI 工具、原生仿真、身份核对、恢复与评分。

本文记录 2026-11-06 原生 Codex 单条测试的代码合同，发布目标为 `Aoraku/VideoICLBench` 的 `codex/embodied-all-handoff-20261103` 分支下 `/simulation`。首轮 relay bootstrap 曾因导入旧 SDK 失败，当时模型 API、Codex session 和物理动作均为 0。修复后 run2 已在 slot2 启动真正 Codex CLI 0.163.0：首个完整 GUI、同 session 连续工具调用、至少 8 个 Commit / 55 个物理动作和逐 pair 公开反馈已核对。snapshot8（17:57:55Z）记录 provider 11 次成功、0 次失败、1 次在途；最新请求 input62005 / cached57856 / output307，缓存率约 93.3%。实际 compact、完整原生终态、评分和资源释放仍待验证。旧 episode 保持暂停。

阶段结果及证据范围见 [LIVE_VALIDATION.md](../LIVE_VALIDATION.md)。

## 固定设置

| 项目 | 设置 |
| --- | --- |
| 运行引擎 | `codex`，开启 `--native-structured-tools` |
| 模型 | `gpt-6-astra`，`high` |
| 本轮 CLI | 固定并记录 `codex-cli 0.163.0` 的实际 binary 路径、版本与 SHA |
| raw context window | `262144` |
| 原生自动 compact 阈值 | `120000` |
| native 工具文本上限 | `32768` token；适配器单份公开文本超过 `24000` UTF-8 字节时显式报错 |
| 物理动作预算 | `500`，按左右臂动作对计数 |
| episode 时间上限 | `--timeout 0`，关闭 |
| 一次 Commit 的队列容量 | `1–24` 对有序动作，受剩余物理预算约束 |
| QA | 本次不做 QA |

`120000` 是自动 compact 触发阈值，`262144` 是配置的 raw window，两者用途不同。模型 catalog 必须支持该窗口并与固定 SHA 一致。实际生效窗口、何时触发 compact、摘要请求的费用分别核对。custom provider 下的 Codex 原生文本摘要仍会调用模型；本版没有声称启用服务端 opaque/V2 compaction。

## 一条 episode 如何运行

1. 加载已准备好的任务包、原生场景与指定示范。核对 task/variant/seed、物体与环境绑定、instruction/rule/video SHA、模型 catalog、CLI 和 SDK 源码版本。
2. 创建该 episode 独占的原生世界、GUI 和私有 profile。启动前检查 GPU、显存与进程内存容量。
3. 读取初始完整 GUI 与公开机器人状态。首个 user prompt 写入任务、条件所允许的规则或示范元信息，以及这份公开状态；初始 GUI 通过真实 `codex exec --image ... -` 附入首个请求。
4. Codex 在同一原生 conversation 中调用结构化 MCP 工具。后续仅由工具返回追加新信息：Commit 完成后的最终 GUI/公开反馈，或模型主动查询的观察、深度、示范帧和历史。宿主不会每轮重新拼接任务、有限历史或强制 memory 文本。
5. API/CLI 基础设施故障后，先确认请求排空及动作状态，再从原 profile 的同一 session 恢复。已接受或结果未知的输入保持原身份，不能用新 ID 重播。
6. 模型通过 GUI `done` / `giveup`，或原生物理预算耗尽后，核对原生终态与末态快照。API 完全排空后才评分并关闭世界。

CLI 退出、最终文字、“完成”自述、错误或预算暂停都不会自动 seal/finish 世界。无法确认终态时保留现场，未评分保留 null。

## 模型能使用的工具

| 工具 | 行为与返回 |
| --- | --- |
| `action_batch(operation_id, actions)` | 通过可见 GUI 选择每对左右臂动作及参数、加入队列，再点击一次 Commit。执行完成后返回最终 GUI、公开状态与逐 pair 回执。 |
| `observe()` | 主动读取当前 GUI 和同步公开状态。 |
| `depth_points(camera, pixels)` | 查询当前帧指定相机的 `1–16` 个 `[row,col]` 像素，返回公开深度、坐标与同帧 calibration 引用。 |
| `demo_frames(seconds)` | 从原 assigned video 按需读取 `1–12` 个时刻。首轮提供示范元信息，默认不强塞固定概览帧。text 条件没有示范访问权限。 |
| `history(start, count, include_images)` | 读取本 episode 已观察过的公开事件；1-based，最多 5 个事件，含图时最多 2 个。只读查询不移动或重放机器人。 |
| `done(summary)` / `giveup(reason)` | 通过原 GUI 提交终态请求，结果由原生记录与评分核对。 |

深度和示范查询不额外返回一份未变化的 GUI。历史图明确属于历史事件，深度/坐标仅对原 frame 有效。图像通过 MCP image 内容块传输，原图不会被塞进文字 base64。

### 多个动作，一次 Commit

`actions` 中每一项都是完整的一对公开动作，例如：

```json
{
  "operation_id": "approach-001",
  "actions": [
    {"left": "<公开左臂token>", "right": "<公开右臂token>", "step_mm": 10, "rotation_deg": 5},
    {"left": "<公开左臂token>", "right": "<公开右臂token>", "step_mm": 5, "rotation_deg": 5}
  ]
}
```

token 和参数必须满足当前 GUI 返回的 action schema。这是一次 Commit 执行两对动作：Commit 计数增加 1，物理动作计数增加 2。24 是现有 GUI 队列容量，不是每轮应执行的动作数。批次执行完成后仿真按原生控制协议等待下一次决策，模型读取轮末新图再继续。

每 pair 公开反馈保留 `reached` / `partial` / `blocked`、原因、请求与实际位移、位置/角度误差。`completed` 表示回执已确认，不能替代运动目标是否达到。显示层紧凑列格式保留缺失、null 和零的区别，完整公开回执留在本 episode 审计记录中。

同一个 `operation_id` 只能对应同一批输入。已完成 ID 再次查询会标记 `cached_receipt=true`、`observation_is_current=false`，省略旧 GUI；需要原图时可主动查询 history。pending/unknown 输入阻止新物理动作和终态提交，等待现场核对。

## 可移植运行示例

以下示例供 **Linux GPU 主机**使用。将所有 `/opt/...` 替换为本机已经安装、验证过的路径。Python/IsaacLab、浏览器、任务包和资产须先就绪；`CASES` 应使用准备工具生成且核过 source/binding SHA 的完整原生 case 文件。凭据文件与输出保持私有。

```bash
cd /path/to/VideoICLBench/simulation/native-codex-20261106/VideoICLBench
REPO="$(pwd)"
RUNTIME=/opt/videoicl/runtime
GUI_PYTHON=/opt/videoicl/gui-env/bin/python
NATIVE_PYTHON=/opt/isaaclab/python.sh
CODEX=/opt/videoicl/bin/codex
CATALOG=/opt/videoicl/config/model-catalog.json
CATALOG_SHA='REPLACE_WITH_THE_CATALOG_64_HEX_SHA256'
CASES=/opt/videoicl/config/validated-cases-real.json
TASKS=/opt/videoicl/tasks
CREDENTIALS=/opt/videoicl/private/credentials.json
CA_BUNDLE=/opt/videoicl/config/provider-ca.pem
API_GATE=/opt/videoicl/private/api-concurrency.json
RUN_OUT=/opt/videoicl/runs/new-native-codex-run

"$GUI_PYTHON" "$REPO/scripts/harbor/run_embodied_pool.py" \
  --native-python "$NATIVE_PYTHON" \
  --gui-python "$GUI_PYTHON" \
  --runtime-root "$RUNTIME" \
  --task-root "$TASKS" \
  --cases "$CASES" \
  --credentials "$CREDENTIALS" \
  --provider-ca-bundle "$CA_BUNDLE" \
  --api-concurrency-config "$API_GATE" \
  --provider-request-metadata \
  --engine codex --binary "$CODEX" \
  --model gpt-6-astra --effort high \
  --condition real --embodied-harness program_gui \
  --native-structured-tools \
  --codex-model-catalog "$CATALOG" \
  --codex-model-catalog-sha256 "$CATALOG_SHA" \
  --codex-context-window 262144 --codex-compact-tokens 120000 \
  --max-actions 500 --timeout 0 \
  --embodied-auto-recover --unknown-api-policy resume_closed_unknown \
  --epoch handoff-native-codex-v1 \
  --out "$RUN_OUT" --allow-unvalidated-environment
```

`--allow-unvalidated-environment` 是当前工程入口要求，不能把该参数当作物理评分验收通过。`RUN_OUT` 使用新的空路径。不同 room 的 episode ID 必须唯一；运行中的任务输入/配置不热换。示例中没有可用凭据，也不会创建自动巡检。

pool 的 `--provider-request-metadata` 会向新 relay 传递 `--request-metadata`。默认关闭的旁路只记录请求结构计数、cache 身份 SHA、instructions/tools/input-item SHA，以及原 request_id 绑定的数字 usage；原 body/header/SSE 字节保持不变。

## 用量、缓存与压缩如何核对

- 每个 API 请求按原 request_id 去重；记录 input、cached、output、reasoning 和上游实际提供的 cache-write TTL。reasoning 属于 output，不能再加一次。
- 相同 completed 事件去重；usage 冲突显式标记，不能相加或任取一个。缺缓存/失败请求费用保留未知，不填 0。
- 缓存率为 `cached / input`。cache key/header SHA 稳定或前缀 item SHA 相同，只证明请求结构稳定，不能保证 provider 命中缓存。
- native `token_count` 的累计字段用合法差分核对 last usage；不能把每份累计快照相加。compact 后重建的上下文估计也不是新的付费请求。
- 实际 compact 读取私有 native rollout 的 `compacted` / `context_compacted` 持久事件。配置 120000 本身不等于已经发生 compact；摘要费用只有与真实请求唯一锚定后才单列。
- 有效推进同时核对完整 API 响应、MCP 回执和原生动作数。HTTP200 不等于模型完成决策，更不等于任务成功。

## 本地回归与待补实测

| 项目 | 当前状态 | 证据 |
| --- | --- | --- |
| 原生工具、监督器及相关入口回归 | 收集 92 项，91 通过、1 项 opt-in 测试跳过 | `NATIVE_STRUCTURED_TESTS.private.xml`；跳过的是隔离真实 CLI + localhost mock 测试 |
| 新原生工具、监督器与 relay bootstrap 修复 | 35 项通过，已含在上述 92 项中 | 覆盖 typed action schema、污染环境下固定 SDK 入口、24-pair、原生 compact 配置、同 ID 不重放、drain 后评分/关闭 |
| 本轮准备工具约束 | 6 项通过 | `PREPARATION_TESTS.private.xml` |
| 独立 usage/compact/metadata 观察器 | 20 项通过 | `native-audit/READINESS.private.json` |
| relay metadata 与真实 localhost TLS 回归 | 24 项通过 | 同上；只有本机假服务，无付费 API |
| 重复 ID 不重放、未知输入保持、24 pair 计数、公开反馈和图片分离 | 离线合同已覆盖 | 原生工具回归 |
| CLI 普通退出不 seal、真正终态 + API drained 后才评分/关闭 | 离线合同已覆盖 | 监督器回归 |
| 首轮启动尝试 | relay bootstrap 旧 SDK 导入失败；当时 0 模型 API / 0 Codex session / 0 物理动作 | 原故障保留；修复后 run2 已真实启动 |
| run2 首 API 与 bootstrap GUI | 已核对 1440×1280 完整 GUI，含 head/双 wrist、初始 0/500；任务与 assigned instruction 逐字匹配 | 真实首请求合同核对，示范 7.3 秒、按需读取 5 帧 |
| run2 连续动作与反馈 | 同 session 已完成至少 8 批：6/4/11/3/6/10/4/11，共 55 个物理动作；每批一次 Commit、一张末图，逐 pair 公开反馈完整 | 原生动作与 MCP 公开回执交叉核对 |
| run2 缓存与输入增长 | 首请求 input9659 / cached3968；先前后续请求缓存约 87–89%，最新 input62005 / cached57856 / output307（约 93.3%）；两个 Commit 后输入增量示例为 4218/4634 token | snapshot8 为 11 success / 0 failure / 1 in-flight；唯一 session，实际 compact 仍待验证 |
| run2 原生终态、分数和资源释放 | 待真实验证 | 未把阶段动作/HTTP 成功计作整条成功，最终还需 native final snapshot / API drained / 资源证明 |

离线回归和 run2 的真实阶段验证分别记录。run2 已验证首图、工具到原生动作的链路与部分请求缓存效果；完整任务成功、最终评分、实际 compact 及完整费用仍待补齐。后续是否扩展评测依据完整结果决定。

表中的 `.private.*` 文件是维护者保存的审计索引，不属于运行依赖；公开代码交付不包含凭据、私有 profile 或原始模型对话。

## 代码位置

- `packages/sdk/vic_sdk/embodied_agent.py`：专用 native 入口、私有 profile 与原生 CLI 参数。
- `packages/sdk/vic_sdk/embodied_codex_mcp.py`：结构化公开工具、图片分离、durable 操作记录与历史查询。
- `packages/sdk/vic_sdk/embodied_codex_mcp_entry.py`：固定 SDK 来源的绝对路径入口。
- `packages/sdk/vic_sdk/native_structured_supervisor.py`：原会话恢复、保持未评分现场、原生终态与 API 排空检查。
- `packages/sdk/vic_sdk/robodawn_turn_executor.py`：复用可见 GUI 队列和一次 Commit；该层不调用模型。
- `packages/sdk/vic_sdk/tls_relay.py`：原字节转发、完整响应排空、可选 request/usage 元数据。
- `packages/sdk/vic_sdk/tls_relay_entry.py`：绝对路径 bootstrap，清除预加载的旧 SDK 模块并核对真实来源。
- `scripts/harbor/run_embodied_pool.py`：原生 pool、逐 room 绑定、进程归属与 relay 参数。
