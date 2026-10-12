from copy import deepcopy
import json
from vic import v2
from vic.execution_prompts import RELATION
from test_application_api import clients
from test_api import admin


def test_all_prompts_name_the_learned_relation_and_remove_environment_switching():
    for task in v2.catalog()['tasks']:
        prompt=task['inference']
        assert RELATION[task['id']] in prompt['instructions']
        assert prompt['steps']==[]
        assert not any(w in prompt['instructions'] for w in ['工作清单','切换下一项','切换下一组'])
        state=v2.generate(task['id'],10001,'eval')
        assert 'work_batch' not in state
        assert state['execution']['instructions']
        if state.get('world'):assert not state['world']['brief']
        if state.get('workset_delivery'):
            assert all('示范视频' not in r['body'] and '规则操作' not in r['body'] for r in state['workset_delivery']['requests'])


def test_run_prompt_names_match_the_actual_instance(clients):
    control,worker=clients
    data=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=16,variant='C',seed=10001,mode='eval',runtime='browser',interaction='human')).json()
    prompt=data['inference_task']
    assert prompt['goal'] and prompt['constraints']
    assert '回复动作' in prompt['instructions']
    detail=control.get('/v1/runs/'+data['id'],headers=admin()).json()
    assert detail['inference_task']==prompt
