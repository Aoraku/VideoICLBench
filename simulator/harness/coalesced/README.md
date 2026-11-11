# 同池并发具身评测 Harness

本目录包含同池并发的原生仿真调度、每房间模型 worker、GUI SDK 和 API relay，DeepSeek / GLM 消融使用了这套实现。Astra 的 Codex 和 Opus 的 Claude Code 复现入口见 [11 月 6 日交付](../../native-codex-20261106/README.md)。数据、版本与实验口径见 [交接文档](../../HANDOFF.md)。

一个 pool 启动一个 IsaacSim 进程，每个房间有自己的 GUI、模型 CLI、API relay 和原生身份。传入 `--coalesce-window-seconds .05` 后，收到动作的房间至多等 50 ms 收集同批动作，再由仿真主线程执行。50 ms 是收集窗口，已有仿真和渲染仍可能造成排队。等待模型的房间在其他房间步进时恢复自己的机器人关节与刚体状态。需要物理隔离的任务应按固定环境清单独立实例化。

`SOURCE_MAP.json` 记录部署源和交付文件的 SHA-256。代码移植时把模型 CLI、浏览器、API 地址及 CA 文件路径改为部署参数，保留各 worker 的模型和推理设置。SDK 另带 GUI 先写完关闭回执、再退出的修复。交付包已做本地调度和协议回归，首次在新环境使用前先跑无模型诊断。

## 安装

使用 Linux、NVIDIA GPU 和与资产相容的 IsaacSim / IsaacLab。GUI Python 可单独安装，原生 Python 同样需要 `setproctitle==1.3.6`。从固定版本的 HF 数据集下载基础仿真运行时。已有完整 runtime 的机器可以直接把该目录交给 `--base-runtime`。

```bash
# 下载基础运行时
hf download JJimmyL/VideoICL-Embodied-Handoff-20261103 --repo-type dataset \
  --revision 99057ec5bc1a6b5655fb15d953aa77b6a9e94f8d \
  --include 'full50-current/runtime/*' --local-dir /work/videoicl/assets

# 从本目录执行
python3 -m venv .venv
.venv/bin/python -m pip install -e 'VideoICLBench[test]'
.venv/bin/python -m playwright install chromium

.venv/bin/python prepare_runtime.py \
  --base-runtime /work/videoicl/assets/full50-current/runtime \
  --out /work/videoicl/runtime-coalesced

.venv/bin/python pool_verified.py --help
```

`--cases` 使用 [cases.example.json](cases.example.json) 的字段。把任务包、机器人 profile 和物体 bindings 绑定到本机文件，保留固定的 task、variant、seed、R/I/E 和输入条件。Harbor 任务包的 `instruction.md` 与 `environment/native.json` 必须匹配，规则放在 `tests/rule.json`，视频文件及 SHA-256 写在 `demo` 或 `demo_sim`。按 HF `benchmark/assignments.jsonl` 选择输入并核对哈希。示例路径是占位符。

## 当前 worker 的固定配置

`pool_verified.py --engine` 选择下表的 worker 配置。模型名、推理等级、窗口和压缩设置由 worker 与其原生 CLI 适配器写入。表内数值是代码配置，实际压缩事件和提供方支持情况由每回合日志记录。

| engine | 模型 | effort | 配置的 context window | 原生自动压缩设置 |
| --- | --- | --- | ---: | --- |
| `dsh` | `deepseek-v4.1-flash-1017` | `high` | 1,048,576 | 阈值 150,000，写入 DSH 原生 compaction 配置。 |
| `zcode` | `glm-5.3-flash` | 请求 `high`，relay 的提供方请求也固定为 `high` | 184,000 | ZCode 按原生公式 `contextWindow - min(normalRequestMaxOutputTokens, 21000) - 13000` 计算。输出预算达到 21,000 时预计阈值为 150,000，实际以原生事件为准。 |
| `kimi` | `kimi-k3` | `high`，开启 thinking | 262,144 | 配置阈值 150,000，对应原生 `compaction_trigger_ratio=150000/262144`，预留 112,144 token。 |
| `qwen`，通过 Claude Code | `qwen3.8-max` | `high` | 1,000,000 | 自动压缩窗口设为 150,000，比例为 80%，名义触发点约 120,000。实际触发由 Claude Code 的原生上下文计算决定。 |
| `gemini` | `gemini-4-argon` | `high` | 1,048,576 | 原生 `compressionThreshold=150000/1048576`。 |

配置来源见 [worker 的模型表与选项](worker/run.py#L17)、[DSH adapter](worker/adapters/dsh.py#L155)、[ZCode adapter](worker/adapters/zcode.py#L122)、[GLM 提供方 effort 映射](worker/zcode_effort.py#L11)、[Kimi adapter](worker/adapters/kimi.py#L27)、[Claude Code 参数](VideoICLBench/packages/sdk/vic_sdk/claude_structured.py#L25) 和 [Gemini adapter](worker/adapters/gemini.py#L37)。

`pool_verified.py` 保留的通用参数 `--model`、`--effort`、`--codex-context-window`、`--codex-compact-tokens` 和 `--binary` 尚未传入当前房间 worker。填写这些参数不会覆盖上表。CLI 路径使用后文的 `VIC_CLI_*` 环境变量。修改运行配置时应在新副本中调整 worker 配置，再核对新 profile 和实际请求记录。[房间启动参数](pool_verified.py#L121) · [worker 参数生成](worker/run.py#L80)

## 运行

`pool_verified.py` 负责启动和回收单个执行池。每个输出目录对应一次执行。诊断和模型运行均可传 `--coalesce-window-seconds .05` 选择短窗口调度。

```bash
.venv/bin/python pool_verified.py \
  --native-python /opt/isaaclab/python.sh --gui-python "$PWD/.venv/bin/python" \
  --runtime-root /work/videoicl/runtime-coalesced --cases /work/videoicl/cases.json \
  --engine dsh --epoch local-probe-01 --out /work/videoicl/probe-01 \
  --max-actions 8 --timeout 120 --probe-only \
  --allow-unvalidated-environment
```

用 `VIC_POOL_AUTHFILE` 指向本机权限为 0600 的密钥文件。普通引擎需要一行 key 和 `VIC_UPSTREAM_ORIGIN`，模型 API 路径由 relay 拼接。Gemini 使用含 `primary` 和 `fallback` 字段的单行 JSON，分别配置 `VIC_GEMINI_PRIMARY`、`VIC_GEMINI_FALLBACK`。私有代理 CA 可通过 `VIC_PROVIDER_CA_BUNDLE` 提供。若浏览器由系统安装，可加 `--browser-path`。依赖 Node 的 CLI 由本机提供匹配的 `node`。

| 引擎参数 | CLI 路径变量 |
| --- | --- |
| `dsh` | `VIC_CLI_DSH` |
| `zcode` | `VIC_CLI_ZCODE` |
| `qwen`，通过 Claude Code | `VIC_CLI_QWEN` |
| `kimi` | `VIC_CLI_KIMI` |
| `gemini` | `VIC_CLI_GEMINI` |

```bash
export VIC_CLI_DSH=/opt/dsh/bin/dsh
export VIC_UPSTREAM_ORIGIN=https://your-provider.example
export VIC_POOL_AUTHFILE=/work/videoicl/secrets/dsh.key

.venv/bin/python pool_verified.py \
  --native-python /opt/isaaclab/python.sh --gui-python "$PWD/.venv/bin/python" \
  --runtime-root /work/videoicl/runtime-coalesced --cases /work/videoicl/cases.json \
  --engine dsh --epoch local-model-01 --out /work/videoicl/model-01 \
  --embodied-harness program_gui --native-structured-tools \
  --coalesce-window-seconds .05 --max-actions 500 --timeout 0 \
  --allow-unvalidated-environment
```

一次 `action_batch` 提交一组动作，执行后返回最新 GUI，随后模型可继续提交。示范、历史与深度由对应工具按需读取。每条物理回合 500 个动作，无墙钟时间限制。运行目录含控制凭据与私有日志，发布时使用经过白名单过滤的轨迹导出。

成绩取自各房间的原生封存终态。`episode.json` 中的 `native_success` 和 `score_100` 保存原生成功状态与工程分，缺分为 `null`。

## 本地回归

```bash
PYTHONPATH=VideoICLBench/packages/sdk:VideoICLBench/tests \
  .venv/bin/python -m pytest -o addopts='' tests/test_coalesced_pool.py \
  VideoICLBench/tests/test_embodied_environment.py -k 'not fake_cli'
```
