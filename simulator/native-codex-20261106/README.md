> 历史实验归档。所有模型的新评测统一使用[最新同池并发 Harness](../harness/coalesced/README.md)。

# 原生 Codex 具身 harness

本目录提供 Astra 物理执行用的 SDK、GUI、pool runner 和本机 API relay。与 [本批实验配置](../astra-iclworld-20261106/README.md) 配套使用。安装步骤见 [INSTALL.md](INSTALL.md)，原生物理环境的装配见 [RUNTIME.md](../astra-iclworld-20261106/deploy/RUNTIME.md)。

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
| QA | 物理执行不嵌入 QA；独立 QA 入口在相邻实验目录 |

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

## 启动与恢复

物理入口为 VideoICLBench/scripts/harbor/run_embodied_pool.py。使用相邻实验目录的 prepare_pool.py 生成当前机器的命令。核对身份和输入条件后启动新的输出目录；恢复在原 profile 和世界里进行。参测进程只使用该条件允许的工具。模型看到的 GUI、原生动作回执以及内部评分文件分别处理。

单条先导实验的历史核对见 [试运行记录](docs/PILOT_VALIDATION.md)。正式复现配置请使用本分支的实验清单。
