"""Stop an E37 author after a completed action reveals robot/table contact."""
from contextlib import contextmanager
import json


@contextmanager
def guard_actions(policy, *, maximum_force_n=1., observer_factory=None):
    from .realworld_tool_expert import ToolExecutionError
    from .engineering_robot_table_contacts import install
    if not 0. < maximum_force_n <= 1.:
        raise ValueError('E37 robot/table contact threshold must not exceed 1 N')
    observer = (observer_factory or install)(
        policy.a, stem='E37-native-all-link-table')
    original = policy.act

    def checked_action(*args, **kwargs):
        # The accepted physical action finishes normally. Only future author
        # actions are refused; neither its ticks nor its targets are cancelled.
        result = original(*args, **kwargs)
        report = observer['snapshot']()
        if not report['measurement_completed']:
            raise ToolExecutionError('E37 full-robot/table force readback incomplete')
        contacts = {name: float(force) for name, force in
                    report['all_link_table_peak_force_n'].items()
                    if force is not None and force > maximum_force_n}
        if contacts:
            report['unexpected_robot_table_contacts_n'] = contacts
            report['completed_action_stopped_future_actions_only'] = True
            (policy.a.out / 'E37-table-contact-stop.private.json').write_text(
                json.dumps(report, indent=2) + '\n')
            raise ToolExecutionError('E37 real robot link contacted the table: ' +
                                     ', '.join(sorted(contacts)))
        return result

    policy.act = checked_action
    try:
        yield observer
    finally:
        policy.act = original
        observer['close']()
