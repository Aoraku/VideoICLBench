"""
chat/views/upload.py
文件上传模块

对应接口：7.1
负责人：同学 B
"""

import mimetypes
import os
import json
import shutil
import subprocess
import uuid

from django.conf import settings as django_settings
from django.utils.text import get_valid_filename
from PIL import Image, UnidentifiedImageError

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework import status

from chat.models import UploadedFile


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
VIDEO_TYPES = {'video/mp4', 'video/webm'}
AUDIO_TYPES = {'audio/webm', 'audio/ogg', 'audio/mpeg', 'audio/mp3'}


def _size_limit_for(mime_type):
    if mime_type in IMAGE_TYPES:
        return 10 * 1024 * 1024
    if mime_type in VIDEO_TYPES:
        return 100 * 1024 * 1024
    if mime_type in AUDIO_TYPES:
        return 10 * 1024 * 1024
    return 50 * 1024 * 1024


def _category_for(mime_type):
    if mime_type in IMAGE_TYPES:
        return 'images'
    if mime_type in VIDEO_TYPES:
        return 'videos'
    if mime_type in AUDIO_TYPES:
        return 'audio'
    return 'files'


def _absolute_media_url(request, relative_path):
    return request.build_absolute_uri(django_settings.MEDIA_URL + relative_path)


def _extract_media_metadata(path):
    if not shutil.which('ffprobe'):
        return None, None, None
    try:
        completed = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'stream=width,height,duration:format=duration',
                '-of', 'json',
                path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(completed.stdout or '{}')
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None, None, None

    width = None
    height = None
    duration = None
    for stream in payload.get('streams', []):
        width = width or stream.get('width')
        height = height or stream.get('height')
        raw_duration = stream.get('duration')
        if duration is None and raw_duration not in (None, 'N/A'):
            try:
                duration = round(float(raw_duration))
            except (TypeError, ValueError):
                duration = None
    if duration is None:
        raw_duration = payload.get('format', {}).get('duration')
        if raw_duration not in (None, 'N/A'):
            try:
                duration = round(float(raw_duration))
            except (TypeError, ValueError):
                duration = None
    return width, height, duration


def _create_video_thumbnail(path, thumb_path):
    if not shutil.which('ffmpeg'):
        return False
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    try:
        subprocess.run(
            [
                'ffmpeg',
                '-y',
                '-i', path,
                '-ss', '00:00:01',
                '-frames:v', '1',
                '-vf', 'scale=480:-1',
                thumb_path,
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return os.path.exists(thumb_path)
    except (subprocess.SubprocessError, OSError):
        return False


class FileUploadView(APIView):
    """7.1 上传文件 — POST /api/upload"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('file')
        purpose = (request.data.get('purpose') or '').strip()
        if not upload:
            return Response(_err('INVALID_PARAMS', '缺少文件'), status=400)
        if purpose not in ('message', 'avatar'):
            return Response(_err('INVALID_PARAMS', 'purpose 仅支持 message/avatar'), status=400)

        guessed_type = mimetypes.guess_type(upload.name or '')[0]
        mime_type = (upload.content_type or guessed_type or 'application/octet-stream').lower()
        max_size = _size_limit_for(mime_type)
        if upload.size > max_size:
            return Response(_err('FILE_TOO_LARGE', '文件大小超过限制'), status=400)

        if purpose == 'avatar' and mime_type not in IMAGE_TYPES:
            return Response(_err('INVALID_FILE_TYPE', '头像仅支持图片文件'), status=400)

        original_name = get_valid_filename(upload.name or 'upload.bin')
        ext = os.path.splitext(original_name)[1].lower()
        if not ext:
            ext = mimetypes.guess_extension(mime_type) or '.bin'

        category = 'avatars' if purpose == 'avatar' else _category_for(mime_type)
        file_id = f'f_{uuid.uuid4().hex}'
        relative_path = f'uploads/{category}/{file_id}{ext}'
        save_path = os.path.join(django_settings.MEDIA_ROOT, relative_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as target:
            for chunk in upload.chunks():
                target.write(chunk)

        width = None
        height = None
        duration = None
        thumbnail_url = None
        if mime_type in IMAGE_TYPES:
            try:
                with Image.open(save_path) as image:
                    width, height = image.size
                    image.thumbnail((480, 480))
                    thumb_relative_path = f'uploads/{category}/{file_id}_thumb.jpg'
                    thumb_path = os.path.join(django_settings.MEDIA_ROOT, thumb_relative_path)
                    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                    if image.mode not in ('RGB', 'L'):
                        image = image.convert('RGB')
                    image.save(thumb_path, format='JPEG', quality=85)
                    thumbnail_url = _absolute_media_url(request, thumb_relative_path)
            except UnidentifiedImageError:
                return Response(_err('INVALID_FILE_TYPE', '图片文件无法解析'), status=400)
        elif mime_type in VIDEO_TYPES:
            width, height, duration = _extract_media_metadata(save_path)
            thumb_relative_path = f'uploads/{category}/{file_id}_thumb.jpg'
            thumb_path = os.path.join(django_settings.MEDIA_ROOT, thumb_relative_path)
            if _create_video_thumbnail(save_path, thumb_path):
                thumbnail_url = _absolute_media_url(request, thumb_relative_path)
        elif mime_type in AUDIO_TYPES:
            _, _, duration = _extract_media_metadata(save_path)

        file_url = _absolute_media_url(request, relative_path)
        UploadedFile.objects.create(
            uploader=request.user,
            file_id=file_id,
            url=file_url,
            thumbnail_url=thumbnail_url or '',
            filename=original_name,
            size=upload.size,
            mime_type=mime_type,
            width=width,
            height=height,
            duration=duration,
            purpose=purpose,
        )

        return Response({
            'file_id': file_id,
            'url': file_url,
            'thumbnail_url': thumbnail_url,
            'filename': original_name,
            'size': upload.size,
            'mime_type': mime_type,
            'width': width,
            'height': height,
            'duration': duration,
        }, status=status.HTTP_201_CREATED)
