"""Apply the campaign's fixed HIGH to this exact provider route only.

Old native sessions persist their originally selected MAX. Never rewrite that
history or mislabel it. The transport records the native and provider levels.
"""
import copy

MODEL = 'glm-5.3-flash'


def enforce(data):
    if data.get('model') != MODEL:
        raise ValueError('ZCode effort mapping requires the fixed campaign model')
    original = data.get('output_config')
    if original is not None and not isinstance(original, dict):
        raise ValueError('Malformed native output_config')
    config = dict(original or {})
    requested = config.get('effort')
    if requested is not None and not isinstance(requested, str):
        raise ValueError('Malformed native effort')
    before = copy.deepcopy(data)
    config['effort'] = 'high'
    data['output_config'] = config
    without_effort = copy.deepcopy(data)
    if original is None:
        without_effort.pop('output_config')
    else:
        without_effort['output_config'] = original
    if without_effort != before:
        raise AssertionError('Effort mapping changed unrelated request content')
    return dict(cli_requested_effort=requested, effective_provider_effort='high',
                effort_overridden=requested != 'high',
                override_reason='campaign_fixed_high_native_session_preserved'
                if requested != 'high' else None)
