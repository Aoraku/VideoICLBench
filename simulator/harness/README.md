# 具身评测 Harness

所有模型新跑时统一使用同一套多房间并发执行入口： [coalesced/](coalesced/README.md)。一池一个 IsaacSim 进程，各房间独立调用模型，原生仿真主线程收集和执行已提交动作。完整任务和结果入口见[数据交接](../HANDOFF.md)。

| 入口 | 使用场景 |
| --- | --- |
| [coalesced/pool_verified.py](coalesced/pool_verified.py) | 当前多房间执行池，支持单独诊断和模型执行。 |
| [coalesced/bootstrap_verified_room.py](coalesced/bootstrap_verified_room.py) | 把任务、示范与 GUI 身份绑定到指定房间。 |
| [coalesced/worker/](coalesced/worker/) | Astra/Codex、Opus/Claude Code、DeepSeek、GLM、Qwen、Kimi、Gemini 的 CLI 适配与本机 API relay。 |
| [coalesced/VideoICLBench/packages/sdk/vic_sdk/](coalesced/VideoICLBench/packages/sdk/vic_sdk/) | GUI、MCP、动作预算、原生回执和评分读取协议。 |
| [coalesced/runtime-overlay/](coalesced/runtime-overlay/) | 原生房间调度、空闲房间状态恢复和控制器覆盖文件。 |
| [原生 Codex Harness](../native-codex-20261106/README.md) | 复现 Astra 已归档的 11 月 6 日配置。 |
| [gui_driver.py](gui_driver.py) | 早期 MuJoCo 原型的浏览器 GUI 驱动。 |

`coalesced/VideoICLBench` 是发布用的独立 Python 包。其旁边的 `process_launcher.py` 与 SDK 使用相对路径绑定，复制到自己的机器时应保留这一层目录结构。模型 CLI 和 IsaacLab 使用部署机器安装的版本，具体环境变量与命令见 [coalesced 安装说明](coalesced/README.md)。
