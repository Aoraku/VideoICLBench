"""Music deliveries require actual saved membership and usable group shares."""
from copy import deepcopy
import json
import pytest
from vic import v2
from vic_apps import music_projects
from test_application_api import clients
from test_api import admin
from test_direct_applications import credential


def plan(initial,variant):
    w=initial['world'];t=initial['task_id'];objects=initial['domain']['objects']
    for index,activity in enumerate(w['activities'],1):
        key=f'list-{index:03d}'
        songs=[]
        for source_id in activity['sources']:
            for song in next(s for s in w['sources'] if s['id']==source_id)['members']:
                if song not in songs:songs.append(song)
        if t==18:
            songs=[x for x in songs+activity['additions'] if x not in activity['exclusions']]
            artist,count,date=activity['artist'],str(len(songs)),activity['date']
            name={'A':f'{artist}_{count}_{date}','B':f'{count}_{date}_{artist}','C':f'{date}_{artist}_{count}'}[variant]
        elif t==28:
            songs=[x for x in songs if objects[x]['available']]
            songs.sort(key={'A':lambda x:objects[x]['year'],'B':lambda x:objects[x]['duration'],'C':lambda x:objects[x]['artist']}[variant],reverse=variant!='A')
            name=activity['playlist_name']
        else:
            songs=[x for x in songs if (objects[x]['rating']>initial['source']['threshold'] if variant=='A' else objects[x]['rating']<initial['source']['threshold'] if variant=='B' else objects[x]['duration']%2==0)]
            songs=list(dict.fromkeys(activity['baseline']+songs));name=activity['playlist_name']
        if t!=32:yield 'playlist.create','',dict(activity=activity['id'],name=name)
        yield 'playlist.add',key,dict(songs=songs)
        yield 'playlist.order',key,dict(songs=songs)
        yield 'playlist.save',key,{}
        yield 'playlist.share',key,dict(group=activity['group_id'])


def complete(initial,variant):
    final=initial;events=[]
    for op,target,data in plan(initial,variant):
        value=json.dumps(data);final=music_projects.apply(final,op,target,value)
        events.append(dict(op=op,target=target,value=value))
    return final,events


@pytest.mark.parametrize('task_id',[18,28,32])
@pytest.mark.parametrize('variant',list('ABC'))
def test_music_real_deliveries_and_reset(clients,task_id,variant):
    control,worker=clients
    response=control.post('/v1/runs',headers=admin(),json=dict(suite='v2',task_id=task_id,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
    assert response.status_code==201,response.text
    run=response.json();path='/api/runs/'+run['id'];headers=credential(run)
    initial=worker.get(path,headers=headers).json()['state']
    assert not v2.evaluate(initial,initial,variant,[])['success']
    assert 'expected' not in json.dumps(initial) and 'variants' not in json.dumps(initial)
    for i,(op,target,data) in enumerate(plan(initial,variant)):
        body=dict(op=op,target=target,value=json.dumps(data),epoch=0,action_id=str(i))
        r=worker.post(path+'/commands',headers=headers,json=body);assert r.status_code==200,r.text
        again=worker.post(path+'/commands',headers=headers,json=body)
        assert again.status_code==200 and again.json()['state']==r.json()['state']
    result=control.post(f'/v2/tasks/{task_id}/eval',headers=admin(),json={'run_id':run['id']})
    assert result.status_code==200 and result.json()['success'],result.text
    final=worker.get(path,headers=headers).json()['state']
    # Every delivered link resolves to the saved native playlist.
    worker.post(f'/native/music/{run["id"]}/authorize',headers=headers)
    for share in final['world']['shares']:
        page=worker.get(f'/native/music/{run["id"]}/{share["link"]}')
        assert page.status_code==200 and share['name'] in page.text
    reset=control.post('/v1/runs/'+run['id']+'/reset',headers=admin());assert reset.status_code==200
    assert worker.get(path,headers=credential(reset.json())).json()['state']==initial
    assert worker.get(path,headers=headers).status_code==403


@pytest.mark.parametrize('task_id',[18,28,32])
@pytest.mark.parametrize('seed',[1000,10001,27183])
def test_music_variants_do_not_collapse(task_id,seed):
    initial=v2.generate(task_id,seed,'eval')
    assert initial==v2.generate(task_id,seed,'eval')
    for variant in 'ABC':
        final,events=complete(initial,variant)
        result=v2.evaluate(initial,final,variant,events);assert result['success'],result
        for other in set('ABC')-{variant}:assert not v2.evaluate(initial,final,other,events)['success']


@pytest.mark.parametrize('task_id',[18,28,32])
def test_saved_results_and_correct_group_snapshots_are_required(task_id):
    initial=v2.generate(task_id,10001,'eval');final,events=complete(initial,'A')
    for field in ('name','members','saved','group','share_name','share_members','added','link','personal','source','missing','duplicate'):
        changed=deepcopy(final);playlist=changed['world']['playlists']['list-001'];share=changed['world']['shares'][0]
        if field=='name':playlist['name']='Incorrect'
        elif field=='members':playlist['members'].pop()
        elif field=='saved':playlist['saved']=None
        elif field=='group':share['group']=50
        elif field=='share_name':share['name']='Stale'
        elif field=='share_members':share['members'].pop()
        elif field=='added':share['added']=[]
        elif field=='link':share['link']='playlists/personal/'
        elif field=='personal':changed['world']['playlists']['personal']['members']=[]
        elif field=='source':changed['world']['sources'][0]['members']=[]
        elif field=='missing':changed['world']['shares']=[]
        else:
            changed['world']['playlists']['extra']=deepcopy(playlist)
        assert not v2.evaluate(initial,changed,'A',events)['success'],field


def test_playlist_operations_reversible_and_stale_shares_fail():
    initial=v2.generate(18,10001,'eval');final,events=complete(initial,'A')
    song=final['world']['playlists']['personal']['members'][0]
    changed=music_projects.apply(final,'playlist.add','list-001',json.dumps(dict(songs=[song])))
    with pytest.raises(ValueError):music_projects.apply(changed,'playlist.share','list-001','{"group":20}')
    with pytest.raises(ValueError):music_projects.apply(changed,'playlist.delete','list-001')
    with pytest.raises(ValueError):music_projects.apply(changed,'playlist.order','list-001','{"songs":[]}')
    restored=music_projects.apply(changed,'playlist.remove','list-001',json.dumps(dict(songs=[song])))
    assert v2.evaluate(initial,restored,'A',events)['success']
    unshared=music_projects.apply(restored,'playlist.unshare','list-001','{"share":"share-1"}')
    assert not v2.evaluate(initial,unshared,'A',events)['success']
    replaced=music_projects.apply(unshared,'playlist.share','list-001','{"group":20}')
    assert v2.evaluate(initial,replaced,'A',events)['success']
    # Song IDs deduplicate overlapping sources, not identical display titles.
    state=music_projects.apply(initial,'playlist.create','',json.dumps(dict(activity='event-1',name='Draft')))
    for source in initial['world']['activities'][0]['sources']:
        state=music_projects.apply(state,'playlist.import','list-001',json.dumps(dict(source=source)))
    assert len(state['world']['playlists']['list-001']['members'])==5
