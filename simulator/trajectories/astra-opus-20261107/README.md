# Astra / Opus 具身实验轨迹

[GitHub Release 发布入口](https://github.com/Aoraku/VideoICLBench/releases/tag/astra-opus-trajectories-20261107)。本目录保存逐条身份索引、发布文件清单和下载、恢复工具；大文件使用同仓库 Release。下载文件、大小与 SHA-256 见 `manifest.json`，五个包的内容和恢复方法见下文。

## 范围

| 模型 | 固定物理执行身份 | 独立视频 QA | 来源 |
| --- | ---: | ---: | --- |
| Astra | 255 | 51 | `astra-iclworld-full-20261106`；254 条本批运行，1 条复用匹配的 E22 I real pilot |
| Opus | 158 | 0 | `opus55-iclworld158-20261106`；157 条本批运行，1 条复用匹配的 E22 I real pilot |

合计 413 个物理执行身份和 51 个独立 QA。复用条目保留目标身份及原始来源，不作为额外运行重复计数。这份归档对应上述正式实验，未把其他历史测试批次并入。

归档包含可用的完整模型会话、工具调用、原生动作及回执、GUI/深度/媒体、原生终态、用量和缓存账本，以及原有输入演示。QA 首答与离线判分单独保留。凭证、鉴权配置、运行缓存和可执行程序不公开；排除理由、读取异常及逐文件校验值见模型导出 manifest。Opus 更换 API 后的 16 份独立传输账本另附于 `opus-supplement` 包。

底层 `native/rpc` 临时通信缓存未上传；这不排除任何 episode，也不删除原服务器文件。Opus 此类缓存共 59,438 个文件、275,246,630,411 字节，详见 `opus-excluded-cache-summary.json`。房间内原生动作、回执、GUI、模型请求的深度和模型会话均保留；正式池级日志另包归档。

评分同时保留原始顶层值与原生 evidence 中可追溯的工程分，并记录来源。Astra 两条 E26 的数值评分不受原生进度协议支持，仍为 `null`。工程评分不代表额外完成了独立物理验收。本次导出不改变任何实验状态或评分。

## 索引

- `fixed-identities.json`：来自固定 manifest 的 464 个身份，作为独立对账基准。
- `astra-identities-and-scores.json`、`opus-identities-and-scores.json`：逐条来源、原生终态、动作数及评分字段。
- `coverage-audit.json`：实际归档与固定身份的对账结果。
- `opus-excluded-cache-summary.json`：底层临时通信缓存的排除范围与数量。
- `manifest.json`：已上传且核对大小及 SHA-256 的 Release 文件清单。
- Release 中每包的 `*-export-manifest.json`：逐文件原始路径、原始 SHA-256、脱敏后 SHA-256、媒体引用及排除记录；包内也有同一 manifest。

## 五个独立归档包

| 包标识 | Release 文件前缀 | 内容 |
| --- | --- | --- |
| `astra-main` | `astra-` | 255 个物理执行身份及 51 个独立 QA 的核心轨迹 |
| `astra-logs` | `astra-logs-` | 正式池级日志、传输账本、QA 输入演示等辅助来源 |
| `opus-main` | `opus-` | 158 个物理执行身份的核心轨迹 |
| `opus-logs` | `opus-logs-` | 正式池级和原生运行日志；不含临时 RPC 缓存 |
| `opus-supplement` | `opus-supplement-` | 更换 API 后的 16 份独立传输账本 |

日志包和补充包不增加实验身份数。每包有自己的导出 manifest 和 receipt；同一模型的不同包也应分别解压。Opus 核心包从已完成的核心 tar 条目恢复；Astra 核心包合并完整的前 305 条归档与从未变化原始文件重新导出的最后一条 QA。这里只重新整理文件，不重新运行模型。恢复部分保留脱敏后文本字节和媒体 SHA；`source_hash_phase` 明示恢复对账时重算的源文件哈希，尾部 QA 的导出来源单独保留。大日志采用流式脱敏，LRU 仅缓存重复行的处理结果，不删行、不折叠重复警告。

## 下载

在本目录执行，Python 3.9 或以上即可，无额外依赖：

```bash
python3 download.py --out trajectory-downloads
# 下载某个模型的全部包
python3 download.py --model astra --out trajectory-downloads
python3 download.py --model opus --out trajectory-downloads
# 或只取核心轨迹；--package 可重复
python3 download.py --package astra-main --package opus-main --out trajectory-downloads
```

下载器逐件检查大小与 SHA-256，匹配的已有文件会跳过；中断的 `.partial` 文件不作为有效下载使用。

## 解包与恢复

每包的分件组成连续 tar.gz 流，按编号拼接。五个包分别解压，避免覆盖各自的 `manifest.json`。下面使用完整分包前缀，不能把 `opus-*` 或 `astra-*` 混为一个流：

```bash
mkdir -p extracted/astra-main extracted/astra-logs extracted/opus-main extracted/opus-logs extracted/opus-supplement
cat trajectory-downloads/astra-trajectories.tar.gz.part* | tar -xz -C extracted/astra-main
cat trajectory-downloads/astra-logs-trajectories.tar.gz.part* | tar -xz -C extracted/astra-logs
cat trajectory-downloads/opus-trajectories.tar.gz.part* | tar -xz -C extracted/opus-main
cat trajectory-downloads/opus-logs-trajectories.tar.gz.part* | tar -xz -C extracted/opus-logs
cat trajectory-downloads/opus-supplement-trajectories.tar.gz.part* | tar -xz -C extracted/opus-supplement

# 恢复图片、录像、深度等媒体的相对路径
python3 restore.py extracted/astra-main --out restored/astra-main-media --media-only
python3 restore.py extracted/astra-logs --out restored/astra-logs-media --media-only
python3 restore.py extracted/opus-main --out restored/opus-main-media --media-only

# 如需把图片重新嵌回模型 JSON/JSONL，使用完整恢复
python3 restore.py extracted/astra-main --out restored/astra-main
python3 restore.py extracted/astra-logs --out restored/astra-logs
python3 restore.py extracted/opus-main --out restored/opus-main
python3 restore.py extracted/opus-logs --out restored/opus-logs
python3 restore.py extracted/opus-supplement --out restored/opus-supplement
```

重复媒体按 SHA-256 去重，保存在 `blobs/sha256`，解码字节不变。恢复器检查媒体哈希，并支持 base64、data URI、字符串中的外置图片标记和嵌套 JSON；输出位于 `episodes/<identity>/<source_relative_path>`。完整恢复会重新复制重复媒体并扩张日志体积，单纯浏览图片时使用 `--media-only`。

凭证脱敏始终保留。文本经过 JSON 规范化或脱敏，不能声称与原始文本逐字节相同；`source_sha256` 指脱敏前源文件，`export_sha256` 指归档中的脱敏文本。恢复器拒绝路径越界、损坏的媒体和覆盖不同内容的文件。
