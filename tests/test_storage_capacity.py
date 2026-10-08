import errno
from types import SimpleNamespace
from unittest.mock import patch
from test_api import client, admin, create
from vic.store import WorkspaceStore
from test_application_api import clients


def test_full_disk_reports_unhealthy_and_blocks_new_runs(client):
    with patch('vic.main.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
        assert client.get('/healthz').status_code == 507
        response=client.post('/v1/runs',headers=admin(),json=dict(task_id=1,variant='A',seed=10001,runtime='web-dev'))
        assert response.status_code == 507
        assert '存储空间不足' in response.json()['detail']
    assert client.get('/v1/runs',headers=admin()).json()==[]
    assert client.get('/healthz').status_code==200


def test_disk_filling_after_preflight_returns_readable_error(client):
    with patch.object(WorkspaceStore,'initialize',side_effect=OSError(errno.ENOSPC,'full')):
        response=client.post('/v1/runs',headers=admin(),json=dict(task_id=1,variant='A',seed=10001,runtime='web-dev'))
        assert response.status_code==507
        assert '已有录像保留' in response.json()['detail']


def test_low_space_upload_does_not_seal_or_replace_work(clients):
    c,w=clients
    run=c.post('/v1/runs',headers=admin(),json=dict(task_id=1,variant='A',seed=0,mode='demo',runtime='browser',interaction='human')).json()
    with patch('vic.main.shutil.disk_usage', return_value=SimpleNamespace(free=100)):
        response=c.post('/v1/runs/'+run['id']+'/recordings/upload?epoch=0',headers={**admin(),'Content-Type':'video/webm'},content=b'not-a-video')
        assert response.status_code==507
    fresh=c.get('/v1/runs/'+run['id'],headers=admin()).json()
    assert fresh['status']=='ready' and not fresh.get('recording')
