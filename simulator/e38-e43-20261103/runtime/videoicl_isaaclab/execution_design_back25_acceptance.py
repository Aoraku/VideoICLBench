"""Second-half release gate: explicit N/A, shared witnesses, native evidence only.

This module never launches a test or changes a score. Existing first-half release
validation is untouched. Engineering attempts are not accepted automatically.
"""
import hashlib
import json
from pathlib import Path
from .execution_design import REVISION_V3,source_sha256

CONTROLS=('positive','wrong_members','wrong_destination','wrong_rule','not_released')
NA={
 'E26':{'wrong_members':'数字牌按铃事件没有配送成员','wrong_destination':'没有交付地点'},
 'E29':{'wrong_members':'八键敲击序列没有配送成员','wrong_destination':'键位属于序列规则，无交付地点','not_released':'规则完成于真实敲击事件，不要求琴槌放桌'},
 'E30':{'wrong_members':'固定抽屉机构没有配送成员','wrong_destination':'开合状态不是交付地点'},
 'E31':{'wrong_destination':'碗盘上下和朝向是组合规则，没有独立交付区'},
 'E35':{'wrong_destination':'尺寸层序不指定固定交付区'},
 'E37':{'wrong_destination':'旋脱指定螺丝，无独立交付区'},
 'E43':{'wrong_members':'单球经过事件没有待选成员集合'},
 'E44':{'wrong_members':'同一张连续纸板没有替换成员','wrong_destination':'目标为折角和贴桌，没有交付地点'},
}
ALIASES={
 'E32':{'wrong_rule':('wrong_members','类别选择错误与成员替换是同一证据')},
 'E33':{'wrong_rule':('wrong_members','饮料瓶类别选择错误与成员替换相同')},
 'E34':{'wrong_rule':('wrong_members','餐具类别选择错误与成员替换相同；另验无关餐具保护')},
 'E36':{'wrong_rule':('wrong_members','数量规则与入盒成员数量使用同一计数证据')},
 'E40':{'wrong_destination':('wrong_rule','夹错图形边缘与图形选择规则是同一证据')},
 'E43':{'wrong_rule':('wrong_destination','错图形路径与经过错目标区是同一轨迹证据')},
 'E47':{'wrong_rule':('wrong_members','红黑选择错误与选错卡片集合是同一证据')},
 'E48':{'wrong_rule':('wrong_members','翻牌数量/左起前缀规则与成员选择是同一证据')},
}
EXTRA={
 'E28':('direct_hand_transport_without_spatula','hand_loaded_spatula_without_scoop'),
 'E34':('unselected_cutlery_moved',),
 'E37':('screw_not_physically_unthreaded',),
 'E39':('reference_workpiece_disturbed', 'preserved_attribute_changed'),
 'E40':('clip_without_actual_open_release_bilateral_contact',),
 'E42':('direct_hand_transport_without_blade_edge',),
 'E43':('ball_crossing_without_gravity_release_or_guide_contact',),
 'E45':('balls_delivered_without_pouring',),
 'E46':('cargo_delivered_without_blade_support',),
 'E47':('unrevealed_cards_disturbed',),
 'E48':('card_near_slot_without_true_insertion',),
 'E49':('unrevealed_cards_disturbed',),
 'E50':('card_delivered_without_clip_transport',),
}

# These named mechanism checks are precisely what canonical wrong_rule runs.
# A single reviewed native history proves both descriptions; no second replay.
EXTRA_ALIASES={
 'E28':{'direct_hand_transport_without_spatula':('wrong_rule','wrong_rule真实手抓搬运，直接检验缺少铲子承载历史')},
 'E42':{'direct_hand_transport_without_blade_edge':('wrong_rule','wrong_rule真实手抓搬运，直接检验缺少铲刃推动历史')},
 'E46':{'cargo_delivered_without_blade_support':('wrong_rule','wrong_rule真实手抓搬运，直接检验缺少铲面支撑历史')},
}


def requirements(spec):
    task=spec['id'];d=spec.get('execution_design',{})
    if task not in {f'E{i:02}'for i in range(26,51)}or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3):
        raise ValueError('Explicit source-checked back25 v3 case required')
    identity=d['assignment_identity_sha256'];aliases=dict(ALIASES.get(task,{}))
    if task=='E36' and spec['variant']=='A':
        aliases['wrong_destination']=('wrong_members','A要求1球；当前两条路线都形成0球入盒，共享同一原生计数witness，不重复计数')
    rows=[]
    for control in CONTROLS:
        reason=NA.get(task,{}).get(control)
        representative,alias_reason=aliases.get(control,(control,None))
        rows.append(dict(control=control,applicability='not_applicable'if reason else'alias'if alias_reason else'required',
            source_reason=reason or alias_reason or '最新版源规则要求正确完成且适用错误应被原生拒绝',
            canonical_control=representative,
            witness_key=None if reason else hashlib.sha256((identity+':'+representative).encode()).hexdigest()))
    for extra in EXTRA.get(task,()):
        representative,reason=EXTRA_ALIASES.get(task,{}).get(extra,(extra,None))
        rows.append(dict(control=extra,applicability='alias'if reason else'required',
            source_reason=reason or '源文档动作机制或保留条件需要独立历史反例',
            canonical_control=representative,witness_key=hashlib.sha256((identity+':'+representative).encode()).hexdigest()))
    return rows


def check_witness(spec,requirement,witness,root):
    """A reviewed evidence envelope references original artifacts by SHA256.

    Negative native scores alone cannot prove the intended counterexample.
    Review must identify an observed wrong condition and rule out execution
    failures; existing null negative_condition_observed therefore stays pending.
    """
    if not witness:return False,'native_witness_missing'
    d=spec['execution_design'];control=requirement['canonical_control']
    if (witness.get('assignment_identity_sha256')!=d['assignment_identity_sha256']
            or witness.get('source_sha256')!=d['source_sha256']
            or witness.get('witness_key')!=requirement['witness_key']
            or witness.get('control')!=control):return False,'witness_identity_mismatch'
    for key in ('native_evidence_valid','initial_sealed','capture_complete','control_execution_completed'):
        if witness.get(key)is not True:return False,'missing_'+key
    if witness.get('execution_errors'):return False,'engineering_execution_failed'
    if control=='positive':
        if witness.get('strict_success')is not True or witness.get('task_score_100')!=100:
            return False,'native_positive_not_successful'
    elif (witness.get('negative_condition_observed')is not True
            or not witness.get('reviewer')or not witness.get('observed_condition')
            or witness.get('other_conditions_checked')is not True):return False,'negative_semantics_unreviewed'
    artifacts=witness.get('artifacts',{});root=Path(root).resolve()
    for kind in ('trajectory','native_score','final_state','head_image'):
        a=artifacts.get(kind,{})
        try:
            p=(root/a['path']).resolve();p.relative_to(root)
            if not p.is_file()or not p.stat().st_size:return False,'artifact_missing_'+kind
            if hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']:return False,'artifact_hash_mismatch_'+kind
        except (ValueError,KeyError,OSError,TypeError):return False,'artifact_invalid_'+kind
    try:
        native=json.loads((root/artifacts['native_score']['path']).read_bytes())
    except (OSError,ValueError,TypeError):return False,'native_score_unreadable'
    if native.get('native_evidence_valid')is not True:return False,'native_score_evidence_invalid'
    if control=='positive':
        if native.get('strict_success')is not True or native.get('task_score_100')!=100:
            return False,'original_native_positive_not_successful'
    elif native.get('strict_success')is not False or native.get('task_score_100') is None:
        return False,'original_native_negative_unscored_or_not_rejected'
    return True,'native_evidence_verified'


def validate_case(spec,witnesses,artifact_root):
    checked=[];cache={}
    for r in requirements(spec):
        if r['applicability']=='not_applicable':
            checked.append(dict(r,status='not_applicable',native_passed=None));continue
        key=r['witness_key']
        if key not in cache:cache[key]=check_witness(spec,r,witnesses.get(key),artifact_root)
        valid,reason=cache[key]
        checked.append(dict(r,status=('verified_shared_witness'if r['applicability']=='alias'else'verified_native_witness')if valid else'pending',
            native_passed=valid if valid else None,reason=reason))
    return dict(task=spec['id'],assignment_identity_sha256=spec['execution_design']['assignment_identity_sha256'],
        controls=checked,independent_required_witnesses=len(cache),
        native_acceptance_ready=bool(cache)and all(x[0]for x in cache.values()),
        model_launch_enabled=False)
