# Harness 目录迁移

新版具身 Harness 已集中到 [simulator/harness/coalesced](../../simulator/harness/coalesced/README.md)。安装、任务绑定、API 配置和测试命令见该目录。完整数据交接见 [simulator/HANDOFF.md](../../simulator/HANDOFF.md)。

原有 `pool_verified.py`、`bootstrap_verified_room.py` 和 `prepare_runtime.py` 命令会转到新目录。安装 Python 包时使用 `simulator/harness/coalesced/VideoICLBench`。
