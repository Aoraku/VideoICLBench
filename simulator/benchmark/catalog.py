import copy
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('tasks.json').read_text())
TASKS = {t['id']: t for t in CATALOG['tasks']}

def task_spec(task_id, variant='A'):
    if task_id not in TASKS or variant not in ('A','B','C'):
        raise ValueError('Unknown task or variant')
    t = copy.deepcopy(TASKS[task_id])
    # B mirrors the lateral layout; C mirrors the longitudinal layout.
    sx,sy = (-1 if variant=='C' else 1),(-1 if variant=='B' else 1)
    def transform(xy): return [xy[0]*sx,xy[1]*sy]
    for item in t['objects']+t['zones']:
        item['xy']=transform(item['xy'])
        if 'yaw' in item: item['yaw'] *= sx*sy
    for goal in t['goals']:
        if 'xy' in goal: goal['xy']=transform(goal['xy'])
        if goal['type']=='yaw': goal['value']*=sx*sy
    t['variant']=variant
    return t
