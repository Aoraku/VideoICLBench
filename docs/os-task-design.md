# OS 任务设计与人工录制手册

本手册覆盖 36 个独立任务族、108 个 A/B/C 条件。面向任务设计者、录制者和审阅者；完整规则及录制说明属于团队资料，不进入被测 agent 的 prompt 或应用画面。

## 设计原则

- **清楚地教方法。** 每段 demo 在同一 A/B/C 条件下呈现多个输入、处理动作及保存后的结果。阈值覆盖边界，分类覆盖命中和不命中，选择提供竞争属性，排序或冲突处理说明并列约定。录制者在任务卡查看规则和逐组预期内容，无需试错反推判定器。
- **Demo 只呈现局部方法。** 从默认桌面自然进入应用，执行已经准备好材料的小例子。完整资料收集、故障排查、成果制作和交付属于 inference。预置前置状态使 hard 的 demo 无需重做整条业务流程。
- **A/B/C 是三个替代规则。** 同 seed 的三个 inference 环境及业务目标相同，分别使用匹配的一段人工视频、独立上下文和独立运行状态。不同版本不出现在同一段 demo 中。
- **一个 inference，一个持续桌面。** 批量对象同时存在于此环境。桌面任务栏可切换九个应用，共享真实文件、设置和作业状态。示范的“下一组”仅用于连续展示局部例子，不出现在 inference。
- **Prompt 是目标与约束。** 明确从视频学习哪一种选择条件、格式、目录组织或映射关系。交付文件名、字段约束和业务范围公开；所选规则的具体值不在 prompt 中泄漏。应用不展示评测目标或解题步骤。
- **真人录制与审核。** 录像由浏览器捕获人工操作，或上传本次示范的人工 WebM / MP4。服务器保存 MP4、原始示例种子、设计指纹、自动检查结果和审核人。只有所有示范组通过检查且人工审核通过的匹配录像可进入 ICL inference。AI 参考录像不计入人工 demo。
- **判实际结果。** 评测读取服务器持久状态，核对成果、来源和禁止副作用。严格成功是必要条件的合取；检查项得分含保护条件，不能当作业务完成百分比。人工审核另行确认视频可读、示例充分以及录制来源。

## 难度分级

| 档位 | 数量 | 执行结构 | Demo 范围 |
|---|---:|---|---|
| Easy | 12 | 在一个环境中对多个新对象反复执行同一方法 | 多个局部对象，含竞争项、边界或不命中项 |
| Medium | 12 | 一个主要应用内完成有依赖的长程业务；视频方法只占一个模块 | 该模块的多次实现，输入材料就绪 |
| Hard | 12 | Medium 加多个桌面应用之间必要的内容或状态依赖 | 该模块的多次实现，前置状态就绪 |

OS 的跨平台边界按现有功能应用划分，例如 File Explorer → Notepad → Task Scheduler → Device Manager。必须存在后者消耗前者内容或状态的依赖；只多开窗口不算跨平台难度。分级描述任务结构，不代表独立模型实测成功率。

## 录制与审阅

示范在浏览器内的 OS 桌面模拟器完成，不操作录制者电脑的真实系统。各题共用桌面外观和应用图标，但加载不同业务材料；同题 A/B/C 共享初始材料，方法不同。任务卡的「Demo 操作」只列示范所需应用，「Inference 执行应用」列完整业务所需应用。

1. 在工作台选择 **OS · 36 题**，选择题目与 A/B/C，阅读规则卡、示范范围和逐组预期保存内容。
   「在哪里操作」列出当前示范的图标、菜单、按钮和完整文件路径。文件夹双击进入；Notepad 用 Open… 的 Document 下拉框选择完整路径，再点 OK。每次保存用 Save，保存位置由打开的文件决定。
2. 可预览和试做；“重置示范”创建独立环境。点击“开始录制”会准备干净桌面，请在浏览器分享窗口中选择 OS 应用标签页。
3. 从桌面进入应用，执行各局部示例，展示保存结果。多组示范点击应用右下角“下一组”；最后点击“完成练习”。不录工作台规则卡，不演示完整 inference 流程。
4. 结束后自动上传并保存，无需选择本地录像文件。任务卡显示自动检查结果；填写审核人，确认视频覆盖全部同规则示例后提交审核。服务器录像可回放、下载，切题后保留状态。
5. 审阅台按 OS 分类显示平台、难度、A/B/C、demo 内容、同事录像、inference 目标和独立环境入口，可保存评价与修改建议。

## 任务索引

| 编号 | 任务 | 平台 | 难度 | Demo 组数 |
|---|---|---|---|---:|
| OS-E-01 | 批量规范文件名称 | File Explorer | easy | 1 |
| OS-E-02 | 批量按元数据归档 | File Explorer | easy | 1 |
| OS-E-03 | 批量选择批准版本 | File Explorer | easy | 1 |
| OS-E-04 | 批量保留同名文件两侧 | File Explorer | easy | 1 |
| OS-E-05 | 批量暂停高内存后台进程 | Task Manager | easy | 1 |
| OS-E-06 | 批量处理日志副本个人字段 | Notepad | easy | 1 |
| OS-E-07 | 批量设置外设连接范围 | Device Manager | easy | 1 |
| OS-E-08 | 批量导出事件时间片 | Event Viewer | easy | 1 |
| OS-E-09 | 批量设置既有任务触发 | Task Scheduler | easy | 1 |
| OS-E-10 | 批量整理说明正文 | Notepad | easy | 1 |
| OS-E-11 | 批量控制打印队列状态 | Device Manager 的 Print queue | easy | 1 |
| OS-E-12 | 批量设置文档分页边界 | Notepad | easy | 1 |
| OS-M-01 | 研究材料交接目录制作 | File Explorer | medium | 1 |
| OS-M-02 | 软件版本说明成套编制 | Notepad | medium | 3 |
| OS-M-03 | 现场行动指南编制 | Notepad | medium | 3 |
| OS-M-04 | 迁移配置成套修订 | Notepad | medium | 3 |
| OS-M-05 | 会议打印母稿制作 | Notepad | medium | 1 |
| OS-M-06 | 事故时间线与处置报告 | Notepad | medium | 3 |
| OS-M-07 | 工作目录差异同步 | File Explorer | medium | 3 |
| OS-M-08 | 失败作业依赖链修复 | Task Scheduler | medium | 3 |
| OS-M-09 | 本地回滚点创建与恢复演练 | Task Scheduler | medium | 3 |
| OS-M-10 | 人员资料变更核对与回执 | Notepad | medium | 3 |
| OS-M-11 | 库存批次对账与差异单 | Notepad | medium | 3 |
| OS-M-12 | 双分支字段合并 | Notepad | medium | 3 |
| OS-H-01 | 历史处理环境配置回退 | Notepad、Settings、Task Scheduler | hard | 3 |
| OS-H-02 | 签名软件发布恢复 | Settings、File Explorer、Notepad、Task Scheduler、Event Viewer | hard | 3 |
| OS-H-03 | 历史快照灾后重启 | Transfer Manager、File Explorer、Notepad、Task Scheduler、Terminal | hard | 3 |
| OS-H-04 | 相机素材补录与字幕校正 | Device Manager、Transfer Manager、File Explorer、Notepad、Settings、Task Scheduler | hard | 3 |
| OS-H-05 | 会议材料校样与首次提交 | File Explorer、Notepad、Device Manager、Settings、Task Scheduler | hard | 3 |
| OS-H-06 | 离线资源缓存修复 | Device Manager、Transfer Manager、File Explorer、Notepad、Settings、Task Scheduler、Terminal | hard | 3 |
| OS-H-07 | 嵌套工作区迁移与启动 | File Explorer、Notepad、Settings、Task Scheduler、Terminal | hard | 3 |
| OS-H-08 | 失败构建双阶段恢复 | Task Manager、File Explorer、Notepad、Settings、Task Scheduler | hard | 3 |
| OS-H-09 | 事故证据脱敏归档 | Event Viewer、File Explorer、Notepad、Settings、Task Scheduler | hard | 3 |
| OS-H-10 | 共享盘分发故障修复 | Device Manager、Settings、File Explorer、Notepad、Task Scheduler | hard | 3 |
| OS-H-11 | 存储清理与服务恢复 | File Explorer、Task Manager、Settings、Task Scheduler、Notepad、Terminal | hard | 3 |
| OS-H-12 | 已提交打印件的修订撤回与重发 | Device Manager、File Explorer、Notepad、Settings、Task Scheduler | hard | 3 |

## 逐题规范

### OS-E-01 批量规范文件名称

**平台：** File Explorer

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 对三份含不同词数、连续空格和大小写的文件改名。逐个展示改前、改后名称；扩展名、内容及无关文件保持。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 词间空格改为连字符，连续空格折叠。Replace word spaces with hyphens. 

- **B：** 词间空格改为下划线，连续空格折叠。Replace word spaces with underscores. 

- **C：** 每词首字母大写其余小写，词间一个空格。Title-case each word, single spaces. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 整理指定六份文档的名称，按视频学习的格式处理标题；保留内容、扩展名与范围外文件。

**实例资料：** 六个新标题，含混合大小写和多空格；目标名称不碰撞。

**学习关系：** file-title word formatting while preserving extensions

**验收依据：** 六份目标名称准确；内容、扩展名、父目录与身份不变；非目标不动。


### OS-E-02 批量按元数据归档

**平台：** File Explorer

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 将六份材料归档；两个项目都包含 resource-0 和 resource-1，同一种扩展名也来自不同项目。逐个展示来源、resource_key 与实际目标路径。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 按扩展名目录归档。File by extension. 

- **B：** 按原项目目录/扩展名归档。File by source project, then extension. 

- **C：** 按 Properties 中的 resource_key 目录归档。File by resource_key. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 将范围内六份材料按视频中的目录组织方法移动到已有目标目录，内容和范围外材料保持。

**实例资料：** 项目关系来自初始父目录，resource_key 是现有可见业务键；所有候选目录预先存在。

**学习关系：** destination grouping by file metadata

**验收依据：** 父目录符合学到的方法；内容、身份保持且无额外副本；非目标不动。


### OS-E-03 批量选择批准版本

**平台：** File Explorer

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 完成三个独立文档组。先展示每组四份候选的 Approved、Revision 和 Size；仅在 Approved = Yes 的三份中比较。A 取 Revision 最大，B 取 Size 最小，C 取 Size 最大；展示所选文件和复制结果。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 批准版本中选修订号最高者。Choose the highest approved revision. 先排除 Approved = No；A 比较 Revision（修订号），B/C 比较 Size（字节数）。Properties 可查看这些属性，文件名中的 r 后数字与 Revision 一致。若比较值相同，先按文件名，再按完整路径的 Unicode 码点顺序取首项。

- **B：** 批准版本中选字节数最小者。Choose the smallest approved byte size. 先排除 Approved = No；A 比较 Revision（修订号），B/C 比较 Size（字节数）。Properties 可查看这些属性，文件名中的 r 后数字与 Revision 一致。若比较值相同，先按文件名，再按完整路径的 Unicode 码点顺序取首项。

- **C：** 批准版本中选字节数最大者。Choose the largest approved byte size. 先排除 Approved = No；A 比较 Revision（修订号），B/C 比较 Size（字节数）。Properties 可查看这些属性，文件名中的 r 后数字与 Revision 一致。若比较值相同，先按文件名，再按完整路径的 Unicode 码点顺序取首项。

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为四个独立文档组分别选出视频方法确定的批准版本，复制到各组已有 Selected 目录；所有原件保持。

**实例资料：** 四组批准和未批准版本，revision/approved/bytes 均通过现有属性可见；路径唯一。

**学习关系：** approved-version selection criterion

**验收依据：** 每组恰一份正确来源与内容的副本；全部源和非目标不变。


### OS-E-04 批量保留同名文件两侧

**平台：** File Explorer

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 处理三组同名来件与现有件，双方内容、修订号不同；展示保留后的两份文件名及内容，不覆盖丢失任何一侧。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 现有件留原名，来件加 -incoming。Existing keeps its name; incoming gets -incoming. 

- **B：** 来件留原名，现有件加 -previous。Incoming keeps its name; existing gets -previous. 

- **C：** 两侧分别加 -r{revision}，原名留空。Both get their own -r{revision} suffix. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 处理四组同名来件和现有件，按视频中的命名保留办法保存双方内容；无冲突来件原名保留。

**实例资料：** 四组不同目录冲突；两侧修订不同；所有后缀名预留空闲。

**学习关系：** existing-versus-incoming conflict naming convention

**验收依据：** 两侧内容各保留一份且名称对应正确；无冲突件原名保留；其他对象不变。


### OS-E-05 批量暂停高内存后台进程

**平台：** Task Manager

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 查看九个后台进程的内存，覆盖 127/128/129、255/256/257、383/384/385 MB；按同一阈值处理所有对象，保留范围外系统进程。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 内存达到 128 MB 时暂停。Pause workers using at least 128 MB. 示范处理所有 Background worker，范围外 Protected system service 保持。

- **B：** 内存达到 256 MB 时暂停。Pause workers using at least 256 MB. 示范处理所有 Background worker，范围外 Protected system service 保持。

- **C：** 内存达到 384 MB 时暂停。Pause workers using at least 384 MB. 示范处理所有 Background worker，范围外 Protected system service 保持。

**Demo 操作应用：** Task Manager

**从哪里进入：** 左下角 Start → Task Manager。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 对指定六个后台进程采用视频展示的内存条件暂停命中对象，未命中与范围外对象保持原状态。

**实例资料：** 冻结内存值含 127/128、255/256、383/384 MB；至少各有命中且初始 Running 的对象。

**学习关系：** memory threshold and inclusive comparison

**验收依据：** 命中进程为 Paused；未命中初始状态保持；锁、名称及非目标进程不变。


### OS-E-06 批量处理日志副本个人字段

**平台：** Notepad

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 修改三份日志副本，每份含不同联系人记录；展示原始值、处理后字段及保存结果，原始日志不变。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** contact 值替换为 [REDACTED]，保留字段。Mask contact values as [REDACTED]. operator_id 是纯数字标识，例如 1004；C 写为 Contact-1004。保留 operator_id 本身及其他字段。

- **B：** 删除 contact 字段。Remove contact fields. operator_id 是纯数字标识，例如 1004；C 写为 Contact-1004。保留 operator_id 本身及其他字段。

- **C：** contact 值替换为 Contact-{operator_id}，operator_id 保留。Replace contact with Contact-{operator_id}. operator_id 是纯数字标识，例如 1004；C 写为 Contact-1004。保留 operator_id 本身及其他字段。

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择下列待编辑文件的完整路径 → OK。不要打开默认选中的 Unrelated note.txt。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按视频中的个人字段处理方法保存六份已有日志副本；保留事件 ID、时间和原始日志。

**实例资料：** 每份日志副本已可编辑，operator_id 为公开合成编号；无额外敏感字段；源文件与副本清晰分开。 operator_id/contact 只作为普通 JSON 行内容，不增加系统模型字段或专用处理按钮。

**学习关系：** contact-field transformation

**验收依据：** 所有行 contact 处理正确；事件 ID、时间、描述与 operator_id 不变；原始日志未改。


### OS-E-07 批量设置外设连接范围

**平台：** Device Manager

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 处理六个不同类别和初始连接状态的设备，展示命中与不命中类别的结果；不动范围外打印机。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 范围内仅连接 Camera 类，其余断开。Connect only Camera devices; disconnect other target categories. 

- **B：** 范围内仅连接 Printer 类，其余断开。Connect only Printer devices; disconnect other target categories. 

- **C：** 范围内仅连接 Network storage 类，其余断开。Connect only Network storage devices; disconnect other target categories. 

**Demo 操作应用：** Device Manager

**从哪里进入：** 左下角 Start → Device Manager。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 对清单中的外设按视频中的使用类别设置连接状态，其余设备保持。

**实例资料：** 每类至少两台，初始状态混合；不改变访问权限，不要求刷新、配对或驱动安装。

**学习关系：** device-category connection policy

**验收依据：** 范围内各连接状态正确；非目标设备和共享盘 access 不变。


### OS-E-08 批量导出事件时间片

**平台：** Event Viewer

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 对三个不同时间锚点导出窗口。展示锚点、两端边界、边界外记录和实际导出内容，所有时间按同一时区比较。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 锚点前两分钟至锚点。Export from two minutes before the anchor through the anchor. 闭区间包含两端；同一时区，不转换时刻。

- **B：** 锚点至锚点后两分钟。Export from the anchor through two minutes after it. 闭区间包含两端；同一时区，不转换时刻。

- **C：** 锚点前后各一分钟。Export one minute before through one minute after. 闭区间包含两端；同一时区，不转换时刻。

**Demo 操作应用：** Event Viewer

**从哪里进入：** 左下角 Start → Event Viewer。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为四个给定锚点各导出一份日志时间片，窗口取法从视频学习；源日志不变。

**实例资料：** 四个锚点分属两通道；锚点和公共时区明确；所有候选窗口均有记录。

**学习关系：** anchor-relative time window with inclusive endpoints

**验收依据：** 每个导出事件集合精确符合窗口，来源通道与锚点对应；源日志不变。


### OS-E-09 批量设置既有任务触发

**平台：** Task Scheduler

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 为三项已有作业保存同一触发设置；展示保存后的值，输入、输出、依赖不变，不运行作业。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 所有目标任务设为 Manual。Set target triggers to manual. 

- **B：** 所有目标任务设为 When idle。Set target triggers to idle. 

- **C：** 所有目标任务设为 When plugged in。Set target triggers to plugged-in. 

**Demo 操作应用：** Task Scheduler

**从哪里进入：** 左下角 Start → Task Scheduler。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为六个指定任务按视频方法设置触发方式，不改变输入、输出、依赖，也不要运行任务。

**实例资料：** 六个已存在任务参数各异，初始触发混合；输出尚未生成。

**学习关系：** task trigger setting

**验收依据：** 目标 trigger 正确；输入输出依赖与执行次数保持；非目标不变。


### OS-E-10 批量整理说明正文

**平台：** Notepad

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 整理三份正文不同的文档；每份含两段多行正文、标题和代码围栏。保存后展示正文的转换与其他部分保持。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 正文每段合并一行，段间一空行。Join each paragraph into one line; one blank line between paragraphs. 

- **B：** 每段首新增两个空格，保留段内换行。Add two spaces at each paragraph start; keep internal line breaks. 

- **C：** 正文每段合并为一个 - 项目符号行。Join each paragraph into one bullet line beginning - . 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择下列待编辑文件的完整路径 → OK。不要打开默认选中的 Unrelated note.txt。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按视频方法整理六份文档正文，标题、代码围栏及其他文档不变。

**实例资料：** 空行分段，连续空白行视为一个分隔；A/C 合并非空行插一个空格，行内字符保持；无初始列表标记。

**学习关系：** body-paragraph formatting

**验收依据：** 正文完全符合规则；标题和围栏内容逐字保持；原始保护副本不变。


### OS-E-11 批量控制打印队列状态

**平台：** Device Manager 的 Print queue

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 处理八份页数不同的 Packet 作业；展示阈值本身与阈值两侧的队列状态。保留无关作业，不取消任何作业。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 页数大于 4 时暂停。Pause packets with more than 4 pages; leave other target packets queued. 示范处理所有 Packet，范围外 Unrelated draft 保持。

- **B：** 页数大于 6 时暂停。Pause packets with more than 6 pages; leave other target packets queued. 示范处理所有 Packet，范围外 Unrelated draft 保持。

- **C：** 页数大于 8 时暂停。Pause packets with more than 8 pages; leave other target packets queued. 示范处理所有 Packet，范围外 Unrelated draft 保持。

**Demo 操作应用：** Device Manager

**从哪里进入：** 左下角 Start → Device Manager。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按视频中的页数条件暂停指定打印作业，其余范围内作业保持 Queued；不要取消作业。

**实例资料：** 多个已提交作业含 4/5、6/7、8/9 页；打印机均已连接，作业初态为 Queued 或 Paused。

**学习关系：** page-count threshold and strict comparison

**验收依据：** 命中为 Paused，其他范围内为 Queued；成员、文档、设备和非目标队列保持；无 Cancelled。


### OS-E-12 批量设置文档分页边界

**平台：** Notepad

**难度：** easy。一个持续环境内对多个新对象反复应用同一方法。

**Demo 要录什么：** 为三份内容不同但均含 Appendix、References、Signature 的文档插入分页符；展示分页边界和保存内容。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 在 Appendix 标题前插入分页符。Insert a page break immediately before Appendix. 

- **B：** 在 References 标题前插入分页符。Insert a page break immediately before References. 

- **C：** 在 Signature 标题前插入分页符。Insert a page break immediately before Signature. 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择下列待编辑文件的完整路径 → OK。不要打开默认选中的 Unrelated note.txt。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 给六份指定文档按视频方法插入一个分页符，保留全部文字和其他文档。

**实例资料：** 每份文档三节顺序与正文长度不同，各标题恰一次；初始无分页符。

**学习关系：** section-heading page-break boundary

**验收依据：** 每份恰一个 form-feed 且位置正确；去掉 form-feed 后内容与初始相同。


### OS-M-01 研究材料交接目录制作

**平台：** File Explorer

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 将已选定的三份批准材料放入相应交接目录；展示类别、来源和资源键，以及实际保存位置。无需录版本筛选和依赖收集。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 按资料类别分组。Group by resource category. 

- **B：** 按来源项目分组。Group by source project. 

- **C：** 按业务资源键 resource_key 分组。Group by resource_key. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按请求中的项目范围和依赖清单制作本地交接目录，采用批准修订，保留原件和既有用户编辑；交接目录分组方法从视频学习。

**实例资料：** 外部公共请求给出交付范围、资料依赖关系和目标根目录；文件 Properties 有 approved/revision/resource_key。目标中有要保护的用户文件。

**学习关系：** handoff folder grouping

**验收依据：** 输出集合精确等于请求的批准依赖闭包；分组正确；每份来源和内容对应；无草稿、无缺附件；原件与用户编辑保持。


### OS-M-02 软件版本说明成套编制

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 将两条不同 ID、不同正文的变更写成指定格式。录三组不同变更，保留输入；不录发布文档成套编制。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** change_id: summary。change_id: summary 

- **B：** summary [change_id]。summary [change_id] 

- **C：** [change_id] summary。[change_id] summary 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 根据当前有效变更请求整理版本说明、配置中的 release_version 和交付索引，确保三者与源文件版本一致；变更条目格式从视频学习。

**实例资料：** 预置请求各修订、源应用文本、配置、批准变更和空白索引文件；全部通过 Notepad Open 可读写，源文件受保护。

**学习关系：** change-entry text format

**验收依据：** 说明变更集合完整且无撤回项；说明/配置/源版本一致；索引引用正确文档和修订；原始变更记录不变。


### OS-M-03 现场行动指南编制

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 将两位不同姓名、电话的联系人转换为对应显示格式。录三组不同联系人，不录现场安排关联。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 姓名 <phone>。Name <phone> 

- **B：** 姓名 (phone)。Name (phone) 

- **C：** phone — 姓名。phone — Name 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 依据最新现场安排制作可执行的文字指南，匹配地点、时段、负责人及所需资源，保存到已给出的输出文档；联系人显示格式从视频学习。

**实例资料：** 请求修订、地点表、班次表、联系人和资源清单作为普通文档；有同名不同人员 ID 与撤销班次，输出文件预置。

**学习关系：** person-name and phone display format

**验收依据：** 每个有效安排有正确地点、时段、人员 ID、资源 ID；无撤销项；联系人符合格式；所有输入原件不变。


### OS-M-04 迁移配置成套修订

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 对三份不同的六条 references 列表排序；三组使用不同文件名、逻辑编号和输入顺序，每组 Code、Config、Data 各两条，类别、编号、路径排序互不等同。逐组展示输入和保存结果，不录完整迁移。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** references 按目标路径字典序排列。Order paths alphabetically. A 按完整目标路径升序；B 按 number 数值升序；C 先按 Code → Config → Data 分组，同类别再按完整目标路径升序。路径逐字符比较（本题均为小写 ASCII，因此同目录内就是文件名字母序），不是按原始列表顺序。

- **B：** references 按公开资源表中的逻辑编号排列。Order by logical number. A 按完整目标路径升序；B 按 number 数值升序；C 先按 Code → Config → Data 分组，同类别再按完整目标路径升序。路径逐字符比较（本题均为小写 ASCII，因此同目录内就是文件名字母序），不是按原始列表顺序。

- **C：** references 按资源类别 Code、Config、Data 再按路径排列。Order Code, Config, Data; within each category, order full paths alphabetically. A 按完整目标路径升序；B 按 number 数值升序；C 先按 Code → Config → Data 分组，同类别再按完整目标路径升序。路径逐字符比较（本题均为小写 ASCII，因此同目录内就是文件名字母序），不是按原始列表顺序。

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为已经复制好的新工作区修订 manifest 和 app-settings，保留偏好，使所有内部引用指向新副本；manifest 资源引用排列方法从视频学习。

**实例资料：** 现有复制结果、新根路径、资源对照、工作清单、app-settings 和偏好；内部资源最终均为现有探测支持的绝对路径，外部引用不混入待探测数组。

**学习关系：** reference ordering and tie-breaking

**验收依据：** entry/startup 一致；全部 references 精确指向请求中的新副本且顺序正确；偏好保持；源配置不变。


### OS-M-05 会议打印母稿制作

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 给三个不同章节标题编号并保存。展示每个标题的编号对应关系，不录选稿、组稿和打印提交。

**示范组织：** 1 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 1.、2. 等阿拉伯编号。Arabic numbering. 

- **B：** I.、II. 等罗马编号。Roman numbering. 

- **C：** A.、B. 等字母编号。Letter numbering. 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 依据有效会议议程和批准章节，完成可交付的打印母稿、目录及页码核对表；章节编号方式从视频学习。

**实例资料：** 批准章节、议程顺序、明确每页最大行数、页码核对表和空母稿；全部是普通文档。打印设备与队列不参与本题。

**学习关系：** chapter heading numbering

**验收依据：** 章节集合/修订/次序正确；每页不超公共行限；编号和目录页码与实际 form-feed 一致；输入原件不变。


### OS-M-06 事故时间线与处置报告

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 将两个不同日期/时间转换并保存。录三组，只改变表示形式，不改变时刻；不录事故搜集和时间线编排。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** YYYY-MM-DD HH:MM:SS。YYYY-MM-DD HH:MM:SS 

- **B：** YYYY/MM/DD HH:MM:SS。YYYY/MM/DD HH:MM:SS 

- **C：** YYYY-MM-DDTHH:MM:SS。YYYY-MM-DDTHH:MM:SS 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 依据已提供的日志导出和本地处置记录，形成当前事故的完整时间线与处置结论；时间显示格式从视频学习。

**实例资料：** 日志导出已准备好，含多通道同事件、重复记录与另一起事故；处置记录有动作和恢复验证；无需打开 Event Viewer。

**学习关系：** timestamp representation

**验收依据：** 事件覆盖与来源准确；同事件不重复计数；处置和恢复验证有依据；时间值不变仅格式变；原记录不变。


### OS-M-07 工作目录差异同步

**平台：** File Explorer

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 替换一份同名旧文件前先按指定方法保留旧内容，展示新旧两侧均可恢复。录三组不同内容，不录整个目录同步。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 旧文件移动到已有 Previous 目录。Move the old file into Previous before replacing it. 

- **B：** 旧文件在原处加 -previous 后缀。Keep old content with a -previous suffix. 

- **C：** 旧文件复制到已有 Snapshot 目录后再替换。Copy the old file into Snapshot before removing the original conflict. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按有效同步清单把工作目录更新到目标版本，保留本地独有编辑与所有被替换内容；旧文件保留方式从视频学习。

**实例资料：** 源/目标文件有资源键、修订和可比较内容摘要；外部请求公开新增/更新/退出范围及本地编辑保护对象；后缀无碰撞。

**学习关系：** preservation of replaced file contents

**验收依据：** 活动集合符合请求；保留对象不被覆盖；被替换/退出内容可恢复；相同摘要对象不制造重复；其他源不变。


### OS-M-08 失败作业依赖链修复

**平台：** Task Scheduler

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 给 inventory、validate 两个阶段建立对应名称，展示阶段顺序与命名关系。录三组小项目，不录完整六阶段修复。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** {序号两位}-{operation}。Name stages NN-operation. 

- **B：** {operation}-{序号两位}。Name stages operation-NN. 

- **C：** step{序号两位}_{operation}。Name stages stepNN_operation. 

**Demo 操作应用：** Task Scheduler

**从哪里进入：** 左下角 Start → Task Scheduler。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按公共业务阶段关系重建受影响的作业链，修正输入、输出和依赖，保留无关作业并重新完成交付；新建作业名称格式从视频学习。

**实例资料：** 流水线为现有 inventory→validate→index→package→verify→deliver 合法链；输入输出目录预置；工具可用、文件合法、无锁。公共请求给业务阶段关系。

**学习关系：** stage task-name format

**验收依据：** 目标依赖拓扑和输入输出正确；最终产物继承正确输入；受影响后继重新运行；无关作业配置与结果保持。


### OS-M-09 本地回滚点创建与恢复演练

**平台：** Task Scheduler

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 用已准备的四份资料展示 inventory、backup、restore 的输出目录关系。录三个独立项目；不录比较、复验和完整恢复演练。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 各阶段输出到各自预置阶段目录。Use separate stage output folders. 

- **B：** 各阶段报告集中到 Reports，恢复文件到 Recovery。Use central Reports; restore into Recovery. 

- **C：** 备份进入 Snapshots，其余报告进入 Reports，恢复文件进入 Recovery。Use Snapshots for backup, Reports for other reports, and Recovery for restored files. 

**Demo 操作应用：** Task Scheduler

**从哪里进入：** 左下角 Start → Task Scheduler。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为已经就绪的项目输入创建可恢复的回滚点，恢复到已有空目录并逐文件比较；各阶段成果的目录组织方法从视频学习。

**实例资料：** backup 域完整输入已就绪，文本包含在备份范围、工具已启用、旧快照存在；所有候选目录预置。目标恢复目录无冲突，无需其他界面配置。

**学习关系：** stage output-folder organization

**验收依据：** 本次快照包含全部请求内容；恢复实际消费该快照；恢复文件集合及内容一致；报告位置符合规则；旧快照和源保持。


### OS-M-10 人员资料变更核对与回执

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 将一项已知通过、一项已知拒绝的结论写为对应表示。录三组不同请求 ID；不录申请核查和修改人员主档。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 通过/不通过使用 Approved/Rejected。Approved/Rejected 

- **B：** 通过/不通过使用 accepted=true/false。accepted=true/false 

- **C：** 通过/不通过使用 status=ok/error。status=ok/error 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 处理当前有效人员资料变更批次，按人员 ID 核对申请与佐证，修改授权字段并编制逐项回执；回执中的处理结论表示方式从视频学习。

**实例资料：** 预置变更申请各修订、人员主表、佐证表和回执文档；含同名不同 ID、撤回申请和佐证不一致项。数据均为合成普通文本。

**学习关系：** approval-result encoding

**验收依据：** 主表仅包含核准变更；被拒/撤回/范围外字段保持；每条有效申请有准确回执且格式正确；主表和回执逐 ID 一致；佐证原件保持。


### OS-M-11 库存批次对账与差异单

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 展示不同产品容量下的数量表示。三组覆盖非零余数、整箱和整包；容量来自输入，不能统一猜一个容量，不录整批对账。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 统一以最小单位件表示：N pcs。N pcs 

- **B：** 按公开箱容量表示为 C box + R pcs，不足一箱保留余件。C box + R pcs 

- **C：** 按公开包容量表示为 P pack + R pcs，不足一包保留余件。P pack + R pcs 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 核对当前有效库存周期的收货、退回和领用记录，修正工作台账并形成逐批次差异单；数量的显示方法从视频学习。

**实例资料：** 台账、收货/退回/领用记录、记录修订与撤销、产品单位容量表和差异单均为普通文本；同名产品以 product_id/lot_id 区分，输出文档预置。

**学习关系：** quantity units, quotient and remainder representation

**验收依据：** 每批次最小单位数正确；无重复/撤销记录参与；三种表示可反解同一数量；台账与差异单一致；来源记录和范围外库存不变。


### OS-M-12 双分支字段合并

**平台：** Notepad

**难度：** medium。一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。

**Demo 要录什么：** 对基线、主分支、审阅分支进行局部字段合并；含主分支较新、审阅较新和同时间冲突，以及两边独有字段。录三组不同数值。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 同字段冲突优先主分支。Conflicts use main. 双方独有字段都保留；C 时间相同取 main。

- **B：** 同字段冲突优先审阅分支。Conflicts use review. 双方独有字段都保留；C 时间相同取 main。

- **C：** 同字段冲突选修改时间较新者，并列取主分支。Conflicts use newer field timestamp; ties main. 双方独有字段都保留；C 时间相同取 main。

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 依据共同基线和批准范围，合并两个工作副本到已有输出文档，保留双方独有修改和全部原件；同字段冲突取值方法从视频学习。

**实例资料：** 基线、两分支含稳定对象 ID 和字段修改时间；冲突均为明确 JSON 标量，不要求自动合并器。

**学习关系：** conflicting-field precedence

**验收依据：** 输出等于三方字段合并；独有字段保留；冲突值正确；引用闭包一致；基线与双方原件不变。


### OS-H-01 历史处理环境配置回退

**平台：** Notepad、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 将两个可见配置差异写为记录，before 与 after 均取输入。录三组不同值，不查历史作业，不回退设置和重跑验证。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 每行 key: before -> after。key: before -> after 

- **B：** 带列头 key,before,after 的 CSV。CSV key,before,after 

- **C：** JSON 数组，每项含 key、before、after。JSON key/before/after array 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 根据受保护的历史成功作业报告，将请求指定的处理配置回退到当时状态，并用新的验证作业确认实际生效；配置差异记录格式从视频学习。

**实例资料：** 有多个历史作业报告，公共请求指定 project/run 和需回退的现有设置键；报告含已支持 settings。当前设置与目标多项不同，另有必须保持的设置。只恢复现有 archive.format、verification.mode、media.preview、scheduler.trigger 等合法字段。

**学习关系：** configuration difference record format

**验收依据：** 请求键等于指定历史配置；范围外设置保持初值；新作业实际 configuration 与相关产物参数采用恢复值；差异记录的 before/after 准确；历史报告与已完成作业不变。

**跨应用必要依赖：**

- Notepad 历史报告 settings→Settings 对应现有键
- Settings 保存的值→Task Scheduler 新作业 configuration/产物参数
- Scheduler 复验结果→Notepad 差异记录及结论


### OS-H-02 签名软件发布恢复

**平台：** Settings、File Explorer、Notepad、Task Scheduler、Event Viewer

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 将两条变更写成指定条目格式。录三组不同 ID 和正文，不录修工具、构建、签名或发布。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** change_id: summary。change_id: summary 

- **B：** summary [change_id]。summary [change_id] 

- **C：** [change_id] summary。[change_id] summary 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 修复当前发布请求中的工具和配置问题，生成版本一致的签名发布包，保留上次发布；版本说明变更条目格式从视频学习。

**实例资料：** release 域中 compiler 或 signer 缺失，entry 路径或说明版本错误；源版本、配置和旧发布均可见。

**学习关系：** release change-entry format

**验收依据：** 应用、配置、说明版本一致；实际签名验证通过且对应本轮构建；交付包含该签名内容；旧发布与源保持。

**跨应用必要依赖：**

- Scheduler/事件错误→Settings 的具体工具状态
- Notepad 工作配置→Scheduler 的构建入口和版本
- Scheduler 生成构建→签名/校验→文件交付结果


### OS-H-03 历史快照灾后重启

**平台：** Transfer Manager、File Explorer、Notepad、Task Scheduler、Terminal

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 把已给的数据与报告放入对应恢复目录及其 Reports 子目录。录三个不同项目，只展示布局，不筛快照或恢复任务。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 项目下 Recovery/Restored，报告放其 Reports。Recovery/Restored with Reports inside. 

- **B：** 项目下 Restored/Workspace，报告放其 Reports。Restored/Workspace with Reports inside. 

- **C：** 项目下 Recovered，报告放其 Reports。Recovered with Reports inside. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 从最新完整快照恢复项目，保留本地编辑，修复引用并恢复快照记录的任务，使 restore-check 通过；恢复工作区布局从视频学习。

**实例资料：** restoration 域含更新但不完整的快照、完整旧快照、未下载输入、同名本地编辑及缺失/错误任务。

**学习关系：** recovery folder layout

**验收依据：** 采用最新完整快照；恢复内容和引用正确；原本地编辑保留；快照中的每个任务输入/输出/trigger 正确且 Ready；探测真实通过。

**跨应用必要依赖：**

- 快照文件内容→Notepad 中的新引用
- 快照 scheduled_tasks→Scheduler 的实际任务配置
- Scheduler 恢复任务与文件→Terminal restore-check


### OS-H-04 相机素材补录与字幕校正

**平台：** Device Manager、Transfer Manager、File Explorer、Notepad、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 使用已配对的片段和字幕设置同一预览规格，生成并查看实际输出尺寸。录三个项目，不录连接相机、下载或字幕校正。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** Compact：640×360。Compact 640 x 360. 

- **B：** Review：1280×720。Review 1280 x 720. 

- **C：** Detailed：1920×1080。Detailed 1920 x 1080. 

**Demo 操作应用：** Settings → Task Scheduler

**从哪里进入：** 左下角 Start → Settings。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 完成当前拍摄的批准素材补录，修正字幕关联并生成可追溯预览库；预览规格从视频学习。

**实例资料：** media 域相机断连、sidecar 尚未下载且混有上一场次 clip_id；当前 take 与元数据已存在。

**学习关系：** preview size profile

**验收依据：** 每个预览的尺寸、clip_id、caption、source_hash 正确；目录引用真实预览；无旧场次混入；源素材保持。

**跨应用必要依赖：**

- Device Manager 相机状态→Transfers 的 sidecar 下载
- 下载内容→Files 导入→Notepad 字幕校正
- Settings 规格和 sidecar 内容→Scheduler 实际预览与目录


### OS-H-05 会议材料校样与首次提交

**平台：** File Explorer、Notepad、Device Manager、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 用已准备的短文档设置纸型、单双面及顺序，生成布局与校样并查看结果。录三组，不提交打印，不录组稿和故障修复。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** A4、双面、正序。A4, duplex, forward. 

- **B：** Letter、双面、正序。Letter, duplex, forward. 

- **C：** A4、单面、倒序。A4, simplex, reverse. 

**Demo 操作应用：** Settings → Task Scheduler

**从哪里进入：** 左下角 Start → Settings。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 完成当前批准文档包的排版校样与首次队列提交，选择兼容设备，保留全部原件；打印配置组合从视频学习。

**实例资料：** print 域工作副本、页容量、能力不同的打印机；至少一台支持全部候选组合；公共请求不另行固定纸型/单双面以免泄漏或冲突。 批准封面与公共请求不固定纸型或单双面；三种条件共享同一业务请求。

**学习关系：** paper, duplex and page-order profile

**验收依据：** 内容与修订正确；页容量合法；组合符合 demo 且设备支持；队列文档与最后通过的校样一致；未提前取消或额外提交。

**跨应用必要依赖：**

- Device Manager 能力→Settings 合法配置
- Notepad 分页内容→Scheduler layout/proof
- Scheduler deliver→Device Manager 的实际队列内容


### OS-H-06 离线资源缓存修复

**平台：** Device Manager、Transfer Manager、File Explorer、Notepad、Settings、Task Scheduler、Terminal

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 对已缓存的四份资源按同一方法命名，同步指南链接并验证离线可读。录三个项目；不录下载、设备恢复或缓存重建。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 保留原文件名。Keep original resource names. C 使用 R0/R1/R2/R3，对应四份公开资源的顺序，保留扩展名；指南内引用须同步。

- **B：** 文件名加 {project_id}- 前缀。Prefix names with project_id-. C 使用 R0/R1/R2/R3，对应四份公开资源的顺序，保留扩展名；指南内引用须同步。

- **C：** 用公共资源 ID 作文件名并保留原扩展名。Use R0/R1/R2/R3 stems and preserve extensions. C 使用 R0/R1/R2/R3，对应四份公开资源的顺序，保留扩展名；指南内引用须同步。

**Demo 操作应用：** File Explorer → Notepad → Terminal

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 为当前现场任务修复下载和缓存缺项，使地图、联系人及指南断网可用，保留下载原件；工作包内文件命名方法从视频学习。

**实例资料：** offline 域中 relay 断连、下载未完成，旧缓存缺联系人；源指南仍指网络路径。资源 ID 对照公开；全部方案使用现有绝对路径解析。

**学习关系：** cached resource naming and corresponding links

**验收依据：** 断网 probe 实际读到地图/联系人；指南链接绑定正确 source 身份和版本；命名正确；旧下载源保持；无远程链接残留。

**跨应用必要依赖：**

- Device Manager relay→Transfer Manager 完成下载
- Files 文件名→Notepad 指南→Scheduler 缓存文件
- Settings 断网及缓存内容→Terminal 实际离线访问


### OS-H-07 嵌套工作区迁移与启动

**平台：** File Explorer、Notepad、Settings、Task Scheduler、Terminal

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 对一份同名冲突保存本地旧内容并放入来件，展示两侧位置和可恢复内容。录三个不同项目，不录路径修订和工作区启动。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 把整个新工作区放到原目标的独立兄弟目录，原目标不动。Use a fresh sibling workspace; leave the original destination untouched. 

- **B：** 将冲突现有文件加 -local 后缀后在原目标迁移。Rename the conflicting local file with -local before copying incoming. 

- **C：** 先把冲突现有文件复制到已有 Local-preserved 目录，再清除冲突并在原目标迁移。Copy the local file to Local-preserved, then clear the original conflict. 

**Demo 操作应用：** File Explorer

**从哪里进入：** 桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 把完整工作区迁移到请求的新位置，保留目标已有编辑和源工作区，保持用户偏好并验证启动；冲突保留方法从视频学习。

**实例资料：** migration 域嵌套源资源、manifest、app-settings、偏好和目标本地编辑；tools 可禁用；三个方案所需目录初态均存在。

**学习关系：** local file conflict preservation

**验收依据：** 新入口和内部引用实际可达；app-settings root/startup 正确且偏好保持；本地编辑按策略可恢复；源内容保持；启动 probe 通过。

**跨应用必要依赖：**

- Files 冲突处理→Scheduler 可写入目标
- Notepad manifest/settings→Scheduler 迁移内容
- 迁移结果与偏好→Terminal workspace-open


### OS-H-08 失败构建双阶段恢复

**平台：** Task Manager、File Explorer、Notepad、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 将已经给出的测试结果转成摘要。三组使用不同 build_artifact、断言和值，保留全部字段；不录构建、测试修复和进程恢复。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 逐行 key: value。key: value lines 公共字段顺序为 build_artifact、passed、assertions；嵌套断言是 JSON，CSV 使用标准双引号转义。

- **B：** JSON 对象，字段名与原结果一致。JSON object 公共字段顺序为 build_artifact、passed、assertions；嵌套断言是 JSON，CSV 使用标准双引号转义。

- **C：** 带列头的一行 CSV，列序沿用源结果。CSV build_artifact,passed,assertions 公共字段顺序为 build_artifact、passed、assertions；嵌套断言是 JSON，CSV 使用标准双引号转义。

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 恢复指定失败构建，修复独立的构建和测试问题，保留旧包并恢复锁所有者状态；测试摘要表示方式从视频学习。

**实例资料：** build 域真实所有者锁、build_ready=false、独立 test_expectations 错误；源常量和公开请求给正确 project/revision，不能把断言改为无条件通过。 所有摘要字段均取现有测试结果内容；project/revision 只来自 assertions，不能虚构顶层字段。

**学习关系：** test-result summary representation

**验收依据：** build/test 绑定同一输入；测试期望等于公共真实规格且断言全部通过；摘要准确引用实际测试；旧包保留；原进程状态恢复。

**跨应用必要依赖：**

- Task Manager 锁状态→Files 工作副本获取
- Notepad 修复配置→Scheduler 的构建与测试分支
- Scheduler 测试结果→Notepad 摘要→最终包


### OS-H-09 事故证据脱敏归档

**平台：** Event Viewer、File Explorer、Notepad、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 对已准备的事故副本应用同一种敏感字段处理，展示不同记录及重复个人值的一致结果。录三组，不录日志搜集和打包。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 保留字段并掩码敏感值。Mask personal values. 

- **B：** 删除敏感字段。Remove personal fields. 

- **C：** 用现有处理器生成稳定合成代号。Use stable pseudonyms. 

**Demo 操作应用：** Settings → Task Scheduler

**从哪里进入：** 左下角 Start → Settings。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 按事故时间和敏感字段表制作完整可共享证据包，形成可追溯时间线，保留原日志；敏感值处理方法从视频学习。

**实例资料：** evidence 域两通道原始日志、事故窗口、字段清单、时间线模板；包含范围外事件和 contact 以外的敏感字段。 导出内容通过 Notepad 写入对应原通道的工作副本，保留来源身份，供脱敏流程校验。

**学习关系：** sensitive-field treatment

**验收依据：** 窗口事件集合准确；所有要求敏感值已处理；事件 ID/时间/描述保留；时间线有实际来源；最终包包含真实脱敏副本和审计链；原日志不变。

**跨应用必要依赖：**

- Event Viewer 导出记录→Files/Notepad 证据与时间线
- Settings 敏感范围/方法→Scheduler 实际脱敏内容
- 脱敏副本→打包审计链→最终交付


### OS-H-10 共享盘分发故障修复

**平台：** Device Manager、Settings、File Explorer、Notepad、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 给已验证的分发载荷设置最终触发方式，展示 Scheduled 且未派发。录三个不同项目，不录选盘、权限修复或前置流水线。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 最终交付 Manual。Final delivery trigger: manual. 

- **B：** 最终交付 When idle。Final delivery trigger: idle. 

- **C：** 最终交付 When plugged in。Final delivery trigger: plugged-in. 

**Demo 操作应用：** Task Scheduler

**从哪里进入：** 左下角 Start → Task Scheduler。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 恢复当前分发请求的正确接收共享盘和载荷，干运行验证后保存待交付计划，不提前分发；最终触发方式从视频学习。

**实例资料：** distribution 域正确 share 断开且只读，另一个可写盘属于错误接收方；载荷说明有旧版本/接收方信息需修订。

**学习关系：** final delivery trigger setting

**验收依据：** 正确 recipient/share；载荷内容及干运行哈希相同；可写验证真实完成；依赖和 trigger 正确；dispatched=false；错误接收盘不被当作成功目标。

**跨应用必要依赖：**

- Notepad 请求载荷身份→Device Manager share 的 recipient
- Device Manager 连接/权限→Settings 目的地→Scheduler dry-run
- dry-run 绑定的载荷→后继调度结果


### OS-H-11 存储清理与服务恢复

**平台：** File Explorer、Task Manager、Settings、Task Scheduler、Notepad、Terminal

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 将 4096、3660、3845 三个字节数分别转换并保存，覆盖精确值及向下/向上舍入。基数 1024，HALF_UP；不录清理、备份或服务恢复。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** 以整数 B 表示。integer B 1 KiB = 1024 B；1 MiB = 1048576 B。定点四舍五入 HALF_UP；精确值也保留规定的小数位。

- **B：** 以 KiB 表示，保留三位小数。KiB, three decimals 1 KiB = 1024 B；1 MiB = 1048576 B。定点四舍五入 HALF_UP；精确值也保留规定的小数位。

- **C：** 以 MiB 表示，保留六位小数。MiB, six decimals 1 KiB = 1024 B；1 MiB = 1048576 B。定点四舍五入 HALF_UP；精确值也保留规定的小数位。

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-509/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 在可恢复和服务状态保持的前提下清理指定项目的可再生缓存，完成压缩与空间核算；维护报告的字节单位表示从视频学习。

**实例资料：** storage 域缓存与伪装 .cache 用户笔记混合；所有者初始状态混合；备份未完成，存储统计含生成报告与压缩对象。

**学习关系：** byte-unit conversion and rounding

**验收依据：** 删除集合只含可再生缓存；先有真实校验的保护备份；用户笔记和项目不变；压缩可无损解码；每个所有者恢复初态；报告单位数值对应实际释放字节。

**跨应用必要依赖：**

- Files regenerable/owners→Task Manager 暂停范围
- Scheduler 校验备份→Files 缓存删除被允许
- Files 删除与进程恢复→Terminal audit→Notepad 数值报告


### OS-H-12 已提交打印件的修订撤回与重发

**平台：** Device Manager、File Explorer、Notepad、Settings、Task Scheduler

**难度：** hard。完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。

**Demo 要录什么：** 给两个不同标题加入各自修订号。录三组不同标题和修订，不录撤回旧队列和重新提交。

**示范组织：** 3 组局部练习，连续录为一段人工视频；一段只呈现 A/B/C 中的一个版本。

- **A：** [r{revision}] {title}。[rN] Title 

- **B：** {title} [r{revision}]。Title [rN] 

- **C：** r{revision} — {title}。rN — Title 

**Demo 操作应用：** Notepad

**从哪里进入：** 桌面单击 Notepad → Open… → Document 选择 /Projects/Project-1001/Workspace/Example input.json → OK。先阅读输入，再打开结果文件。

完整的 A/B/C 逐组按钮路径、输入与保存位置见工作台「在哪里操作」，审阅台也提供同一份录制说明。

**Inference 目标：** 撤回指定已提交旧版打印件，按当前有效修订重新校样提交，保留无关队列和原稿；修订标记的标题格式从视频学习。

**实例资料：** print 域已有 Queued/Paused 旧作业和完整生产者依赖链，公共修订请求改变正文；另有必须保持的无关作业；纸型/单双面/顺序公开固定。

**学习关系：** revision marker placement in a title

**验收依据：** 目标旧队列 Cancelled；新队列含当前正文和正确标记且绑定新校样；目标恰一个有效新版；无关队列保持；旧稿内容可恢复。

**跨应用必要依赖：**

- Device Manager 取消旧队列→Scheduler 原生产任务允许重置
- Notepad 当前修订→Scheduler 新校样/提交
- Scheduler 新提交→Device Manager 一旧取消/一新有效
