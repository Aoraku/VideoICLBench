from collections import Counter
from simulator.benchmark.catalog import TASKS, task_spec

def test_sources_and_distinct_tasks():
    assert len(TASKS)==50
    assert Counter(t['source']['project'] for t in TASKS.values())=={'RoboTwin':25,'RoboCasa':25}
    assert len({(t['source']['project'],t['source']['task']) for t in TASKS.values()})==50
    for t in TASKS.values():
        ids={o['id'] for o in t['objects']}; zones={z['id'] for z in t['zones']}
        assert t['demo_status']=='missing'
        assert len(t['source']['revision'])==40
        for g in t['goals']:
            assert g.get('object',g.get('objects',[''])[0]) in ids
            if g['type']=='place': assert g['target'] in zones
            if g['type'] in ('nest','stack'): assert g['target'] in ids

def test_mirrors_keep_goal_relations():
    a=task_spec('rt05','A'); b=task_spec('rt05','B'); c=task_spec('rt05','C')
    assert a['objects'][0]['xy'][1]==-b['objects'][0]['xy'][1]
    assert a['goals'][0]['xy'][0]==-c['goals'][0]['xy'][0]
    assert TASKS['rt05']['objects'][0]['xy']==a['objects'][0]['xy']

def test_desktop_filming_has_no_kitchen_requirements():
    forbidden=('锅','食材','蔬菜','面包','餐具','水果','奶酪','糕点','调味','烹饪','麦片','腌制')
    for task in TASKS.values():
        assert task['scene_domain']=='desktop-non-kitchen'
        presentation=task['title']+task['filming']['instruction']+' '.join(task['filming']['props'])
        assert not any(word in presentation for word in forbidden)
        assert all(o.get('display_name') for o in task['objects'])
