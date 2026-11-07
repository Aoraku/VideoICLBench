# 四模型具身评测：已结束任务轨迹

本交付对应 `five-cli-iclworld-20261107`，每个模型固定158条身份（79 text、79 real，包含主表100条及新增泛化58条）。用户于2026年11月7日要求停止未完成任务，并发布已经结束任务的轨迹与结果。

| 模型 | 已有原生终态 | 全批固定身份 |
|---|---:|---:|
| DeepSeek Flash / DSH | 50 | 158 |
| GLM-5.3-Flash / ZCode | 20 | 158 |
| Qwen3.8-Max | 3 | 158 |
| Kimi K3 | 0 | 158 |
| 合计 | 73 | 632 |

“已有原生终态”包含失败和give_up，不代表成功。用户停止的未完成episode与未启动队列单独保留停止记录，不补0分、不伪造模型终态，也不混入这73条完成轨迹。独立工程诊断、Astra与Opus其他campaign均不计入本目录。

## 文件与校验

- [逐题结果与原始证据SHA](metadata/results.jsonl)
- [结果范围与设置差异](metadata/summary.json)
- [归档内逐题轨迹索引](metadata/trajectory-index.jsonl)
- [轨迹归档内容摘要](metadata/trajectory-summary.json)
- [导出完整性与脱敏校验](metadata/export-verification.json)
- [用户停止与资源释放记录](stop_status.json)

### 完整轨迹与媒体

[GitHub Release 下载页](https://github.com/Aoraku/VideoICLBench/releases/tag/four-model-trajectories-20261107)提供 `completed73.tar.gz`（1,259,689,349 字节，约1.17 GiB）。[下载清单](downloads.json)记录附件地址、大小和SHA256。

```sh
curl -fLO https://github.com/Aoraku/VideoICLBench/releases/download/four-model-trajectories-20261107/completed73.tar.gz
curl -fLO https://github.com/Aoraku/VideoICLBench/releases/download/four-model-trajectories-20261107/SHA256SUMS.txt
shasum -a 256 -c SHA256SUMS.txt
tar -xzf completed73.tar.gz
```

解压目录为 `completed73/`。其中 `episodes/<episode_id>/` 保存逐题原生结果、环境与动作批回执、结构化轨迹、模型/工具交互记录和API用量；`media/` 保存1,897份按内容SHA256去重的观测媒体。原有动作和公开交互顺序保留，重复base64图像以媒体引用代替；冗余低层RPC逐步副本不重复存储。原始录制未提供的内容不会补造。

[逐文件校验清单](metadata/archive-checksums.json)覆盖3,673份数据文件，共1,892,088,777字节。归档另附导出摘要和校验清单。原始结果的SHA位于逐题metadata，脱敏副本的SHA位于归档校验清单，两者分别用于源证据追溯和下载完整性检查。

原始凭证、provider配置、连接令牌、环境变量、cookie及机器私有配置不属于交付内容。脱敏发生在导出副本中，不改写远端封存证据。

## 用户停止与资源释放

403条已启动未完成任务和156条未启动身份按用户取消记录，分数保持null。这些身份不计入上述73条模型终态。60个正式仿真GPU进程已释放；42个分配槽位独立复核中，本campaign目标活进程和GPU上下文均为0。73条完成结果及原生终态共146份源文件SHA保持不变。此处只报告本项目释放，不表示同卡其他工作负载已经停止。

## 比较与评分限制

- 请求配置约定HIGH，但GLM早期适配存在档位映射偏差。整个GLM固定158条中，86条已记录请求全为HIGH，67条先MAX后HIGH，5条仅记录到MAX。逐条以effort审计为准，不能将全批汇报为纯HIGH。
- 本次导出的GLM20条具体为8条HIGH、8条MAX后切HIGH、4条仅MAX。
- GLM另有4条早期盲图、零物理动作的终态：主表real的E05、E09、E23、E26。保留其原始结果并标记缺陷，不能当作通过视觉验收的模型能力证据。
- Qwen的3条终态来自曾发生原生MCP工具等待超时的旧批次，不能作为修复后干净样本；逐题工具错误以导出轨迹为准。HIGH是请求设置，供应商具体路由的有效档位映射尚未完全核实。
- 工程评分与正式物理验收分开。`native_positive_negative_controls_pending`等原有限制必须随结果保留。
- 模型调用Done、API返回成功、进程存在均不替代原生终态；原生0分与未提供评分的null严格区分。
