# 已结束v79诊断的失败修复表

冻结版本47族、141条件：96成功、45失败。这是作者执行诊断，不是最终50族验收或agent成绩。F10旧设计不一致，单独排除；F07/F10/F44有后续源码修复，不能据此改写旧结果。

| 任务 | 未通过规则 | 原始原因 |
| --- | --- | --- |
| F07 | A,B,C | RuntimeError: Physical grasp failed for part0_1 |
| F09 | C | RuntimeError: No physically clear hand-relay location |
| F11 | A,B,C | RuntimeError: Dropped red after lift；RuntimeError: Dropped green after lift；RuntimeError: Dropped blue after lift |
| F12 | A,B,C | predicate false |
| F14 | C | predicate false |
| F15 | A,B,C | RuntimeError: Fine positioning did not converge |
| F18 | A,C | predicate false |
| F25 | A,C,B | RuntimeError: Fine positioning did not converge |
| F26 | B | RuntimeError: Action budget exhausted |
| F27 | A,B,C | RuntimeError: Physical grasp failed for spare2 |
| F29 | A,B | predicate false |
| F31 | B,A,C | RuntimeError: Fine positioning did not converge；predicate false |
| F32 | A | predicate false |
| F35 | B,A,C | predicate false；RuntimeError: Physical grasp failed for part1_2 |
| F37 | A,B,C | RuntimeError: Dropped ring0 after lift；predicate false；RuntimeError: Physical grasp failed for ring2 |
| F40 | B | RuntimeError: Some contents did not physically pour from the cup |
| F44 | A,C | RuntimeError: Fine positioning did not converge |
| F45 | A,B,C | RuntimeError: Shaft positioning did not converge |
| F48 | A,B | predicate false |
| F50 | A,B | RuntimeError: Fine positioning did not converge；predicate false |
