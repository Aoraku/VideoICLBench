"""Private, immutable inputs used by the evaluator at the terminal sample.

Do not query the live scene here: another room may subsequently advance that
scene. These are the measured inputs already consumed by the evaluator, not
commands, inferred poses, or model-visible feedback.
"""
import hashlib
import json
import math

import numpy as np


def _plain(value):
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite terminal geometry')
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError('Terminal geometry requires string dictionary keys')
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    raise TypeError('Unsupported terminal geometry value')


def capture(evaluator, *, shared_tick, controller_tick):
    """Copy an allowlist only; absence is explicit and never changes the score."""
    header = dict(schema='videoicl-terminal-geometry-evidence-v1',
                  source='evaluator_consumed_native_snapshot',
                  coordinate_frame='room-local task frame',
                  shared_tick=shared_tick, controller_tick=controller_tick,
                  evaluator_step=getattr(evaluator, 'steps', None))
    if not isinstance(getattr(evaluator, 'state', None), dict):
        return dict(header, available=False, reason='evaluator_state_unavailable')
    try:
        payload = dict(state=_plain(evaluator.state),
                       contacts=sorted(sorted(pair) for pair in getattr(evaluator, 'contacts', ())))
        # Forces use frozenset keys internally; retain the pair explicitly.
        forces = getattr(evaluator, 'forces', None)
        if forces is not None:
            payload['contact_forces'] = [dict(pair=sorted(pair), force=_plain(force))
                                        for pair, force in sorted(forces.items(), key=lambda item: sorted(item[0]))]
        for name in ('objects', 'semantic', 'mechanisms', 'clip_records',
                     'hold_seconds', 'progress_hold', 'history_valid'):
            if hasattr(evaluator, name):
                payload[name] = _plain(getattr(evaluator, name))
        # Clip histories use (clip ID, target label) tuple keys, mixed with
        # initial clip-ID entries. Preserve key types rather than stringifying
        # them into ambiguous JSON object keys.
        for name in ('clip_samples', 'clip_driven'):
            if hasattr(evaluator, name):
                payload[name] = [dict(key=_plain(key), value=_plain(value))
                                 for key, value in getattr(evaluator, name).items()]
                payload[name].sort(key=lambda row: json.dumps(row['key']))
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return dict(header, available=True, payload=payload,
                    payload_sha256=hashlib.sha256(raw.encode()).hexdigest())
    except (TypeError, ValueError) as exc:
        # Missing diagnostics must not erase an otherwise valid native result.
        return dict(header, available=False, reason='terminal_geometry_serialization_failed',
                    error_type=type(exc).__name__)
