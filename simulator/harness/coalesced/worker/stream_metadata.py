"""Record completion metadata without retaining model text or changing delivery."""


def record_stop_metadata(receipt, event):
    """SSE deltas carry the final stop reason, unlike assistant start events."""
    if not isinstance(event, dict):
        return
    candidates = [event]
    for key in ('message', 'delta'):
        value = event.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for value in candidates:
        reason = value.get('stop_reason')
        if isinstance(reason, str) and reason and len(reason) <= 128:
            receipt['stop_reason'] = reason
    choices = event.get('choices')
    if isinstance(choices, list):
        reasons = receipt.setdefault('choice_finish_reasons', {})
        for position, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            reason = choice.get('finish_reason')
            index = choice.get('index', position)
            if type(index) is int and isinstance(reason, str) and reason and len(reason) <= 128:
                reasons[str(index)] = reason
        if not reasons:
            receipt.pop('choice_finish_reasons', None)
    if event.get('type') == 'message_stop':
        receipt['message_stop_observed'] = True
