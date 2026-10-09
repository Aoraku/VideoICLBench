# 桌面第一人称仿真：阶段性作者录像

2026-10-09。**尚未完成50族／150条件。** 录像、物理执行、可见性和正式actor示范准入分开验收；真人视频与独立agent实验均为0。

## 可见性合格的作者预览

当前30个条件的合格录像（按任务与规则去重），10族A/B/C完整；来自历史冻结源码，不能直接作为最新版服务的示范。

- [可见支架穿杆](visible-preview-v46/index.html)：F13-A/B/C三段，孔框明确可见；[验收清单](visible-preview-v46/manifest.private.json)、[冻结源码](visible-source-v46.tar.gz)、[道具初态渲染](visible-scene-previews-v46/README.md)。
- [真实铰链展示板](articulation-preview-v43/index.html)：F49-A/B/C三段；[录像验收清单](articulation-preview-v43/manifest.private.json)、[冻结源码](articulation-source-v43.tar.gz)。
- [基础任务](foundation-v1/index.html)：F01、F02、F04、F05、F06、F07共18段；[验收清单](foundation-v1/manifest.private.json)、[冻结源码](foundation-source.tar.gz)。
- [托盘与交接](assembly-preview-v15/index.html)：F22、F47共6段；[验收清单](assembly-preview-v15/manifest.private.json)、[冻结源码](assembly-source-v15.tar.gz)。该页额外保留的F48-C不计入合格数，见下文。
- [最新50题及真人录制卡](../../simulator/tabletop50/TASKS_50.md)。实物可录性仍需试录确认。

所有录像均由读取状态的作者控制器通过真实双Panda动作产生，不是独立agent成绩或真人视频。无物体传送、夹爪附着或成功状态注入。

## 视觉复查发现的历史缺陷

以下6段虽通过成功判定和完整解码，静态支架位于相机隐藏的碰撞渲染组，**不得用作agent示范**，也不计入上述合格数量。证据与失败原因保留，修复后重录，不篡改原物理结果。

- F48-C：箱内导向件未显示，保留在托盘与交接历史页。
- [推杆历史页](tools-preview-v34/index.html)：F36-A/B通道未显示；[原验收](tools-preview-v34/manifest.private.json)、[精确冻结源码](tools-source-v34.tar.gz)。
- [穿双孔历史页](mechanics-preview-v42/index.html)：F13-A/B/C孔框未显示；[原验收](mechanics-preview-v42/manifest.private.json)。

私有清单新增 `usable_for_agent_demo` 和 `visual_environment`，明确区分完整解码与道具可见性。最新版录制器记录静态道具可见性，审计器和actor服务拒绝不可见支架视频。正式准入还要求源码版本一致、相同规则、不同示范／推理seed；这里的合格预览数不等于服务中已安装示范数。

## 物理验收与重录

- [物理验收 v42](physical-acceptance-v42/manifest.private.json)：F13双孔穿杆和F36推板送件各三版全部成功，六条件源码一致，各族实际初态相同、终态互斥；[对应源码](mechanics-source-v42.tar.gz)。这不替代视频可见性验收。
- [铰链板物理验收 v43](physical-acceptance-v43/manifest.private.json)：F49三版全部成功，三版初态与铰链角度一致；[对应源码](articulation-source-v43.tar.gz)。完整示范已完成解码与可见性验收，见上方预览。
- Agentlab的 `visible-recordings-v46` 正在统一重录F13、F36、F49九个条件，包含支架可见性证据。
- [历史完整诊断 v26](diagnostics-v26.private.json)：117条件的成功、失败原因及未满足目标，供逐族修复；不是当前源码验收或独立agent成绩。

相机是模拟第一人称近似视角。各源码包和任务编号均属新版F清单，不与旧rt/rc或旧提案编号混算。
