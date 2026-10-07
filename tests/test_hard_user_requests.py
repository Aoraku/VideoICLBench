import hashlib
import json
import re
from copy import deepcopy

import pytest
from vic import business, v2, lessons
from vic.execution_prompts import HARD
from vic.identity_context import contextualize
from vic_apps.domain import initialize
from test_v2_communications import apply_all


def test_all_hard_requests_are_goals_with_constraints_and_preserve_recording_identity():
    raw = {t['id']:t for t in v2._recording_catalog()['tasks']}
    assert set(HARD) == {i for i,t in raw.items() if t['difficulty']=='hard'}
    for i in HARD:
        spec=v2.task(i)
        assert spec['inference']['goal'] and spec['inference']['constraints']
        assert spec['inference']['steps']==[]
        assert not re.search(r'点击|点“|先点|→|按下面|步骤',spec['inference']['instructions'])
        assert spec['demo']==raw[i]['demo']
        assert v2.digest(i)==hashlib.sha256(json.dumps(raw[i],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        # Even hard demos are base rule exercises, with no business workflow.
        demo=v2.generate(i,0,'demo')
        assert demo==contextualize(initialize(business.generate(i,0)),'demo')
        assert not {'workflow','world','cross_platform','work_batch'} & demo.keys()
        execution=v2.generate(i,10001,'eval')
        assert not re.search(r'点击|点“|先点|→|按下面|步骤',execution['world']['brief'])
    assert '紧急' not in v2.task(13)['inference']['instructions']


def test_13_scope_requests_have_roles_and_mixed_message_categories():
    state=v2.generate(13,10001,'eval')
    for request in state['world']['requests']:
        assert request['project'] in request['body'] and '晚班-0115' in request['body']
        assert '负责人' in next(c['name'] for c in state['world']['conversations'] if c['id']==request['conversation'])
        rows=[x['text'] for x in state['items'] if x['project']==request['project']]
        assert any('收到' in s and '紧急' not in s for s in rows)
        assert any('紧急' in s for s in rows)


def test_13_reports_extra_handover_rows_and_messages_in_readable_feedback():
    initial=v2.generate(13,10001,'eval');final,events=apply_all(initial,'A')
    assert v2.evaluate(initial,final,'A',events)['success']
    wrong=deepcopy(final)
    extra=next(x for x in initial['items'] if x['batch']=='早班-0115')
    wrong['world']['handover']['rows'][extra['id']]={'status':'已转发'}
    result=v2.evaluate(initial,wrong,'A',events)
    assert not result['success'] and any(extra['record_code'] in s for s in result['feedback'])


def test_28_music_features_vary_across_rule_examples_and_inference():
    for seeds in (lessons.seeds_for(28,0), [1000,10001,10002,27183]):
        samples=[business.generate(28,seed)['items'] for seed in seeds]
        assert len({tuple(sorted(x['duration'] for x in rows)) for rows in samples})==len(samples)
        assert len({tuple(sorted(x['artist'] for x in rows)) for rows in samples})==len(samples)
        for rows in samples:
            assert len({x['duration'] for x in rows})==6
            assert len({x['artist'] for x in rows})==6
            orders=[business.ordering(28,i,rows) for i in range(3)]
            assert len({tuple(o) for o in orders})==3


@pytest.mark.parametrize('seed',[0,1,2,1000,10001])
def test_29_titles_use_natural_spacing_and_exact_visible_length(seed):
    state=business.generate(29,seed)
    for item in state['items']:
        assert not re.search(r'\d +| +\d',item['name'])
        assert item['name_length']==len(item['name'])
