"""
chat/views/ai.py
智能对话模块【拓展功能】

对应接口：9.1 - 9.2
负责人：同学 B
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import StreamingHttpResponse
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from chat.manual import manual_text
from chat.models import Conversation, ConversationMember, Message, UploadedFile, User


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _message_payload(message):
    return {
        'msg_id': message.id,
        'type': message.type,
        'content': message.content,
        'created_at': message.created_at.isoformat(),
    }


def _get_ai_user():
    user, created = User.objects.get_or_create(
        username='ai_assistant',
        defaults={
            'email': '',
            'phone': '',
            'avatar': '',
            'presence': 'online',
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


TEXT_FILE_MIME_PREFIXES = ('text/',)
TEXT_FILE_MIME_TYPES = {
    'application/json',
    'application/javascript',
    'application/xml',
    'application/x-python-code',
    'application/x-sh',
}
TEXT_FILE_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.xml', '.yaml', '.yml',
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
    '.go', '.rs', '.rb', '.php', '.sh', '.sql', '.css', '.html',
}

MANUAL_ACTION_KEYWORDS = (
    '怎么', '怎样', '如何', '在哪', '哪里', '什么功能', '使用', '操作', '教程',
    '帮助', '手册', '说明', 'manual', 'help',
)
MANUAL_FEATURE_KEYWORDS = (
    '软件', '系统', 'chatglmj', '会话', '消息', '聊天', '私聊', '群聊', '好友',
    '通讯录', '联系人', '黑名单', '白名单', '名片', '待办', '收藏', '日历',
    '日程', '邀请', 'ai助手', 'ai 助手', '@ai', '代码块', '文件', '图片',
    '转发', '回复', '撤回', '已读', '搜索', '状态', '头像', 'api key', 'api-key', 'api_key', 'apikey',
)


def _looks_like_manual_question(text):
    raw = str(text or '').strip().lower()
    if not raw:
        return False
    if '帮助文档' in raw or '使用手册' in raw:
        return True
    has_action = any(keyword in raw for keyword in MANUAL_ACTION_KEYWORDS)
    has_feature = any(keyword in raw for keyword in MANUAL_FEATURE_KEYWORDS)
    return has_action and has_feature


def _media_path_from_url(url):
    raw = str(url or '').strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    path = unquote(parsed.path if parsed.scheme else raw)
    media_url = str(settings.MEDIA_URL or '/media/')
    if path.startswith(media_url):
        rel = path[len(media_url):]
    elif path.startswith('/media/'):
        rel = path[len('/media/'):]
    else:
        return None
    rel = rel.lstrip('/')
    full_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, rel))
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    if os.path.commonpath([media_root, full_path]) != media_root:
        return None
    return full_path


def _read_text_file_preview(content, limit=12000):
    file_id = str((content or {}).get('file_id') or '').strip()
    filename = str((content or {}).get('filename') or '').strip()
    mime_type = str((content or {}).get('mime_type') or '').lower()
    ext = os.path.splitext(filename)[1].lower()
    text_like = (
        any(mime_type.startswith(prefix) for prefix in TEXT_FILE_MIME_PREFIXES)
        or mime_type in TEXT_FILE_MIME_TYPES
        or ext in TEXT_FILE_EXTENSIONS
    )
    if not text_like:
        return ''

    file_url = str((content or {}).get('url') or '').strip()
    if file_id:
        uploaded = UploadedFile.objects.filter(file_id=file_id).first()
        if uploaded:
            file_url = uploaded.url or file_url
    path = _media_path_from_url(file_url)
    if not path or not os.path.exists(path) or os.path.getsize(path) > 2 * 1024 * 1024:
        return ''
    with open(path, 'rb') as handle:
        raw = handle.read(limit + 1)
    text = raw.decode('utf-8', errors='replace')
    if len(raw) > limit:
        text += '\n...'
    return text


def _message_to_ai_text(message):
    content = message.content or {}
    if not isinstance(content, dict):
        content = {}
    msg_type = message.type

    if msg_type == 'text':
        return str(content.get('text') or '').strip()
    if msg_type in ('group_announcement', 'announcement', 'system'):
        return str(content.get('content') or content.get('text') or '').strip()
    if msg_type == 'code':
        language = str(content.get('language') or 'text').strip() or 'text'
        code = str(content.get('code') or '').strip()
        return f'```{language}\n{code}\n```' if code else ''
    if msg_type == 'contact_card':
        return f"[名片] {content.get('username') or ''} user_id={content.get('user_id') or ''}".strip()
    if msg_type == 'forward':
        summary = content.get('summary') if isinstance(content.get('summary'), list) else []
        lines = '\n'.join(str(line) for line in summary[:8])
        return f"[转发消息] {content.get('title') or '聊天记录'}\n{lines}".strip()
    if msg_type == 'image':
        return f"[图片] {content.get('filename') or '图片'} {content.get('url') or ''}".strip()
    if msg_type in ('video', 'audio'):
        return f"[{msg_type}] {content.get('filename') or content.get('url') or ''}".strip()
    if msg_type == 'file':
        filename = content.get('filename') or '文件'
        mime_type = content.get('mime_type') or ''
        preview = _read_text_file_preview(content)
        if preview:
            language = 'markdown' if str(filename).lower().endswith(('.md', '.markdown')) else 'text'
            return f"[文件] {filename} ({mime_type})\n```{language}\n{preview}\n```"
        return f"[文件] {filename} ({mime_type}) {content.get('url') or ''}".strip()
    return f"[{msg_type}] {json.dumps(content, ensure_ascii=False)}"


def _build_context(conversation, include_manual=False):
    max_messages = max(1, int(getattr(settings, 'AI_CONTEXT_MAX_MESSAGES', 20)))
    max_tokens = max(200, int(getattr(settings, 'AI_CONTEXT_MAX_TOKENS', 3000)))
    char_budget = max_tokens * 4
    messages = list(
        Message.objects.filter(conversation=conversation)
        .select_related('sender')
        .order_by('-created_at', '-id')[:max_messages]
    )
    context = [{
        'role': 'system',
        'content': (
            '你是 ChatGLMJ 的 AI 助手。回答时优先参考最近的会话上下文；'
            '上下文可能包含普通文本、Markdown、代码块、文件摘要、图片或音视频说明。'
        ),
    }]
    total_chars = len(context[0]['content'])
    if include_manual:
        manual_content = (
            '用户正在询问 ChatGLMJ 软件使用方法。请优先依据以下帮助文档回答；'
            '如果文档没有覆盖，再说明目前文档未写明。\n\n'
            f'{manual_text()}'
        )
        context.append({'role': 'system', 'content': manual_content})
        total_chars += len(manual_content)
    for message in reversed(messages):
        if message.is_recalled:
            continue
        role = 'assistant' if message.sender and message.sender.username == 'ai_assistant' else 'user'
        text = _message_to_ai_text(message)
        if text:
            if role == 'user' and conversation.type == 'group':
                sender_name = message.sender.username if message.sender else '未知用户'
                text = f'{sender_name}: {text}'
            if len(text) > 8000:
                text = text[:8000] + '\n...'
            context.append({'role': role, 'content': text})
            total_chars += len(text)

    trim_index = 2 if include_manual else 1
    while len(context) > trim_index + 1 and total_chars > char_budget:
        removed = context.pop(trim_index)
        total_chars -= len(removed.get('content', ''))
    return context


def _get_user_ai_api_key(user):
    return str(getattr(user, 'ai_api_key', '') or '').strip()


def _llm_payload(messages, stream=False):
    payload = {
        'model': settings.AI_MODEL,
        'messages': messages,
    }
    if stream:
        payload['stream'] = True
    extra_body = getattr(settings, 'AI_REQUEST_EXTRA_BODY', None)
    if extra_body:
        payload['extra_body'] = extra_body
    return payload


def _call_llm(messages, api_key):
    if not api_key:
        raise RuntimeError('missing api key')

    payload = json.dumps(_llm_payload(messages)).encode('utf-8')
    request = urllib.request.Request(
        f'{settings.AI_BASE_URL}/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.AI_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        return body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError('invalid ai response') from exc


def _stream_llm(messages, api_key):
    if not api_key:
        raise RuntimeError('missing api key')

    payload = json.dumps(_llm_payload(messages, stream=True)).encode('utf-8')
    request = urllib.request.Request(
        f'{settings.AI_BASE_URL}/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
        },
        method='POST',
    )
    try:
        response = urllib.request.urlopen(request, timeout=settings.AI_TIMEOUT_SECONDS)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        with response:
            for raw_line in response:
                line = raw_line.decode('utf-8').strip()
                if not line or line.startswith(':'):
                    continue
                if line.startswith('data:'):
                    line = line[5:].strip()
                if line == '[DONE]':
                    break
                try:
                    payload = json.loads(line)
                    delta = payload['choices'][0].get('delta', {})
                    content = delta.get('content') or ''
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if content:
                    yield content
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def _rate_limited(user_id):
    key = f'ai-rate:{user_id}:{timezone.now().strftime("%Y%m%d%H%M")}'
    count = cache.get(key, 0)
    if count >= settings.AI_RATE_LIMIT_PER_MINUTE:
        return True
    cache.set(key, count + 1, timeout=70)
    return False


class AIConversationCreateView(APIView):
    """9.1 创建 AI 会话 — POST /api/ai/conversations【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = str(request.data.get('name') or '我的AI助手').strip()
        if not name:
            return Response(_err('INVALID_PARAMS', 'AI 会话名称不能为空'), status=400)
        if len(name) > 50:
            return Response(_err('INVALID_PARAMS', 'AI 会话名称长度不能超过 50'), status=400)

        ai_user = _get_ai_user()
        with transaction.atomic():
            conv = Conversation.objects.create(type='ai', name=name)
            ConversationMember.objects.create(conversation=conv, user=request.user, role='member')
            ConversationMember.objects.create(conversation=conv, user=ai_user, role='member')

        return Response({
            'conversation_id': conv.id,
            'type': conv.type,
            'name': conv.name,
            'ai_model': settings.AI_MODEL,
            'created_at': conv.created_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class AIMessageView(APIView):
    """9.2 向 AI 发送消息 — POST /api/ai/conversations/{conv_id}/messages【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv = Conversation.objects.filter(pk=conv_id, type='ai').first()
        if not conv:
            return Response(_err('CONVERSATION_NOT_FOUND', 'AI 会话不存在'), status=404)
        if not ConversationMember.objects.filter(
            conversation=conv,
            user=request.user,
            is_removed=False,
        ).exists():
            return Response(_err('CONVERSATION_NOT_FOUND', 'AI 会话不存在'), status=404)

        content = str(request.data.get('content') or '').strip()
        if not content:
            return Response(_err('EMPTY_CONTENT', '消息为空'), status=400)
        if _rate_limited(request.user.id):
            return Response(_err('AI_RATE_LIMITED', 'AI 调用过于频繁'), status=429)
        api_key = _get_user_ai_api_key(request.user)
        if not api_key:
            return Response(_err('AI_API_KEY_REQUIRED', '请先在个人设置中配置 AI API Key'), status=403)

        ai_user = _get_ai_user()
        with transaction.atomic():
            user_message = Message.objects.create(
                conversation=conv,
                sender=request.user,
                type='text',
                content={'text': content},
            )
            conv.updated_at = timezone.now()
            conv.save(update_fields=['updated_at'])

        llm_messages = _build_context(conv, include_manual=_looks_like_manual_question(content))
        if not llm_messages or llm_messages[-1].get('content') != content:
            llm_messages.append({'role': 'user', 'content': content})

        stream_enabled = request.query_params.get('stream') != 'false'
        if not stream_enabled:
            try:
                answer = _call_llm(llm_messages, api_key)
            except RuntimeError:
                return Response(_err('AI_SERVICE_ERROR', 'LLM API 调用失败'), status=502)

            ai_message = Message.objects.create(
                conversation=conv,
                sender=ai_user,
                type='text',
                content={'text': answer},
            )
            conv.updated_at = timezone.now()
            conv.save(update_fields=['updated_at'])
            return Response({
                'user_message': _message_payload(user_message),
                'ai_message': _message_payload(ai_message),
            })

        ai_message = Message.objects.create(
            conversation=conv,
            sender=ai_user,
            type='text',
            content={'text': ''},
        )

        def event_stream():
            yield f'data: {json.dumps({"type": "start", "msg_id": ai_message.id, "user_msg_id": user_message.id}, ensure_ascii=False)}\n\n'
            chunks = []
            try:
                for chunk in _stream_llm(llm_messages, api_key):
                    chunks.append(chunk)
                    yield f'data: {json.dumps({"type": "delta", "content": chunk}, ensure_ascii=False)}\n\n'
            except RuntimeError:
                yield f'data: {json.dumps({"type": "error", "code": "AI_SERVICE_ERROR"}, ensure_ascii=False)}\n\n'
                return
            answer = ''.join(chunks)
            ai_message.content = {'text': answer}
            ai_message.save(update_fields=['content'])
            conv.updated_at = timezone.now()
            conv.save(update_fields=['updated_at'])
            yield f'data: {json.dumps({"type": "done", "msg_id": ai_message.id, "full_content": answer}, ensure_ascii=False)}\n\n'

        return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
