# VideoICL 具身数据与代码交接

本文面向接手数据分析和复现实验的同学。题目、模型输入、执行轨迹和代码均可通过下面的公开链接下载。查看视频、文字、动作、步数和分数可在自己的电脑完成。

本次快照交付 150 组题目材料、1,237 条已封存回合的完整留存原图、完整观察回放与模型输入文字。两条未完成 GLM 回合在索引中预留，待后续补充。

## 下载入口

| 内容 | 公开入口 | 主要文件 |
| --- | --- | --- |
| 50 题 A/B/C、消音 real/sim、prompt 和文字规则 | [Demo 与输入数据集](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Demos50) | `TASK_INDEX.md`、`tasks/`、`archives/` |
| 实际评测输入与每个模型保存的文字上下文 | [固定评测输入](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Demos50/tree/main/evaluation) · [模型输入](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Demos50/tree/main/model_inputs) | `assignments.jsonl`、`cases/`、`model_inputs/`、`input_archives/` |
| 六模型执行轨迹、步数、分数、完整观察视频和原图 | [轨迹数据集](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Evaluation-Trajectories-Public) | `episodes.csv`、`episodes.parquet`、`full_observations/`、`full_replays/` |
| 机器人、场景、USD、纹理与物体资产 | [仿真资产数据集](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Handoff-20261103) | `full50-current/`、`g2-ur5-v1/` |
| 代码与运行说明 | [main/simulator](https://github.com/Aoraku/VideoICLBench/tree/main/simulator) | [当前 Harness](harness/coalesced/README.md) · [Harness 导航](harness/README.md) |

## 先查看一题

打开 Demo 数据集的 `TASK_INDEX.md`，选择任务和 A/B/C 规则版本。例如 `tasks/E01/C/` 下有以下文件。

| 文件 | 内容 |
| --- | --- |
| `real.mp4` | 真实示范，无音轨，H264。 |
| `sim.mp4` | 对应规则的仿真示范，无音轨，H264。 |
| `prompt.md` | 题目目标与作者设计的完整执行目标。 |
| `text_rule.md` | text 输入使用的 A/B/C 局部规则。 |
| `task.json` | 规则、任务构造、环境支持、评分设计、视频来源和哈希。 |

共 150 组材料、150 段 real 和 150 段 sim。真实示范从源 HEVC 转为便于浏览的 H264，校验帧数、方向、时长与零音轨。仿真示范保留 H264 视频流并去音轨。E37 的三段仿真示范使用后补固定版本，来源记录在各 `task.json` 中。

HF 查看器的 `task_catalog` 配置直接显示 `prompt_text` 与 `text_context` 正文；`model_inputs` 配置直接显示逐回合 `initial_prompt_text`。也可下载对应 Markdown 阅读。

`archives/` 按每十题打包，解压后得到同样的目录。逐文件 SHA-256 见 `FILE_MANIFEST.jsonl`，压缩包校验信息见 `ARCHIVES.json`。

## 查模型实际收到的内容

`evaluation/assignments.jsonl` 固定 255 个物理配置，含 task、variant、R/I/E、seed、输入模式和实验归属。每个 `evaluation/cases/<episode_id>/` 单独提供可读的 `instruction.md` 和 `case.json`。text 条件另有 `text_rule.md`。该目录保留当次评测的环境附加目标和任务指令。

`evaluation/media/` 提供实际输入视频的 101 段消音发布版。每段记录发布文件 SHA-256，以及原评测文件的 `evaluated_input_sha256`。`downloads/fixed-evaluation-inputs.tar.gz` 一次下载固定配置、文字和视频。

`model_inputs/<model>/<experiment>/<task>/<case>/` 对应一个模型的物理回合，包含以下输入记录。

| 文件 | 内容 |
| --- | --- |
| `initial_user_prompt.txt` | 宿主保存的初始任务 prompt，包含该模式的任务、文字规则、示范元信息和初始公开状态。 |
| `worker_instruction_fragments.json` | 已保存 worker 中可溯源的附加指令和版本信息。 |
| `public_context.jsonl` | 按序保存模型主动观察、动作执行、历史、深度查询等工具产生的公开文字上下文，图像以哈希关联。 |
| `first_recorded_user_message.json` | 从该回合原生会话记录提取的首条实际 user 消息。 |
| `native_input_messages.jsonl` | 原生会话中已保存的 user、system、developer、tool 输入记录。 |
| `native_conversation_messages.jsonl` | 另保留可见 assistant 文字、工具调用和公开会话输入，便于查看后续请求所用的对话历史。 |
| `native_conversation_coverage.json` | 对话投影的日志来源、重复记录与顺序说明。 |
| `input.json`、`native_input_coverage.json` | 输入来源、公开配置、源日志 SHA-256、记录数量与覆盖范围。 |

原生记录的首条 user 消息可能是 CLI 自动加入的环境说明，后续任务正文和工具返回按 `source_record_index` 保留在 `native_input_messages.jsonl` 中。

宿主 prompt 后可能追加 worker 指令，原生 CLI 还会生成系统内容与 compact 上下文。各文件按实际留存范围记录来源。公开对话投影保留来源文件和记录序号，不能直接拼成每次请求的精确 wire 内容。`public_context` 留存全部公开工具事件，不代表每次请求都发送全部事件；Token 用量应读取提供方请求用量，不能直接相加会话记录的文字长度。复现时同时记录模型、CLI 版本、工具定义、窗口和 compact 配置，具体参数见对应 Harness 和回合元数据。

`MODEL_INPUT_INDEX.csv` 和 `MODEL_INPUT_INDEX.jsonl` 按模型、题目和逻辑回合列出 prompt、原生输入消息、公开上下文与覆盖文件的直接路径。`prompt_templates/standalone-qa/` 另有独立视频 QA 的首轮文字、工具说明和窗口设置。

`downloads/prompts-and-context-templates.tar.gz` 打包题目 prompt、text 规则、固定评测指令、QA 题目与 Harness 模型/工具文字。`input_archives/all-saved-model-inputs.tar.gz` 一次下载所有已封存回合留存的模型输入文字和公开对话历史。其余分片包按模型和回合组织，解压到同一 `model_inputs/` 目录。使用文字模式时把 `instruction` 与对应 `text_rule` 作为输入。视频模式使用指令和指定 real/sim 视频。none 模式使用该条件下的任务指令。

## 查执行轨迹

先下载 `episodes.csv`，即可查看模型、题号、A/B/C、环境、输入模式、步数、原生成功与工程分。JSONL 适合逐行处理，Parquet 适合 pandas/Arrow。表间共用回合通过 `logical_episode_id` 和模型关联，`experiments` 记录归属。跨模型比较使用 `task_id`、`variant`、`environment`、`input`、`seed` 共同匹配，逻辑 ID 的批次前缀可能不同。

每个回合的基础目录采用 `<model>/<experiment>/<task>/<variant>-<environment>-<input>-s<seed>/`。

| 文件或索引 | 内容 |
| --- | --- |
| `episode.json` | 回合身份、终态原因、分数来源、动作数、媒体引用和哈希。 |
| `actions.jsonl.gz` | 完整已确认动作及原生回执，step 从 1 连续到动作总数。 |
| `final_head.jpg`、`final_left_wrist.jpg`、`final_right_wrist.jpg` | 封存时三路相机图像。 |
| `observations.mp4` | 便于快速浏览的采样观察回放。 |
| `observations.jsonl`、`frames.zip` | 采样回放的步数映射与可解包帧。 |
| `supplement.json` | 原生耗时、墙钟时间、基础设施等待、请求用量、完整帧数量和大文件归档引用。 |
| `full_replays/` | 使用全部已保存 GUI 事件生成的原尺寸无音视频。 |
| `full_observations/` | 完整原图、公开事件、原生终态条件和逐请求用量的分片归档。 |

完整归档内，`original_images/` 保留原 PNG/JPEG 字节和逐图哈希，`public_events.jsonl` 关联观察、动作和深度等公开工具数据。`native_conditions.json` 保存原生终态条件，`terminal.json` 保存步数和各类耗时，`api_requests.jsonl` 保存已记录请求的用量字段。`FILES.jsonl` 校验包内文件，`COVERAGE.jsonl` 给出每条回合的覆盖信息。

观察视频按 4 fps 回放保存的观察事件，播放时长由帧数决定。实际运行耗时在终态元数据中。动作之间的物理过程按当时保存的材料提供。

`native_success` 保留原生回执的 success 值，`score_100` 是记录的工程分，`score_source` 标明来源。几何验收的验证状态按各原生条件文件保留，工程分不直接等同于正式验收。缺分为 `null`。Token 字段保留提供方原始名称，缓存计数及可用请求范围在 `api_usage` 中注明。Astra 与 Opus 的原生 CLI 逐回合补充审计在 `cli_usage/`，索引中的 `audited_*` 列使用去重响应的小计，不把累计计数再次相加；没有保存用量的请求计费仍为未知。

## 实验与进度

主表用 50 题固定 C，每题 text 和 real 各一次，共 100 条。泛化使用同一组 17 题，支持的 R/I/E 与 text/real 配置共 92 条，其中 34 条复用主表，去重后每模型 158 条。完整消融另加 sim 46 条、A/B 视频 34 条、none 17 条，共 255 条。

R 为按视频复现的场景，I 更换物体，E 使用新环境。支持范围见 Demo 数据集的 `environments/`，实际配置见固定清单。

| 模型 | 原生终态 / 固定物理回合 | 原生成功 | 有工程分 | 已评分子集平均 / 100 |
| --- | ---: | ---: | ---: | ---: |
| Astra | 255 / 255 | 59 | 255 | 28.471 |
| Opus 5.5 | 158 / 158 | 42 | 158 | 34.378 |
| DeepSeek Flash 1017 | 255 / 255 | 19 | 222 | 13.243 |
| GLM-5.3-Flash | 253 / 255 | 9 | 226 | 8.789 |
| Kimi K3 | 158 / 158 | 0 | 152 | 2.862 |
| Qwen3.8-Max | 158 / 158 | 8 | 141 | 10.461 |

表中均分只使用该模型已经记录工程分的回合。模型实验范围和缺分数量不同；这张表用于交接核数，模型对比需按相同任务和条件取交集。

完整原图共 44,655 张，完整原始观察归档共 54 个分片，独立完整 GUI 事件回放 1,237 段。留存原生输入消息为 66,316 条，公开对话投影为 230,337 条。投影可能含原日志镜像条目，不是API请求数。

本次交付快照有 1,237 条原生终态，GLM E41C-I-text 与 E45C-I-text 两条待补。独立视频 QA 共 153 个首答，保存在轨迹库的 `qa.parquet` 与 `qa.jsonl`。题库和作者答案放在 Demo 库，模型首答与判分放在结果库。

## 下载到自己的电脑

安装 `huggingface_hub` 后可使用以下命令，公开材料可匿名读取。

```bash
python3 -m pip install huggingface_hub
hf download JJimmyL/VideoICL-Embodied-Demos50 --repo-type dataset \
  --local-dir ./videoicl-inputs
hf download JJimmyL/VideoICL-Embodied-Evaluation-Trajectories-Public --repo-type dataset \
  episodes.csv episodes.parquet qa.parquet README.md \
  --local-dir ./videoicl-trajectories
```

只查看模型输入文字时，可先下载索引与单个文字包。

```bash
hf download JJimmyL/VideoICL-Embodied-Demos50 --repo-type dataset \
  MODEL_INPUT_INDEX.csv input_archives/all-saved-model-inputs.tar.gz \
  downloads/prompts-and-context-templates.tar.gz \
  --local-dir ./videoicl-inputs
tar -xzf ./videoicl-inputs/input_archives/all-saved-model-inputs.tar.gz \
  -C ./videoicl-inputs
```

再把 `downloads/prompts-and-context-templates.tar.gz` 解压到同一目录，即可同时查看题目文字和 Harness 文字模板。

先读轨迹索引，按回合的归档和视频引用下载所需文件。HF 的 `full_observations/README.md` 列出分片与大小，避免一次下载所有原图。离线解包后可直接用播放器和文本编辑器查看。

## 最新统一代码入口

新评测的所有模型统一使用 `harness/coalesced/pool_verified.py`：Astra 选 `--engine codex`，Opus 选 `--engine claude`，其余模型选择对应 CLI adapter。默认 50ms 收集窗口，各房间独立发模型请求，已就绪房间无需等其他模型响应。各模型共用 GUI/MCP、动作执行、恢复和原生评分流程。配置及适配差异见 [统一 Harness README](harness/coalesced/README.md)。

以下数据版本记录已经完成的历史实验；更新发布代码不会改变那些实验真实使用的版本。

`simulator/harness/coalesced/` 集中当前多房间 Harness、CLI worker、GUI SDK、原生调度覆盖文件、安装说明和回归测试。每房间独立请求模型，仿真主线程通过短窗口合并已经提交的动作，空闲房间保存和恢复刚体、关节状态。

`simulator/astra-iclworld-20261106/` 保留 Astra 固定实验、QA 和运行时装配，`simulator/native-codex-20261106/` 对应归档 Codex 配置。历史 MuJoCo 套件从 `simulator/README.md` 的历史入口进入。

新机器运行仿真时准备匹配的 Linux、GPU 驱动、IsaacLab/IsaacSim、模型 CLI 和浏览器。数据浏览与下载按上面的公开材料完成。安装和启动步骤见 [Harness README](harness/coalesced/README.md)。

## 本次交付的固定版本

| 材料 | 固定版本 |
| --- | --- |
| Demo、prompt 与模型输入 | [6850489d7886334cb0d463f08ceb9eea461227bd](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Demos50/tree/6850489d7886334cb0d463f08ceb9eea461227bd) |
| 模型结果与完整执行轨迹 | [0a84cd0305240eb98512b71e429ac9f0a6e9f304](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Evaluation-Trajectories-Public/tree/0a84cd0305240eb98512b71e429ac9f0a6e9f304) |
| 11月11日数据交接时附带的代码（历史固定版本） | [37a25a4d7a99ec57705cd5c3d295143f3702d787](https://github.com/Aoraku/VideoICLBench/tree/37a25a4d7a99ec57705cd5c3d295143f3702d787/simulator) |
| 仿真资产 | [99057ec5bc1a6b5655fb15d953aa77b6a9e94f8d](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Handoff-20261103/tree/99057ec5bc1a6b5655fb15d953aa77b6a9e94f8d) |

HF 主分支后续可以补齐两条 GLM；复核本次交接时使用上述固定 revision。全部发布文件核对远端哈希，并抽样以匿名方式下载验证。
