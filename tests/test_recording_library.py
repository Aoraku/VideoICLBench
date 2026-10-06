"""Saved takes remain discoverable independently of transient portal sessions."""
import json
from test_api import client, admin, create


def save_take(tmp_path, run, **fields):
    directory = tmp_path / 'artifacts' / run['id']
    directory.mkdir(parents=True, exist_ok=True)
    meta = dict(epoch=run['epoch'], status='approved', approved=True,
                reviewer='Recorder', task_digest=run['manifest']['task_digest'], **fields)
    (directory / 'recording.json').write_text(json.dumps(meta))
    (directory / 'tutorial.mp4').write_bytes(b'saved-video-fixture')


def test_saved_recordings_survive_reset_and_are_authenticated(client, tmp_path):
    run = create(client, mode='demo', seed=0)
    save_take(tmp_path, run)
    url = f"/v1/runs/{run['id']}"
    assert client.get('/v1/recordings').status_code == 401
    saved = client.get('/v1/recordings', headers=admin()).json()[0]
    assert saved['recording']['approved'] and saved['recording']['available']
    assert saved['recording']['contract_current']
    assert client.get(url, headers=admin()).json()['recording']['reviewer'] == 'Recorder'
    assert client.post(url+'/reset', headers=admin()).status_code == 200
    archived = client.get('/v1/recordings', headers=admin()).json()[0]
    assert archived['epoch'] == 0 and archived['recording']['archived']
    assert archived['recording']['approved']
    assert client.get(url+'/recordings/video?epoch=0', headers=admin()).content == b'saved-video-fixture'
    assert client.get(url+'/recordings/metadata?epoch=0', headers=admin()).json()['approved']
    assert client.get(url+'/recordings/video?epoch=-1', headers=admin()).status_code == 404
    assert client.get(url+'/recordings/video?epoch=0').status_code == 401


def test_library_is_not_truncated_by_recent_runs(client, tmp_path):
    run = create(client, mode='demo', seed=0)
    save_take(tmp_path, run)
    for _ in range(201):
        create(client)
    assert run['id'] not in [r['id'] for r in client.get('/v1/runs', headers=admin()).json()]
    assert client.get('/v1/recordings', headers=admin()).json()[0]['id'] == run['id']


def test_older_contract_recordings_remain_downloadable(client, tmp_path):
    run = create(client, mode='demo', seed=0)
    save_take(tmp_path, run)
    path = tmp_path/'artifacts'/run['id']/'recording.json'
    meta=json.loads(path.read_text());meta['task_digest']='historical-contract';path.write_text(json.dumps(meta))
    item=client.get('/v1/recordings',headers=admin()).json()[0]
    assert not item['recording']['contract_current']
    assert item['recording']['available']
