# 原生 Codex 具身 harness 交接

发布目录：[Aoraku/VideoICLBench · codex/embodied-all-handoff-20261103 · simulation](https://github.com/Aoraku/VideoICLBench/tree/codex/embodied-all-handoff-20261103/simulation)。

- [运行流程与可移植启动示例](native-codex-20261106/README.md)
- [完整交接合同与验收状态](native-codex-20261106/docs/HANDOFF_NATIVE_CODEX.md)
- [安装与外部 runtime/任务资产映射](native-codex-20261106/INSTALL.md)
- [源码逐文件映射与 SHA](native-codex-20261106/SOURCE_MAP.json)
- [run2 最终工程结果](LIVE_VALIDATION.md)

本版保留真正 Codex 连续会话：raw window262144、原生compact120000、500物理动作、episode无时间上限。
首轮 relay bootstrap 因旧 SDK 导入失败，当时模型 API/session/物理动作均为 0。修复后的 run2 已在唯一 Codex CLI 0.163.0 session 中完成 130 个物理动作、18 次 Commit，Done 工程评分100/100、success=true（validation_only=true、scientific_evaluation=false）。最终27个上游请求全部成功，0失败、0在途；精确 input1769349、cached1533824、uncached235525、output6100，总 token1775449。原生 compact 1次，压缩后同会话 observe→Done，没有再执行物理动作。独立核查确认本轮 live进程0/GPU进程0，上游已排空、uncertain=false。CLI exit1 源于 Done 后两次本地410保护拒绝（forward_attempts=0），未计作上游失败或clean exit0。共享GPU仍有他人9488MiB显存占用，保持原样。
上游相关回归共92项（91通过、1个opt-in用例跳过）。离线通过不等于模型或物理实测成功。
本目录只含代码、测试与说明；runtime、任务/视频/资产和私有运行配置由启动参数提供。
