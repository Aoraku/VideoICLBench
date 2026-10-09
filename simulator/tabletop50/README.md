# 第一人称桌面双臂任务新版

**先看：[视频索引（99段）](VIDEOS.md) · [部署与网页查看](DEPLOY.md) · [实现进度](PROGRESS.md)。** 所有运行工具、任务视频和验收资料均在 `simulator/` 内；`index.html` 是本地可播放的50题总览。

2026-10-09。任务清单与真人录制卡见 [TASKS_50.md](TASKS_50.md)，机器可读清单见 [families.json](families.json)。本目录是重新设计的50族，不沿用旧 `rt/rc` 编号，也不把旧50段视频算作新版成果。

## 当前边界

50族的设计卡已写好；实现、作者成功验收和视频解码验收分别记录，不能互相替代。`catalog.IMPLEMENTED` 仅表示有可生成的配方，不表示已经通过物理验收。没有配方的族明确抛出 `NotImplementedError`，不会偷偷降级为通用抓放。真人录制和独立agent实验均未完成。

模拟 `fpv` 是位于桌面操作侧的固定第一人称近似视角，不是已录真人视频，也不等同于头部运动。先检查构图，再用实物试录验证。执行仍为 robosuite 1.5.1 双 Panda、MuJoCo 3.2.6，沿用已安装依赖，不是裸MuJoCo控制器。

## 运行与录制

使用仓库现有 `simulator/benchmark/requirements.txt` 安装依赖。Linux无头渲染用OSMesa；macOS不设置下面两个GL变量。

```bash
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python simulator/tabletop50/tools/record.py --task F01 --variant A --seed 0 --output .local/tabletop50-recordings --record
python simulator/tabletop50/tools/batch.py --output .local/tabletop50-batch --workers 4 --record
python simulator/tabletop50/tools/audit-media.py --recordings .local/tabletop50-batch --output .local/tabletop50-preview
```

运行目录不可覆盖同名条件。失败的动作、日志、视频和结果都保留；修复后用新的输出目录。批处理对已有结果跳过，不将失败自动当成成功；发布前另行审计视频和同初态三规则。录制使用冻结代码目录，运行期间不可编辑其中源文件。

录制器使用真实公开动作字母表推进物理，不传送物件、不附着夹爪、不注入成功状态。作者读取真实状态规划动作，因此只能称为作者工程可解性验收。新增 `_FINE` 动作用于宽松插孔的最后对准：平移2mm、旋转1度；粗动作仍为2cm、10度，两种动作均推进0.4秒。

每段10fps，按物理20Hz每两步采样，完整记录执行和结束，不在中途第一次成功时截断。视频末帧、动作日志、源码及视频校验和写入私有证据。发布脚本完整解码视频、核对帧数和末帧，并检查三版实际初态完全相同和终态规则互斥。

## 规则与实例

同族同seed的A/B/C世界完全相同；规则只影响私有目标与作者计划。`visible_world` 排除这两项。不同seed用于示范／执行分离；当前族的实例变化范围须逐项审查，不能把少量位置抖动泛称为物体或规则泛化。

公共委托统一为“按照示范完成这项桌面工作”。作者清单、A/B/C标签、目标、计划、源码和验收JSON不得暴露给actor。旧 `simulator.benchmark.server` 仍加载旧catalog，不能用旧入口冒充本套件；新版 `simulator.tabletop50.server` 采用独立worker，并已通过Agentlab真实接口测试。

唯一汇总指标是任务成功率。判定应只描述任务本身：分类看物件进入哪个标记盒，允许盒子被移动；恢复任务才要求恢复结构。工具倾倒和空中交接包含定义该操作的过程证据，用于排除逐件抓放和桌面转手冒充任务；没有轨迹打分、双手动作配额或强制模仿作者路径。静止与释放检查用于排除尚在夹爪中或短暂经过目标的物件。当前仍需逐项审查其余配方是否存在无关的绝对位置限制。

## 道具与来源

新道具为程序生成的刚体代理，不分发RoboTwin、RLBench或其他套件资产。已有操作原型用于任务设计参考：

- [RoboTwin任务目录](https://robotwin-platform.github.io/doc/tasks/)：叠放、杯垫摆放、排序、交接、容器倾倒。
- [robosuite环境](https://robosuite.ai/docs/modules/environments.html)：分类抓放、套柱、双臂操作。实际机器人与控制器通过依赖提供。
- [RLBench任务源码](https://github.com/stepjam/RLBench/tree/master/rlbench/tasks)：形状盒、插架、铲取、扫拢、盖盒等参照。
- [ManiSkill任务卡](https://maniskill.readthedocs.io/en/latest/tasks/table_top_gripper/)：插孔与工具接触参照。

相似原型不等于移植官方任务、原生双臂支持或取得上游官方成绩。新增恢复、空间规划与视频规则单独描述，不宣称所有组合都是原创技能。

## Agentlab

隔离工作区 `/home/qingle/services/videoicl-tabletop50-fpv-v1`，复用 `/home/qingle/services/videoicl-embodied-50/.venv/bin/python`。各批次放冻结源码和独立输出目录。现有18660服务不受本目录的批处理影响；不要将旧服务的成功率或演示数量计入本新版。

新版服务独立监听 `127.0.0.1:18661`，systemd单元为 `videoicl-tabletop50-fpv.service`。部署命令：

```bash
bash simulator/tabletop50/tools/deploy-agentlab.sh
```

管理token位于服务数据目录的 `admin.token`，不提交仓库。作者通过 `/admin/sessions` 选择task、variant、推理seed和demo_seed；动作预算统一1600。默认 `sim_video` 必须满足规则匹配、示范和推理seed不同、源码版本一致、完整成功视频及解码证据；缺失则409，不自动回退其他规则视频。把最终审计出的每个案例目录复制到服务数据目录的 `demos/`。历史foundation视频对应旧源码，不能直接作为最新版服务的示范。

actor只持有随机session capability，调用 `/actor/{session}/observe`、`action`、`demo`、`submit`；无目标、状态、实时奖励或成功结果。作者结果需要管理token。当前尚无真人视频条件，不能用仿真视频替代真人条件。服务部署成功不表示50族或150视频全部验收完成。
