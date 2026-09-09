import json
import time
import pytest
from unittest.mock import patch
from django.test import Client
from django.contrib.auth.models import User
from accounts.models import (
    Conversation, ConversationMember, Friend, Message, UserProfile
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def users():
    u1 = User.objects.create_user(username="alice", password="password")
    u2 = User.objects.create_user(username="bob", password="password")
    u3 = User.objects.create_user(username="charlie", password="password")
    u4 = User.objects.create_user(username="dave", password="password")  # Not friends with alice

    UserProfile.objects.create(user=u1, avatar="avatar1.png", created_at=time.time())
    UserProfile.objects.create(user=u2, avatar="avatar2.png", created_at=time.time())
    UserProfile.objects.create(user=u3, avatar="avatar3.png", created_at=time.time())
    UserProfile.objects.create(user=u4, avatar="avatar4.png", created_at=time.time())

    # Create friendships (Alice is friends with Bob and Charlie)
    Friend.objects.create(user=u1, friend_user=u2)
    Friend.objects.create(user=u2, friend_user=u1)
    Friend.objects.create(user=u1, friend_user=u3)
    Friend.objects.create(user=u3, friend_user=u1)

    return u1, u2, u3, u4


@pytest.fixture
def mock_auth_alice(users):
    u1 = users[0]
    with patch("accounts.conversations_views.authenticate_request", return_value=u1) as m:
        yield m


@pytest.fixture
def mock_auth_none():
    with patch("accounts.conversations_views.authenticate_request", return_value=None) as m:
        yield m


class TestConversationsListAPI:
    def test_unauthorized(self, client, mock_auth_none):
        response = client.get("/api/conversations")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == -1
        assert data["info"] == "Invalid or expired JWT"

    def test_bad_method(self, client, mock_auth_alice):
        response = client.put("/api/conversations")
        assert response.status_code == 405
        data = response.json()
        assert data["code"] == -3
        assert data["info"] == "Bad method"

    def test_empty_conversations(self, client, mock_auth_alice):
        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["conversations"] == []

    def test_list_conversations_success(self, client, mock_auth_alice, users):
        u1, u2, u3, _ = users
        
        # 1. Private conversation with u2
        c1 = Conversation.objects.create(type="private", created_by=u1, updated_at=100)
        ConversationMember.objects.create(conversation=c1, user=u1, is_pinned=False)
        ConversationMember.objects.create(conversation=c1, user=u2)
        Message.objects.create(conversation=c1, sender=u2, content="Hello Alice", created_at=101)

        # 2. Group conversation with u2 and u3, pinned
        c2 = Conversation.objects.create(type="group", name="My Project Group", created_by=u1, updated_at=200)
        ConversationMember.objects.create(conversation=c2, user=u1, is_pinned=True, is_muted=True, unread_count=5)
        ConversationMember.objects.create(conversation=c2, user=u2)
        ConversationMember.objects.create(conversation=c2, user=u3)

        # 3. Private conversation but other member missing (Edge case line 37)
        c3 = Conversation.objects.create(type="private", created_by=u1, updated_at=300)
        ConversationMember.objects.create(conversation=c3, user=u1, is_pinned=False)

        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        
        conversations = data["conversations"]
        assert len(conversations) == 3
        
        # Pinned should be first
        assert conversations[0]["conversation_id"] == c2.id
        assert conversations[0]["type"] == "group"
        assert conversations[0]["name"] == "My Project Group"
        assert conversations[0]["is_pinned"] == True
        assert conversations[0]["is_muted"] == True
        assert conversations[0]["unread_count"] == 5
        assert conversations[0]["last_message"] is None

        # Then the newly created one (c3 updated_at=300 vs c1 updated_at=100)
        assert conversations[1]["conversation_id"] == c3.id
        assert conversations[1]["type"] == "private"
        assert conversations[1]["name"] == "（已注销用户）"  # other member missing → deactivated placeholder

        # Then c1
        assert conversations[2]["conversation_id"] == c1.id
        assert conversations[2]["type"] == "private"
        assert conversations[2]["name"] == "bob"  # Should resolve to other member's username
        assert conversations[2]["avatar"] == u2.profile.avatar
        assert conversations[2]["last_message"]["content"] == "Hello Alice"
        assert conversations[2]["last_message"]["sender_name"] == "bob"
        assert conversations[2]["is_pinned"] == False


class TestConversationsCreateAPI:
    def test_unauthorized(self, client, mock_auth_none):
        response = client.post("/api/conversations", data={}, content_type="application/json")
        assert response.status_code == 401

    def test_invalid_json(self, client, mock_auth_alice):
        response = client.post("/api/conversations", data="NOT JSON", content_type="application/json")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == -2
        assert "body" in data["info"].lower()

    def test_invalid_fields(self, client, mock_auth_alice):
        # 1. Extra parameter
        response = client.post("/api/conversations", data={"name": "A", "member_ids": [1, 2], "extra": 1}, content_type="application/json")
        assert response.status_code == 400
        assert "extra" in response.json()["info"]

        # 2. Missing parameter
        response = client.post("/api/conversations", data={"name": "Group"}, content_type="application/json")
        assert response.status_code == 400

        # 3. Invalid name type/empty
        response = client.post("/api/conversations", data={"name": "", "member_ids": [1, 2]}, content_type="application/json")
        assert response.status_code == 400
        assert "name" in response.json()["info"]

        # 4. Invalid member_ids format
        response = client.post("/api/conversations", data={"name": "Valid Name", "member_ids": "not_a_list"}, content_type="application/json")
        assert response.status_code == 400
        assert "member_ids" in response.json()["info"]

        # 5. member_ids element not int
        response = client.post("/api/conversations", data={"name": "Valid Name", "member_ids": [1, "two"]}, content_type="application/json")
        assert response.status_code == 400
        assert "member_ids" in response.json()["info"]



    def test_not_friends(self, client, mock_auth_alice, users):
        _, u2, _, u4 = users  # u4 is not a friend of alice
        response = client.post("/api/conversations", data={"name": "GroupName", "member_ids": [u2.id, u4.id]}, content_type="application/json")
        assert response.status_code == 400
        assert response.json()["code"] == -2
        assert f"User [{u4.id}] is not your friend" in response.json()["info"]

    def test_success(self, client, mock_auth_alice, users):
        u1, u2, u3, _ = users
        response = client.post("/api/conversations", data={"name": "  New Group  ", "member_ids": [u2.id, u3.id]}, content_type="application/json")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        conversation_id = data["conversation_id"]

        # Verify DB changes
        c = Conversation.objects.get(id=conversation_id)
        assert c.type == "group"
        assert c.name == "New Group"
        assert c.created_by == u1
        
        members = list(c.members.values_list("user_id", flat=True))
        assert set(members) == {u1.id, u2.id, u3.id}


class TestConversationSettingsAPI:
    def test_unauthorized(self, client, mock_auth_none):
        response = client.put("/api/conversations/1/settings", data={}, content_type="application/json")
        assert response.status_code == 401

    def test_bad_method(self, client, mock_auth_alice):
        response = client.post("/api/conversations/1/settings", data={}, content_type="application/json")
        assert response.status_code == 405

    def test_invalid_body(self, client, mock_auth_alice, users):
        u1 = users[0]
        c = Conversation.objects.create(type="group", created_by=u1)
        cm = ConversationMember.objects.create(conversation=c, user=u1)

        response = client.put(f"/api/conversations/{c.id}/settings", data="NOT JSON", content_type="application/json")
        assert response.status_code == 400
        assert "body" in response.json()["info"].lower()

        response = client.put(f"/api/conversations/{c.id}/settings", data={"extra_field": True}, content_type="application/json")
        assert response.status_code == 400
        
        response = client.put(f"/api/conversations/{c.id}/settings", data={"is_pinned": "not_a_bool"}, content_type="application/json")
        assert response.status_code == 400
        assert "is_pinned" in response.json()["info"]
        
        response = client.put(f"/api/conversations/{c.id}/settings", data={"is_muted": "not_a_bool"}, content_type="application/json")
        assert response.status_code == 400
        assert "is_muted" in response.json()["info"]

    def test_not_found_or_not_member(self, client, mock_auth_alice, users):
        u1, u2, _, _ = users
        # Conversation exists but alice is not a member
        c = Conversation.objects.create(type="group", created_by=u2)
        ConversationMember.objects.create(conversation=c, user=u2)
        
        response = client.put(f"/api/conversations/{c.id}/settings", data={"is_pinned": True}, content_type="application/json")
        assert response.status_code == 404
        assert response.json()["code"] == 1
        assert "not found" in response.json()["info"].lower()

    def test_success(self, client, mock_auth_alice, users):
        u1 = users[0]
        c = Conversation.objects.create(type="group", created_by=u1)
        cm = ConversationMember.objects.create(conversation=c, user=u1, is_pinned=False, is_muted=False)

        # Update only pinned
        response = client.put(f"/api/conversations/{c.id}/settings", data={"is_pinned": True}, content_type="application/json")
        assert response.status_code == 200
        assert response.json()["code"] == 0
        
        cm.refresh_from_db()
        assert cm.is_pinned is True
        assert cm.is_muted is False

        # Update both
        response = client.put(f"/api/conversations/{c.id}/settings", data={"is_pinned": False, "is_muted": True}, content_type="application/json")
        assert response.status_code == 200
        
        cm.refresh_from_db()
        assert cm.is_pinned is False
        assert cm.is_muted is True


class TestStressAndEdgeCases:
    def test_bulk_conversations_retrieval(self, client, mock_auth_alice, users):
        """Stress test: User is part of 200 conversations, tests performance/sorting."""
        u1, u2 = users[0], users[1]
        
        # Create 200 conversations
        conversations = []
        for i in range(200):
            c = Conversation(type="group", name=f"Group {i}", created_by=u1, updated_at=1000 + i)
            conversations.append(c)
        Conversation.objects.bulk_create(conversations)

        # Re-fetch to get IDs
        conversations = list(Conversation.objects.all().order_by('id'))
        
        members = []
        messages = []
        for i, c in enumerate(conversations):
            members.append(ConversationMember(conversation=c, user=u1, is_pinned=(i % 5 == 0)))
            members.append(ConversationMember(conversation=c, user=u2))
            messages.append(Message(conversation=c, sender=u2, content=f"Msg {i}", created_at=1000 + i))
            
        ConversationMember.objects.bulk_create(members)
        Message.objects.bulk_create(messages)

        # Trigger GET API
        start_time = time.time()
        response = client.get("/api/conversations")
        end_time = time.time()
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["conversations"]) == 200
        
        # Verify ordering: First 40 should be the pinned ones (since 200/5 = 40)
        # and ordered by updated_at descending
        pinned_conversations = [conv for conv in data["conversations"] if conv["is_pinned"]]
        assert len(pinned_conversations) == 40
        
        # The topmost pinned conversation should be the one with the highest updated_at
        highest_pinned_updated_at = max(c.updated_at for i, c in enumerate(conversations) if i % 5 == 0)
        assert data["conversations"][0]["updated_at"] == highest_pinned_updated_at
        
        # Should respond fast
        assert (end_time - start_time) < 2.0

    def test_large_group_creation_stress(self, client, mock_auth_alice, users):
        """Stress test: Creating a large WeChat-like group (e.g. 500 members)."""
        u1 = users[0]
        
        # Create 500 new users and make them friends
        friends = []
        new_users = []
        for i in range(500):
            u = User(username=f"stress_user_{i}", password="password")
            new_users.append(u)
        User.objects.bulk_create(new_users)
        
        # Re-fetch to get IDs
        new_users = list(User.objects.filter(username__startswith="stress_user_"))
        for u in new_users:
            friends.append(Friend(user=u1, friend_user=u))
        Friend.objects.bulk_create(friends)
        
        member_ids = [u.id for u in new_users]

        start_time = time.time()
        response = client.post(
            "/api/conversations", 
            data={"name": "Massive WeChat Group", "member_ids": member_ids}, 
            content_type="application/json"
        )
        end_time = time.time()

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        conversation_id = data["conversation_id"]

        # Validate that all 501 members (creator + 500 friends) were successfully added
        assert ConversationMember.objects.filter(conversation_id=conversation_id).count() == 501
        
        # Creation should be optimized via bulk_create, testing DB atomicity and speed (<1.5s)
        assert (end_time - start_time) < 1.5

    def test_frequent_settings_update_stress(self, client, mock_auth_alice, users):
        """Stress test: User rapidly toggles pinned/muted settings multiple times (e.g., fast tapping)."""
        u1 = users[0]
        c = Conversation.objects.create(type="group", created_by=u1)
        cm = ConversationMember.objects.create(conversation=c, user=u1, is_pinned=False, is_muted=False)

        for i in range(50):
            # Toggle rapidly
            response = client.put(
                f"/api/conversations/{c.id}/settings", 
                data={"is_pinned": bool(i % 2 == 0), "is_muted": bool(i % 3 == 0)}, 
                content_type="application/json"
            )
            assert response.status_code == 200
            
        cm.refresh_from_db()
        assert cm.is_pinned is False  # 49 % 2 != 0 -> False
        assert cm.is_muted is False   # 49 % 3 != 0 -> False

