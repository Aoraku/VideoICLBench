"""Independent decision-turn acceptance: no sockets/model/simulator/browser.

Mock success checks protocol and persistence only, never real model quality,
physical feasibility, or a provider's actual cache hit rate.
"""
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from vic_sdk.robodawn_turn_context import TurnContext, TurnPolicy
from vic_sdk.robodawn_runner import ProviderFailure


def image(label):
    raw = ('synthetic-frame-' + label).encode()
    return {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(raw).decode(),
            'detail': 'high'}, hashlib.sha256(raw).hexdigest()


def observation(index, status='running', step=0):
    picture, digest = image('gui-' + str(index))
    return {'frame_id': 'gui-' + str(index), 'image': picture, 'image_sha256': digest,
            'width': 1440, 'height': 1280, 'camera_views': {}, 'episode_status': status,
            'step': step, 'max_robot_actions': 500,
            'public_observation': {'native_frame_id': 'native-' + str(index),
                                   'robot_feedback': {'observation_tick': index}}}


def decision(index, commands=None):
    return {'scene': 'Only visible synthetic geometry.', 'progress': 'Reviewing the last public receipt.',
            'memory': 'memory-' + str(index), 'plan': 'Inspect then choose the next public action.',
            'commands': commands if commands is not None else [
                {'type': 'depth_points', 'camera': 'head', 'pixels': [[179, 416], [250, 422], [331, 430], [244, 269]]}]}


def response(index, value):
    return {'id': 'response-' + str(index), 'status': 'completed',
            'output': [{'type': 'function_call', 'name': 'robot_turn', 'call_id': 'turn-' + str(index),
                        'arguments': json.dumps(value)}],
            'usage': {'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 80},
                      'output_tokens': 33, 'output_tokens_details': {'reasoning_tokens': 0}}}


class FakeResponses:
    def __init__(self, replies):
        self.replies = list(replies)
        self.bodies = []
    def complete(self, body):
        self.bodies.append(deepcopy(body))
        if not self.replies:
            raise AssertionError('Unexpected extra model request')
        answer = self.replies.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer, {}
    def close(self):
        pass


class FakeExecutor:
    def __init__(self, anchors=(), *, report_flags=()):
        self.anchors = deepcopy(list(anchors))
        self.calls = []
        self.flags = list(report_flags)
        self.on_intent = None
        self.on_receipt = None
        self.initialized = 0
        self.steps = 0
    def initialize(self):
        self.initialized += 1
        result = {'observation': observation(0), 'demo_anchors': deepcopy(self.anchors)}
        if self.anchors:
            first = self.anchors[0]
            source = first['source_sha256'] if isinstance(first, dict) else first.source_sha256
            result['demo_info'] = {'available': True, 'source_sha256': source,
                'duration_seconds': 12.0, 'fps': 24.0, 'frame_count': 288, 'on_demand': True}
        else:
            result['demo_info'] = {'available': False}
        return result
    def execute(self, commands, *, decision_id):
        self.calls.append((deepcopy(commands), decision_id))
        flags = self.flags.pop(0) if self.flags else {}
        physical = flags.get('physical_commits', sum(c.get('type') == 'action' for c in commands))
        self.steps += physical
        terminal = commands[0].get('type') in ('done', 'giveup')
        status = 'done' if terminal and commands[0]['type'] == 'done' else 'give_up' if terminal else 'running'
        return {'results': [{'command': deepcopy(command), 'ok': True,
                             'physical_commit': physical > 0 and command.get('type') == 'action',
                             'receipt': {'public_only': True}} for command in commands],
                'observation': observation(len(self.calls), status, self.steps), 'physical_commits': physical,
                'pending': flags.get('pending', False), 'uncertain': flags.get('uncertain', False),
                'terminal': terminal, 'step': self.steps, 'tcp': observation(len(self.calls), status, self.steps)}
    def close(self):
        pass


def make_runner(tmp_path, replies, *, executor=None, policy=None, real=False, config_extra=None):
    from vic_sdk.robodawn_turn_runner import Runner
    tmp_path.mkdir(parents=True, exist_ok=True)
    instruction = tmp_path / 'instruction.txt'; instruction.write_text('Original fixed task rule.')
    computer = {'run_id': 'new-turn-test', 'condition': 'real' if real else 'text_rule',
                'program_episode_identity': {'run_id': 'new-turn-test', 'task_id': 'E22', 'variant': 'C',
                    'seed': 4201, 'suite': 'embodied', 'epoch': 'offline-turn'},
                'output_dir': str(tmp_path / 'gui'), 'max_actions': 500, 'timeout_seconds': 0}
    if real:
        video = tmp_path / 'real.mp4'; video.write_bytes(b'fixed original assigned video')
        computer['demo_video'] = str(video)
    config_file = tmp_path / 'computer.json'; config_file.write_text(json.dumps(computer))
    transport = FakeResponses(replies)
    config = {'protocol': 'decision_turn', 'profile': str(tmp_path / 'profile'),
        'output_root': str(tmp_path / 'output'), 'computer_config': str(config_file),
        'instruction_path': str(instruction), 'model': 'offline-model',
        'base_url': 'http://unused.invalid/v1', 'policy': policy or {}}
    config.update(config_extra or {})
    runner = Runner(config,
        executor=executor or FakeExecutor(), transport=transport, sleep=lambda _: None, emit=lambda _: None)
    return runner, transport


def test_e22_120_readonly_replies_pause_before_fourth_paid_decision(tmp_path):
    executor = FakeExecutor()
    runner, transport = make_runner(tmp_path, [response(i, decision(i)) for i in range(1, 121)],
        executor=executor, config_extra={'information_guard': {'mode': 'strict3'}})
    state = runner.run(max_decisions=120)
    assert len(transport.bodies) == len(executor.calls) == 3
    assert state.get('phase') == 'paused' or state.get('paused') is True
    assert not state.get('terminal')
    build = runner.context.build()
    assert build.physical_turn_count == 0 and build.readonly_count == 3
    assert state['usage']['input_tokens'] == 300 and state['usage']['output_tokens'] == 99
    assert state['usage']['cached_input_tokens'] == 240
    persisted = (tmp_path / 'profile' / 'decision-turn-state.private.json').read_text()
    assert 'memory-3' in persisted and 'memory-4' not in persisted


def test_real_commit_resets_readonly_streak_and_each_turn_persists_memory(tmp_path):
    action = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 10, 'rotation_deg': 5}]
    values = [decision(1), decision(2), decision(3, action), decision(4), decision(5), decision(6)]
    executor = FakeExecutor()
    runner, transport = make_runner(tmp_path, [response(i, v) for i, v in enumerate(values, 1)],
        executor=executor, config_extra={'information_guard': {'mode': 'strict3'}})
    state = runner.run(max_decisions=120)
    assert len(transport.bodies) == len(executor.calls) == 6
    assert runner.context.build().physical_turn_count == 1
    assert state.get('phase') == 'paused' or state.get('paused') is True
    assert 'memory-6' in (tmp_path / 'profile' / 'decision-turn-state.private.json').read_text()
    assert state['usage']['input_tokens'] == 600


def test_physical_classification_uses_commit_receipt_not_command_name(tmp_path):
    action = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 10, 'rotation_deg': 5}]
    executor = FakeExecutor(report_flags=[{'physical_commits': 0}] * 3)
    runner, transport = make_runner(tmp_path, [response(i, decision(i, action)) for i in range(1, 8)],
        executor=executor, config_extra={'information_guard': {'mode': 'strict3'}})
    state = runner.run(max_decisions=120)
    assert len(transport.bodies) == 3
    assert runner.context.build().physical_turn_count == 0
    assert not state.get('terminal')


@pytest.mark.parametrize('bad', [
    {'scene': 'missing other required fields'},
    {**decision(1), 'memory': ''},
    {**decision(1), 'memory': 'x' * 2501},
    {**decision(1), 'commands': decision(1)['commands'] * 5},
    {**decision(1), 'commands': 'not-an-array'},
])
def test_invalid_decision_cannot_reach_executor(tmp_path, bad):
    executor = FakeExecutor()
    runner, transport = make_runner(tmp_path, [response(1, bad)], executor=executor)
    try:
        state = runner.run(max_decisions=1)
    except (ValueError, RuntimeError):
        state = runner.state
    assert not executor.calls
    assert len(transport.bodies) == 1
    assert not state.get('terminal')


def test_one_dual_arm_action_is_one_commit_and_one_physical_history_turn(tmp_path):
    commands = [{'type': 'action', 'left': 'UP', 'right': 'GRASP', 'step_mm': 1, 'rotation_deg': 1}]
    runner, transport = make_runner(tmp_path, [response(1, decision(1, commands))])
    state = runner.run(max_decisions=1)
    assert len(runner.executor.calls) == len(transport.bodies) == 1
    assert len(runner.executor.calls[0][0]) == 1
    assert runner.executor.calls[0][0][0] == commands[0]
    assert runner.context.build().physical_turn_count == 1
    assert state['usage']['output_tokens'] == 33
    assert 'memory-1' in (tmp_path / 'profile' / 'decision-turn-state.private.json').read_text()


@pytest.mark.parametrize('count', [2, 4])
def test_multiple_physical_commands_are_rejected_before_gui(tmp_path, count):
    commands = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}] * count
    runner, transport = make_runner(tmp_path, [response(1, decision(1, commands))])
    state = runner.run(max_decisions=1)
    assert not runner.executor.calls
    assert len(transport.bodies) == 1
    assert state['phase'] == 'paused' and not state['terminal']
    assert runner.context.build().physical_turn_count == 0


def test_next_model_decision_has_automatic_latest_gui_and_no_free_tool_loop(tmp_path):
    actions = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
    runner, transport = make_runner(tmp_path, [response(1, decision(1, actions)),
        response(2, decision(2, [{'type': 'done', 'summary': 'Observed synthetic result.'}]))])
    state = runner.run(max_decisions=120)
    assert state['terminal'] and len(transport.bodies) == len(runner.executor.calls) == 2
    assert {tool['name'] for tool in transport.bodies[0]['tools']} == {'robot_turn'}
    first_picture = observation(0)['image']
    next_picture = observation(1)['image']
    second_images = [block for item in transport.bodies[1]['input'] for block in item.get('content', [])
                     if isinstance(block, dict) and block.get('type') == 'input_image']
    assert second_images == [next_picture] and first_picture not in second_images
    assert state['physical_commits'] == 1


def test_every_commit_new_frame_and_public_step_reach_next_model_request(tmp_path):
    action = [{'type': 'action', 'left': 'UP', 'right': 'GRASP', 'step_mm': 2, 'rotation_deg': 3}]
    runner, transport = make_runner(tmp_path, [response(1, decision(1, action)),
        response(2, decision(2, action)), response(3, decision(3, [{'type': 'done', 'summary': 'Synthetic only.'}]))])
    state = runner.run(max_decisions=120)
    assert state['terminal'] and state['physical_commits'] == 2
    assert len(runner.executor.calls) == len(transport.bodies) == 3
    for index, body in enumerate(transport.bodies):
        records = []
        for item in body['input']:
            for block in item.get('content', []):
                if isinstance(block, dict) and block.get('type') == 'input_text':
                    try:
                        value = json.loads(block['text'])
                    except ValueError:
                        continue
                    if isinstance(value, dict):
                        records.append(value)
        current = next(row for row in records if row.get('image_role') == 'current_gui')
        public = next(row for row in records if 'current_public_observation' in row)
        assert current['frame_id'] == 'gui-' + str(index)
        assert public['current_public_observation']['native_frame_id'] == 'native-' + str(index)
        assert public['current_public_gui_state']['step'] == index
        assert public['current_public_gui_state']['max_robot_actions'] == 500
        images = [block for item in body['input'] for block in item.get('content', [])
                  if isinstance(block, dict) and block.get('type') == 'input_image']
        assert images == [observation(index)['image']]


@pytest.mark.parametrize('flag', ['uncertain', 'pending'])
def test_uncertain_accepted_command_pauses_without_replaying_or_new_model_request(tmp_path, flag):
    commands = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
    executor = FakeExecutor(report_flags=[{'physical_commits': 1, flag: True}])
    runner, transport = make_runner(tmp_path, [response(1, decision(1, commands))], executor=executor)
    state = runner.run(max_decisions=120)
    assert len(executor.calls) == len(transport.bodies) == 1
    assert state.get('phase') == 'paused' or state.get('paused') is True
    assert not state.get('terminal')


def test_fixed_demo_prefix_memory_and_no_cross_episode_oracle(tmp_path):
    picture, digest = image('assigned-demo')
    source_sha = hashlib.sha256(b'fixed original assigned video').hexdigest()
    anchor = {'image_item': picture, 'sha256': digest, 'seconds': 1.5, 'source_sha256': source_sha, 'kind': 'demo'}
    executor = FakeExecutor([anchor])
    runner, transport = make_runner(tmp_path, [response(i, decision(i)) for i in range(1, 4)],
        executor=executor, real=True, config_extra={'information_guard': {'mode': 'strict3'}})
    runner.initialize()
    before = runner.context.build().static_prefix_hash
    runner.initialize = lambda: None
    runner.run(max_decisions=120)
    assert runner.context.build().static_prefix_hash == before
    assert executor.initialized == 1
    for body in transport.bodies:
        assert 'PRIVATE_OBJECT_POSE' not in json.dumps(body)
        images = [block for item in body['input'] for block in item.get('content', [])
                  if isinstance(block, dict) and block.get('type') == 'input_image']
        assert picture in images
        assert all(block.get('detail') == 'high' for block in images)
    assert 'memory-3' in (tmp_path / 'profile' / 'decision-turn-state.private.json').read_text()


def test_explicit_cache_boundary_requires_declared_provider_capability(tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        policy = TurnPolicy(cache_breakpoint_enabled=True, provider_cache_breakpoint_capability=False)
        context = TurnContext({'episode_id': 'local'}, 'fixed', 'developer', [], archive_dir=tmp_path, policy=policy)
        picture, digest = image('gui')
        from vic_sdk.robodawn_context import ImageAnchor
        context.set_current_gui(ImageAnchor(picture, digest, 2800, 'gui', frame_id='f'))
        context.build()


def test_unverified_explicit_cache_cannot_silently_downgrade_to_implicit(tmp_path):
    executor = FakeExecutor()
    with pytest.raises(ValueError, match='wire format|verified|wire protocol'):
        make_runner(tmp_path, [], executor=executor,
            policy={'cache_breakpoint_enabled': True, 'provider_cache_breakpoint_capability': True})
    assert not executor.calls and executor.initialized == 0


def standalone_context(tmp_path, *, cache_enabled=False, episode_id='new-local-episode'):
    from vic_sdk.robodawn_context import ImageAnchor
    policy = TurnPolicy(cache_breakpoint_enabled=cache_enabled,
                        provider_cache_breakpoint_capability=cache_enabled)
    context = TurnContext({'episode_id': episode_id}, 'ORIGINAL ASSIGNED RULE',
                          'Fixed developer contract', [], archive_dir=tmp_path, policy=policy)
    picture, digest = image('gui-initial')
    context.set_current_gui(ImageAnchor(picture, digest, 2800, 'gui', frame_id='gui-initial'),
                            public_observation=observation(0))
    return context


def test_declared_cache_boundary_metadata_is_stable_and_not_a_real_cache_hit_claim(tmp_path):
    context = standalone_context(tmp_path, cache_enabled=True)
    initial = context.build()
    context.record_decision(decision(1), [{'ok': True, 'physical_commit': True}],
                            physical=True, decision_id='physical-1')
    after = context.build()
    assert after.static_prefix_hash == initial.static_prefix_hash
    assert after.cache_breakpoint['enabled'] is True
    assert after.cache_breakpoint['provider_capability_declared'] is True
    assert after.cache_breakpoint['empirically_validated'] is False
    # Only the transport can mark whether this candidate is placed on the wire.
    assert after.cache_breakpoint['applied_to_wire'] is False
    boundary = after.cache_breakpoint['boundary_message_index']
    assert initial.items[:boundary + 1] == after.items[:boundary + 1]


def test_fixed_demo_input_change_after_first_build_is_refused(tmp_path):
    from vic_sdk.robodawn_context import ImageAnchor
    context = standalone_context(tmp_path)
    picture, digest = image('fixed-video-frame')
    source = hashlib.sha256(b'original-assigned-demo').hexdigest()
    context.set_demo_info({'available': True, 'source_sha256': source,
                           'duration_seconds': 12, 'on_demand': True})
    context.set_demo_anchors([ImageAnchor(picture, digest, 2800, 'demo', source_sha256=source, seconds=1.5)])
    before = context.build()
    replacement, replacement_sha = image('a-different-video-frame')
    with pytest.raises(ValueError, match='Fixed demo|fixed demo|cannot change'):
        context.set_demo_anchors([ImageAnchor(replacement, replacement_sha, 2800, 'demo',
                                             source_sha256=source, seconds=1.5)])
    assert context.build().static_prefix_hash == before.static_prefix_hash


def test_physical_history_12_turns_readonly_queue_separate_unknown_never_evicted(tmp_path):
    context = standalone_context(tmp_path)
    initial = context.build().static_prefix_hash
    for n in range(1, 16):
        commands = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
        context.record_decision(decision(n, commands), [{'ok': True, 'physical_commit': True}],
                                physical=True, decision_id='physical-' + str(n))
        context.record_decision(decision(100 + n), [{'ok': True, 'physical_commit': False}],
                                physical=False, decision_id='readonly-' + str(n))
    context.record_decision(decision(999, commands), [{'ok': False, 'physical_commit': True}],
                            physical=True, decision_id='unknown-accepted', state='unknown')
    built = context.build()
    assert built.physical_turn_count == 12 and built.readonly_count == 4
    assert built.protected_decision_ids == ['unknown-accepted']
    assert built.static_prefix_hash == initial
    assert context.memory == 'memory-999'


def test_same_video_frame_bytes_at_different_timestamps_keep_the_demo_timeline(tmp_path):
    from vic_sdk.robodawn_context import ImageAnchor
    context = standalone_context(tmp_path)
    picture, digest = image('unchanged-pose-in-assigned-video')
    source = hashlib.sha256(b'original-assigned-demo').hexdigest()
    context.set_demo_info({'available': True, 'source_sha256': source,
                           'duration_seconds': 12, 'on_demand': True})
    context.set_demo_anchors([ImageAnchor(picture, digest, 2800, 'demo', source_sha256=source, seconds=t)
                              for t in (1.5, 4.5)])
    built = context.build()
    demos = [item for item in built.items if any(block.get('type') == 'input_image'
             and block.get('image_url') == picture['image_url'] for block in item.get('content', []))]
    assert len(demos) == 2


def test_retry_preserves_exact_decision_request_and_never_executes_before_success(tmp_path):
    commands = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
    runner, transport = make_runner(tmp_path, [ProviderFailure('temporary failure', 503, 'temporary'),
                                              response(1, decision(1, commands))])
    state = runner.run(max_decisions=1)
    assert len(transport.bodies) == 2 and transport.bodies[0] == transport.bodies[1]
    assert len(runner.executor.calls) == 1
    assert state['usage']['input_tokens'] == 100 and state['usage']['output_tokens'] == 33
    assert state['failures'] == 1 and state['successes'] == 1


def test_single_commit_policy_refuses_legacy_four_command_configuration_before_api(tmp_path):
    executor = FakeExecutor()
    with pytest.raises(ValueError):
        make_runner(tmp_path, [], executor=executor, policy={'max_commands': 4})
    assert not executor.calls and executor.initialized == 0


def test_declared_explicit_cache_applies_wire_marker_without_mutating_fixed_materials(tmp_path):
    policy = {'cache_breakpoint_enabled': True, 'provider_cache_breakpoint_capability': True}
    runner, transport = make_runner(tmp_path, [response(i, decision(i)) for i in range(1, 4)],
        policy=policy, config_extra={'provider_cache_wire_protocol': 'openai_responses_explicit_v1',
                                    'information_guard': {'mode': 'strict3'}})
    state = runner.run(max_decisions=120)
    assert state['phase'] == 'paused' and len(transport.bodies) == 3
    context_build = runner.context.build()
    boundary = context_build.cache_breakpoint['boundary_message_index']
    content_index = context_build.cache_breakpoint['boundary_content_index']
    fixed_prefix = None
    for body in transport.bodies:
        assert body['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}
        block = body['input'][boundary]['content'][content_index]
        assert block['type'] == 'input_text'
        assert json.loads(block['text'])['static_materials_end'] is True
        assert block['prompt_cache_breakpoint'] == {'mode': 'explicit'}
        prefix = body['input'][:boundary + 1]
        assert fixed_prefix is None or prefix == fixed_prefix
        fixed_prefix = deepcopy(prefix)
        assert sum('prompt_cache_breakpoint' in b for item in body['input']
                   for b in item.get('content', []) if isinstance(b, dict)) == 1
    # Applying a wire marker must not rewrite the context's frozen original items.
    assert 'prompt_cache_breakpoint' not in context_build.items[boundary]['content'][content_index]
    assert context_build.cache_breakpoint['empirically_validated'] is False


def test_explicit_cache_rejection_pauses_with_no_unmarked_retry_or_model_switch(tmp_path):
    policy = {'cache_breakpoint_enabled': True, 'provider_cache_breakpoint_capability': True}
    runner, transport = make_runner(tmp_path,
        [ProviderFailure('cache breakpoint not supported by this provider', 400, 'unsupported_parameter')],
        policy=policy, config_extra={'provider_cache_wire_protocol': 'openai_responses_explicit_v1'})
    state = runner.run(max_decisions=120)
    assert state['phase'] == 'paused' and not state['terminal']
    assert len(transport.bodies) == 1 and not runner.executor.calls
    assert transport.bodies[0]['prompt_cache_options']['mode'] == 'explicit'
    assert transport.bodies[0]['model'] == 'offline-model'
    assert state['successes'] == 0 and state['failures'] == 1


def assigned_demo_anchor(seconds, *, source_sha=None):
    picture, digest = image('assigned-video-at-' + str(seconds))
    return {'image_item': picture, 'sha256': digest, 'seconds': seconds, 'kind': 'demo',
            'source_sha256': source_sha or hashlib.sha256(b'fixed original assigned video').hexdigest()}


class OnDemandDemoExecutor(FakeExecutor):
    def __init__(self, *, foreign_source=False):
        super().__init__([assigned_demo_anchor(t) for t in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)])
        self.current = observation(0)
        self.selected_batches = []
        self.foreign_source = foreign_source
    def execute(self, commands, *, decision_id):
        result = super().execute(commands, decision_id=decision_id)
        if commands[0]['type'] == 'demo_frames':
            selected = sorted(commands[0]['seconds'])
            self.selected_batches.append(selected)
            result['demo_frames'] = [assigned_demo_anchor(t,
                source_sha='a' * 64 if self.foreign_source else None) for t in selected]
            # Re-viewing the video does not advance or replace the live world.
            result['observation'] = deepcopy(self.current)
            result['step'] = self.steps
        else:
            self.current = deepcopy(result['observation'])
        return result


def image_metadata(body, role):
    found = []
    for item in body['input']:
        for block in item.get('content', []):
            if not isinstance(block, dict) or block.get('type') != 'input_text':
                continue
            try:
                data = json.loads(block['text'])
            except ValueError:
                continue
            if isinstance(data, dict) and data.get('image_role') == role:
                pictures = [b for b in item.get('content', []) if isinstance(b, dict) and b.get('type') == 'input_image']
                found.append((data, pictures))
    return found


def structured_texts(body):
    for item in body['input']:
        for block in item.get('content', []):
            if not isinstance(block, dict) or block.get('type') != 'input_text':
                continue
            try:
                value = json.loads(block['text'])
            except ValueError:
                continue
            if isinstance(value, dict):
                yield value


def test_demo_can_be_revisited_after_action_new_batch_replaces_old_not_fixed_prefix(tmp_path):
    first = [{'type': 'demo_frames', 'seconds': [5.25, 1.25]}]
    action = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 2, 'rotation_deg': 3}]
    second = [{'type': 'demo_frames', 'seconds': [8.75]}]
    values = [decision(1, first), decision(2, action), decision(3, second),
              decision(4, [{'type': 'done', 'summary': 'Synthetic task end.'}])]
    executor = OnDemandDemoExecutor()
    runner, transport = make_runner(tmp_path, [response(i, value) for i, value in enumerate(values, 1)],
                                    executor=executor, real=True)
    runner.initialize()
    original_prefix = runner.context.build().static_prefix_hash
    runner.initialize = lambda: None
    state = runner.run(max_decisions=120)
    assert state['terminal'] and len(transport.bodies) == 4
    assert state['physical_commits'] == runner.context.build().physical_turn_count == 1
    assert executor.selected_batches == [[1.25, 5.25], [8.75]]
    assert runner.context.build().static_prefix_hash == original_prefix
    source = hashlib.sha256(b'fixed original assigned video').hexdigest()
    info = next(row['assigned_demo_info'] for row in structured_texts(transport.bodies[0])
                if 'assigned_demo_info' in row)
    assert info['source_sha256'] == source and info['duration_seconds'] == 12
    assert info['fps'] == 24 and info['frame_count'] == 288 and info['on_demand'] is True
    assert 'demo_frames' in json.dumps(transport.bodies[0]['tools'])
    first_batch = image_metadata(transport.bodies[1], 'assigned_demo_revisit')
    last_batch = image_metadata(transport.bodies[3], 'assigned_demo_revisit')
    assert [meta['seconds'] for meta, _ in first_batch] == [1.25, 5.25]
    assert [meta['seconds'] for meta, _ in last_batch] == [8.75]
    assert all(meta['source_sha256'] == source for meta, _ in first_batch + last_batch)
    assert all(pictures == [assigned_demo_anchor(meta['seconds'])['image_item']] for meta, pictures in first_batch + last_batch)
    assert runner.context.build().demo_inspection_count == 1
    # The first re-view preserves GUI-0. After the Commit, the second re-view
    # preserves GUI-2, without misclassifying either screenshot as a video frame.
    assert image_metadata(transport.bodies[1], 'current_gui')[0][0]['frame_id'] == 'gui-0'
    assert image_metadata(transport.bodies[3], 'current_gui')[0][0]['frame_id'] == 'gui-2'
    assert all('gui-' not in str(meta.get('frame_id', '')) for meta, _ in last_batch)
    assert all(len(image_metadata(body, 'current_gui')) == 1 for body in transport.bodies)
    assert all(len(image_metadata(body, 'assigned_demo')) == 6 for body in transport.bodies)


def test_text_condition_has_no_demo_command_and_cannot_obtain_video(tmp_path):
    runner, transport = make_runner(tmp_path, [response(1, decision(1,
        [{'type': 'demo_frames', 'seconds': [1.0]}]))])
    state = runner.run(max_decisions=120)
    assert state['phase'] == 'paused' and not state['terminal']
    assert not runner.executor.calls and len(transport.bodies) == 1
    schema = json.dumps(transport.bodies[0]['tools'])
    assert 'demo_frames' not in schema
    assert not image_metadata(transport.bodies[0], 'assigned_demo')
    assert not image_metadata(transport.bodies[0], 'assigned_demo_revisit')


def test_demo_revisit_never_counts_as_commit_and_three_readonly_guard_still_applies(tmp_path):
    executor = OnDemandDemoExecutor()
    runner, transport = make_runner(tmp_path, [response(i, decision(i,
        [{'type': 'demo_frames', 'seconds': [i / 10]}])) for i in range(1, 121)], executor=executor,
        real=True, config_extra={'information_guard': {'mode': 'strict3'}})
    state = runner.run(max_decisions=120)
    assert state['phase'] == 'paused' and len(transport.bodies) == len(executor.calls) == 3
    assert state['physical_commits'] == runner.context.build().physical_turn_count == 0
    assert state['readonly_streak'] == 3
    assert runner.context.build().demo_inspection_count == 1


def test_foreign_video_sha_revisit_is_rejected_before_another_model_request(tmp_path):
    executor = OnDemandDemoExecutor(foreign_source=True)
    runner, transport = make_runner(tmp_path, [response(1, decision(1,
        [{'type': 'demo_frames', 'seconds': [1.0]}]))], executor=executor, real=True)
    state = runner.run(max_decisions=120)
    assert state['phase'] == 'paused' and not state['terminal']
    assert len(transport.bodies) == len(executor.calls) == 1
    assert state['physical_commits'] == 0


def test_early_public_history_can_be_inspected_after_window_eviction_without_replay(tmp_path):
    action = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
    values = [decision(i, action) for i in range(1, 15)]
    values += [decision(15, [{'type': 'history', 'start': 1, 'count': 1, 'include_images': True}]),
               decision(16, [{'type': 'history', 'start': 2, 'count': 1, 'include_images': True}]),
               decision(17, [{'type': 'done', 'summary': 'Synthetic task end.'}])]
    runner, transport = make_runner(tmp_path, [response(i, value) for i, value in enumerate(values, 1)])
    state = runner.run(max_decisions=120)
    assert state['terminal'] and state['physical_commits'] == 14
    assert len(transport.bodies) == 17
    assert len(runner.executor.calls) == 15  # Fourteen Commit calls plus done, no history calls.
    assert all(command['type'] != 'history' for commands, _ in runner.executor.calls for command in commands)
    assert runner.context.build().physical_turn_count == 12
    first = image_metadata(transport.bodies[15], 'episode_history')
    second = image_metadata(transport.bodies[16], 'episode_history')
    assert [meta['decision_number'] for meta, _ in first] == [1]
    assert [meta['frame_id'] for meta, _ in first] == ['gui-0']
    assert first[0][1] == [observation(0)['image']]
    assert [meta['decision_number'] for meta, _ in second] == [2]
    assert second[0][1] == [observation(1)['image']]
    assert len(first) == len(second) == 1
    for body in transport.bodies[15:17]:
        current = image_metadata(body, 'current_gui')
        assert len(current) == 1 and current[0][0]['frame_id'] == 'gui-14'
        assert current[0][1] == [observation(14)['image']]
    def checkpoint_image_urls(value):
        if isinstance(value, dict):
            if 'image_url' in value:
                yield value['image_url']
            for child in value.values():
                yield from checkpoint_image_urls(child)
        elif isinstance(value, list):
            for child in value:
                yield from checkpoint_image_urls(child)
    checkpoint_urls = list(checkpoint_image_urls(runner.context.export_state()))
    assert observation(0)['image']['image_url'] not in checkpoint_urls
    assert observation(1)['image']['image_url'] not in checkpoint_urls


def test_public_history_rejects_paths_future_pending_and_another_episode(tmp_path):
    context = standalone_context(tmp_path / 'episode-a', episode_id='episode-a')
    commands = [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 1, 'rotation_deg': 1}]
    context.record_decision(decision(1, commands), [{'ok': True, 'physical_commit': True,
        'receipt': {'score': 'NEVER_PRIVATE_SCORE', 'hidden_object_pose': 'NEVER_PRIVATE_OBJECT'}}],
        physical=True, decision_id='public-first')
    context.record_decision(decision(2, commands), [], physical=False,
                            decision_id='pending-not-completed', state='pending')
    assert context.inspect_history(1, 1, True)['ok'] is True
    body = json.dumps(context.build().items)
    assert 'NEVER_PRIVATE_SCORE' not in body and 'NEVER_PRIVATE_OBJECT' not in body
    for start, count, images in [('../episode-a', 1, False), (0, 1, False),
                                  (2, 1, False), (1, 6, False), (1, 3, True)]:
        with pytest.raises((ValueError, TypeError)):
            context.inspect_history(start, count, images)
    other = standalone_context(tmp_path / 'episode-b', episode_id='episode-b')
    with pytest.raises((ValueError, TypeError)):
        other.inspect_history(1, 1, True)
    with pytest.raises((ValueError, TypeError)):
        TurnContext.from_state(context.export_state(), archive_dir=tmp_path / 'episode-a',
                               expected_identity={'episode_id': 'episode-b'})


def test_information_guard_allows_demo_depth7_corrected_depth6_then_one_commit(tmp_path):
    values = [
        decision(1, [{'type': 'demo_frames', 'seconds': [1.0, 2.0, 3.0]}]),
        decision(2, [{'type': 'depth_points', 'camera': 'head',
                       'pixels': [[20 + i, 30 + i] for i in range(7)]}]),
        decision(3, [{'type': 'depth_points', 'camera': 'head',
                       'pixels': [[50 + i, 60 + i] for i in range(6)]}]),
        decision(4, [{'type': 'action', 'left': 'UP', 'right': 'STILL', 'step_mm': 2, 'rotation_deg': 3}]),
        decision(5, [{'type': 'done', 'summary': 'Synthetic task end.'}]),
    ]
    executor = OnDemandDemoExecutor()
    runner, transport = make_runner(tmp_path,
        [response(i, value) for i, value in enumerate(values, 1)], executor=executor, real=True,
        config_extra={'information_guard': {'mode': 'information_gain_v1'}})
    state = runner.run(max_decisions=120)
    assert state['terminal'] and not state['paused']
    assert len(transport.bodies) == len(executor.calls) == 5
    assert state['physical_commits'] == 1 and state['failures'] == 0
    assert state['usage']['input_tokens'] == 500 and state['usage']['output_tokens'] == 165
    assert [commands[0]['type'] for commands, _ in executor.calls] == [
        'demo_frames', 'depth_points', 'depth_points', 'action', 'done']
    assert len(executor.calls[1][0][0]['pixels']) == 7
    assert len(executor.calls[2][0][0]['pixels']) == 6
