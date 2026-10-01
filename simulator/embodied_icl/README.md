# VideoICL：GUMI GUI → MuJoCo → 私有判分

本目录是 Show-Harness/GUMI 操作方式的物理后端适配，不是原论文成绩的复现。

## 启动

从本工作区根目录运行：

```bash
simulation_b01/.venv/bin/python simulation_b01/build_scene.py
simulation_b01/.venv/bin/python embodied_icl/make_demos.py
simulation_b01/.venv/bin/python embodied_icl/test_contract.py
simulation_b01/.venv/bin/python embodied_icl/server.py --variant B --seed 17 --port 18621
```

迁移到另一台机器时，先用 Python 创建 `simulation_b01/.venv` 并安装 `simulation_b01/requirements.txt`；必须重新运行 `build_scene.py`，以更新场景中的绝对资源路径。

打开 http://127.0.0.1:18621 。macOS 需要允许进程使用图形系统。Python 依赖复用 `simulation_b01/requirements.txt`，场景与官方 Panda 资源复用该目录。远程 Linux 可配置 MUJOCO_GL=egl 或 osmesa；本物理版本在本地运行，远程 ubuntu-descfly 的原版 GUMI 保持独立运行。

## Agent 操作协议

1. 使用新会话。只提供通用 GUI 使用说明及本页演示；不向 Agent 提供 variant、目标颜色顺序或源码。
2. 看视频或点击“12 张按时间排序的演示帧”。本 MVP 为原视频均匀时间采样，抽帧是可见输入策略，须记录，不能宣称原生视频推理。
3. START 后，各臂排入移动/旋转/夹爪动作，COMMIT 执行。重复同一按钮可排入最多 9 次同一原子动作；每对动作分别计入预算。
4. 移动步长 20/10/5 mm；旋转为世界 Z 轴 ±10°（仅 yaw，未实现任意 roll/pitch）。STILL 保持另一臂。夹爪只是闭合/张开，不自动选择、对齐、吸附或判断物体。
5. 提交可以发生在任何运行时刻。提交后锁定本 episode，不能重试、重开或查询成功提示。判分仅写服务端私有目录。

允许观察：四路相机、夹爪控制目标、动作完成反馈和步数。没有物体坐标、颜色对象列表、抓住哪个物体、目标层序或实时 task_done 信号。网页/DOM/URL 不含 A/B/C 标签，demo 使用相同 `/demo.mp4` 地址。

执行是离散决策式仿真：等待 Agent 时暂停物理时钟，每个原子动作对推进 0.9 秒仿真，双臂共享每个 mj_step。动作之间仍保持动力学结果，不将方块重置。移动使用 Cartesian IK + 原模型关节 PD，夹持仅靠接触和摩擦；机器人有理想重力补偿。路径不是通用避障规划器，碰撞可能发生。

## 演示与测试条件

A/B/C 是三种颜色层序，私有定义在作者/判分代码中。用于开发的演示为脚本驱动的物理仿真，不是真实人手拍摄。演示布局和 seed 17 的测试布局不同。正式真实人手输入条件需要后续录制真实视频；不得把本 MVP 的成功等同于 real-to-sim 成功。

目前测试布局是三个颜色各自在相应半桌范围内抖动，未做到任意颜色位置置换。若跨左右半桌置换，应验证可达性再纳入正式分布。三色塔属于最终空间关系任务，不能单凭该任务宣称已测出时序规则理解；需要后续过程判定任务。

## 产物与判分

每次进程启动生成新的随机 episode ID：`private_runs/<id>/`。

- `episode.json`：私有条件、初始状态与预算。
- `gui_events.jsonl`：客户端按钮操作审计（辅助记录，非防篡改证明）。
- `actions.jsonl`：服务端实际执行的动作对、步长、仿真时间。
- `private_states.jsonl`：服务端物体状态审计，不对外提供。
- `execution.mp4`：按物理时间 25 fps 记录四视角画面，不是浏览器屏幕录像。
- `result.json` / `final.png`：提交后判分与最终画面。

判分检查：相邻层真实接触、底块与桌面接触、中心高度、水平对齐、底块位于垫上、朝向直立、1 秒位置漂移、所有方块无机器人接触、TCP 已撤离。任何一项失败都算失败。测试包含错误层序拒绝、初始未完成状态拒绝、非法动作不改变物理状态、双臂共享时间、旋转执行及 oracle 正例。oracle 仅用于控制/判分单元验收，物理类复用了演示模块中的模型初始化和 IK 基础实现，但 GUI 动作路径不调用自动 pick_place 或颜色选取逻辑。

开发者 GUI 验收与正式盲测严格区分：开发者已知实现及任务设计，成功只能说明链路可用，不能算独立 VideoICL 成绩。

## 配对评测建议

固定 seed，对 A/B/C 各启动独立进程和新 Agent 会话，使用相同动作预算。输入条件分别为：demo-only（主条件）、明确规则（控制诊断）、无 demo（先验/泄漏诊断）、错误 demo（条件敏感性诊断）。记录随机种子、模型、截图尺寸、视频采样策略、决策次数、原子动作对数、token/时间消耗和成功率。不同条件不可沿用一个会话的记忆。

本 MVP 不在环境里硬编码任何模型 API；浏览器 Agent 通过截图、点击即可运行。直接发 `/api/step` 的策略必须另列 API action track。网页端点不是安全隔离沙箱：正式评测仍需外部 runner 限制 Agent 的文件系统/网络/源码访问。

## 来源

GUI HTML/CSS 从 Show-Harness `137d5718c3b7af0150764d8f9beeb252c9f2794a` 的 `gumi/web_teleop_dual/static/index.html` 改编，保留 `GUMI_LICENSE`。双臂排队+COMMIT 的交互约定沿用 GUMI；本目录 Python 物理适配、视频输入、提交/判分协议为新增实现。Panda 资源许可证位于 `simulation_b01/assets/franka_emika_panda/LICENSE`。

本次已通过的 GUI 验收及具体限制见 [验收结果](验收结果.md)。

相机/观察修订：腕部相机沿手指方向向下看，偏角约 22°；默认抓取姿态的左右方向与俯视图一致，旋转后随手腕转动。TCP 数值已从 GUI 与公开 API 删除，仍仅供底层 IK 控制与私有判分使用。旧 215 步验收使用过 TCP 显示，不能计作本修订的纯视觉成功。旧交付 zip 和录像为历史快照，最新代码以本目录为准。
