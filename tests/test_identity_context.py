"""Fixture identities must be varied without changing the rule's evidence."""
import base64
import hashlib
import json
import pytest
from vic import business, v2
from vic.identity_context import SOURCE_NAMES, contextualize, identity_map


def test_identity_mapping_preserves_length_and_is_disjoint_across_modes():
    rosters=[]
    for task_id in range(1,76):
        demo=identity_map(task_id,7,'demo');query=identity_map(task_id,10007,'eval')
        assert set(demo.values()).isdisjoint(query.values())
        assert len(set(demo.values())) == len(demo)
        assert all(len(old)==len(new) for old,new in demo.items())
        assert demo == identity_map(task_id,7,'demo')
        assert demo != identity_map(task_id,8,'demo')
        rosters.append(demo['林若宁'])
    assert len(set(rosters)) >= 50


@pytest.mark.parametrize('task_id',range(1,76))
@pytest.mark.parametrize('mode,seed',[('demo',7),('eval',10007)])
def test_all_task_modes_use_consistent_contextual_identities(task_id,mode,seed):
    state=v2.generate(task_id,seed,mode)
    assert contextualize(state,mode)==state
    serialized=json.dumps(state,ensure_ascii=False)
    assert not any(name in serialized for name in SOURCE_NAMES)
    for file in state.get('domain',{}).get('files',{}).values():
        raw=base64.b64decode(file['content'])
        assert len(raw)==file['size']
        assert hashlib.sha256(raw).hexdigest()==file['sha256']
        try:text=raw.decode('utf-8')
        except UnicodeError:continue
        assert not any(name in text for name in SOURCE_NAMES)
    for item in state.get('items',[]):
        obj=state.get('domain',{}).get('objects',{}).get(item['id'])
        if obj:assert obj['name']==item['name']


def test_traveler_name_and_legal_spelling_agree_in_profiles_and_notices():
    state=v2.generate(44,10007,'eval');world=state['world']
    first=world['people'][0];namesake=world['people'][4]
    assert namesake['name']==first['name']+'（其他部门）'
    assert namesake['document']!=first['document']
    for person in world['people']:
        assert world['profiles'][person['id']]['full_name']==person['surname']+person['given_name']
    assert all(p['name'] in world['notices'][0]['body'] for p in world['people'][:4])


def test_english_linguistic_examples_are_not_renamed():
    state=business.generate(6,7)
    assert any(not any(v in item['name'].lower() for v in 'aeiou') for item in state['items'])
    for variant in 'ABC':
        effect=business.expected_effect(6,variant,state)
        assert effect['labels']


def test_business_setting_aliases_keep_meaningful_consistent_project_references():
    from vic.identity_context import SETTING_ALIASES, setting_map
    for original, aliases in SETTING_ALIASES.items():
        assert all(len(original)==len(alias) for alias in aliases)
        assert not any(old in alias for old in SETTING_ALIASES for alias in aliases)
    assert set(setting_map(13,7,'demo').values()).isdisjoint(setting_map(13,10007,'eval').values())
    state=v2.generate(13,10007,'eval')
    world=state['world']
    for project in world['projects']:
        assert project['name'] in world['brief']
        rows=[r for r in state['items'] if r['project']==project['id'] and '紧急' in r['text'] and r.get('batch')=='晚班-0115']
        assert len(set(r['text'] for r in rows))==len(rows)
        assert all('请核对' not in r['text'] for r in rows)


@pytest.mark.parametrize('task_id',[35,40,41,43,51,52,58,60,64,65])
def test_cross_platform_request_people_and_attachments_keep_diverse_identities(task_id):
    state=v2.generate(task_id,10007,'eval');h=state['cross_platform']
    assert len({p['name'] for p in h['people']})==len(h['people'])
    assert not any(name in json.dumps(h,ensure_ascii=False) for name in SOURCE_NAMES)
    other=v2.generate(task_id,10008,'eval')['cross_platform']
    assert [p['name'] for p in h['people']]!=[p['name'] for p in other['people']]
    for request in h['requests']:
        file=request['attachment'];raw=base64.b64decode(file['content'])
        assert len(raw)==file['size'] and hashlib.sha256(raw).hexdigest()==file['sha256']
        assert not any(name in raw.decode() for name in SOURCE_NAMES)
        assert request['requester'] in {p['id'] for p in h['people']}
        assert request['recipient'] in {p['id'] for p in h['people']}
