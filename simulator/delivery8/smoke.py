"""Real-service protocol validation. One diagnostic move per case, not a task trial."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .release import TASKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18664")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = (args.data/"platform.key").read_text().strip()
    def call(path, body=None, control=False, raw=False):
        req = Request(args.url+path, data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type":"application/json", **({"Authorization":"Bearer "+key} if control else {})})
        with urlopen(req, timeout=360) as response:
            data = response.read()
        return data if raw else json.loads(data)
    def rejected(path, status, body=None):
        try: call(path, body)
        except HTTPError as error: assert error.code == status, (path,error.code)
        else: raise AssertionError("Expected rejection")
    rejected('/control/tasks', 401)
    rejected('/release.private.json', 404)
    rejected('/client/server.py', 404)
    assert len(call('/control/tasks', control=True)) == 8
    report = dict(kind='real-http-protocol-smoke-not-agent-success', independent_agent=False,
                  human_recorded=False, started_at=time.time(), cases=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        for variant in 'ABC':
            sid = call('/control/sessions', dict(task=task, variant=variant, seed=7,
                trial_kind='protocol_smoke'), control=True)['session']
            actor = '/actor/'+sid
            try:
                video = call(actor+'/demo', raw=True)
                expected = TASKS[task]['demos'][variant]
                assert hashlib.sha256(video).hexdigest() == expected['video_sha256']
                frames = call(actor+'/demo-frames')['frames']; assert len(frames) == 12
                obs = call(actor+'/observe')
                assert set(obs['images']) == {'fpv','robot0_eye_in_hand','robot1_eye_in_hand'}
                assert set(obs) == {'images','instruction','observation_id','actions','remaining','tokens','motion'}
                body = dict(left='UP', right='STILL', step_mm=7.5, expected_observation=obs['observation_id'])
                response = call(actor+'/action', body)
                assert response['accepted'] and response['observation_id'] == 1
                rejected(actor+'/action', 409, body)
                rejected(actor+'/action', 422, dict(body, step_mm=50.1, expected_observation=1))
                after = call(actor+'/observe'); assert after['actions'] == 1
                assert after['images']['fpv'] != obs['images']['fpv']
            finally: call(actor+'/submit', {})
            rejected(actor+'/observe', 410)
            result = call('/control/results/'+sid, control=True)
            assert result['trial_kind'] == 'protocol_smoke' and result['actions'] == 1
            assert result['video']['video_frames'] > 0
            execution = call('/control/execution/'+sid, control=True, raw=True)
            assert len(execution) > 1000
            episode = args.data/'episodes'/sid
            manifest = json.loads((episode/'manifest.private.json').read_text())
            assert manifest['scene_source_sha256'] == expected['source_sha256']
            log = [json.loads(x) for x in (episode/'actions.private.jsonl').read_text().splitlines()]
            assert len(log) == 1 and log[0]['step_mm'] == 7.5
            report['cases'].append(dict(task=task, variant=variant, seed=7,
                scene_source_sha256=manifest['scene_source_sha256'], world_sha256=manifest['world_sha256'],
                demo_sha256=expected['video_sha256'], demo_frames=12, cameras=3,
                requested_step_mm=7.5, execution_bytes=len(execution), protocol_pass=True))
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report['cases'][-1], ensure_ascii=False), flush=True)
    for task in TASKS:
        rows=[x for x in report['cases'] if x['task']==task]
        assert len({x['world_sha256'] for x in rows}) == 1
    report['passed'] = 24
    report['finished_at'] = time.time()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': main()
