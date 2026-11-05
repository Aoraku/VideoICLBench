"""Actual Chrome -> public queue -> HTTP -> Episode, with a synthetic runtime only."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import queue
import threading

import httpx
import pytest

from vic_sdk.embodied_environment.server import serve
from vic_sdk.robodawn_tools import GUIBridge
from vic_sdk.robodawn_turn_executor import TurnExecutor
from test_embodied_action_batch import make_episode, pair
from test_embodied_gui_mcp import chrome_path, ASSETS


@pytest.fixture
def batch_owner(tmp_path):
    episode,runtime=make_episode(tmp_path,budget=50)
    ready=queue.Queue();errors=[]
    data=dict(episode=episode,runtime=runtime,batch_calls=[],single_calls=[],fail_at=None,reject_at=None)
    native_action=runtime.action
    def action(**fields):
        if data['reject_at']==len(runtime.actions)+1:
            return {'accepted':False,'reason':'synthetic_nonadmission'}
        if data['fail_at']==len(runtime.actions)+1:
            raise RuntimeError('Synthetic native outcome unavailable')
        return native_action(**fields)
    runtime.action=action
    batch=episode.action_batch
    def recorded_batch(**fields):
        data['batch_calls'].append(deepcopy(fields));return batch(**fields)
    episode.action_batch=recorded_batch
    single=episode.action
    def recorded_single(**fields):
        data['single_calls'].append(deepcopy(fields));return single(**fields)
    episode.action=recorded_single
    def owner():
        try:serve(episode,port=0,agent_token='actor-test',admin_token='admin-test',frontend=ASSETS,ready=ready.put)
        except BaseException as exc:errors.append(exc);ready.put(exc)
    thread=threading.Thread(target=owner,daemon=True);thread.start();port=ready.get(timeout=10)
    if isinstance(port,BaseException):raise port
    data['url']='http://127.0.0.1:'+str(port)
    try:yield data
    finally:
        with httpx.Client(trust_env=False,timeout=10)as client:
            client.post(data['url']+'/api/private/close',headers={'Authorization':'Bearer admin-test'},
                json={'identity':asdict(episode.identity)})
        thread.join(timeout=10)
        assert not thread.is_alive()and not errors


def make_executor(tmp_path,owner,chrome):
    config=dict(control_url=owner['url'],actor_token='actor-test',run_id=owner['episode'].identity.run_id,
        program_episode_identity=asdict(owner['episode'].identity),output_dir=str(tmp_path/'gui'),
        condition='text_rule',embodied_harness='program_gui',max_actions=50,max_gui_inputs=1000,
        timeout_seconds=0,budget_policy='effective_time_graceful_v1',browser_path=chrome,gui_observation_timeout_ms=4000,gui_settle_timeout_ms=4000)
    bridge=GUIBridge(config);return TurnExecutor(config,bridge=bridge),bridge


def command(actions):return {'type':'action_batch','actions':actions}


def test_actual_chrome_ordered_pairs_one_commit_one_native_observation_at_end(tmp_path,batch_owner,chrome_path):
    executor,bridge=make_executor(tmp_path,batch_owner,chrome_path)
    try:
        first=executor.initialize();before=batch_owner['runtime'].observation_calls
        actions=[pair('UP','DOWN',3.,2.),pair('GRASP','UP',7.,4.),pair('DOWN','RELEASE',9.,6.)]
        result=executor.execute([command(actions)],decision_id='browser-batch-one')
        assert not result['uncertain'],[r.get('error')for r in result['results']]
        assert result['physical_commits']==1 and result['physical_action_count']==3
        assert batch_owner['runtime'].actions==actions
        assert len(batch_owner['batch_calls'])==1 and not batch_owner['single_calls']
        assert batch_owner['runtime'].observation_calls==before+1
        assert result['observation']['step']==3 and result['observation']['frame_id']!=first['observation']['frame_id']
        assert result['results'][0]['receipt']['completed_count']==3
        with pytest.raises(ValueError,match='one-shot'):
            executor.execute([command(actions)],decision_id='browser-batch-one')
        assert len(batch_owner['batch_calls'])==1
    finally:bridge.close()


def test_actual_chrome_unknown_batch_keeps_prefix_and_never_commits_again(tmp_path,batch_owner,chrome_path):
    batch_owner['fail_at']=2
    executor,bridge=make_executor(tmp_path,batch_owner,chrome_path)
    try:
        executor.initialize();actions=[pair(),pair('DOWN'),pair('GRASP')]
        result=executor.execute([command(actions)],decision_id='unknown-browser-batch')
        assert result['uncertain']and not result['terminal']
        assert len(batch_owner['runtime'].actions)==1 and len(batch_owner['batch_calls'])==1,[r.get('error')for r in result['results']]
        assert batch_owner['episode'].last_action_batch['status']=='unknown'
        with pytest.raises(ValueError,match='one-shot'):
            executor.execute([command(actions)],decision_id='unknown-browser-batch')
        assert len(batch_owner['batch_calls'])==1 and len(batch_owner['runtime'].actions)==1
        replacement=executor.execute([command(actions)],decision_id='different-id-must-not-replay')
        assert replacement['uncertain']and len(batch_owner['batch_calls'])==1 and len(batch_owner['runtime'].actions)==1
        assert batch_owner['runtime'].scored==0
    finally:bridge.close()


def test_actual_chrome_known_partial_batch_returns_count_without_replaying_suffix(tmp_path,batch_owner,chrome_path):
    batch_owner['reject_at']=2
    executor,bridge=make_executor(tmp_path,batch_owner,chrome_path)
    try:
        executor.initialize();actions=[pair(),pair('DOWN'),pair('GRASP')]
        result=executor.execute([command(actions)],decision_id='partial-browser-batch')
        assert result['uncertain']and not result['terminal'],[r.get('error')for r in result['results']]
        assert result['physical_commits']==1 and result['physical_action_count']==1
        assert len(batch_owner['runtime'].actions)==1 and len(batch_owner['batch_calls'])==1
        assert result['results'][0]['receipt']['status']=='partial'
        with pytest.raises(ValueError):executor.execute([command(actions)],decision_id='partial-browser-batch')
        assert len(batch_owner['runtime'].actions)==1 and len(batch_owner['batch_calls'])==1
    finally:bridge.close()


def test_actual_chrome_twentyfour_queue_items_keep_commit_visible_and_execute_once(tmp_path,batch_owner,chrome_path):
    executor,bridge=make_executor(tmp_path,batch_owner,chrome_path)
    try:
        executor.initialize();actions=[pair('UP'if n%2==0 else'DOWN','STILL',1.+n/10,2.)for n in range(24)]
        result=executor.execute([command(actions)],decision_id='maximum-browser-batch')
        assert not result['uncertain'],[r.get('error')for r in result['results']]
        assert result['physical_commits']==1 and result['physical_action_count']==24
        assert batch_owner['runtime'].actions==actions and len(batch_owner['batch_calls'])==1
        assert not batch_owner['single_calls']
    finally:bridge.close()


def test_actual_runner_chrome_batch_counts_one_commit_three_actions_and_one_decision(tmp_path,batch_owner,chrome_path):
    from vic_sdk.robodawn_turn_runner import Runner
    from test_robodawn_turn_integration import FakeResponses,response,decision
    executor,bridge=make_executor(tmp_path,batch_owner,chrome_path)
    computer=deepcopy(executor.config);computer['program_episode_identity']=asdict(batch_owner['episode'].identity)
    path=tmp_path/'computer.json';path.write_text(json.dumps(computer))
    instruction=tmp_path/'instruction.txt';instruction.write_text('Synthetic ordered public actions only.')
    transport=FakeResponses([response(1,decision(1,[command([pair(),pair('DOWN'),pair('GRASP')])]))])
    runner=Runner(dict(protocol='decision_turn',profile=str(tmp_path/'profile'),output_root=str(tmp_path/'output'),
        computer_config=str(path),instruction_path=str(instruction),model='local-fake',base_url='http://unused.invalid/v1',
        policy={'lean_public_input':True}),executor=executor,transport=transport,emit=lambda _:None)
    try:
        state=runner.run(max_decisions=1)
        assert state['phase']=='ready',state.get('diagnostic')
        assert state['physical_commits']==1 and state['physical_action_count']==3 and state['physical_turns']==1
        assert len(transport.bodies)==len(batch_owner['batch_calls'])==1
        assert runner.context.build().physical_turn_count==1
    finally:runner.close();bridge.close()
