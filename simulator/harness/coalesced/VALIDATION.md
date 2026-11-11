# 2026-11-12 统一 Harness 验证

本次发布使用同一 pool、bootstrap、GUI/MCP、worker attempt_loop、原生身份与评分入口，按CLI/API协议接入模型。Astra/Codex 与 Opus/Claude Code 已加入同一流程；默认 coalescing 窗口50ms，已就绪房间不等其他房间的模型响应。

在隔离 Python 3.13 环境安装本包声明的测试依赖后运行：

```bash
PYTHONPATH=VideoICLBench/packages/sdk:VideoICLBench/tests \
  python -m pytest -q -o addopts='' tests \
  VideoICLBench/tests/test_embodied_environment.py
```

结果：58 passed，3 subtests passed。包含七种engine的入口与参数透传、Codex完整catalog容量校验与exec/resume配置、Claude持久化配置、初图只在首轮附带、原session恢复、GLM不支持配置的明确拒绝、Responses完整/失败/截断/压缩流与用量去重、本机HTTP/MCP、合成GUI与同池ready-room推进。测试是离线回归，未调用真实模型API或启动GPU仿真。新机器首次执行仍需按README运行无模型物理诊断并核对安装CLI/提供方兼容性。

历史评测数据保持其实际运行版本。此次发布不会使已经结束的Astra/Opus轨迹变为新版harness产生的数据。
