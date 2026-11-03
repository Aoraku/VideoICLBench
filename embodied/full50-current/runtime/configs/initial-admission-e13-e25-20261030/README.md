# E13/E25 初态隔离诊断候选（未部署）

2026-10-30：300 条 GUI 探针成功不等于物理初态合格。此目录仅准备了候选配置，未修改远端、未启动 GPU，未修改任务成功规则或评分规则。

## 已证实

- E25C real，card-00 / pool-00 / room_04：三件餐具原地直落，封存 z 约 -10.37 m；tray 仍约 0.82 m。对应日志对 fork 的三个 mesh、spoon、knife 明确报 `Unable to create convex mesh`。这是碰撞构建失败造成的物体穿桌，并非 origin 转换错误，也没有横向爆炸证据。
- E25C text，card-15 / pool-01 / room_02：三件均在桌面且 supported/stable 为真。所有 E25 runtime-bundles 的 E25 taskbinding 与当前配置完全相同；替换 binding 本身没有可证实的修复作用。
- E13C text，card-04 / pool-00 / room_00：phone 仍在相同桌面位置；stand 中心 z=0.789616 m，明显倾倒、supported=False，但 stable=True。E13C real 同为 room_00，stand z=0.862862 m 且 supported=True。不能把 stable 当作初始布局有效的证明。此坏池另有 phone 两个 convex mesh 构建失败；尚未证明 stand 的具体失败机制。
- 已验证的 E13 hframe-v2 ABC 录像使用 `e13_stand_hframe_v2/stand.usda`；当前池仍使用旧 `phone_stand0.usda`。存在明确的录像/评测资产版本偏差。

## 本地候选

`e13-hframe-v2-bindings.candidate.json` 仅替换 `tasks.E13.objects.stand.source_asset`，目标、尺寸、摆位、ABC 规则、质量和摩擦均保持当前值；配套 stand 与纹理 SHA 均已检查。该几何曾在单任务原生 ABC 录像中成功，但尚未验证当前多 room 启动，因此不能直接声称修复。

`e25-recording-validated-robot.control.json` 是 E25C 原生 6/6 通过录像的冻结机器人配置，仅用于隔离对照。它不是修复承诺。与当前 profile 的机器人安装点、控制时长等存在差异，不能未经评估直接替换整个正式评测。

`manifest.json` 记录配置来源、资产 SHA 和不变规则。`observed-initial-failures.private.json` 保存只读取得的精简初态与错误证据。

## 最小验证顺序

1. 在新的独立池输出目录做当前配置的 E25C 对照：相同 seed 放 room_00 与 room_04，单池和双池分别测试；每次保存建模错误与所有 collider 实际表示。首先确认是否为并发 cook/cache 冲突，不能先假设碰撞几何需要改变。
2. E13 ABC 使用独立候选 stand，先检查初始 stand 的真实支持、中心和姿态，再验证原成功条件；phone 缺 mesh 仍必须判为初始化失败。
3. 任何 `Unable to create convex mesh` 都应阻止模型入场。已发生穿桌/倒塌的源初态必须阻止入场，不能通过延长 settle 或放宽 stable 限制掩盖。
4. 所有检查通过后，再验证不同 room 位置和 real/text 配对一致性。不得将某次“碰巧未失败”的初始化作为正式稳定性验收。

可能的并行 cooking/shared cache 冲突目前只是待验证假设；没有改 collision approximation、降低判定阈值、补不可见支撑或重新采样布局。

## 已实现的入场门禁

独立 runtime 的 `initial_layout_failures` 对 E13 phone/stand、E25 四件物体检查真实 supported/released，并把实际 task-frame 中心/姿态与加载后的 seed-resolved recipe 比较。允许 2 cm 中心误差和 10° 姿态误差，仅用于防止错误初态进入评测；不修改成功阈值、接触数据或历史。异常会随原始初态 evidence 写盘并阻止封存，额外 settle 不会尝试“修复”这个异常。四个已捕获初态回放均符合预期：坏两例拒绝、好两例接受。

`VideoICLBench/scripts/harbor/native_collision_admission.py` 提供日志门禁，需 runner 在 native ready 后、GUI/model 前调用。它拒绝实际 `Unable to create convex mesh`，正常 GPU hull 回退 CPU 的 warning 不拒绝。助手未修改该 runner 的最终集成；由 root 合并。

本轮相关 CPU 回归 545 项通过，不能代替下一轮 GPU 初始化与完整任务验收。
