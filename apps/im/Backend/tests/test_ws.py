import json
from django.test import TestCase
from django.contrib.auth.models import User
from accounts.ws import ChatWebSocketApp
from accounts.jwt_utils import generate_jwt

class WebSocketLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ws_user", password="p")
        self.token = generate_jwt(self.user.id)
        self.app = ChatWebSocketApp()

    async def test_auth_logic(self):
        # Testing the _authenticate method logic
        scope = {"query_string": f"token={self.token}".encode()}
        user = await self.app._authenticate(scope)
        self.assertEqual(user.id, self.user.id)
