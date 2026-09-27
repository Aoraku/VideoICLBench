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
    entry=worker.get(path)
    assert entry.status_code==200 and 'music-state' not in entry.text
    assert '正在打开音乐资料库' in entry.text
    assert worker.post(path+'authorize',headers={'Authorization':'Bearer '+token}).status_code==403
    assert worker.get('/api/runs/'+first['id'],headers={'Authorization':'Bearer '+token}).status_code==403


@pytest.mark.parametrize('task_id,route,notice', [
    (17, 'songs/target/', '✓ 名称已保存'),
    (18, 'playlists/', '✓ 播放列表已创建'),
])
def test_music_save_feedback_survives_server_page_reload(clients, task_id, route, notice):
    from html.parser import HTMLParser

    class VisibleText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hidden = 0
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'):
                self.hidden += 1

        def handle_endtag(self, tag):
            if tag in ('script', 'style'):
                self.hidden -= 1

        def handle_data(self, text):
            if not self.hidden:
                self.parts.append(text)

    control, worker = clients
    run = create(control, task_id)
    auth = {'Authorization': 'Bearer ' + run['workspace_url'].split('#')[1]}
    path = f"/native/music/{run['id']}/"
    worker.post(path + 'authorize', headers=auth).raise_for_status()
    before = worker.get(path + route)
    before.raise_for_status()
    assert notice not in before.text
    saved = 'Saved <Song> & Playlist'
    worker.post(f"/api/runs/{run['id']}/commands", headers=auth,
                json=dict(epoch=0, action_id='save-feedback', op='save', target='target', value=saved)).raise_for_status()
    for _ in range(2):
        response = worker.get(path + route)
        response.raise_for_status()
        parser = VisibleText()
        parser.feed(response.text)
        visible = ''.join(parser.parts)
        assert notice in visible and saved in visible
        assert '<Song>' not in response.text


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
        await recorder.start('abc','http://application.localhost/apps/chat/abc#credential')
    assert not recorder.active


@pytest.mark.asyncio
async def test_recorder_preserves_first_frame_without_rule_overlay(tmp_path):
    import asyncio
    import io
    import inspect
    from PIL import Image, ImageChops

    original = Image.new('RGB', (1280, 960), '#5d9361')
    buffer = io.BytesIO()
    original.save(buffer, format='PNG')

    class Runtime:
        sessions = {}
        async def ensure(self, run_id, url):
            return {'page': SimpleNamespace(url=url)}
        async def capture(self, run_id, url):
            return buffer.getvalue()

    recorder = Recorder(tmp_path, Runtime())
    # Private rule text cannot enter the rendering API at all.
    assert 'rule' not in inspect.signature(recorder.start).parameters
    await recorder.start('clean', 'http://application.localhost/apps/chat/clean#token')
    try:
        async with asyncio.timeout(3):
            while recorder.active['clean']['frames'] < 2:
                await asyncio.sleep(.01)
        for path in (tmp_path / 'clean').glob('*.png'):
            frame = Image.open(path).convert('RGB')
            assert ImageChops.difference(frame, original).getbbox() is None
        metadata = await recorder.stop('clean')
        assert metadata['rule_overlay'] is False
    finally:
        await recorder.close()
