# Astra 具身实验配置

`config/experiment.json` 列出 255 个物理 episode 的身份、所属实验、共享 17 题和 25 个 pool 的成员。主表 50 题均取 C 版，每题分别运行文本与真实视频。42 题用 I，另 8 题用 R。主表、泛化和示范类型消融合计 204 个唯一执行；无规则条件增加 17 条，真实视频 A/B 条件增加 34 条。另有 51 道独立视频 QA（17 × A/B/C），见 `config/qa51.json`。

25 个 pool 实际分配了 254 条新执行。E22C-I 真实视频复用了先导实验的相同配置，其历史身份记录为 `reuse_source`。所有物理条目均独立于问答，使用 gpt-6-astra、high、program_gui，窗口 262144，原生压缩阈值 120000，500 个物理动作上限、无 episode 时间上限。共享 API 门控上限为 50。

## 生成运行目录

使用 Python 3.11 或以上版本组装配置。先按主文档组装运行代码，再将 `config/paths.example.json` 复制到工作目录，填写两套 Python、浏览器、Codex、系统 CA、Isaac Sim experience 和资产路径。保留 Kit 参数和深度开关。使用 transport 文档生成本地凭证和共享 gate；所有 pool 应使用同一锁目录。

用原批次的本地 Codex 模型缓存生成私有 catalog：

```sh
python3 extract_catalog.py --source /work/private/original-models-cache.json --out /work/private/model-catalog.json
```

这一步仅保留 models 数组，复原 Astra 两项配置，并对完整字节校验 config/model-catalog-pin.json 的 SHA-256。也可直接使用当批已封存且哈希匹配的私有文件。缓存模型清单发生变化会导致校验失败；完全复现需要原批次缓存。

示例只生成配置和命令，不启动仿真或模型：

```sh
python3 prepare_pool.py --pool p06-main-real \
  --bench /opt/embodied/VideoICLBench --runtime /opt/embodied/runtime \
  --model-catalog /work/private/model-catalog.json --paths /work/local-paths.json --credentials /work/private/provider.json \
  --gate /work/private/shared-gate.json --media-root /data/videoicl/demos \
  --out /work/new-astra/p06
```

输出目录必须是新目录。视频条件按 SHA-256 在指定媒体树中匹配示范，可以使用不同文件名；文本和无规则条件可省略媒体目录。`config/media.json` 列出路径和哈希。GPU、媒体及配置路径均须在执行主机上有效。确认 GPU 分配和预算后，在全新实验上执行 `CUDA_VISIBLE_DEVICES=0 sh /work/new-astra/p06/run.sh`，结果写入该工作目录的 `result/`。避免对已在运行的身份重复启动。

## 文件与验证范围

- `config/tasks.json` 与 `config/task-content/` 还原 176 套任务包。按文件原始字节对指令、GUI 说明、文本规则、服务端判定规则去重，生成时校验哈希。条件隔离由任务 loader 实施；判定规则仅供服务端使用。
- `config/bindings/` 包含 R、I、E 绑定和 I canonical 配对基线，生成时恢复 loader 要求的文件名。E41C 使用该题的显式尺寸适配版本。机房源路径已改为可移植的来源标签，运行资产保留相对路径和原哈希。
- 模型目录和 Franka 平滑 IK 配置来自当批实际运行文件。CLI 保留原生结构化工具、请求元数据、自动恢复和未知请求保留世界策略。结果属于工程验收。
- 交付前离线生成全部 25 个 pool，逐条用冻结版任务 loader 核对 254 条新执行的身份、条件隔离和所需视频字节。该检查不调用付费 API。
