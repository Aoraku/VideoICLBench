# 具身视频规则选择题：后续评测接入

题库为 **50 道题，每题四个选项**。每个任务的 A/B/C 三个视频共用同一题干、同一选项顺序，但有各自答案，总计 150 条答案映射。题库版本冻结后，所有模型和 G0/G1/G2 使用一致的题干及选项顺序。

- `选择题清单与标准答案.md`：人工审阅全卷，含答案，不交给模型。
- `questions.json`：题库；其中任务标识、标题仅供调度使用。
- `answer_key.private.json`：私有答案、源视频 SHA256 和既有标注证据。
- `adapter.py`：后续任务的离线材料适配、视频绑定验证、答题钩子和独立评分。

本目录未安装到当前运行器，未改当前 150 条任务，也不创建巡检、API 请求或仿真 episode。后续导出新任务时由运行器显式调用。题目依据既有已复核的真人视频标注生成，本次没有重新观看全部视频。

## 评测协议

推荐单独统计 `isolated_qa`：从看完视频时的材料建立隔离答题分支，其选项和答案都不进入动作分支。分支隔离由后续运行器保证，适配器本身不克隆会话。

若按“看完视频→答题→操作”接入同一个会话，必须标为 `qa_then_act`：选项已经提示了候选规则，会影响后面的操作，不与没有 QA 的动作基线直接混报。

模型只收到匿名视频及单个 packet 的题干、四个选项、字母回答要求。**不能把整个题库、答案表、分组标签、任务目录、原始视频文件名或私有 grading 元数据挂载给模型。** `packet_id` 是匿名关联标识；private 记录负责映射实际 episode。

答题只记录首次输出，不根据对错重问，不回传标准答案或正确性。格式错误单独记 `format_valid=false, qa_correct=null`，不伪装为原生物理 0 分。汇总时同时报告格式有效率、全部应答数、正确数；需要总体准确率时以全部应答数为分母并注明格式无效计未答对，避免只筛有效答案抬高准确率。原生动作评分保持独立。

同一源视频在 G0/G1/G2 重用时，可以按 episode 关联 QA，但统计视频理解时按视频 SHA256 去重，不能算三份独立视频证据。真人和仿真视频也要分开统计。

## 新任务准备

Python helper 与现有导出任务的 `environment/native.json` 对齐：

```python
from adapter import binding_from_native, prepare
binding = binding_from_native(
    '/path/to/FUTURE/task/environment/native.json',
    condition='real',  # real 或 sim；text_rule 不属于视频 QA
    episode_id='future-episode-001', generalization='G1',
    source_binding=reviewed_transcode_binding,
)
public, private = prepare({
    'enabled': True, 'run_state': 'planned', 'protocol': 'qa_then_act',
    'bindings': [binding],
})
```

helper 读取 `task_id/variant/demo/demo_sim`，支持环境变量及相对 task 根目录的媒体路径。`run_state=planned` 是导出者对新任务的声明，不是进程检查；切勿用该声明给在跑任务改协议。默认没有任何自动启用路径。

手写 manifest 的一个 binding：

```json
{
  "episode_id": "future-episode-001",
  "task_id": "E01", "variant": "A", "input_mode": "real_demo",
  "generalization": "G1",
  "demo_path": "/path/to/video.MOV", "demo_sha256": "实际视频的64位SHA256"
}
```

`prepare` 实际读取媒体并校验 SHA256。真人原文件须匹配私有答案表。现有 human.mp4 是转码文件，其 SHA 与原 MOV 不同：须额外提供 `source_binding`，包含 `status: reviewed`、`task_id`、`variant`、`sha256`（转码文件）、`source_sha256`（答案表原文件）、`rule_preserving_transcode: true`、`reviewer` 和 `evidence`。应引用转码溯源记录，不能只因文件名相似填真。

仿真 binding 的 `input_mode=sim_demo`，额外提供 `sim_review`，包含 `status: reviewed`、`task_id`、`variant`、`sha256`、`rule_matches_source: true`、`reviewer`、`evidence`（对应视频时间段及规则）。原生运动验证或完整解码并不能证明视频规则与题目一致；缺这份复核时适配器拒绝准备，不自动视为通过。

```sh
python3 adapter.py prepare --manifest /path/to/future-manifest.json --out /path/to/new-qa-export
```

输出 `packets.json` 和 `grading.private.json`。输出目录须不存在，禁止覆盖已有材料。传入 manifest 的媒体路径应为绝对路径；helper 会解析原生 spec 的任务相对路径。

## 后续 runner 的调用点

1. 新任务导出阶段准备 sidecar；不放入模型可访问任务目录中的私有文件。
2. `assigned_material` 交付指定匿名视频后，运行器记录真实交付文件 SHA256，再调用 `question_after_video(packet, private_record, watched_sha256)`；哈希一致才取得题目。交付收据由运行器负责，哈希不证明模型真的看懂或完整观看。
3. 模型输出单个大写字母，运行器用独占创建保存首次原始输出，提交状态持久化后不因重连再问；错答和格式错误均不请求重答。
4. `qa_then_act` 继续原动作流程；`isolated_qa` 销毁隔离分支并让原动作分支继续。不得注入 grading 返回值。
5. episode 外的分析程序评分：

```sh
python3 adapter.py grade --private /path/to/grading.private.json \
  --packet-id qp_ANONYMOUS_ID --answer-file /path/to/first-answer.txt \
  --out /path/to/new-result.private.json
```

结果文件独占创建；恢复时读取已保存结果，不覆盖、不重选答案。输出只含 `qa_correct` 等 QA 字段，不修改 native task score。CLI 不发模型请求；目前已具备可调用接入接口，实际 runner hook 留给下一批任务导出配置。

## 测试

```sh
python3 -m unittest discover -s RoboDojo-Audit/evaluation/rule_qa -p 'test*.py' -v
```

覆盖视频错绑、内容变化、转码溯源、仿真复核门控、ABC/G0G1G2映射、答案解析、私有字段隔离、视频交付收据、重复记录和覆盖保护。

## 可直接调用的持久化答题关卡

`qa_then_act` 使用以下钩子，原始回答和视频交付收据均落在 runner 私有状态目录。文件先完整写入并 fsync，再通过原子独占发布保存；重复提交返回已提交状态，保留第一次回答。重启后读取磁盘状态，有首次回答就直接允许继续动作，不再次出题。题目、episode 或视频身份改变时拒绝复用旧记录。

```python
from adapter import stage_after_video, record_first_answer

def run_qa_gate(packet, private_record, delivered_sha256, state_dir, ask_model):
    # 仅在真实视频材料已交付后调用；ask_model 接收匿名题目并返回原始文本。
    state = stage_after_video(packet, private_record, delivered_sha256, state_dir)
    if not state['action_allowed']:
        raw_text = ask_model(state['question'])
        state = record_first_answer(packet, private_record, raw_text, state_dir)
    return state['action_allowed']  # True 后再执行原动作流程
```

`record_first_answer` 要求已有匹配的视频收据。任何文本（包括格式错误）只提交一次，返回确认不含正确答案、正确性或格式提示。原始文本供私有离线 `grade` 使用。若 API 已返回但进程在调用保存钩子前崩溃，仍需 runner 用原 API 请求标识找回那次输出后提交；该钩子不能凭磁盘证明尚未保存的远端请求结果。未收到输出前再次调用 stage 仍返回同一道题，runner 不应为同一 packet 同时派发多个答题请求。

`isolated_qa` 仍需 runner 管理分支隔离，以上动作关卡只接受 `qa_then_act`。两种协议的名称不能相互替代。

## 本次验证记录

50道题与150条冻结视频标注逐项一致；17项单元测试通过，含首次答案持久化和恢复。详见 `test-results.txt` 与 `validation-receipt.json`。

E05-C、E31-A原MOV之前为 `compressed,dataless` 占位文件，读取超时。现已从冻结数据集版本 `89f009bb76ee5ffb58ee66ec584e519c86f3d4b6` 重新下载，核对原始SHA256完全一致并通过完整解码后，原子恢复原路径。恢复副本位于 `recovered-media/`，记录见 `media-recovery-receipt.json`。

恢复后150/150原视频SHA256全部匹配，150份匿名QA packet及答案离线往返均通过。本次没有调用模型、启动仿真或修改当前150条任务。

`python3 RoboDojo-Audit/evaluation/rule_qa/validate_release.py` 可重新执行离线源文件绑定验证。

额外完成150份原视频与150份评测转码MP4的完整解码，共300/300通过；150/150转码来源、SHA和无裁剪/截断转换参数核对通过。生成 `real-transcode-bindings.private.json`，后续真人视频QA可直接选取对应task/variant的source_binding；这些来源记录的复核不表示重新人工观看全部视频。150份转码材料均已通过适配器离线prepare。详见 `full-media-validation.private.json`。

本次检查还修复了视频后出题钩子遗漏question_id核对的问题：即使packet_id相同，错题目也会拒绝。17项测试全部通过。仿真视频的语义一致性仍需按具体视频独立复核，未将真人来源检查冒充仿真复核。
