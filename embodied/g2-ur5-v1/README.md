> 模型资产、纹理和视频位于 Hugging Face 数据集。先在仓库根目录运行 `python fetch_assets.py` 下载，原路径会自动恢复。

# 原版 G2：UR5 十题交付

2026-11-04：启动入口新增 `--engine gemini/dsh/zcode/kimi`，沿用原 CLI 的历史和 compact。固定版本、配置示例、原生图像测试与自动恢复的当前边界见 [多 CLI 接入说明](../../docs/native-cli-adapters.md)。默认仍为 Codex；新接入不修改原任务与 QA。

这是最初已迁移到 **双 UR5 + WSG 夹爪、蓝灰色新桌面** 的十题：

|题号|推理场景|
|---|---|
|E04|苹果、梨、蓝收纳罐与图形配对|
|E05|礼盒、橙子、三角糕点与图形配对|
|E06|三颗小柑橘放入六孔托盘|
|E07|五个不同尺寸套娃排序|
|E09|九块彩色图形饼干分组|
|E11|四个水果按布局变换入框|
|E20|彩色纽扣按规则补足数量|
|E36|按数量把小苹果装盒|
|E41|按长短关系接续橡皮条|
|E49|薄照片卡按原序号分盘|

每题包含 A/B/C，共 **30 个任务变体**；real、sim、text_rule 三种输入均已准备，共90种任务/输入组合。默认 seed4201。E09/E20保留原来的局部分组/补量任务，未应用后续新版的封装运输流程。

本次按用户要求直接交付，**没有重新运行仿真、模型或物理验收**。历史迁移、动作/GUI工程准入与任务完整成功属于不同证据，不新增“全部30条100分”的声明。模型、纹理、机器人、示范视频已完整保存到本交付的数据集；下载方式以数据集当前访问设置为准。

## 下载

```bash
git clone --single-branch --branch codex/embodied-all-handoff-20261103 \
  git@github.com:Aoraku/VideoICLBench.git
cd VideoICLBench/embodied/g2-ur5-v1
```

## 环境

- Linux + NVIDIA RTX，原运行版本为 Isaac Sim **5.0**。使用与该版本匹配、已安装 IsaacLab 的 Python；不包含 NVIDIA 软件安装包。
- GUI/模型侧：Python3.11，安装本目录 `requirements-gui.txt`，再安装 Chromium。
- 原 harness 固定支持 Codex CLI `0.163.0` / `0.164.0`，建议沿用 `0.164.0`。模型使用 Responses API；模型名和API地址由实验者提供。目录自带原 `gpt-6-astra` 模型目录，其他模型需提供兼容的 `--model-catalog`。
- Kit、GUI、CLI 必须在**同一台机器/同一个容器**中运行，file-RPC不能跨主机共享。

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-gui.txt
.venv/bin/python -m playwright install chromium
# 在原有 IsaacLab/IsaacSim Python 环境中补齐以下依赖；不要替换其torch/Isaac版本：
/path/to/isaac-python -m pip install pillow imageio-ffmpeg trimesh scipy setproctitle==1.3.6
```

私有API配置放在仓库外，例如 `/secure/provider.json`：

```json
{
  "codex": {
    "base_url": "https://YOUR_RESPONSES_API_HOST/v1",
    "api_key": "YOUR_PRIVATE_API_KEY"
  }
}
```

该文件不随交付提供；Hugging Face token也不属于模型API配置。

## 跑一个任务

```bash
CUDA_VISIBLE_DEVICES=0 .venv/bin/python run.py \
  --task E04 --variant A --condition sim \
  --native-python /path/to/isaac-python \
  --gui-python "$PWD/.venv/bin/python" \
  --binary /path/to/codex \
  --credentials /secure/provider.json \
  --out "$PWD/outputs/e04-a-sim-001"
```

换题时改 `--task`，换规则时改 `--variant A/B/C`，换输入时改 `--condition real/sim/text_rule`。每次使用新的输出目录；脚本不会覆盖或重启已有实验。

默认：**500个物理动作、无episode时间上限、原生compact、1,050,000 context window /945,000自动压缩阈值、program_gui、high effort**。实际API必须支持所选模型和窗口。`--ca-bundle`可指定中转站TLS证书，`--experience`可指定本机IsaacSim5.0的`.kit`文件。暂时只想获取命令可加 `--print-command`，只生成启动JSON，不占GPU、不调用API。

请使用本目录 `run.py`，它显式覆盖底层通用脚本的历史默认值；直接调用底层脚本时需要自行传入上述参数。[harness 检查记录](HARNESS_AUDIT.md)列明本轮离线检查及实际服务端能力边界。

模型先通过demo工具查看原示范，再答一道四选一QA，然后操作仿真。QA首次有效答案持久化，错误答案也继续执行；正确性只供离线统计，不反馈给模型。三种条件均有各自绑定，QA答案在控制侧`evaluator/qa-bindings.json`，不放入模型工作目录。

默认运行入口每次一个room；并行时给不同命令设置各自`CUDA_VISIBLE_DEVICES`及输出目录，不使用原RTX账号、原实验队列或原进程。API凭证和运行日志由学长自己的环境产生。

## 目录和结果

- `runtime/`：冻结的原G2/IK平滑运行代码、UR5/WSG配置和机器人USD。
- `assets/`：仅这十题依赖的物体、容器、纹理和源资产，原字节保留。
- `media/`：30段real +30段原sim head视频；未重新录制、裁剪、加速或解码。
- `tasks/`：30个原任务包、公开指令及90份QA侧车文件。
- `VideoICLBench/`：原生GUI、file-RPC、Codex harness、评分与资源清理代码。
- `config/cases.json`：固定任务清单；`asset-manifest.json` / `media-manifest.json`记录文件与SHA。
- `config/provenance.json`：原绑定和UR5 profile指纹；`FILES.sha256`记录本次交付文件。
- `outputs/<run>/`：native状态、轨迹、RGB/深度、模型会话、API用量及最终评分。以实际原生终态为准；基础设施未评分保留null。

当前原harness仍保留`--allow-unvalidated-environment`的工程标记，由`run.py`自动传入，以沿用现有任务清单状态；它不在启动前自动跑验收，也不修改物理评分。要改变正式结果的统计口径，应由实验负责人按已持有的原验收证据另行冻结。

`evaluator/grade_qa.py --help`说明QA离线计分参数。私有规则、评分器和答案文件只交给环境/评测侧；模型仅接收单题公开指令、对应示范/文本规则和匿名选项。

## 来源

源代码来自2026-11-02固定发布 `inference450-remaining300-qa-20261102`，早于本轮执行任务重设计。保留双UR5/WSG、腕相机TCP居中配置及原.4–1.2秒收敛窗口。共享原始50题catalog仅用于原生加载依赖，本交付入口限定上述十题。

机器人转换来自固定的RoboTwin资产；来源见`runtime/reference/robotwin/source_snapshot.json`和`runtime/assets/embodiments/robotwin-r5/conversion.private.json`。替换物体与照片贴图来源见`assets/VIC_INFERENCE_ASSETS/g2/provenance.json`，照片来自固定版本scikit-image样例。视频保留原实拍/仿真来源，不因本次交付改变许可或署名。
