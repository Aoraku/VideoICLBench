"""Recorder lesson plans and aggregate evidence; never imported by application UIs."""
from functools import lru_cache
from .teaching import BATCH_TASKS

VERSION = 1


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
