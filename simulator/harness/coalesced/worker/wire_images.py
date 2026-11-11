"""Count image parts on the outgoing wire; never log image contents or URLs."""
from collections import Counter


def image_layout(request):
    messages = request.get('messages') or request.get('contents') or []
    total = Counter()
    last = Counter()
    for msg in messages:
        last = Counter()
        if not isinstance(msg, dict):
            continue
        role = msg.get('role', 'unknown')
        if role not in ('user', 'assistant', 'model', 'tool', 'system'):
            role = 'other'
        parts = msg.get('content', msg.get('parts', []))
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if _image(part):
                last[role] += 1
            elif part.get('type') == 'tool_result':
                nested = part.get('content')
                if isinstance(nested, list):
                    last[role+'.tool_result'] += sum(_image(item) for item in nested)
            else:
                response = part.get('functionResponse') or part.get('function_response')
                if isinstance(response, dict) and isinstance(response.get('parts'), list):
                    last[role+'.function_response'] += sum(_image(item) for item in response['parts'])
        total.update(last)
    return {'all_messages': dict(+total), 'last_message': dict(+last)}


def _image(part):
    if not isinstance(part, dict):
        return False
    if part.get('type') in ('image', 'image_url', 'input_image'):
        return True
    for key in ('inlineData', 'inline_data', 'fileData', 'file_data'):
        data = part.get(key)
        if isinstance(data, dict) and str(data.get('mimeType', data.get('mime_type', ''))).startswith('image/'):
            return True
    return False
