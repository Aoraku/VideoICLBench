"""Decision macros use actual GUI acknowledgements, never hidden robot RPC."""
import base64
from copy import deepcopy
import json

import pytest

from vic_sdk.robodawn_tools import GUIBridge, ToolResult
from vic_sdk.robodawn_turn_executor import TurnExecutor


def action(**updates):
    return dict(type='action', left='UP', right='STILL', step_mm=20, rotation_deg=10, **updates)


class Bridge:
    def __init__(self):
        self.calls = []
        self.steps = 0
        self.error_at = None
        self.ack_delta = 1
        self.macros = []

    def public_action_count(self):
        return self.steps

    def public_action_inputs(self, command):
        self.macros.append(deepcopy(command))
        return [dict(kind='click', x=10, y=20)]

    def observation(self, status='running'):
        public = dict(native_frame_id='native-' + str(self.steps),
            robot_feedback=dict(arms=dict(left=dict(tcp_position=[.1,.2,.3]))),
            action_schema=dict(tokens=['STILL','UP','MV_FWD'],
                step_mm=dict(minimum=.5, maximum=50), rotation_deg=dict(minimum=.5, maximum=20)),
            secret_objects='PRIVATE_OBJECTS', score=100)
        payload = dict(frame_id='gui-' + str(self.steps), public_observation=public,
            width=1440, height=1280, episode_status=status, max_robot_actions=500)
        image = dict(type='input_image', image_url='data:image/png;base64,' + base64.b64encode(b'test-frame').decode())
        return ToolResult('observe', [dict(type='input_text', text=json.dumps(payload))], [image], payload,
                          image_sources=[dict(kind='gui')])

    def call_tool(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == 'act':
            if self.error_at == self.steps + 1:
                return ToolResult('act', [dict(type='input_text', text='GUI transport failed; outcome unknown')], [], {}, True)
            self.steps += self.ack_delta
        if name == 'depth_points':
            raw = dict(native_frame_id='native-' + str(self.steps), measurements=[dict(valid=False, reason='synthetic_invalid_pixel')])
            return ToolResult(name, [dict(type='input_text', text=json.dumps(raw))], [], raw)
        return self.observation('done' if name == 'done' else 'running')


def executor(bridge, **options):
    return TurnExecutor(dict(condition='text_rule'), bridge=bridge, **options)


def test_complete_control_selection_one_original_commit_then_new_observation():
    bridge = Bridge()
    log = []
    e = executor(bridge, on_intent=lambda row: log.append(('intent', row['command_index'], len(bridge.calls))),
                 on_receipt=lambda row: log.append(('receipt', row['command_index'], len(bridge.calls))))
    initialized = e.initialize()
    assert 'PRIVATE' not in json.dumps(initialized)
    command = dict(type='action', left='UP', right='MV_FWD', step_mm=7.5, rotation_deg=12.5)
    result = e.execute([command], decision_id='turn-1')
    assert result['physical_commits'] == bridge.steps == 1
    assert bridge.macros == [command]
    assert [name for name, _ in bridge.calls] == ['observe', 'act']
    assert [args['frame_id'] for name, args in bridge.calls if name == 'act'] == ['gui-0']
    assert log[0] == ('intent', 0, 1) and log[1] == ('receipt', 0, 2)
    assert result['observation']['frame_id'] == 'gui-1'
    assert not result['uncertain']
    with pytest.raises(ValueError, match='one-shot'):
        e.execute([action()], decision_id='turn-1')
    assert bridge.steps == 1


def test_unknown_commit_never_replays_the_decision():
    bridge = Bridge(); bridge.error_at = 1
    e = executor(bridge); e.initialize()
    result = e.execute([action()], decision_id='unknown-turn')
    assert result['uncertain'] and result['physical_commits'] == 0
    assert len(result['results']) == 1 and len(bridge.calls) == 2
    assert bridge.steps == 0
    with pytest.raises(ValueError):
        e.execute([action()], decision_id='unknown-turn')


@pytest.mark.parametrize('count', [0, 2, 4, 20])
def test_multiple_physical_commands_rejected_before_gui_edits(count):
    bridge = Bridge(); e = executor(bridge); e.initialize()
    with pytest.raises(ValueError, match='exactly one'):
        e.execute([action() for _ in range(count)], decision_id='invalid-batch')
    assert bridge.macros == []
    assert [name for name, _ in bridge.calls] == ['observe']
    # Invalid input has not consumed a decision identity or touched the world.
    result = e.execute([action()], decision_id='invalid-batch')
    assert result['physical_commits'] == 1


def test_acknowledgement_is_verified_from_actual_visible_budget():
    bridge = Bridge(); bridge.ack_delta = 0
    e = executor(bridge); e.initialize()
    result = e.execute([action()], decision_id='no-ack')
    assert result['uncertain'] and result['physical_commits'] == 0
    assert 'acknowledge exactly one' in result['results'][0]['error']


def test_public_bounds_and_tokens_checked_before_any_gui_mutation():
    bridge = Bridge(); e = executor(bridge); e.initialize()
    for commands in [[], [dict(type='observe')], [dict(type='action', left='RESET', right='STILL', step_mm=10, rotation_deg=10)],
                     [dict(type='action', left='UP', right='STILL', step_mm=999, rotation_deg=10)],
                     [action(), dict(type='done', summary='premature')]]:
        with pytest.raises(ValueError):
            e.execute(commands, decision_id='invalid')
    assert len(bridge.calls) == 1


def test_sensor_queries_do_not_move_and_terminal_is_separate():
    bridge = Bridge(); e = executor(bridge); e.initialize()
    result = e.readonly([dict(type='depth_points', camera='head', pixels=[[1,2]])], decision_id='sense')
    assert result['physical_commits'] == bridge.steps == 0 and result['results'][0]['measurements']
    result = e.execute([dict(type='done', summary='Model chose done')], decision_id='done')
    assert result['terminal'] and bridge.steps == 0
    assert not any(name in ('seal', 'evaluate', 'reset', 'home') for name, _ in bridge.calls)


def test_short_public_alias_maps_only_when_the_target_is_actually_available():
    bridge = Bridge(); e = executor(bridge); e.initialize()
    command = dict(type='action', left='FWD', right='STILL', step_mm=20, rotation_deg=10)
    e.execute([command], decision_id='alias')
    assert bridge.macros[0]['left'] == 'MV_FWD'
    assert command['left'] == 'FWD'


def test_sensor_projection_preserves_returned_coordinates_instead_of_stdout_clipping():
    class SensorBridge(Bridge):
        def call_tool(self, name, arguments):
            if name != 'depth_points':
                return super().call_tool(name, arguments)
            self.calls.append((name, deepcopy(arguments)))
            identity = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
            calibration = dict(available=True, frame_id='native-0', camera='head', units='m',
                convention='opengl', width=640, height=480, K=[[100,0,0],[0,100,0],[0,0,1]],
                T_task_from_camera=identity, T_world_from_camera=identity)
            point = dict(valid=True, estimated=False, physical_action=False, units='m', frame_id='native-0',
                camera='head', pixel=[1,2], pixel_order='row_col', pixel_space='native_image',
                width=640, height=480, depth_m=1., camera_calibration=calibration,
                measurement_source='simulator_depth', method='simulator_axial_depth',
                sensor_source='isaac_camera_distance_to_image_plane', depth_convention='optical_axis_m',
                target_frame='world', private_target_pose='PRIVATE_POSE')
            payload = dict(native_frame_id='native-0', measurements=[point])
            return ToolResult(name, [dict(type='input_text', text=json.dumps(payload))], [], payload)
    bridge = SensorBridge(); e = executor(bridge); e.initialize()
    result = e.readonly([dict(type='depth_points', camera='head', pixels=[[1,2]])], decision_id='project')
    point = result['results'][0]['measurements'][0]
    assert point['xyz_task_m'] == pytest.approx([.02,-.01,-1.])
    assert point['xyz_world_m'] == pytest.approx([.02,-.01,-1.])
    assert 'PRIVATE_POSE' not in json.dumps(result) and result['physical_commits'] == 0


class VideoBridge(Bridge):
    def call_tool(self, name, arguments):
        if name not in ('demo_info', 'demo_frames'):
            return super().call_tool(name, arguments)
        self.calls.append((name, deepcopy(arguments)))
        if name == 'demo_info':
            payload = dict(available=True, duration_seconds=7.3, fps=30,
                           private_expert_path='PRIVATE_EXPERT')
            return ToolResult(name, [dict(type='input_text', text=json.dumps(payload))], [], payload)
        times = sorted(arguments['seconds'])
        images = [dict(type='input_image', image_url='data:image/png;base64,' +
                       base64.b64encode(('original-demo-' + str(t)).encode()).decode()) for t in times]
        return ToolResult(name, [], images, {}, image_sources=[dict(kind='demo', demo_seconds=t) for t in times])


def video_executor(tmp_path, bridge, **options):
    video = tmp_path / 'assigned.mp4'; video.write_bytes(b'original-assigned-video')
    return TurnExecutor(dict(condition='real', demo_video=str(video)), bridge=bridge, **options)


def test_video_default_is_metadata_only_until_the_model_requests_frames(tmp_path):
    bridge = VideoBridge(); e = video_executor(tmp_path, bridge)
    initial = e.initialize()
    assert initial['demo_anchors'] == [] and initial['demo_info']['duration_seconds'] == 7.3
    assert [name for name, _ in bridge.calls] == ['observe', 'demo_info']
    result = e.readonly([dict(type='demo_frames', seconds=[.5, 5])], decision_id='model-chooses-when')
    assert len(result['demo_frames']) == 2 and bridge.steps == 0
    assert [name for name, _ in bridge.calls] == ['observe', 'demo_info', 'demo_frames']


def test_assigned_demo_can_be_revisited_between_physical_decisions_without_moving(tmp_path):
    bridge = VideoBridge(); e = video_executor(tmp_path, bridge, demo_frame_count=6)
    initial = e.initialize()
    assert len(initial['demo_anchors']) == 6 and initial['demo_info']['on_demand']
    assert 'PRIVATE_EXPERT' not in json.dumps(initial)
    e.execute([action()], decision_id='commit-before-revisit')
    before = deepcopy(e.observation)
    result = e.readonly([dict(type='demo_frames', seconds=[6.8, .15, 3.25])], decision_id='revisit')
    assert result['physical_commits'] == 0 and bridge.steps == 1
    assert result['observation'] == before and e.observation == before
    assert [a['seconds'] for a in result['demo_frames']] == [.15, 3.25, 6.8]
    assert {a['source_sha256'] for a in result['demo_frames']} == {initial['demo_info']['source_sha256']}
    assert [n for n, _ in bridge.calls] == ['observe', 'demo_info', 'demo_frames', 'act', 'demo_frames']
    e.execute([action()], decision_id='commit-after-revisit')
    assert bridge.steps == 2


@pytest.mark.parametrize('seconds', [[], [-.1], [7.3], [float('nan')], [True], [0]*13])
def test_demo_revisit_invalid_timestamps_never_reach_tools(tmp_path, seconds):
    bridge = VideoBridge(); e = video_executor(tmp_path, bridge); e.initialize()
    count = len(bridge.calls)
    with pytest.raises(ValueError):
        e.execute([dict(type='demo_frames', seconds=seconds)], decision_id='bad-demo')
    assert len(bridge.calls) == count and bridge.steps == 0


def test_text_condition_cannot_retrieve_a_demo():
    bridge = Bridge(); e = executor(bridge); e.initialize()
    with pytest.raises(ValueError, match='Only video conditions'):
        e.execute([dict(type='demo_frames', seconds=[0])], decision_id='no-demo')
    assert [name for name, _ in bridge.calls] == ['observe']


def test_demo_revisit_refuses_source_substitution_without_touching_the_world(tmp_path):
    bridge = VideoBridge(); e = video_executor(tmp_path, bridge); e.initialize()
    (tmp_path / 'assigned.mp4').write_bytes(b'substituted-video')
    count = len(bridge.calls)
    with pytest.raises(ValueError, match='source changed'):
        e.execute([dict(type='demo_frames', seconds=[1])], decision_id='wrong-source')
    assert len(bridge.calls) == count and bridge.steps == 0


from test_embodied_gui_mcp import gui_controller, chrome_path, IDENTITY


def test_actual_chrome_and_original_video_decoder_can_seek_between_commits(
        tmp_path, gui_controller, chrome_path):
    import hashlib
    import subprocess
    import imageio_ffmpeg
    video = tmp_path / 'assigned.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi',
        '-i', 'testsrc=size=320x240:rate=10', '-t', '1.2', '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True, timeout=20)
    source_sha = hashlib.sha256(video.read_bytes()).hexdigest()
    gui_controller.update(condition='real', demo_bytes=video.read_bytes())
    computer = dict(control_url=gui_controller['url'], actor_token='actor-test',
        run_id=IDENTITY['run_id'], program_episode_identity=dict(IDENTITY),
        output_dir=str(tmp_path / 'gui'), condition='real', demo_video=str(video),
        embodied_harness='program_gui', max_actions=6, max_gui_inputs=120,
        timeout_seconds=90, browser_path=chrome_path,
        gui_observation_timeout_ms=3000, gui_settle_timeout_ms=3000)
    bridge = GUIBridge(computer)
    try:
        e = TurnExecutor(computer, bridge=bridge)
        initial = e.initialize()
        assert initial['demo_info']['source_sha256'] == source_sha
        e.execute([action()], decision_id='first-commit')
        before = deepcopy(e.observation)
        result = e.readonly([dict(type='demo_frames', seconds=[.9, .1, .5])], decision_id='seek-anytime')
        assert result['physical_commits'] == 0 and result['observation'] == before
        assert [a['seconds'] for a in result['demo_frames']] == [.1, .5, .9]
        assert len({a['sha256'] for a in result['demo_frames']}) == 3
        assert {a['source_sha256'] for a in result['demo_frames']} == {source_sha}
        assert gui_controller['steps'] == 1
        e.execute([action()], decision_id='second-commit')
        assert gui_controller['steps'] == 2
        assert len([c for c in gui_controller['calls'] if c[1] == '/api/action']) == 2
    finally:
        bridge.close()


def test_actual_portal_chrome_multiple_control_edits_use_one_original_commit(
        tmp_path, gui_controller, chrome_path):
    gui_controller['condition'] = 'text_rule'
    computer = dict(control_url=gui_controller['url'], actor_token='actor-test',
        run_id=IDENTITY['run_id'], program_episode_identity=dict(IDENTITY),
        output_dir=str(tmp_path / 'gui'), condition='text_rule', embodied_harness='program_gui',
        max_actions=6, max_gui_inputs=120, timeout_seconds=90, browser_path=chrome_path,
        gui_observation_timeout_ms=3000, gui_settle_timeout_ms=3000)
    bridge = GUIBridge(computer)
    try:
        e = TurnExecutor(computer, bridge=bridge)
        initial = e.initialize()
        assert initial['observation']['step'] == 0
        command = dict(type='action', left='UP', right='FWD', step_mm=7.5, rotation_deg=12.5)
        inputs = bridge.public_action_inputs(command)
        assert len(inputs) == 9  # Both arm buttons, both parameter edits, and one final Commit.
        result = e.execute([command], decision_id='actual-single')
        assert result['physical_commits'] == gui_controller['steps'] == 1, {k:v for k,v in result.items()if k!='observation'}
        assert not result['uncertain']
        native = [row for row in gui_controller['calls'] if row[1] == '/api/action']
        assert len(native) == 1
        assert {k: native[0][3][k] for k in ('left', 'right', 'step_mm', 'rotation_deg')} == {
            'left': 'UP', 'right': 'FWD', 'step_mm': 7.5, 'rotation_deg': 12.5}
        assert result['observation']['frame_id'] != initial['observation']['frame_id']
        assert 'PRIVATE_' not in json.dumps(result) and 'actor-test' not in json.dumps(result)
    finally:
        bridge.close()


def test_actual_decision_runner_executor_chrome_one_commit_then_done_in_two_model_replies(
        tmp_path, gui_controller, chrome_path):
    from vic_sdk.robodawn_turn_runner import Runner
    from test_robodawn_turn_integration import FakeResponses, response, decision

    gui_controller['condition'] = 'text_rule'
    computer = dict(control_url=gui_controller['url'], actor_token='actor-test',
        run_id=IDENTITY['run_id'], program_episode_identity=dict(IDENTITY),
        output_dir=str(tmp_path / 'gui'), condition='text_rule', embodied_harness='program_gui',
        max_actions=6, max_gui_inputs=120, timeout_seconds=90, browser_path=chrome_path,
        gui_observation_timeout_ms=3000, gui_settle_timeout_ms=3000)
    path = tmp_path / 'computer.json'; path.write_text(json.dumps(computer))
    instruction = tmp_path / 'instruction.txt'; instruction.write_text('Synthetic local GUI regression only.')
    bridge = GUIBridge(computer)
    executor = TurnExecutor(computer, bridge=bridge)
    transport = FakeResponses([response(1, decision(1, [action()])),
                              response(2, decision(2, [dict(type='done', summary='Synthetic local regression complete')]))])
    runner = Runner(dict(protocol='decision_turn', profile=str(tmp_path / 'profile'),
        output_root=str(tmp_path / 'output'), computer_config=str(path), instruction_path=str(instruction),
        model='offline-mock', base_url='http://unused.invalid/v1', policy={}),
        executor=executor, transport=transport, emit=lambda _: None)
    try:
        state = runner.run(max_decisions=2)
        assert state['terminal'] and state['physical_commits'] == gui_controller['steps'] == 1, state.get('diagnostic')
        assert state['decisions'] == state['successes'] == 2 and len(transport.bodies) == 2
        assert runner.context.build().physical_turn_count == 1
        assert 'memory-1' in json.dumps(transport.bodies[1]['input'])
        assert [tool['name'] for tool in transport.bodies[0]['tools']] == ['robot_turn']
        assert not any('PRIVATE_' in json.dumps(body) or 'actor-test' in json.dumps(body) for body in transport.bodies)
    finally:
        runner.close()
        bridge.close()


def test_actual_final_commit_uses_remaining_budget_without_more_model_calls(
        tmp_path, gui_controller, chrome_path):
    from vic_sdk.robodawn_turn_runner import Runner
    from test_robodawn_turn_integration import FakeResponses, response, decision
    gui_controller.update(condition='text_rule', max_actions=1)
    computer = dict(control_url=gui_controller['url'], actor_token='actor-test',
        run_id=IDENTITY['run_id'], program_episode_identity=dict(IDENTITY),
        output_dir=str(tmp_path / 'gui'), condition='text_rule', embodied_harness='program_gui',
        max_actions=1, max_gui_inputs=20, timeout_seconds=90, browser_path=chrome_path,
        gui_observation_timeout_ms=3000, gui_settle_timeout_ms=3000)
    path = tmp_path / 'computer.json'; path.write_text(json.dumps(computer))
    instruction = tmp_path / 'instruction.txt'; instruction.write_text('Local budget boundary regression.')
    bridge = GUIBridge(computer)
    transport = FakeResponses([response(1, decision(1, [action()]))])
    runner = Runner(dict(protocol='decision_turn', profile=str(tmp_path / 'profile'),
        output_root=str(tmp_path / 'output'), computer_config=str(path), instruction_path=str(instruction),
        model='offline-mock', base_url='http://unused.invalid/v1', policy={}),
        executor=TurnExecutor(computer, bridge=bridge), transport=transport, emit=lambda _: None)
    try:
        state = runner.run(max_decisions=2)
        assert state['terminal'] and state['physical_commits'] == gui_controller['steps'] == 1, state.get('diagnostic')
        assert len(transport.bodies) == 1 and state['last_observation']['episode_status'] == 'budget_exhausted'
        assert not [row for row in gui_controller['calls'] if row[1] in ('/api/done', '/api/giveup')]
    finally:
        runner.close(); bridge.close()


class QueueBridge(Bridge):
    def __init__(self):
        super().__init__();self.queue=[];self.visible_id=None;self.selected=None
        self.commit_clicks=0;self.adds=0;self.batch_metadata=None;self.fail_queue_at=None
        self.completed_override=None;self.batch_status='completed';self.bad_batch_id=False
    def public_action_inputs(self,command):
        self.macros.append(deepcopy(command));self.selected=deepcopy(command)
        return [dict(kind='click',x=10,y=20),dict(kind='click',x=90,y=90,visible_op='commit')]
    def public_queue_inputs(self,operation,*,batch_id=None):
        return [dict(kind='click',x=30,y=40,visible_op=operation,batch_id=batch_id)]
    def observation(self,status='running'):
        result=super().observation(status)
        if self.batch_metadata is not None:
            payload=json.loads(result.text_blocks[0]['text']);payload['action_batch']=deepcopy(self.batch_metadata)
            result=ToolResult('observe',[dict(type='input_text',text=json.dumps(payload))],result.images,payload,
                image_sources=[dict(kind='gui')])
        return result
    def call_tool(self,name,arguments):
        if name!='act':return super().call_tool(name,arguments)
        self.calls.append((name,deepcopy(arguments)))
        assert arguments['frame_id']=='gui-'+str(self.steps)
        for item in arguments['inputs']:
            op=item.get('visible_op')
            if op=='clear':self.queue=[];self.visible_id=None
            elif op=='id':self.visible_id=item['batch_id']
            elif op=='add':
                self.queue.append(deepcopy(self.selected));self.adds+=1
                if self.fail_queue_at==self.adds:
                    return ToolResult('act',[dict(type='input_text',text='GUI transport failed; queue outcome unknown')],[],{},True)
            elif op=='commit':
                self.commit_clicks+=1
                count=len(self.queue)if self.completed_override is None else self.completed_override
                before=self.steps;self.steps+=count
                self.batch_metadata=dict(batch_id='wrong-id'if self.bad_batch_id else self.visible_id,
                    requested_count=len(self.queue),completed_count=count,physical_action_count=count,
                    accepted=True,status=self.batch_status,next_index=count,
                    receipts=[dict(index=i,status='completed',step=before+i+1)for i in range(count)])
        return self.observation()


def batch(*pairs):
    return dict(type='action_batch',actions=[{k:v for k,v in pair.items()if k!='type'}for pair in pairs])


def test_public_ordered_queue_three_pairs_produces_one_commit_and_three_physical_actions():
    bridge=QueueBridge();events=[]
    e=executor(bridge,on_intent=lambda r:events.append(('intent',len(bridge.calls))),
        on_receipt=lambda r:events.append(('receipt',len(bridge.calls))))
    e.initialize();command=batch(action(),dict(type='action',left='STILL',right='MV_FWD',step_mm=10,rotation_deg=5),action())
    result=e.execute([command],decision_id='batch-decision')
    assert result['physical_commits']==bridge.commit_clicks==1
    assert result['physical_action_count']==bridge.steps==3
    assert bridge.adds==3 and result['observation']['step']==3 and not result['uncertain']
    assert [p['left']for p in bridge.queue]==[p['left']for p in command['actions']]
    assert all(len(args['inputs'])<=12 for name,args in bridge.calls if name=='act')
    assert events[0]==('intent',1)and events[-1][0]=='receipt'
    assert result['results'][0]['receipt']['requested_count']==3
    with pytest.raises(ValueError,match='one-shot'):e.execute([command],decision_id='batch-decision')
    assert bridge.commit_clicks==1


@pytest.mark.parametrize('count',[0,25])
def test_queue_batch_limits_rejected_before_any_visible_queue_edit(count):
    bridge=QueueBridge();e=executor(bridge);e.initialize()
    with pytest.raises(ValueError):e.execute([batch(*[action()for _ in range(count)])],decision_id='invalid')
    assert len(bridge.calls)==1 and bridge.commit_clicks==0 and bridge.adds==0


def test_batch_public_validation_checks_every_pair_before_queue_mutation():
    bridge=QueueBridge();e=executor(bridge);e.initialize()
    bad=dict(type='action',left='RESET',right='STILL',step_mm=10,rotation_deg=10)
    with pytest.raises(ValueError):e.execute([batch(action(),bad)],decision_id='bad-token')
    assert not bridge.macros and bridge.commit_clicks==0 and len(bridge.calls)==1


def test_queue_edit_interruption_never_commits_or_replays_the_decision():
    bridge=QueueBridge();bridge.fail_queue_at=2;e=executor(bridge);e.initialize()
    command=batch(action(),action(),action());result=e.execute([command],decision_id='queue-interrupted')
    assert result['uncertain']and result['physical_commits']==result['physical_action_count']==0
    assert bridge.commit_clicks==0 and bridge.adds==2
    with pytest.raises(ValueError):e.execute([command],decision_id='queue-interrupted')
    assert bridge.adds==2


def test_partial_batch_preserves_completed_pair_count_and_never_replays_prefix():
    bridge=QueueBridge();bridge.completed_override=2;bridge.batch_status='partial'
    e=executor(bridge);e.initialize();command=batch(action(),action(),action())
    result=e.execute([command],decision_id='partial')
    assert result['physical_commits']==1 and result['physical_action_count']==2
    assert result['uncertain']and result['results'][0]['partial']is True
    assert result['observation']['step']==2 and bridge.commit_clicks==1
    with pytest.raises(ValueError):e.execute([command],decision_id='partial')
    assert bridge.commit_clicks==1 and bridge.steps==2


def test_batch_receipt_identity_mismatch_does_not_manufacture_completed_count():
    bridge=QueueBridge();bridge.bad_batch_id=True;e=executor(bridge);e.initialize()
    result=e.execute([batch(action(),action())],decision_id='bad-ack')
    assert result['uncertain']and result['physical_action_count']==0
    assert bridge.steps==2 and bridge.commit_clicks==1
    assert 'identity'in result['results'][0]['error']


def test_public_batch_metadata_filters_private_native_results():
    from vic_sdk.embodied_gui_mcp import public_action_batch_metadata
    raw=dict(batch_id='b1',status='completed',requested_count=2,completed_count=2,physical_action_count=2,
        next_index=2,accepted=True,commands_sha256='a'*64,score=100,private_native_state='SECRET',
        receipts=[dict(index=0,status='completed',step=1,receipt={'hidden_pose':[9,9,9]},score=100)])
    shown=public_action_batch_metadata(raw)
    assert shown['physical_action_count']==2 and shown['receipts']==[dict(index=0,status='completed',step=1)]
    assert 'SECRET'not in json.dumps(shown)and 'score'not in json.dumps(shown)and 'hidden_pose'not in json.dumps(shown)


def test_batch_larger_than_visible_remaining_budget_is_rejected_before_any_queue_mutation():
    bridge=QueueBridge();e=executor(bridge);e.initialize();e.observation['max_robot_actions']=1
    with pytest.raises(ValueError,match='remaining'):
        e.execute([batch(action(),action())],decision_id='oversized')
    assert len(bridge.calls)==1 and not bridge.macros and bridge.commit_clicks==0


def test_known_terminal_cutoff_accepts_only_confirmed_prefix_and_no_uncertain_next_pair():
    class TerminalQueue(QueueBridge):
        def observation(self,status='running'):
            return super().observation('budget_exhausted'if self.commit_clicks else status)
    bridge=TerminalQueue();bridge.completed_override=2;bridge.batch_status='partial'
    e=executor(bridge);e.initialize();result=e.execute([batch(action(),action(),action())],decision_id='budget-cutoff')
    assert result['terminal']and not result['uncertain']and result['physical_commits']==1
    assert result['physical_action_count']==2 and result['results'][0]['ok']is True
    assert result['results'][0]['known_public_terminal_cutoff']is True
