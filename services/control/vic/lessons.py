"""Recorder lesson plans and aggregate evidence; never imported by application UIs."""
from functools import lru_cache
from .teaching import BATCH_TASKS

VERSION = 1


def incomplete_message(state, result):
    """Explain the failed operation without revealing the private rule."""
    task_id = state['task_id']
    if task_id in (1, 3, 4):
        sent = [m for m in state.get('domain', {}).get('messages', []) if m.get('sender') == 'self']
        if not sent:
            return '尚未收到发送结果。请在目标会话发送消息，再点击下一组。'
        if len(sent) > 1:
            return '本组要求发送一条消息，但已发送多条。请重置环境后重新完成；录制前请核对版本规则。'
        return '消息已发送，但文本格式不符合本组要求。请核对整段文本与单词的处理范围；需要重做时在任务卡重置环境。'
    if task_id == 31:
        if not state.get('selection'):
            return '尚未选择视频。请从视频资料库打开要选择的视频，再点击下一组。'
        return '视频选择已保存，但不符合本组要求。请返回视频资料库重新选择，再点击下一组。'
    if task_id in (66, 67) and 'no_action' in result.get('violations', []):
        return '尚未收到棋盘操作。请打开练习棋谱，点击绿色边框候选点，确认出现已保存标记或已落子后继续。'
    return '本组操作已检查，但尚未满足完成要求。请检查操作及保存状态，再点击下一组。'


def episode_count(task_id):
    # Task 30 has single-choice variants even though C is a batch operation.
    return 1 if task_id in BATCH_TASKS and task_id != 30 else 6


@lru_cache(maxsize=512)
def seeds_for(task_id, seed):
    if task_id != 68:
        return tuple((seed + n) % 1000 for n in range(episode_count(task_id)))
    from .games import fixture, expected
    candidates = [(seed + n) % 1000 for n in range(128)]
    signatures = {s: tuple(expected(68, v, fixture(68, s)) for v in 'ABC') for s in candidates}
    chosen = [seed]
    seen = [{signatures[seed][v]} for v in range(3)]
    pairs = ((0, 1), (0, 2), (1, 2))
    separated = {pair for pair in pairs if signatures[seed][pair[0]] != signatures[seed][pair[1]]}
    while len(chosen) < 6:
        following = max((s for s in candidates if s not in chosen),
            key=lambda s: (sum(pair not in separated and signatures[s][pair[0]] != signatures[s][pair[1]] for pair in pairs),
                           sum(signatures[s][v] not in seen[v] for v in range(3)), -candidates.index(s)))
        chosen.append(following)
        for v in range(3): seen[v].add(signatures[following][v])
        separated.update(pair for pair in pairs if signatures[following][pair[0]] != signatures[following][pair[1]])
    if len(separated) != 3 or len(seen[0]) < 2 or len(seen[1]) < 2 or len(seen[2]) < 3:
        raise ValueError('2048 lesson lacks direction diversity')
    return tuple(chosen)


def plan(task_id, seed):
    return dict(version=VERSION, index=0, seeds=list(seeds_for(task_id, seed)),
                completed=[], finished=False)


def progress(lesson):
    if not lesson:
        return None
    return dict(index=lesson['index'], total=len(lesson['seeds']),
                completed=len(lesson['completed']), finished=lesson['finished'])


def native_path(app, run_id):
    if app == 'im':
        return f'/native-assets/im/?run={run_id}'
    if app in ('chat', 'music', 'code', 'gomoku'):
        return f'/native/{app}/{run_id}/'
    if app == 'news':
        return f'/native/news/{run_id}'
    return f'/native/product/{app}/{run_id}'


def aggregate(lesson, current):
    """Every episode is required. A stopped recording cannot conceal missing work."""
    results = list(lesson['completed'])
    if len(results) == lesson['index']:
        results.append(dict(index=lesson['index'], result=current))
    total = len(lesson['seeds'])
    checks = [dict(id=f'episode:{index + 1}', passed=index < len(results) and
                   results[index]['index'] == index and results[index]['result']['success'])
              for index in range(total)]
    return dict(current, success=all(c['passed'] for c in checks),
                completion=sum(c['passed'] for c in checks) / total,
                checks=checks,
                violations=[] if all(c['passed'] for c in checks) else ['incomplete_lesson'],
                episodes=results, episode_count=total)
