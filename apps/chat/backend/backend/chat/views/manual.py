from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.manual import manual_payload


class ManualView(APIView):
    """帮助文档 — GET /api/manual"""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(manual_payload())

