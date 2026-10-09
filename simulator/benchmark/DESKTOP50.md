# 非厨房桌面50题与仿真录像

本版把任务统一为80×80厘米桌面上的双 Panda 操作。人手采集不需要锅、食材、灶台、厨房背景或家电；道具主要是彩色积木、长条、圆柱件、开口收纳盒／托盘、底座、方杯和桌面物品模型。RoboTwin 与 RoboCasa 各25个上游任务作为设计来源，来源名称及固定 commit 保留；这不是两个上游平台的原生运行结果。

完整作者题单与道具尺寸见 [TASKS.md](TASKS.md)，50张A布局比例图在 [filming](filming)。其中 `bowl`、`bottle` 等内部字段是几何类型；实际采集道具按 `display_name` 与题单准备，不要求使用餐具、调味瓶或食品。手机可使用无文字模型，秤台、鼠标、鞋、订书机等也使用无功能代理模型。

## 录像与评测边界

每题录制A布局、seed 0的一段成功仿真示范，512×384、20 fps，固定agentview相机使用60°垂直视场角，按20 Hz控制步直接渲染；没有插帧、瞬移、qpos修改、成功状态注入或剪辑。画面不带任务字幕、目标坐标或私有状态。达到判分成功并稳定2秒后停止录像，作者控制器可以继续收臂。动作数包含整个作者执行，视频可能在收臂结束前停止。

作者控制器读取私有状态来规划合法动作，所以这些视频证明工程可解性与采集流程，**不代表独立 agent 成绩**。当前人手示范和独立 agent 实验均为0。50个设计配方包含相同操作关系在不同道具、目标与布局上的实例，不表示50种互不重复的操作技能。B/C布局和多个seed的成功示范尚未采集。

视频不直接整理自上游：本版机器人、代理道具、初态及成功条件已适配，直接拿原生 RoboTwin／RoboCasa 录像会与实际任务不对应。因此本版重新执行并录制，再统一归档。上游任务仅作可追溯的设计来源。

## 本次物理与判分修订

- 收纳盒嵌套采用真实开口五面体；大小排序用可夹取的实心积木，保留尺寸排序关系。RoboCasa尺寸排序沿桌面X排列，区别于RoboTwin的Y方向排列。
- 两种空中交接均采用沿Y长280毫米的道具，为双 Panda 留出分离夹持位置。抬托盘使用宽280毫米的托盘。交接仍要求接收臂在离桌时独占夹持，桌面暂放不能替代交接。
- 旋转托盘的目标垫扩大到280×240毫米，完整容纳托盘；不是只检查质心。
- `rt22` 将瓶子代理改成48×48×140毫米长方积木，保留从横倒到扶正的姿态操作。作者策略通过空中转向、第二臂上端再抓取和正常朝下夹爪放置完成；没有把转腕失败的轨迹算成成功。
- `rt19` 使用150×48×16毫米手机模型与有重量的窄槽支架，保留竖立放入支架。判分检查下端入槽、真实接触、竖直与松开后的稳定；手机上半部可以露出支架。悬空不能成功。
- `rc17` 用较短圆柱件替代高的清洁液瓶，降低桌面采集的道具负担。

所有非抬举题还要求全部道具通过真实接触链支撑在桌面上；仅仅相互嵌套、但盒子被开着的夹爪勾在空中，不能成功。该规则记为 `table-support-v2`，所有题的版本已更新。入盒时在容器壁上方松开，让零件自然落入，再收臂，避免松爪时勾起容器。

所有改动都有任务版本。旧示范导入后仍保持不可变，修订题目不能使用旧版本示范。历史六题记录在 [PILOT.md](PILOT.md)，不是当前整套任务的验收文件。

## 复现与整理

在已安装依赖的Linux环境设置 `MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LP_NUM_THREADS=1`，执行：

```bash
python scripts/embodied50/batch-record.py \
  --output /absolute/new/recordings --workers 12
python scripts/embodied50/package-videos.py \
  --recordings /absolute/new/recordings \
  --output /absolute/new/desktop50-media
```

失败结果、动作、私有状态日志和原始失败录像保留在外部数据目录。打包脚本只选取当前任务版本和配方匹配、判分成功且录像终态成功的案例；输出 `index.html`、50段 `videos/*.mp4`、终态封面、作者检查图和公开 `manifest.json`。不将私有状态或完整轨迹混入视频包。

每段视频记录任务配方、执行器、环境代码与原始视频的哈希。正式包只接受当前任务版本、相同配方和相同环境代码的成功录像；试录和旧版本不混入。

审核每段录像后，才能通过 `python -m simulator.benchmark.demos TASK sim VIDEO --data DATA --author-verified` 导入为actor示范。人手视频必须真实录制，使用 `human` 导入，不能把仿真视频改名冒充。

运行时作者 `/admin/catalog` 接口报告每题实际可用的仿真／人手示范；仓库本身不包含媒体，不能只凭静态catalog的 `demo_status` 判断服务器数据是否齐全。

Agentlab的新数据根目录为 `/home/qingle/services/videoicl-embodied-50/data-desktop50`；旧 `data` 内的pilot与失败证据保留。服务仍为 `videoicl-embodied-50.service`，只监听127.0.0.1:18660。部署脚本支持通过 `EMBODIED_DATA` 指定隔离数据集。

## 2026-10-09 交付验收

50/50题完成A布局、seed 0作者执行并录制成功，共70.98分钟、20 fps。逐题检查首帧／中段／终态，公开逐题来源、任务版本、环境与视频哈希见 [desktop50_validation.json](desktop50_validation.json)，总体验收与视频包校验值见 [validation.json](validation.json)。最终版本150/150个A/B/C布局通过加载、三相机渲染和未完成负例检查；13/13项回归测试通过。

外部视频包 `desktop50-media-release.zip`（38,725,817字节）解压后直接打开 `index.html`，可搜索并观看全部50段。包包含MP4、封面、检查图和公开manifest。工作区副本在 `.local/desktop50-media-release`；Agentlab副本在上述数据根目录的 `media`。服务器已导入50段仿真示范及800张示范帧，人手示范仍为0。

夹杯题 `rt12` 已通过Agentlab实际actor API回放验收：`sim_frames` 条件、175个合法动作、提交成功，终态稳定24.65秒；该验收标记为 `author_replay`，不计入独立agent成绩。
