"""Isolation and lifecycle regressions introduced by native application adapters."""
from types import SimpleNamespace
import pytest
from test_application_api import clients, create
from test_api import SECRET, admin
from vic.business import generate
from vic.games import expected
from vic_apps.domain import initialize
from vic_apps.store import ApplicationStore
from vic_apps.gomoku_native import GomokuBridge
from vic.recording import Recorder


def test_music_cookie_is_run_scoped_and_rotates(clients):
    control, worker = clients
    first, second = create(control,17), create(control,17)
    token=first['workspace_url'].split('#')[1]
    path=f"/native/music/{first['id']}/"
    auth=worker.post(path+'authorize',headers={'Authorization':'Bearer '+token})
    assert auth.status_code==204
    assert f'Path={path}' in auth.headers['set-cookie']
    page=worker.get(path)
    assert page.status_code==200 and 'music-state' in page.text
    assert '青楽' in page.text
    assert worker.post(f"/native/music/{second['id']}/authorize",headers={'Authorization':'Bearer '+token}).status_code==403
    assert worker.get(f"/native/product/shop/{first['id']}").status_code==404
    control.post(f"/v1/runs/{first['id']}/reset",headers=admin()).raise_for_status()
    assert worker.get(path).status_code==403


def test_native_release_requires_seal_and_preserves_data(clients):
    control, worker=clients
    run=create(control,58);rid=run['id'];private={'Authorization':'Bearer '+SECRET}
    token={'Authorization':'Bearer '+run['workspace_url'].split('#')[1]}
    assert worker.post(f'/internal/runs/{rid}/release',headers=private).status_code==409
    assert worker.post(f'/internal/runs/{rid}/release',headers=token).status_code==403
    worker.post(f'/internal/runs/{rid}/seal',headers=private).raise_for_status()
    assert worker.post(f'/native/code/{rid}/authorize',headers=token).status_code==409
    worker.post(f'/internal/runs/{rid}/release',headers=private).raise_for_status()
    assert worker.get(f'/api/runs/{rid}',headers=token).json()['state']['task_id']==58


def test_sdl_intents_wait_for_complete_lines_and_respect_seal(tmp_path):
    rid='a'*32;store=ApplicationStore(tmp_path);state=initialize(generate(66,0));store.initialize(rid,state)
    metadata={'app':'gomoku','status':'active','epoch':0}
    bridge=GomokuBridge(tmp_path,store,lambda _:metadata)
    bridge.export(rid)
    r,c=expected(66,'A',state)[0]
    path=tmp_path/rid/'gomoku-intents.txt'
    path.write_text(f'mark {r} {c}')
    bridge.drain(rid);assert not store.events(rid)
    path.write_text(f'mark {r} {c}\n')
    bridge.drain(rid);bridge.drain(rid)
    assert len(store.events(rid))==1 and store.snapshot(rid)['marks']==[[r,c]]
    metadata['status']='sealed'
    path.write_text(f'mark {r} {c}\nmark {r} {c}\n')
    bridge.drain(rid);assert len(store.events(rid))==1


@pytest.mark.asyncio
@pytest.mark.parametrize('current',['http://application.localhost/native/chat/abc/chat','http://application.localhost/apps/chat/abc?diagnostic=1'])
async def test_recording_must_start_at_launcher(tmp_path,current):
    class Runtime:
        async def ensure(self,*args):return {'page':SimpleNamespace(url=current)}
    recorder=Recorder(tmp_path,Runtime())
    with pytest.raises(ValueError,match='入口'):
        await recorder.start('abc','http://application.localhost/apps/chat/abc#credential','rule')
    assert not recorder.active
