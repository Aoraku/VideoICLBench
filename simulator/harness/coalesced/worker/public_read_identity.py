"""Give each explicit information-tool invocation its own executor identity.

The frozen SDK derives read IDs from the number of successful public events.
An information error consumes that ID without appending an event, so the next
corrected read is rejected as a replay. Physical operation IDs remain untouched.
There is no automatic retry and no change to the requested frames or pixels.
"""
import functools
import uuid


def install(native_tools, make_server):
    class IndependentReadIdentity(native_tools):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            executor = self.executor
            if getattr(executor, '_vic_independent_public_reads', False):
                return
            original = executor.execute

            @functools.wraps(original)
            def execute(commands, *, decision_id):
                if (isinstance(decision_id, str) and decision_id.startswith('native-read-')
                        and isinstance(commands, list) and len(commands) == 1
                        and isinstance(commands[0], dict)
                        and commands[0].get('type') in ('demo_frames', 'depth_points')):
                    decision_id = 'native-read-' + uuid.uuid4().hex
                return original(commands, decision_id=decision_id)

            executor.execute = execute
            executor._vic_independent_public_reads = True

    return IndependentReadIdentity, make_server
