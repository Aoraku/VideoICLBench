# 原生 Codex 具身 harness 交接

发布目录：[Aoraku/VideoICLBench · codex/embodied-all-handoff-20261103 · simulation](https://github.com/Aoraku/VideoICLBench/tree/codex/embodied-all-handoff-20261103/simulation)。

- [运行流程与可移植启动示例](native-codex-20261106/README.md)
- [完整交接合同与验收状态](native-codex-20261106/docs/HANDOFF_NATIVE_CODEX.md)
- [安装与外部 runtime/任务资产映射](native-codex-20261106/INSTALL.md)
- [源码逐文件映射与 SHA](native-codex-20261106/SOURCE_MAP.json)

本版保留真正 Codex 连续会话：raw window262144、原生compact120000、500物理动作、episode无时间上限。
首轮 relay bootstrap 因旧SDK导入失败，模型API/session/物理动作均为0；固定绝对入口修复后离线新35项通过，真实运行验证仍待完成。
上游相关回归共92项（91通过、1个opt-in用例跳过）。离线通过不等于模型或物理实测成功。
本目录只含代码、测试与说明；runtime、任务/视频/资产和私有运行配置由启动参数提供。
