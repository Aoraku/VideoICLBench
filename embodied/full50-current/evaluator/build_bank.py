"""Build 50 shared four-option questions and 150 private video answer bindings."""
from pathlib import Path
import hashlib
import json
import random
from collections import Counter

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parents[2] / 'isaaclab_tasks/configs/realworld50_catalog.json'
VERSION = 'embodied-rule-qa-v1'
# Each line: task-specific question and a fourth alternative, not present in ABC.
AUTHORING = '''
E01|视频中的示范按哪一种食物组合装盘？|把汉堡、薯条和饮料全部装盘。
E02|视频中三色块最终自下而上的叠放顺序是什么？|自下而上红、蓝、绿。
E03|视频中三个彩杯由外层到内层如何套叠？|外层到内层：红、蓝、绿。
E04|视频中的三个彩杯分别与哪些图形配对？|绿杯→三角；蓝杯→方；红杯→圆。
E05|视频中方块、球和三角块分别放到哪些图形标记处？|方块→方形；球→三角形；三角块→圆形。
E06|以示范操作者的视角看，视频中三个球放入蛋托的哪些孔？|右列两端、左列中间各放一球。
E07|视频中五块物体按尺寸从远到近如何排列？|从远到近：最小、中等、最大、次大、次小。
E08|视频中两只鞋放入鞋盒后，鞋尖或鞋跟与标签端是什么关系？|左脚鞋跟朝鞋盒标签端，右脚鞋尖朝标签端。
E09|视频中九件物体按哪一种成员关系分成三组？|红圆+红三角+绿方；绿圆+绿三角+蓝方；蓝圆+蓝三角+红方。
E10|视频中按什么属性选择零件套到柱上？|只套入同时为红色且为方形的零件，共1件。
E11|视频中如何将初始2×2布局变换后搬入四格框？|初始布局逆时针旋转90°后入框。
E12|视频中两个充电器插入插排的哪两个插位？|插入中间两个插位，两端插位空着。
E13|从支架开口观看侧看，视频中手机如何放在支架上？|竖放，后摄像头端朝下。
E14|相对初始层序，视频中四层塔如何重排？|交换从顶端数第3、4层，其余不变。
E15|相对初始状态，视频中两个T形块的位置和朝向如何变化？|两块的位置和朝向都保持不变。
E16|视频中三件物体搬入托盘时，相对位置和各自朝向如何变化？|将三件的相对位置左右镜像，各件朝向保持不变后搬入。
E17|视频中四件物体如何分配到点心架上下两层？|四件全部放下层。
E18|视频中从抽屉取出哪些球放到白色目标纸上，并关回抽屉？|把红、绿、蓝三个球都取到白色目标纸上，关回抽屉。
E19|视频中雪碧瓶、水瓶和可乐瓶分别配什么颜色的盖？|雪碧配黄盖，水配红盖，可乐配白盖。
E20|视频中如何按颜色给三个图形标记处补齐筹码？|圆标记放黄片、方标记放红片、三角标记放蓝片，在各处现有数量上再加2片。
E21|视频中按什么颜色顺序，将物体依次放入四格盘的左上、右上、左下、右下格？|按黄、红、蓝、绿顺序，依次放入左上、右上、左下、右下格。
E22|以玩具车自身的前、左、右为参照，视频中三个色块如何摆放？|车前放红块，车左放蓝块，车右放绿块。
E23|视频中彩杯套上杯架后，从高层到低层是什么颜色顺序？|从高到低绿、红、蓝。
E24|视频中三个彩杯按什么顺序装盒，然后盖上盒盖？|红→蓝→绿依次装盒，盖上盒盖。
E25|以操作者为参照，视频中勺、刀、叉如何摆在盘边？|勺、刀、叉排在盘近侧，柄端靠盘。
E26|视频中左右数字牌与左右铃的按铃次数遵循哪一种对应规则？|仅右铃按两牌数字之和，左铃不按（本片0、10次）。
E27|以操作者为参照，视频中勺和叉如何摆在盘的两侧？|勺叉都放盘右侧，靠盘为勺，外侧为叉。
E28|视频中用平铲选择哪些食物放入盘中？|两块食物都留在桌上，不放入盘中。
E29|视频中用琴槌按哪一种顺序敲击八个琴键？按最长到最短将琴键编号为1到8。|从最长到最短再返回，折返点只敲一次：1→2→3→4→5→6→7→8→7→6→5→4→3→2→1。
E30|视频结束时，上层红抽屉和下层蓝抽屉分别是什么开合状态？|上层红抽屉和下层蓝抽屉都关闭。
E31|视频中碗和盘以哪一种方式组合？|碗口朝下倒扣在正放的盘内。
E32|视频中从杂乱桌面选择哪些物体放到白色交付板？|把雪碧瓶和可乐瓶都放到白色交付板。
E33|视频中选择哪些饮料瓶投入垃圾桶，其余留在桌上？|把雪碧瓶、可乐瓶和橙色芬达瓶都投入桶中。
E34|视频中选择哪些餐具放到收纳盘左上格？|把餐刀、勺子和叉子都放到盘左上格。
E35|视频中三块同色、不同尺寸的物体，从下到上如何叠放？|从下到上中、大、小。
E36|视频中向空盒放入几个球？|向空盒放入4个球。
E37|以操作者面对横梁时的左右为准，视频中卸下哪些螺丝？|左右两颗螺丝都保留，不卸下。
E38|视频中三个彩环套在同一根柱上后，从下到上是什么颜色顺序？|从下到上绿、红、蓝。
E39|以上排T形块为参照，视频中如何调整下排的颜色次序和朝向？|下排的颜色次序和各T朝向都保持原样。
E40|视频中把长尾夹夹在托盘边的哪些图形标记处？|夹住圆形、方形、三角形和叉号对应的全部四处盘边。
E41|视频中不同长度的前段木条分别接续什么长度的备件？|短前段接中备件，中前段接长备件，长前段接短备件。
E42|视频中用平铲侧沿把两个球如何分配到图形标记纸区域？|一个球推到圆标记纸区域，另一个球推到三角标记纸区域。
E43|视频中用导向条让球的运动轨迹经过哪一种图形标记区域？|用导向条挡住球，使球留在起始板上。
E44|视频中纸板一面贴桌，另一面与它形成哪一种夹角？|两面展开并都贴在桌上，形成平角。
E45|视频中把杯中所有球倒入哪一种图形格？|全部倒入叉号格。
E46|视频中用平铲承托黄色块，送到哪一种图形标记纸处？|铲起黄色块，放在圆标记纸和三角标记纸之间的桌面上，不接触两张标记纸。
E47|视频中翻开左起前两张牌后，按什么规则选择入盒的牌？|翻开左起前两张，两张都留在盒外。
E48|视频中从左起翻开几张牌，并插入同一卡座？|从左起翻开4张牌并插入卡座。
E49|视频中翻开左起前三张牌后，按原始左起序号依次放入哪三个盘？|翻开左起前三张，依次放入蓝、绿、红盘。
E50|视频中翻牌后，用长尾夹夹取并送到哪个彩盘，再释放？|翻牌后用长尾夹夹取，放在绿盘和蓝盘之间的桌面上并释放。
'''
# Make every choice standalone; do not encode arbitrary coordinates or extra acceptance constraints.
OVERRIDES = {
 'E20': [f'圆标记放黄片、方标记放红片、三角标记放蓝片，各补到总共{n}片。' for n in (2,3,4)],
 'E21': [f'按{seq}顺序，依次放入左上、右上、左下、右下格。' for seq in ('红、黄、蓝、绿','红、绿、蓝、黄','绿、蓝、黄、红')],
 'E25': ['勺、刀、叉从左到右排在盘远侧，柄端靠盘。','勺、刀、叉从左到右排在盘远侧，工作端靠盘。','刀放盘左侧，勺和叉放盘右侧，右侧由靠盘到外侧为勺、叉，柄朝操作者。'],
 'E43': ['用导向条让球经过圆标记区域。','用导向条让球经过三角标记区域。','用导向条让球经过方标记区域。'],
}

def build():
 raw = CATALOG.read_bytes()
 cat = json.loads(raw)
 authoring = {row.split('|')[0]: row.split('|')[1:] for row in AUTHORING.strip().splitlines()}
 assert len(authoring) == len(cat['tasks']) == 50
 rng = random.Random(20261101)
 excluded = list('A'*13 + 'B'*13 + 'C'*12 + 'D'*12)
 rng.shuffle(excluded)
 questions, keys = [], []
 md = ['# 具身视频规则选择题：50题与标准答案', '',
 '每个任务一道题、四个选项。同一任务的A/B/C三个视频使用完全相同的题干和选项顺序，分别对应一个正确答案。共50道题、150条视频答案映射。视频版本字母与选项字母是两套独立标识。', '',
 '四个选项由三个实录规则和一个额外干扰规则组成。选项排列冻结，不能按视频版本重新打乱。此文件供人工审核，含答案，不应交给被测模型。', '',
 '来源：已冻结的50任务实录目录及其逐视频标注；本次未重新观看150段视频。仿真视频须核对实际播放资产与规则再绑定，不能凭任务名直接套用答案。题目测量示范中的规则识别，不能代替原生物理成功验收。', '',
 'G0/G1/G2如果沿用同一源视频，则共用同一题与答案；重复作答可以分别记录，但不能称为新增独立视频。', '',
 '## 答案速查', '', '|任务|名称|视频A答案|视频B答案|视频C答案|', '|---|---|---|---|---|']
 details = []
 for t, extra_label in zip(cat['tasks'], excluded):
  tid=t['id']; prompt, distractor=authoring[tid]
  variants={v['variant']:v for v in t['variants']}
  texts=OVERRIDES.get(tid,[variants[v]['observed_demo'].rstrip('。')+'。' for v in 'ABC'])
  labels=[x for x in 'ABCD' if x!=extra_label]; rng.shuffle(labels)
  answers=dict(zip('ABC',labels))
  choices={label: text for label,text in zip(labels,texts)}; choices[extra_label]=distractor
  choices={label: choices[label] for label in 'ABCD'}
  assert len(set(choices.values()))==4
  qid='rq_'+hashlib.sha256((VERSION+':'+tid).encode()).hexdigest()[:12]
  questions.append(dict(question_id=qid,task_id=tid,title=t['title'],prompt=prompt,options=choices))
  sources={v:{k:variants[v][k] for k in ('video_id','sha256','relative_path','evidence','observed_demo','status','source_commit')} for v in 'ABC'}
  keys.append(dict(question_id=qid,task_id=tid,answers=answers,sources=sources,distractor_option=extra_label,scope_note=t['scope_note'],review_status='derived_from_reviewed_catalog_not_new_video_review'))
  md.append('|'+ '|'.join([tid,t['title'],*[answers[v] for v in 'ABC']])+'|')
  details += ['',f'## {tid} {t["title"]}', '',prompt,'',*[f'{label}. {choices[label]}' for label in 'ABCD'],'',f'**标准答案：视频A → {answers["A"]}；视频B → {answers["B"]}；视频C → {answers["C"]}。**','',f'审核边界：{t["scope_note"]}', '',*[f'- 视频{v}依据：{variants[v]["evidence"]}' for v in 'ABC']]
 common=dict(schema='videoicl.rule_qa.v1',bank_version=VERSION)
 public={**common,'question_count':50,'questions':questions}
 private={**common,'answer_count':150,'catalog_sha256':hashlib.sha256(raw).hexdigest(),'catalog_path':'isaaclab_tasks/configs/realworld50_catalog.json','dataset_revision':cat['dataset_revision'],'questions':keys}
 counts=Counter(a for q in keys for a in q['answers'].values())
 md += ['', '150条答案位置分布：'+ '、'.join(f'{k}={counts[k]}' for k in 'ABCD')+'。']+details
 for name,data in [('questions.json',public),('answer_key.private.json',private)]:
  p=HERE/name;p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
  if 'private' in name:p.chmod(0o600)
 (HERE/'选择题清单与标准答案.md').write_text('\n'.join(md)+'\n')
 print(json.dumps(dict(question_count=len(questions),answer_count=sum(len(q['answers']) for q in keys),answer_positions=counts),ensure_ascii=False))

if __name__=='__main__': build()
