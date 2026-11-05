# 原生 Codex run2：最终单条工程结果

本页依据维护者核对的 snapshot18 与首请求合同证据，记录这条运行的原生结果。原始审计件保持私有；本页不发布图像数据、凭据或 session 私有路径。

## 结果

| 项目 | 最终核对结果 |
| --- | --- |
| 运行引擎 | 真正 Codex CLI **0.163.0**，全程唯一原生 session |
| 物理动作 / Commit | **130 / 18**；物理预算按动作对计数 |
| 原生终态 | **Done** |
| 工程评分 / 成功 | **100/100，success=true** |
| 评测属性 | **validation_only=true，scientific_evaluation=false** |
| 真实上游请求 | **27 次成功、0 次失败、0 次在途** |
| 原生 compact | **1 次**，120k 配置触发后完成原会话收尾 |
| 独立资源核查 | **本轮 live 进程0、GPU进程0**；native/GUI/relay/model 均已退出 |
| CLI 退出状态 | **exit1**，由 Done 后2次本地410保护拒绝导致；这两次均未转发上游 |

首轮 relay bootstrap 曾因导入旧 SDK 失败，当时模型 API、Codex session 和物理动作均为 0。固定源码的绝对路径 relay 入口修复后，run2 得到以上真实结果；原故障历史保留。

## 首图、任务与动作合同

- 初始完整 GUI 为 **1440×1280**，维护者实际查看了 head、左右 wrist 三路视图及初始 **0/500** 动作计数。
- 首请求任务与 assigned instruction **逐字匹配**。
- assigned video 时长 **7.3 秒**；模型通过 `demo_frames` 按需读取 **5 帧**。
- 同 session 实际执行了 `demo_frames → depth_points → observe → action_batch`。最终完成 18 次 Commit、130 个物理动作；每批经原 GUI 队列后一次 Commit，轮末新图及逐 pair 公开反馈合同已验证。
- 原生 runtime 等待下一请求时仅 sleep、不调用物理 step（`scripts/serve_realworld_room_pool.py:348–349`）；网络等待期间仿真不会自行推进。

## 精确用量

provider 逐请求记录与 native 用量精确核对：

| 计量项 | Token |
| --- | ---: |
| input | **1,769,349** |
| cached input | **1,533,824** |
| uncached input | **235,525** |
| output | **6,100** |
| input + output | **1,775,449** |

cached 与 uncached 是 input 的分桶；reasoning 已包含在 output 中，均不能再次相加。摘要请求也已包含在以上总额中。

先前快照中，首请求 input/cached 为 **9,659/3,968**；后续请求曾观察到约 **87–89%** 缓存率，snapshot8 的单次请求为 **62,005 input / 57,856 cached / 307 output**（约 **93.3%**）。这些是历史单次样例，不是最终累计数。两个 Commit 后的输入增长样例 **4,218/4,634 token** 也不代表每个物理动作固定消耗。

## 真正的原生 compact 与同会话收尾

配置为 raw window **262144**、自动 compact 阈值 **120000**。本轮实际发生 **1 次 Codex 原生 compact**：

| 请求 | input | cached | output |
| --- | ---: | ---: | ---: |
| 原生摘要请求 | **120,473** | **3,968** | **902** |
| 压缩后的请求26 | **8,373** | **3,968** | **15** |
| 压缩后的请求27 | **11,891** | **8,192** | **73** |

摘要请求费用对应的 token 已包含在整条总额中。压缩后模型在同一原生 session 中继续 **observe → Done**，随后得到真实原生终态与工程评分。压缩后没有再次执行物理动作；本轮验证的是原会话续接和正确收尾。

## 收尾状态

原生终态、工程评分、完整 token 账和27个真实上游HTTP200请求已核对。API已排空，`uncertain=false`。

Done 后发生2次本地 `410 episode_closed / admission_rejected`，两次 `forward_attempts=0`，没有发送到上游。因此 CLI 记录为 **exit1**，属于终态后 admission 保护拒绝；不是上游失败，也不记作 clean exit0。

独立只读资源核查的 SSH 返回0，完整回传通过双SHA校验。native、GUI、relay、model 进程均已退出；controller/pool 按精确 PID/start_ticks 核对仅剩 Z 状态条目，本轮 live进程0、GPU进程0。核查时共享GPU上其他用户 UID65534 仍使用9488MiB显存，该占用保持原样。
