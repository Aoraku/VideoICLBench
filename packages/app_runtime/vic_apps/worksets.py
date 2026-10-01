"""Public business scopes and persisted collections in the native applications.

Scopes identify a department, date, project, or account. They never contain a
learned rule, expected selection, or grading result.
"""
from copy import deepcopy
import json
from vic import business
from . import domain


CONFIG = {
    2: ('项目', ['春季发布组'], None, None),
    6: ('部门', ['研发部'], None, None),
    7: ('部门', ['研发部', '设计部', '运营部'], None, None),
    8: ('项目', ['星桥计划'], None, None),
    9: ('部门', ['研发部', '设计部', '运营部'], None, None),
    12: ('工作区', ['产品协作', '客户交付'], None, None),
    14: ('项目', ['星桥交接'], None, None),
    16: ('项目', ['产品验收', '官网发布', '客户培训', '运营交接'], ('notification_batch', '通知批次', 'N2026-0115', 'N2025-1220'), None),
    22: ('专辑', ['山间来信', '夜行电台'], ('edition','版本','录音室版','现场版'), None),
    23: ('专题', ['城市公共空间'], ('period','发布月份','2026-01','2025-12'), None),
    26: ('栏目', ['纪录影像', '城市观察'], None, '栏目推荐位'),
    31: ('课程主题', ['自然观察', '影像叙事', '城市文化'], None, '课程收藏夹'),
    33: ('栏目', ['社区生活', '文化纪事'], ('period','发布月份','2026-01','2025-12'), None),
    34: ('播放列表', ['周末观影', '课后学习'], None, None),
    38: ('项目', ['城市研究', '生活观察'], None, None),
    47: ('出发日期', ['2026-02-12', '2026-02-15'], None, '路线比较清单'),
    48: ('商品类目', ['保温杯', '机械键盘'], ('specification', '规格', '标准款', '便携款'), '优选商品集合'),
    49: ('账户', ['日常支出账户', '项目经费账户'], ('period', '账单月份', '2026-01', '2025-12'), None),
    50: ('账户组', ['个人储蓄', '家庭共同账户'], None, None),
    53: ('账户', ['日常支出账户', '项目经费账户'], ('period', '账单月份', '2026-01', '2025-12'), '对账单凭证'),
    57: ('账户清单', ['常用账户'], None, None),
    61: ('题目', ['两数之和', '区间合并'], None, None),
    63: ('课程专题', ['数组与区间', '图与路径', '字符串'], None, None),
}
TASKS = set(CONFIG)
SNAPSHOT_TASKS = {26, 47, 48}
SINGLE_TASKS = {31, 53}


def members(state, scope):
    return [x for x in state['items'] if x['scope_id'] == scope['id'] and
            all(x.get(k) == value for k, value in scope['filters'].items())]


def apply(state, op, target='', value='', ids=None):
    out = deepcopy(state); t = out['task_id']; d = out['domain']; ids = ids or []
    if op == 'contact.nickname' and t == 2:
        if target not in {x['id'] for x in out['items']} or not isinstance(value,str) or len(value)>64:
            raise ValueError('请选择有效联系人，备注昵称最多 64 个字符')
        d['objects'][target]['nickname']=value
    elif op == 'conversation.settings' and t == 14:
        if target not in {x['id'] for x in out['items']}:raise ValueError('会话不存在')
        changes=json.loads(value)
        if not isinstance(changes,dict) or not changes or not set(changes)<={'pinned','muted','archived'} or not all(type(v) is bool for v in changes.values()):
            raise ValueError('会话设置需要有效的开关状态')
        d['objects'][target].update(changes)
    elif op == 'order' and t == 12:
        if len(ids)!=len(out['items']) or set(ids)!={x['id'] for x in out['items']}:
            raise ValueError('列表顺序须包含全部会话且不重复')
        d['orders']['main']=list(ids);out['order']=list(ids)
    elif op == 'message.send' and t == 9:
        if target not in {x['id'] for x in out['items']} or not isinstance(value,str) or not value.strip():
            raise ValueError('请选择收件人并填写通知正文')
        d['messages'].append(dict(id=f'sent-{len(d["messages"])+1}',sender='self',recipient=target,
            body=value,reference=d['objects'][target]['scope_id'],attachment=None))
    elif op.startswith('course.') and t == 63:
        order = d['orders']['course']
        if op == 'course.add':
            if target not in d['objects']:
                raise ValueError('请选择题库中的题目')
            scope = d['objects'][target]['scope_id']
            existing = next((i for i, key in enumerate(order) if d['objects'][key]['scope_id'] == scope), None)
            if existing is None: order.append(target)
            else: order[existing] = target
        elif op == 'course.remove':
            if target not in order: raise ValueError('题目不在课程中')
            order.remove(target)
        elif op == 'course.order':
            if len(ids) != len(order) or set(ids) != set(order):
                raise ValueError('排序必须包含课程中的全部题目且不重复')
            d['orders']['course'] = list(ids)
        elif op == 'course.save':
            d['artifacts'] = [a for a in d['artifacts'] if a.get('kind') != 'course_list']
            d['artifacts'].append(dict(kind='course_list', title='课程练习列表',
                items=list(order), topics=[d['objects'][key]['scope_id'] for key in order]))
        else: raise ValueError('未知课程操作')
    elif op == 'workset.collect' and t in SNAPSHOT_TASKS | SINGLE_TASKS:
        if target not in {s['id'] for s in out['scopes']}:
            raise ValueError('请选择保存位置')
        known = {x['id'] for x in out['items']}
        if len(ids) != len(set(ids)) or not set(ids) <= known:
            raise ValueError('收藏内容包含无效或重复对象')
        if t in SINGLE_TASKS and len(ids) != 1:
            raise ValueError('每个收藏夹或对账单保存一个对象')
        d['collections']['scope:' + target] = list(ids)
        if t == 53:
            item = d['objects'][ids[0]]
            d['artifacts'] = [a for a in d['artifacts'] if not (a.get('kind') == 'statement_voucher' and a['statement'] == target)]
            d['artifacts'].append(dict(kind='statement_voucher', statement=target,
                transaction=item['id'], number='PZ-' + item['record_code'], account=item['account'],
                amount=item['amount'], occurred_at=item['created_at']))
    elif op == 'reminder.channel' and t == 57:
        if target not in {x['id'] for x in out['items']} or value not in ('站内信', '短信', '电子邮件'):
            raise ValueError('请选择有效账户和通知渠道')
        d['objects'][target]['reminder_channel'] = value
    elif op in ('label', 'action'):
        out = business.apply_mutation(out, op, target, value, ids)
        out = domain.apply(out, op, target, value, ids)
        if t == 16 and op == 'action' and value == '回复':
            out['domain']['messages'][-1]['recipient'] = out['domain']['objects'][target]['scope_id']
    else:
        raise ValueError('请通过分类、业务操作或保存集合完成此任务')
    return out
