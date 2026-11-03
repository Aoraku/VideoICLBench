# E38–E43 具身仿真任务交付

本目录交付6个任务，每题A/B/C，共18条，固定I条件、seed4201、Franka。代码在GitHub，场景资产、机器人和私有评分/QA数据统一在 [VideoICL-Embodied-Handoff-20261103](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Handoff-20261103/tree/main/deliveries/e38-e43-20261103-r1)。

**当前10/18条有功能证明：E38/E41的ABC从初态通过；E42/E43的A/B为检查点接续证明。E39ABC、E40ABC、E42C、E43C尚未完整通过。** 逐条状态在 [STATUS.json](STATUS.json)，接续证据不等于初态全流程通过或正式模型分数。

## 下载和运行

使用Linux Python3.11及已经安装的Isaac Sim/Isaac Lab环境：

```bash
git clone --branch codex/embodied-e38-e43-delivery-20261103-r1 https://github.com/Aoraku/VideoICLBench.git
cd VideoICLBench/simulator/e38-e43-20261103
python -m pip install -r requirements-download.txt
# 私有HF仓库需要已有读取权限；使用hf auth login或HF_TOKEN环境变量。
python download_data.py
/path/to/isaaclab/python.sh run.py --task E38 --variant A --out outputs/e38-a
```

`download_data.py`以8线程下载分块，合并后只安装资产与私有数据，保留GitHub源码。HF提交固定在 `DATA.json`。需要检查本机文件时可运行 `python run.py --check`，该命令不启动世界。

未完整通过项可以显式运行，例如：

```bash
/path/to/isaaclab/python.sh run.py --task E40 --variant A --allow-unverified --out outputs/e40-a
```

默认执行**无模型、无API的工程参考动作**，工程预算3000动作，用于接收者查看任务行为。输出目录必须全新。`--serve`改为原生房间服务，接收方可连接自己的agent runner；它不等于启动一套完整的正式模型评测。原150/300条正式实验状态不由本入口改变。

## 任务与QA

参见 [任务清单](docs/TASKS.md) 和六篇任务说明。`tasks/*/task.public.json`保存公开任务，`qa.public.json`保存四选一题；ABC对应不同规则答案。演示/文本规则交付后先收首次QA答案，再开放动作；真实/仿真演示视频由接收方提供既有绑定，本目录不把末态图片替代演示。

`docs/tasks/`面向维护者，包含ABC规则和验收条件；模型输入应由公开任务、演示及QA包生成。`private_data/evaluator/`包含答案及评分数据，应由私有评分进程读取。

## 交付内容

- `runtime/`：仿真、动作接口、原生评分、工程参考及QA SDK相关源码。
- `bindings/`、`profiles/`：源资产绑定及任务对应的控制配置。
- `tasks/`、`cases.json`：18条固定任务身份与公开输入。
- `DATA.json`、`download_data.py`：统一HF数据位置及下载入口。
- `STATUS.json`、`docs/tasks/`：已证明范围、已知问题和任务规则。

此次没有追加物理验收、模型调用或定时巡检。E44–E50由另一个交付目录负责。
