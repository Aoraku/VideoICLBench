# 原生 Codex 具身 harness 交接

发布目录：[Aoraku/VideoICLBench · codex/embodied-all-handoff-20261103 · simulation](https://github.com/Aoraku/VideoICLBench/tree/codex/embodied-all-handoff-20261103/simulation)。

- [运行流程与可移植启动示例](native-codex-20261106/README.md)
- [完整交接合同与验收状态](native-codex-20261106/docs/HANDOFF_NATIVE_CODEX.md)
- [安装与外部 runtime/任务资产映射](native-codex-20261106/INSTALL.md)
- [源码逐文件映射与 SHA](native-codex-20261106/SOURCE_MAP.json)
- [run2 真实阶段验证](LIVE_VALIDATION.md)

本版保留真正 Codex 连续会话：raw window262144、原生compact120000、500物理动作、episode无时间上限。
首轮 relay bootstrap 因旧 SDK 导入失败，当时模型 API/session/物理动作均为 0。修复后的 run2 已在 slot2 启动 Codex CLI 0.163.0：完整首图、同 session 工具链、8 个 Commit / 至少 55 个物理动作及逐 pair 反馈已核对。snapshot8（17:57:55Z）为 provider 11 次成功 / 0 次失败 / 1 次在途；最新请求 input62005、cached57856、output307，缓存率约 93.3%。实际 compact、完整终态、评分和资源释放仍待验证。
上游相关回归共92项（91通过、1个opt-in用例跳过）。离线通过不等于模型或物理实测成功。
本目录只含代码、测试与说明；runtime、任务/视频/资产和私有运行配置由启动参数提供。
