# 独立真实视频 QA

题目在 [qa51.json](../config/qa51.json)。每条固定 qa_id、视频 SHA-256、四个选项和题目版本。QA 运行器只注册 demo_info、demo_frames、qa_question、qa_answer。取得至少一帧后才允许取题；首个有效答案落盘后关闭该房间的请求入口，答案的正误留给离线评分。

以下命令从实验目录运行。SDK 指向相邻 native-codex 目录中的 VideoICLBench/packages/sdk，MEDIA_ROOT 下按 qa51.json 的 video_path 放置对应视频；使用 [配置说明](../CONFIGURATION.md) 中提取并校验的模型目录，以及执行池共用的凭据和 gate 配置。先用自己的 Python 创建配置。运行 runner 时使用已经安装 harness 依赖的 GUI Python：

```sh
python3 qa/prepare_config.py --qa-id "$QA_ID" --media-root "$MEDIA_ROOT" \
  --sdk-root "$SDK_ROOT" --binary "$CODEX_BIN" --credentials "$PRIVATE/provider.private.json" \
  --ca-bundle "$CA_BUNDLE" --api-gate-config "$PRIVATE/api-concurrency.private.json" \
  --model-catalog "$PRIVATE/model-catalog.json" --output-dir "$WORK/qa/$QA_ID" \
  --config-out "$PRIVATE/$QA_ID.json"
"$GUI_PYTHON" qa/standalone_qa_runner.py --config "$PRIVATE/$QA_ID.json"
"$GUI_PYTHON" qa/standalone_qa_runner.py --config "$PRIVATE/$QA_ID.json" --execute
```

默认仅校验，显式 --execute 才调用模型。输出目录与 qa_id 一一对应；已记录首答时 runner 直接返回，已有未完成 claim 时保留现场。原批首条独立完成后，其余 50 条至多 8 条并行，共享 API 门控 50。

在评分者环境单独提供与清单哈希对应的原始题包（含 qa_grading_private）。按题目和原始示范核对后离线评分：

```sh
python3 qa/grade_answer.py --manifest config/qa51.json \
  --output-dir "$WORK/qa/$QA_ID" --private-packet "$PRIVATE_GRADING_PACKET"
```

私有题包、模型首答和运行日志均留在各自的受控环境。复现统计时逐一匹配清单的 51 个身份，答题正确率和物理执行成功率分开报告。
