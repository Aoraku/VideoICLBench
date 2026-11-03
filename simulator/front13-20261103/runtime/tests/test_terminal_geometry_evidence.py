"""Ensure forensic evidence survives subsequent shared-world motion."""
import hashlib
import json
from types import SimpleNamespace

import numpy as np

from videoicl_isaaclab.terminal_geometry_evidence import capture
from test_room_pool_actions import active_pool


def measured_evaluator():
    return SimpleNamespace(steps=123, state={'shoe': dict(pos=np.array([.1, .2, .3]),
        mat=np.eye(3), grasp=[False, False])}, contacts={frozenset(('shoe', 'box'))},
        forces={frozenset(('shoe', 'box')): np.float64(.8)},
        mechanisms={'clip': {'joint_pos': [.002]}}, clip_samples={'clip': [], ('clip', 'circle'): [[1, .002]]},
        clip_driven={('clip', 'circle'): True}, objects={'shoe': {'size': [.1, .03, .02]}},
        semantic={'containers': {'box': {'lower': [-.2, -.1, 0], 'upper': [.2, .1, .1]}}})


def test_serializable_snapshot_is_detached_and_source_bound():
    e = measured_evaluator()
    out = capture(e, shared_tick=123, controller_tick=123)
    assert out['available']
    assert out['payload']['contact_forces'] == [{'pair': ['box', 'shoe'], 'force': .8}]
    raw = json.dumps(out['payload'], sort_keys=True, separators=(',', ':'), allow_nan=False)
    assert hashlib.sha256(raw.encode()).hexdigest() == out['payload_sha256']
    e.state['shoe']['pos'][0] = 99
    e.mechanisms['clip']['joint_pos'][0] = 99
    e.clip_samples[('clip', 'circle')].append([2, 99])
    assert out['payload']['state']['shoe']['pos'][0] == .1
    assert out['payload']['mechanisms']['clip']['joint_pos'] == [.002]
    records = out['payload']['clip_samples']
    assert next(row for row in records if row['key'] == ['clip', 'circle'])['value'] == [[1, .002]]
    assert out['payload']['clip_driven'] == [dict(key=['clip', 'circle'], value=True)]


def test_unavailable_or_nonfinite_evidence_is_explicit_not_fabricated():
    assert capture(SimpleNamespace(), shared_tick=1, controller_tick=1)['available'] is False
    e = measured_evaluator()
    e.state['shoe']['pos'][0] = np.nan
    result = capture(e, shared_tick=1, controller_tick=1)
    assert result['available'] is False
    assert result['reason'] == 'terminal_geometry_serialization_failed'
    assert 'payload' not in result


def test_pool_latches_original_evaluator_inputs_without_stepping_or_resampling():
    pool, controllers, sim, events = active_pool()
    c = controllers['E05']
    evidence = measured_evaluator()
    c.evaluator.state = evidence.state
    c.evaluator.contacts = evidence.contacts
    c.snapshot = lambda: (_ for _ in ()).throw(AssertionError('Must not resample scene'))
    terminal = pool.seal('E05')
    assert not terminal['native']['success']
    assert sim.current_time == 0 and events == []
    c.evaluator.state['shoe']['pos'][0] = 99
    assert pool.seal('E05') == terminal
    terminal['terminal_geometry']['payload']['state']['shoe']['pos'][0] = -99
    assert pool.terminal_result('E05')['terminal_geometry']['payload']['state']['shoe']['pos'][0] == .1
