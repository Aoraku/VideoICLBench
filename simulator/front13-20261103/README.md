# E01–E13 可运行交付版（2026-11-03）

范围是前13题，每题ABC各一个、seed4201，共39个主体。E12用原生支持的R条件，其余用I。按本次交付要求优先把核心流程做完；**24/39已功能通过，其中21/39有单世界原生100分证据**，其余15个身份实现已打包但完整功能验收仍在进行。逐条状态见`acceptance.json`，不将未通过写成已通过。

已通过：E02/E03/E04/E05/E06/E07/E11的ABC（原生100）；E12的ABC（可追溯检查点链完成，两只充电器已释放/真实插入/承托，整体原生分不拼接）。E01/E08/E09/E10/E13尚待完整功能确认。此次交付允许学长先运行这些环境，不承诺所有工程参考作者能自动完成每题。

## 1. 下载资产

在有Python3.11和Isaac Sim/IsaacLab的Linux NVIDIA机器上使用。源码包含完整原生环境、评分器、公开GUI SDK与QA首答overlay；Isaac Sim/IsaacLab本身需按其许可自行安装。资产压缩包另含原始物体/纹理依赖、原Franka机器人与38段已冻结真人局部规则示范；约282MB。

```bash
python -m pip install -r requirements-inspection.txt
hf auth login                         # 需有私有数据集访问权限的HF账号
python download_assets.py
python run_front13.py inspect --all --verify-assets
```

已有压缩包可以离线解包，使用`python download_assets.py --archive /path/front13-assets-20261103-r1.tar.gz`。下载器逐文件校验SHA256。物体资产依照原始来源/许可使用，不将其重新声明为本项目原创。

## 2. 先跑一个无模型物理用例

在原Isaac环境中，设置IsaacLab源码路径。已有能启动IsaacLab的Python命令可直接使用；包内`runtime/scripts/run_gpu.sh`也可配置`VIC_ISAACLAB_ROOT`和`VIC_ISAAC_PYTHON`后启动。

```bash
export PYTHONPATH="$PWD/runtime:$PWD/sdk:$ISAACLAB_ROOT/source/isaaclab:$ISAACLAB_ROOT/source/isaaclab_assets:${PYTHONPATH:-}"
export VIC_ENGINEERING_FUNCTIONAL_ACCEPTANCE=1
python run_front13.py probe --task E02 --variant A --out runs/e02-a-first
```

`python`必须是已安装Isaac Sim/IsaacLab的Python3.11。用`--experience /path/isaacsim.exp.base.python.kit`指定安装的Kit experience；`--runtime-python /path/python`可选择实际执行器。`--dry-run`仅输出命令。替换task/variant即可运行前13题；每次用新的输出目录，保留已有证据。

`probe`是无模型的内部工程参考作者，不是模型成绩。其工程动作上限E01=6000/E09=12000/其余3000；模型正式动作预算需在评测runner设置为500。原生控制器力/速度/加速度/关节限位均保持原配置，时间上限由接入评测runner明确设为关闭。

## 3. 学长接模型时运行原生环境服务

```bash
python run_front13.py serve --task E02 --variant A --out runs/e02-a-model-env
```

原生服务会生成当前room的私有连接/文件RPC信息，由同机sidecar/公开GUI SDK接入；接口实现位于`sdk/vic_sdk/embodied_environment/pool.py`和`sdk/vic_sdk/embodied_gui_mcp.py`。模型凭证由使用方注入，本包不含API密钥，不会启动模型或后台巡检。

每题公开指令及text/real/sim QA数据在`tasks/<case_id>/`。模型应先看对应局部规则示范/文本，提交一次QA首答，再进入动作；私有正确答案不放入agent输入。本包`qa/questions.json`仅含题目与选项，原有私有grader由控制方保存。

## 当前已知问题

- E01/E08/E09/E10/E13完整工程流程仍在续测，调用环境/评分/GUI可用不等于参考策略已经走完。
- E05-A真人转码缺少可用发布绑定，该输入暂留缺失；不要用别的变体视频替代。其环境与文本规则可运行。
- 本次打包的真人视频是局部规则示范；仿真局部示范仍需按审核后的媒体显式绑定，不用完整工程解法视频替代。
- 当前在RTX5090验证使用CPU物理后端；隔离5步GPU兼容模式测试19.3秒，比CPU13.8秒慢，故沿用CPU。渲染仍使用GPU。
- `acceptance.json`中的`native_single_world_score_100=null`表示该完整身份尚无单世界整体成绩；检查点链的功能通过不合成100分。

原生评分逻辑、原始物体和ABC核心规则保留。工程参考作者放宽的是中途私有精度/稳定等待；精确原生评分照实记录。模型正式450评测仍暂停，本交付不修改旧批次或既有运行世界。
