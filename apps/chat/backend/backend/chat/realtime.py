try:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
except ImportError:  # Channels is optional in local test environments.
    async_to_sync = None
    get_channel_layer = None


def conversation_group(conversation_id):
    return f'conversation_{conversation_id}'


def user_group(user_id):
    return f'user_{user_id}'


def _send(group_name, event_type, data):
    if not async_to_sync or not get_channel_layer:
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'push.event',
            'event': {
                'type': event_type,
                'data': data,
            },
        },
    )


def send_to_conversation(conversation_id, event_type, data):
    _send(conversation_group(conversation_id), event_type, data)


def send_to_user(user_id, event_type, data):
    _send(user_group(user_id), event_type, data)
