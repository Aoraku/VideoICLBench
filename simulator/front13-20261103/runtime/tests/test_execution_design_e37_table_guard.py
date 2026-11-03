from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e37_table_guard import guard_actions
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def policy_and_observer(tmp_path, *, force=0., measured=True):
    events=[]
    policy=SimpleNamespace(a=SimpleNamespace(out=tmp_path))
    def act(*args, **kwargs):
        events.append('completed-action')
        return 'native-receipt'
    policy.act=act
    def observer(author, **kwargs):
        return dict(snapshot=lambda:dict(measurement_completed=measured,
                    all_link_table_peak_force_n={'left/panda_link6':force}),
                    close=lambda:events.append('closed-observer'))
    return policy,observer,events


def test_clear_actual_contact_keeps_receipt_without_extra_action(tmp_path):
    policy,factory,events=policy_and_observer(tmp_path)
    original=policy.act
    with guard_actions(policy,observer_factory=factory):
        assert policy.act('left','DOWN')=='native-receipt'
    assert events==['completed-action','closed-observer']
    assert policy.act is original


@pytest.mark.parametrize('force,measured,message',[
    (24.06,True,'real robot link'),
    (None,False,'readback incomplete'),
])
def test_actual_collision_or_missing_readback_stops_future_actions(
        tmp_path,force,measured,message):
    policy,factory,events=policy_and_observer(tmp_path,force=force,measured=measured)
    original=policy.act
    with pytest.raises(ToolExecutionError,match=message):
        with guard_actions(policy,observer_factory=factory):
            policy.act('left','DOWN')
            policy.act('left','DOWN')
    assert events==['completed-action','closed-observer']
    assert policy.act is original
    if measured:assert (tmp_path/'E37-table-contact-stop.private.json').is_file()
