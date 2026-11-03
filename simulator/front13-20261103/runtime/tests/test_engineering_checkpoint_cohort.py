import hashlib
import json
from types import SimpleNamespace
from copy import deepcopy
import pytest
from videoicl_isaaclab.engineering_checkpoint_cohort import selected_requests,SCHEMA


def cohort(tmp_path):
    cases=[dict(task=f'E{i}',variant='A',seed=4201,episode_id=f'room-{i}')for i in(47,48,49)]
    controllers={c['episode_id']:object()for c in cases};requests=[]
    for case in(cases[0],cases[2]):
        name=case['task']+'.json';raw=b'{"schema":"native-fixture"}'
        (tmp_path/name).write_bytes(raw)
        requests.append(dict(task=case['task'],variant='A',seed=4201,entry='cards-isolation-ready',checkpoint=name,sha256=hashlib.sha256(raw).hexdigest()))
    return dict(schema=SCHEMA,diagnostic_only=True,requests=requests),cases,controllers,tmp_path/'requests.json'


def test_partial_cohort_restores_only_matching_rooms_and_keeps_fresh_room(tmp_path):
    args=cohort(tmp_path);rows=selected_requests(*args,'positive')
    assert [room for room,case,request in rows]==['room-47','room-49']
    assert all(case['task']==request['task']for room,case,request in rows)
    assert 'room-48'not in{room for room,case,request in rows}


@pytest.mark.parametrize('failure',('bad_hash','duplicate','unmatched','outside_scope','negative','nested'))
def test_every_request_is_checked_before_any_native_restore(tmp_path,failure):
    request,cases,controllers,path=cohort(tmp_path);control='positive'
    if failure=='bad_hash':request['requests'][-1]['sha256']='0'*64
    if failure=='duplicate':request['requests'][-1]=deepcopy(request['requests'][0])
    if failure=='unmatched':request['requests'][-1]['variant']='C'
    if failure=='outside_scope':cases[1]['task']='E18'
    if failure=='negative':control='wrong_members'
    if failure=='nested':request['requests'][0]['schema']=SCHEMA
    with pytest.raises(ValueError):selected_requests(request,cases,controllers,path,control)


def test_restore_dispatch_keeps_unlisted_room_fresh_and_reuses_single_room_path(tmp_path,monkeypatch):
    from videoicl_isaaclab import engineering_checkpoint as native
    from videoicl_isaaclab import realworld_evaluator_selector as selector
    from videoicl_isaaclab.engineering_checkpoint_reference import restore_requested
    request,cases,_,path=cohort(tmp_path)
    controllers={c['episode_id']:SimpleNamespace(scene=SimpleNamespace(spec={'id':c['task']}))for c in cases}
    for single in request['requests']:
        raw=json.dumps(dict(schema='engineering-native-checkpoint-v1',source={'steps':54},stage='safe-boundary')).encode()
        (tmp_path/single['checkpoint']).write_bytes(raw);single['sha256']=hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(request));monkeypatch.setenv('VIC_ENGINEERING_CHECKPOINT_REQUEST',str(path))
    calls=[]
    def restore(controller,state):
        calls.append((controller.scene.spec['id'],state['source']['steps']));return {'passed':True}
    monkeypatch.setattr(native,'restore_startup',restore)
    monkeypatch.setattr(selector,'create_evaluator',lambda spec:SimpleNamespace(reset_episode=lambda:None))
    result=restore_requested(controllers,cases,'positive')
    assert set(result)=={'room-47','room-49'}
    assert calls==[('E47',54),('E49',54)]
    assert controllers['room-48'].scene.spec=={'id':'E48'}
    assert all(controllers[room].scene.spec['engineering_checkpoint_resume']['diagnostic_only']for room in result)
