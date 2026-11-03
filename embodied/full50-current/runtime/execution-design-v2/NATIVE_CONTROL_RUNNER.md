# 显式工程控制入口

`scripts/probe_realworld_room_pool.py` 不带 `--execution-control` 时仍运行原容量探针。
新增选项只在已授权、独立工程验收世界使用，不是模型评测启动入口，也不会自动批准发布。

先离线校验一个 case batch：

```sh
python scripts/probe_realworld_room_pool.py --cases CASES.json --out NEW_OUT \
  --execution-control positive --validate-only
```

此模式只读取规格/绑定、检查三元身份和 I/E revision；不导入 Isaac 应用、不启动仿真、不创建 `NEW_OUT`，也不验证远端资产已安装。

原生工程调用使用相同参数，去掉 `--validate-only` 并附实际设备/Kit 参数。`--execution-control` 支持 `positive`、`wrong_members`、`wrong_destination`、`wrong_rule`、`not_released`。每次必须使用不存在的新输出目录；不要将已开始的模型 episode 作为输入或重用世界。

`--execution-settle-ticks` 默认 600，用于所有房间共同初态历史采集；`--execution-action-budget` 默认 1500，是独立工程参考路线动作预算。模型评测配置不受影响。

所有 case 的初态 seal 均发生在第一条机器人动作之前。单房间路线失败会保存其错误与末态，然后继续其他已 seal 房间。所有参考动作经 `RoomPool.action_batch`；没有绕过共享时钟的单 controller 步进。

每个 room 独立保存：

- 初态诊断、seal 屏障、原生分数与 terminal 记录。
- 全部行动回执及实际 TCP、阶段；原生子步物体轨迹与原始接触对。
- 完整末态对象/手臂反馈、接触力、传感器路径诊断，以及 head/left_wrist/right_wrist 三路 RGB。
- 工程录像、路线错误、负例扰动计划及原生评分器实际 observation。

正例只有路线无错、证据完整、原生历史有效且 `strict_success=true` / `task_score_100=100` 才标为本条原生正例通过。负例始终保留 `negative_condition_observed=null`，要求后续独立审核具体末态、接触和轨迹，不能用低分或路线返回代替反例成立。所有输出仍为 `release_ready=false`、`model_launch_enabled=false`。

## 固定三种子 ABC × I/E 矩阵

`execution_design_probe.matrix_case_batches({'I': I_BINDINGS, 'E': E_BINDINGS})` 返回六组、每组 15 case；覆盖五任务 × ABC × 4201/4202/4203 × I/E 共 90 个独立身份。它只生成 Python 数据，不写文件、不分配 GPU、不启动进程。调用方可将每组保存为单独 `CASES.json`，针对五种 control 分别使用独立输出目录运行。I/E 绑定必须显式包含新 revision，旧 full50 绑定不能冒充新版验收。
