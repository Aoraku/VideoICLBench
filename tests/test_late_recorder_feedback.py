import json
import pytest
from vic import business,v2,application_eval
from vic_apps import domain,worksets
from test_api import client,admin

@pytest.mark.parametrize('suite',['v1','v2'])
@pytest.mark.parametrize('mode',['demo','eval'])
def test_conversation_settings_are_reversible_without_losing_other_flags(suite,mode):
    state=v2.generate(14,0 if mode=='demo' else 10001,mode) if suite=='v2' else domain.initialize(business.generate(14,0))
    initial=state;target=state['items'][0]['id']
    def apply(state,value):
        if state.get('v2_worksets'):return worksets.apply(state,'conversation.settings',target,json.dumps(value))
        out=business.apply_mutation(state,'conversation.settings',target,json.dumps(value))
        return domain.apply(out,'conversation.settings',target,json.dumps(value))
    for key in ['archived','pinned','muted']:
        state=apply(state,{key:True});assert state['domain']['objects'][target][key]
    for key in ['archived','pinned','muted']:
        state=apply(state,{key:False});assert not state['domain']['objects'][target][key]
    assert state==initial

@pytest.mark.parametrize('variant',list('ABC'))
def test_corrected_demo_settings_pass_evaluation(variant):
    initial=domain.initialize(business.generate(14,0));state=initial;events=[]
    target=state['items'][0]['id']
    actions=[('conversation.settings',target,'{"archived":true,"pinned":true,"muted":true}'),('conversation.settings',target,'{"archived":false,"pinned":false,"muted":false}')]
    mapping={'归档':'archived','置顶':'pinned','静音':'muted'}
    actions += [('conversation.settings',target,json.dumps({mapping[action]:True})) for target,action in business.expected_effect(14,variant,initial)['actions']]
    for op,target,value in actions:
        state=domain.apply(business.apply_mutation(state,op,target,value),op,target,value)
        events.append(dict(op=op,target=target,value=value))
    assert application_eval.evaluate(initial,state,variant,events)['success']

def test_recording_card_exposes_fixed_reply_without_changing_contract(client):
    before=v2.digest(16)
    task=next(t for t in client.get('/v2/tasks',headers=admin()).json()['tasks'] if t['id']==16)
    assert task['recording_parameters']['fixed_reply']==v2.generate(16,0,'demo')['source']['fixed_reply']=='已确认'
    assert v2.digest(16)==before
