# OS-ICL 原生 Agent 验收

入口：http://127.0.0.1:18765/ → **OS · 36 题**。共 36 题、108 段配套示范，使用现有平台密钥和 SSH 隧道。

抽样包含选择、恢复、跨应用三类，均为版本 A、执行 seed 20261005；Codex 使用 GPT-5.5，Claude Code 使用 Sonnet 4.6。模型通过示范帧学习规则，以截图和坐标键鼠执行任务。

| 任务 | Codex | Claude Code |
|---|---|---|
| OS-SEL-01 · 文件属性选择 | success | success |
| OS-REC-01 · 文件冲突恢复 | success | fail |
| OS-XAPP-01 · 日志 → 文件管理器 | fail | success |

六条验收运行均由原始 evaluator 返回 success/fail，且没有 GUI 工具错误。五条运行正常退出并显式 finish；CC 恢复题达到 $1.5 原生费用上限，控制器按实际环境提交评分为 fail（4/6 个业务步骤）。预算终止保留原生退出码和原因，不属于模型 API 或平台通信故障。

这是接口验收样本，不是稳定成功率估计。CC 的跨应用题在全部完整运行中有两次 fail、一次 success；失败轨迹缺少来源记录的 inspect 动作。完整运行及诊断记录见 [机器可读验收记录](os-icl-agentlab.json)。

恢复类任务公开显示 Index，并明确要求按 Index 升序处理；每个对象内部的两步策略由示范教授。原 evaluator、隐藏策略及 canonical 视频均使用上游实现和资源。

资源校验覆盖 108 段视频；界面检查覆盖 36 题及恢复类的序号可见性。上游测试 16 项、平台测试 2,215 项、最终适配检查 20 项通过。验收不录制新视频。

使用与维护命令见 [OS-ICL 团队任务](../os-icl.md)。
