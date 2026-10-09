# 桌面第一人称仿真：阶段性作者录像

2026-10-09。**尚未完成50族／150条件。** 录像、物理执行、可见性和正式actor示范准入分开验收；真人视频与独立agent实验均为0。

## 可见性合格的作者预览

当前93个条件的合格录像（按任务与规则去重），31族A/B/C完整；来自历史冻结源码，不能直接作为最新版服务的示范。

- [可见支架穿杆](visible-preview-v46/index.html)：F13/F36/F49各三段，共九段；孔框、通道壁与铰链支撑均可见（F49与v43按条件去重）；[验收清单](visible-preview-v46/manifest.private.json)、[冻结源码](visible-source-v46.tar.gz)、[道具初态渲染](visible-scene-previews-v46/README.md)。
- [真实铰链展示板](articulation-preview-v43/index.html)：F49-A/B/C三段；[录像验收清单](articulation-preview-v43/manifest.private.json)、[冻结源码](articulation-source-v43.tar.gz)。
- [基础任务](foundation-v1/index.html)：F01、F02、F04、F05、F06、F07共18段；[验收清单](foundation-v1/manifest.private.json)、[冻结源码](foundation-source.tar.gz)。
- [托盘与交接](assembly-preview-v15/index.html)：F22、F47共6段；[验收清单](assembly-preview-v15/manifest.private.json)、[冻结源码](assembly-source-v15.tar.gz)。该页额外保留的F48-C不计入合格数，见下文。
- [扫拢木球](sweep-preview-v48/index.html)：F39-A/B/C三段；[验收清单](sweep-preview-v48/manifest.private.json)、[冻结源码](sweep-source-v48.tar.gz)。
- [最新50题及真人录制卡](../TASKS_50.md)。实物可录性仍需试录确认。

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
- Agentlab的 `visible-recordings-v46` 九条件已全部完成并通过解码与可见性验收。
- [历史完整诊断 v26](diagnostics-v26.private.json)：117条件的成功、失败原因及未满足目标，供逐族修复；不是当前源码验收或独立agent成绩。

相机是模拟第一人称近似视角。各源码包和任务编号均属新版F清单，不与旧rt/rc或旧提案编号混算。

## 新增物理验证

- [扫拢不同布局 v51](physical-acceptance-v51/manifest.private.json)：seed19和37各三规则，六条件全部成功；[源码](tools-source-v51.tar.gz)。收集区排列、颜色、木球半径和共享布局扰动有变化；不宣称跨物体类别泛化。
- [绕障推送 v52](physical-acceptance-v52/manifest.private.json)：三规则全部成功；[源码](tools-source-v52.tar.gz)。[三规则录像](corner-preview-v53/index.html)已全部完成并通过解码与可见性验收；[录像清单](corner-preview-v53/manifest.private.json)、[录像源码](tools-source-v53.tar.gz)。

- [清障搬运物理验收 v66](physical-acceptance-v66/manifest.private.json)：F21三规则全部成功；[冻结源码](clearance-source-v66.tar.gz)。[v67三规则录像](clearance-preview-v67/index.html)已完成解码、可见性和互斥终态审计，计入合格视频数。
- [宽铲开发诊断](shovel-development.private.json)：历史失败与未满足目标，不作为agent成绩。
- [导向板开发诊断](guidance-development.private.json)与[冻结源码、动作及结果归档](guidance-development-history.tar.gz)：保存F44各次真实失败及部分成功；这些开发批次不计入合格视频数；完整三规则成功录像见v81。

- [宽铲承托物理验收 v69](physical-acceptance-v69/manifest.private.json)：F38三规则在同一源码下全部成功（A1240/B1235/C1151动作）；[冻结源码](tools-source-v69.tar.gz)。[宽铲三规则录像](shovel-preview-v69/index.html)已完成完整解码、道具可见性和终态互斥审计，计入合格视频数。

- [导向板送球物理验收 v81](physical-acceptance-v81/manifest.private.json)：同一源码A629/B654/C621动作全部成功，初态一致、终态互斥；[冻结源码](guidance-source-v81.tar.gz)。[三规则视频](guidance-preview-v81/index.html)已通过完整解码、末帧、可见性、实际初态一致和互斥终态审计，计入48段历史合格预览。

- [导向板seed19补充结果](guidance-transfer-v81/batch.private.json)：A失败、B/C成功，不能宣称跨布局全部通过。
- [夹具开发诊断](clamp-development.private.json)及[冻结源码与动作归档](clamp-development-history.tar.gz)：F43仍未通过三规则，不计入合格视频。
- [47族完整诊断进度快照](all-family-v79.live-snapshot.private.json)：冻结[full-v79源码](full-source-v79.tar.gz)，批次仍在运行；不是最终验收结果。

- [接杆与插销盒开发诊断](prototype-development.private.json)及[冻结源码、动作与失败归档](prototype-development-history.tar.gz)：原型未通过完整执行，不能作为示范视频。

- [插销盒失败动作真实重放](lock-debug-v95/README.md)：首帧、打开盖后和失败末帧，用于检查第一人称可见性与实际碰撞，不作为成功示范。

- [执行修复诊断 v95–v102](execution-development-v95-v102.private.json)及[冻结源码与公开动作](execution-development-v95-v102.tar.gz)：分类抓取和插销盒开盖后取件仍失败，原结果保留。

- [分类作者回归 v102](author-regression-v102/manifest.private.json)：F03-A seed0经866个公开动作完整成功，互斥终态检查通过；不是三规则或视频验收。

- [F07分类三规则物理验收 v105](physical-acceptance-v105/manifest.private.json)：A729/B659/C914动作完整成功，初态一致、终态互斥；[冻结源码](classification-source-v105.tar.gz)。三规则录像正在Agentlab执行。
- [F08形状插孔三规则视频](shape-preview-v79/index.html)与[完整审计](shape-preview-v79/manifest.private.json)：已检查孔壁与首末帧，计入51段合格历史视频；[精确源码](full-source-v79.tar.gz)。
- [v79首批画面诊断](verified-preview-v79-first/index.html)：F10-A虽解码通过，但参照不是2×2，与设计不一致，明确排除合格示范；不把物理判定成功冒充设计验收。

- [执行开发记录 v103–v109](execution-development-v103-v109.private.json)及[冻结源码、动作与结果归档](execution-development-v103-v109.tar.gz)：保留分类修复成功、插销盒与拼板失败，不能混作最终统一验收。
- [v79设计审阅排除记录](design-review-v79.private.json)：旧F10拼板任务不符合文档变换关系；物理成功结果保持原样，视频不准入。

- [F16单空位重排三版视频](vacancy-preview-v79/index.html)与[审阅清单](vacancy-preview-v79/manifest.private.json)：按第一人称校正方向描述，保留原始变体与动作；计入54段合格历史预览，源码为full-source-v79.tar.gz。

- 拼板开发证据：[v110](mosaic-development-v110.private.json)、[v111](mosaic-development-v111.private.json)、[v112–v113](mosaic-development-v112-v113.private.json)，各有同名tar.gz保存冻结源码与公开动作；均非三规则成功验收。

- `mosaic-preview-v114/`：修正后的F10三规则完整录像；`mosaic-source-v114.tar.gz`为对应源码，`physical-acceptance-v114/`为Mac无渲染独立复验。
- `stack-recovery-preview-v79/`：F17三规则完整录像及解码证据，对应`full-source-v79.tar.gz`；五层按底部起计。

- `physical-acceptance-v116/` / `ring-source-v116.tar.gz`：F11真实套环三规则成功；旧`ring-diagnostics-v115/`继续保留失败。
- `physical-acceptance-v118/` / `slots-source-v118.tar.gz`：F12按实际槽口判定的三规则物理成功。
- `reference-source-v117.tar.gz`：六组录像批次的精确冻结源码，含可见标记和方向修正；F19最终改用v118的2×3图卡版本。
- `scene-review-v118/`：初态构图审阅图，不是成功录像。

`physical-acceptance-v118/`还包含新版F19三规则成功的独立清单`F19.manifest.private.json`，与F12共享同一冻结源码。三张参照图卡与六工作格的初态构图为scene-review-v118/F19.jpg。

- `ring-preview-v117/`：F11圆环分柱三规则Linux完整成功录像及解码审计；对应`reference-source-v117.tar.gz`。初态图形与终态柱穿环关系可见，终态部分底座图形被环局部遮挡，已在清单记录。

- `rack-preview-v118/`：F12三规则完整成功录像，厚片竖直插入真实槽口；对应`slots-source-v118.tar.gz`。槽号从FPV画面右到左为1/2/3，已明确在录制卡。
- `physical-acceptance-v119/` / `key-source-v119.tar.gz`：F14按真实L形孔边界判断的三规则成功物理执行，尚待录像。

- `key-preview-v119/`：F14三规则完整成功录像，真实L形插块进入对应L形孔；对应`key-source-v119.tar.gz`。
- `relocate-preview-v117/`：F20三规则完整成功录像，在可见目标板中保持不对称图案、旋转90度或180度；对应`reference-source-v117.tar.gz`。

- `physical-acceptance-v120/`：F18盒内成员交换、F31有限空间装箱各三规则物理成功，有分任务清单；对应`contents-source-v120.tar.gz`。盒子允许平移与旋转，仍要求真实装入及任务所需盖闭。

- `correction-preview-v118/`：F19新版2×3参照图卡三规则成功录像、完整解码和视觉审阅证据；对应`slots-source-v118.tar.gz`。初终态均可见三张图卡与工作六格。

- [盖盒与压条取件](access-preview-v117/index.html)：F23/F24各三段；[验收清单](access-preview-v117/manifest.private.json)。
- [参照行迁移](reference-row-preview-v117/index.html)：F28三段；[验收清单](reference-row-preview-v117/manifest.private.json)。两批均对应[reference-source-v117](reference-source-v117.tar.gz)。

- [盒内交换与装盒盖合](contents-preview-v120/index.html)：F18/F31各三段；[验收清单](contents-preview-v120/manifest.private.json)、[冻结源码](contents-source-v120.tar.gz)。

- [数量补齐](topup-preview-v125/index.html)：F27三段；[验收清单](topup-preview-v125/manifest.private.json)、[冻结源码](kits-topup-source-v125.tar.gz)。
