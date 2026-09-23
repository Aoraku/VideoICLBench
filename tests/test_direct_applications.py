"""Human application entry keeps run isolation without the remote input layer."""
from test_application_api import clients
from test_api import admin
from vic.business import transform


def human(control, task=1):
    r=control.post('/v1/runs',headers=admin(),json=dict(task_id=task,variant='A',seed=10001,runtime='browser',interaction='human'))
    assert r.status_code==201,r.text
    return r.json()


def credential(run):
    return {'Authorization':'Bearer '+run['application_url'].split('#')[1]}


def test_direct_entry_isolation_reset_and_evaluation(clients,monkeypatch):
    monkeypatch.setenv('VIC_APPLICATION_PUBLIC_BASE','http://127.0.0.1:18766')
    c,w=clients;a=human(c);b=human(c)
    assert a['application_url'].startswith('http://127.0.0.1:18766/apps/chat/')
    assert a['interaction']=='human'
    url='/api/runs/'+a['id'];p='/v1/runs/'+a['id']
    assert w.get('/api/runs/'+b['id'],headers=credential(a)).status_code==403
    state=w.get(url,headers=credential(a)).json()['state']
    value=transform(1,0,state)
    r=w.post(url+'/commands',headers=credential(a),json=dict(epoch=0,action_id='save',op='save',target='target',value=value))
    assert r.status_code==200,r.text
    assert w.get(url,headers=credential(a)).json()['state']['outputs']['target']==value
    assert c.get(p+'/observation',headers=admin()).status_code==409
    assert c.post(p+'/actions',headers=admin(),json=dict(epoch=0,frame=0,action_id='input',kind='click',x=10,y=10)).status_code==409
    result=c.post(p+'/evaluate',headers=admin());assert result.json()['success'],result.text
    assert not c.app.state.runtime.sessions
    assert w.post(url+'/commands',headers=credential(a),json=dict(epoch=0,action_id='late',op='save',target='target',value=value)).status_code==409
    reset=c.post(p+'/reset',headers=admin()).json()
    assert reset['interaction']=='human' and reset['epoch']==1
    assert w.get(url,headers=credential(a)).status_code==403
    assert w.get(url,headers=credential(reset)).json()['state']['outputs']=={}
    assert not c.post(p+'/evaluate',headers=admin()).json()['success']


def test_human_commands_do_not_inherit_agent_budget(clients):
    c,w=clients;r=human(c);path='/api/runs/'+r['id']
    for i in range(302):
        response=w.post(path+'/commands',headers=credential(r),json=dict(epoch=0,action_id=str(i),op='save',target='target',value=f'编辑稿 {i}'))
        assert response.status_code==200,response.text
    assert w.get(path,headers=credential(r)).json()['state']['outputs']['target']=='编辑稿 301'
    assert not c.app.state.runtime.sessions


def test_pilot_gate_and_human_recording_guard(clients,monkeypatch):
    monkeypatch.setenv("VIC_DIRECT_MODULES", "chat,news")
    c,w=clients
    assert c.post('/v1/runs',headers=admin(),json=dict(task_id=17,variant='A',seed=10001,interaction='human')).status_code==409
    r=c.post('/v1/runs',headers=admin(),json=dict(task_id=23,variant='A',seed=0,mode='demo',interaction='human')).json()
    assert c.post('/v1/runs/'+r['id']+'/recordings/start',headers=admin()).status_code==409
    assert not c.app.state.runtime.sessions


def test_all_application_modules_have_direct_entry(clients):
    c,w=clients
    modules={1:'chat',15:'im',17:'music',23:'news',21:'media',36:'blog',37:'studio',44:'travel',45:'shop',46:'bank',58:'code',66:'gomoku',68:'games'}
    for task,module in modules.items():
        r=human(c,task)
        assert '/apps/'+module+'/' in r['application_url']
        assert w.get('/api/runs/'+r['id'],headers=credential(r)).status_code==200
    assert not c.app.state.runtime.sessions


def test_import_recording_decode_seal_review_and_reset(clients,tmp_path):
    import subprocess
    import imageio_ffmpeg
    c,w=clients
    r=c.post('/v1/runs',headers=admin(),json=dict(task_id=1,variant='A',seed=0,mode='demo',interaction='human')).json()
    path='/v1/runs/'+r['id'];wp='/api/runs/'+r['id']
    state=w.get(wp,headers=credential(r)).json()['state']
    assert w.post(wp+'/commands',headers=credential(r),json=dict(epoch=0,action_id='save',op='save',target='target',value=transform(1,0,state))).status_code==200
    upload=path+'/recordings/upload?epoch=0'
    assert c.post(upload,content=b'invalid').status_code==401
    assert c.post(upload,headers=admin(),content=b'invalid').status_code==415
    assert c.post(upload,headers={**admin(),'Content-Type':'video/webm'},content=b'invalid').status_code==422
    clip=tmp_path/'test.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','lavfi','-i','color=c=blue:s=320x240:r=30','-t','1','-c:v','libx264',str(clip)],check=True)
    assert c.post(path+'/recordings/upload?epoch=1',headers={**admin(),'Content-Type':'video/mp4'},content=clip.read_bytes()).status_code==409
    result=c.post(upload,headers={**admin(),'Content-Type':'video/mp4'},content=clip.read_bytes())
    assert result.status_code==200,result.text
    assert result.json()['source']=='human_browser' and result.json()['frames']>=29
    assert not result.json()['entry_verified'] and not result.json()['official']
    assert c.get(path+'/recordings/video',headers=admin()).headers['content-type']=='video/mp4'
    assert w.post(wp+'/commands',headers=credential(r),json=dict(epoch=0,action_id='late',op='save',target='target',value='late')).status_code==409
    review=dict(approved=True,reviewer='test',note='synthetic unit fixture')
    assert c.post(path+'/recordings/review',headers=admin(),json=review).status_code==409
    assert c.post(path+'/evaluate',headers=admin()).json()['success']
    assert c.post(path+'/recordings/review',headers=admin(),json=review).json()['status']=='approved'
    assert c.post(path+'/reset',headers=admin()).json()['epoch']==1
    assert c.get(path+'/recordings/video',headers=admin()).status_code==404
    assert not c.app.state.runtime.sessions


def test_human_clipboard_evidence_is_required_and_identified(clients):
    from test_applications import reference
    c,w=clients
    r=c.post('/v1/runs',headers=admin(),json=dict(task_id=43,variant='B',seed=0,mode='demo',interaction='human')).json()
    path='/v1/runs/'+r['id'];wp='/api/runs/'+r['id']
    assert c.post(path+'/evaluate',headers=admin()).status_code==409
    state=w.get(wp,headers=credential(r)).json()['state']
    for i,(op,target,value,ids) in enumerate(reference(state,'B')):
        response=w.post(wp+'/commands',headers=credential(r),json=dict(epoch=0,action_id=str(i),op=op,target=target,value=value,ids=ids))
        assert response.status_code==200,response.text
    final=w.get(wp,headers=credential(r)).json()['state']
    result=c.post(path+'/evaluate',headers=admin(),json={'clipboard':final['domain']['clipboard_history'][-1]['text']})
    assert result.json()['success'],result.text
    assert result.json()['clipboard_evidence_source']=='human_paste'
    assert not c.app.state.runtime.sessions
