import ast
import json
import math
from pathlib import Path
import tarfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simulator.delivery8 import hosted, motion, release


class Trace:
    def __init__(self):
        self.grips = [-1., -1.]
        self.commands = []
        self.tracks = 0

    def step(self, command): self.commands.append(command.copy())
    def track(self): self.tracks += 1


def test_default_motion_exactly_preserves_every_historical_controller_command():
    for archive in {t['archive'] for t in release.TASKS.values()}:
        with tarfile.open(release.SIMULATOR/archive) as tar:
            method = None
            for name in ('simulator/tabletop50/environment.py', 'simulator/benchmark/environment.py'):
                tree = ast.parse(tar.extractfile(name).read())
                methods = [n for cls in tree.body if isinstance(cls, ast.ClassDef)
                           for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'action']
                if methods:
                    method = methods[0]; break
        namespace = dict(np=np, math=math, TOKENS=motion.TOKENS)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                     archive, 'exec'), namespace)
        # The foundation controller predates fine tokens; test its actual alphabet.
        fine = '_FINE' in ast.unparse(method)
        for token in motion.TOKENS:
            if token.endswith('_FINE') and not fine: continue
            a, b = Trace(), Trace()
            namespace['action'](a, token, token)
            motion.move(b, token, token)
            np.testing.assert_array_equal(a.commands, b.commands)
            assert a.grips == b.grips and a.tracks == b.tracks == 8


@pytest.mark.parametrize('distance', [.5, 2.3, 7.5, 20, 37.25, 50])
def test_continuous_distance_reaches_physics_command(distance):
    trace = Trace()
    motion.move(trace, 'UP_FINE', 'BACK', step_mm=distance)
    assert trace.commands[0][2] == pytest.approx(distance/50)
    assert trace.commands[0][7] == pytest.approx(-distance/50)
    assert np.count_nonzero(trace.commands[1][:6]) == 0
    assert np.count_nonzero(trace.commands[1][7:13]) == 0
    assert len(trace.commands) == 8


@pytest.mark.parametrize('distance', [True, '7.5', 0, -.5, 50.1, float('nan'), float('inf')])
def test_invalid_distances_rejected_before_mutation(distance):
    trace = Trace()
    with pytest.raises(ValueError): motion.move(trace, 'GRASP', step_mm=distance)
    assert trace.grips == [-1., -1.] and trace.commands == []


def test_manifest_has_exact_requested_tasks_and_24_verified_demos():
    assert list(release.TASKS) == ['F01', 'F11', 'F10', 'F08', 'F22', 'F17', 'F39', 'F44']
    assert release.TASKS['F22']['length'] == '长程'
    assert release.TASKS['F39']['length'] == '短程'
    for task in release.TASKS:
        for variant in 'ABC': assert release.verify_demo(task, variant).is_dir()


def test_demo_tampering_is_rejected(tmp_path, monkeypatch):
    import shutil
    task = release.TASKS['F44']
    rel = Path(task['demos']['A']['folder'])
    folder = tmp_path/rel
    shutil.copytree(release.SIMULATOR/rel, folder)
    shutil.copy(release.SIMULATOR/rel.parent/'manifest.private.json', folder.parent)
    monkeypatch.setattr(release, 'SIMULATOR', tmp_path)
    assert release.verify_demo('F44', 'A') == folder
    (folder/'video.mp4').write_bytes(b'corrupt')
    with pytest.raises(ValueError): release.verify_demo('F44', 'A')


def test_http_auth_validation_and_no_privileged_actor_fields(monkeypatch, tmp_path):
    from simulator.delivery8 import server
    monkeypatch.setattr(server, 'prepare', lambda _: None)
    class Fake:
        count = 0; closed = False; started = 0
        req = server.Create(task='F44', variant='A', wall_seconds=7200)
        def rpc(self, payload):
            if payload['op'] == 'observe': return dict(images={'fpv': 'jpeg'})
            assert payload['step_mm'] == 7.5
            return {}
        def close(self, reason='submitted'): self.closed = True
    import time
    fake = Fake(); fake.started = time.monotonic(); fake.folder = tmp_path
    monkeypatch.setattr(server, 'SESSIONS', {'opaque-session': fake})
    with TestClient(server.app) as client:
        assert client.get('/control/tasks').status_code == 401
        assert client.get('/control/tasks', headers={'Authorization': 'Bearer '+server.KEY}).status_code == 200
        obs = client.get('/actor/opaque-session/observe').json()
        assert set(obs) == {'images','instruction','observation_id','actions','remaining','tokens','motion'}
        action = dict(left='UP', step_mm=7.5, expected_observation=0)
        assert client.post('/actor/opaque-session/action', json=action).status_code == 200
        assert client.post('/actor/opaque-session/action', json=action).status_code == 409
        for v in [True, '7.5', 0, 50.1]:
            assert client.post('/actor/opaque-session/action', json=dict(action, step_mm=v,
                expected_observation=1)).status_code == 422
        assert fake.count == 1


def test_hosted_inputs_hide_task_rule_and_keep_fractional_distance():
    obs = dict(images={'fpv':'image'}, instruction='Follow demonstration', observation_id=0,
               actions=0, remaining=1600, tokens=motion.TOKENS, motion={},
               variant='C', task='F44', goals=['private'], object_positions={'private':1})
    p = hosted.payload('model', ['demo'], obs, [])
    text = json.dumps(p)
    assert 'private' not in text and 'F44' not in text and 'variant' not in text
    d = dict(left='UP',right='STILL',step_mm=7.5,rotation_deg=2.5,finish=False,summary='visible')
    assert hosted.decision(json.dumps(d), motion.TOKENS)['step_mm'] == 7.5
    d['step_mm'] = True
    with pytest.raises(ValueError): hosted.decision(json.dumps(d), motion.TOKENS)
