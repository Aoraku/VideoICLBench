from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import Conversation, ConversationMember, Message
from accounts.jwt_utils import generate_jwt

class SyncViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sync_user", password="password")
        self.token = generate_jwt(self.user.id)
        self.conv = Conversation.objects.create(type="private", created_by=self.user)
        self.member = ConversationMember.objects.create(conversation=self.conv, user=self.user)
        # Create a message to sync
        self.msg = Message.objects.create(conversation=self.conv, sender=self.user, content="Hello")

    def test_sync_messages_complex_payload(self):
        # Coverage for the loop and message serialization
        payload = {
            "last_msg_ids": {
                str(self.conv.id): 0
            }
        }
        response = self.client.post("/api/sync", data=payload, content_type="application/json", 
                                    HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("conversations", response.json())

    def test_sync_invalid_last_msg_ids(self):
        # Coverage for invalid_field_response("last_msg_ids")
        payload = {"last_msg_ids": "not_a_dict"}
        response = self.client.post("/api/sync", data=payload, content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 400)