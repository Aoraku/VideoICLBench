import json
import time

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase

from accounts.jwt_utils import generate_jwt
from accounts.models import Friend, FriendGroup, FriendRequest


_FRIEND_TABLES_READY = False


def _ensure_friend_tables():
    global _FRIEND_TABLES_READY
    if _FRIEND_TABLES_READY:
        return

    existing_tables = set(connection.introspection.table_names())
    with connection.schema_editor() as schema_editor:
        for model in (FriendGroup, Friend, FriendRequest):
            table = model._meta.db_table
            if table not in existing_tables:
                schema_editor.create_model(model)
                existing_tables.add(table)
    _FRIEND_TABLES_READY = True


class FriendsViewsTest(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_friend_tables()

    def setUp(self):
        self.client = self.client_class()
        self.alice = User.objects.create_user(
            username="alice",
            password="password123",
            email="alice@example.com",
        )
        self.bob = User.objects.create_user(
            username="bob",
            password="password123",
            email="bob@example.com",
        )
        self.charlie = User.objects.create_user(
            username="charlie",
            password="password123",
            email="charlie@example.com",
        )

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {generate_jwt(user.id)}"}

    def test_friends_view_requires_get_and_auth(self):
        response = self.client.post("/api/friends", **self._auth(self.alice))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)
        self.assertEqual(response.json()["info"], "Bad method")

        response = self.client.get("/api/friends")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], -1)
        self.assertEqual(response.json()["info"], "Invalid or expired JWT")

    def test_unauthenticated_requests(self):
        res1 = self.client.get("/api/friends/groups")
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.json()["code"], -1)
        
        res2 = self.client.get("/api/friends/request")
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.json()["code"], -1)

        res3 = self.client.delete(f"/api/friends/{self.bob.id}")
        self.assertEqual(res3.status_code, 401)
        self.assertEqual(res3.json()["code"], -1)

    def test_friends_get_returns_group_profile_and_avatar_field(self):
        group = FriendGroup.objects.create(user=self.alice, name="同学")
        Friend.objects.create(user=self.alice, friend_user=self.bob, group=group)

        response = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["code"], 0)
        self.assertEqual(data["info"], "Succeed")
        self.assertEqual(len(data["friends"]), 1)
        
        friend = data["friends"][0]
        self.assertEqual(friend["user_id"], self.bob.id)
        self.assertEqual(friend["username"], "bob")
        self.assertEqual(friend["group"], "同学")
        self.assertIn("avatar", friend)
        self.assertIn("online", friend)

    def test_groups_crud_and_move_friend(self):
        response = self.client.post(
            "/api/friends/groups",
            data=json.dumps({"group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        Friend.objects.create(user=self.alice, friend_user=self.bob)
        response = self.client.put(
            "/api/friends/groups",
            data=json.dumps({"friend_id": self.bob.id, "group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertEqual(friends_res.json()["friends"][0]["group"], "室友")

        response = self.client.get("/api/friends/groups", **self._auth(self.alice))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertIn("室友", response.json()["groups"])

        response = self.client.delete(
            "/api/friends/groups",
            data=json.dumps({"group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertNotEqual(friends_res.json()["friends"][0]["group"], "室友")

    def test_groups_create_duplicate_and_bad_params(self):
        FriendGroup.objects.create(user=self.alice, name="同事")
        response = self.client.post(
            "/api/friends/groups",
            data=json.dumps({"group_name": "同事"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 1)
        self.assertEqual(response.json()["info"], "Group already exists")

        response = self.client.post(
            "/api/friends/groups",
            data="not_json",
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid JSON")

    def test_manage_groups_edge_cases(self):
        response = self.client.patch("/api/friends/groups", **self._auth(self.alice))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)
        
        response = self.client.put(
            "/api/friends/groups",
            data="not_json",
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid JSON")
        
        response = self.client.put(
            "/api/friends/groups",
            data=json.dumps({"friend_id": "abc", "group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        
        response = self.client.put(
            "/api/friends/groups",
            data=json.dumps({"friend_id": 999, "group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["info"], "Friend not found")
        
        Friend.objects.create(user=self.alice, friend_user=self.bob)
        response = self.client.put(
            "/api/friends/groups",
            data=json.dumps({"friend_id": self.bob.id, "group_name": "NonExistent"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["info"], "Group not found")
        
        response = self.client.delete(
            "/api/friends/groups",
            data="not_json",
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid JSON")
        
        response = self.client.delete(
            "/api/friends/groups",
            data=json.dumps({"group_name": "默认分组"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Cannot delete default group")
        
        response = self.client.delete(
            "/api/friends/groups",
            data=json.dumps({"group_name": "NonExistent"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["info"], "Group not found")

    def test_manage_groups_put_default_group(self):
        group = FriendGroup.objects.create(user=self.alice, name="室友")
        Friend.objects.create(user=self.alice, friend_user=self.bob, group=group)
        
        response = self.client.put(
            "/api/friends/groups",
            data=json.dumps({"friend_id": self.bob.id, "group_name": "默认分组"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        
        friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        friend_bob = friends_res.json()["friends"][0]
        self.assertEqual(friend_bob["group"], "默认分组")

    def test_requests_send_list_accept_flow(self):
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({
                "to_user_id": self.bob.id,
                "message": "Hi, I am Alice",
                "source": "search",
            }),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        response = self.client.get("/api/friends/request", **self._auth(self.bob))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        
        requests = response.json()["requests"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["from_user"]["user_id"], self.alice.id)
        self.assertEqual(requests[0]["source"], "search")
        self.assertEqual(requests[0]["message"], "Hi, I am Alice")
        self.assertEqual(len(response.json()["received_requests"]), 1)
        self.assertEqual(len(response.json()["sent_requests"]), 0)

        alice_view = self.client.get("/api/friends/request", **self._auth(self.alice))
        self.assertEqual(alice_view.status_code, 200)
        self.assertEqual(alice_view.json()["code"], 0)
        self.assertEqual(len(alice_view.json()["received_requests"]), 0)
        self.assertEqual(len(alice_view.json()["sent_requests"]), 1)
        self.assertEqual(alice_view.json()["sent_requests"][0]["to_user"]["user_id"], self.bob.id)
        self.assertEqual(alice_view.json()["sent_requests"][0]["direction"], "sent")
        self.assertEqual(alice_view.json()["sent_requests"][0]["status"], "pending")

        request_id = requests[0]["request_id"]
        response = self.client.put(
            "/api/friends/request",
            data=json.dumps({"request_id": request_id, "action": "accept"}),
            content_type="application/json",
            **self._auth(self.bob),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        bob_friends_res = self.client.get("/api/friends", **self._auth(self.bob))
        alice_friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertTrue(any(f["user_id"] == self.alice.id for f in bob_friends_res.json()["friends"]))
        self.assertTrue(any(f["user_id"] == self.bob.id for f in alice_friends_res.json()["friends"]))

    def test_requests_user_not_found(self):
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({"to_user_id": 99999}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 1)
        self.assertEqual(response.json()["info"], "User not found")

    def test_requests_already_sent(self):
        FriendRequest.objects.create(from_user=self.alice, to_user=self.charlie, status="pending",message="",source="search",created_at=time.time())
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({"to_user_id": self.charlie.id}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 3)
        self.assertEqual(response.json()["info"], "Request already sent")

    def test_requests_already_friends(self):
        Friend.objects.create(user=self.alice, friend_user=self.bob)
        Friend.objects.create(user=self.bob, friend_user=self.alice)
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({"to_user_id": self.bob.id}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Already friends")

    def test_requests_not_found(self):
        response = self.client.put(
            "/api/friends/request",
            data=json.dumps({"request_id": 99999, "action": "accept"}),
            content_type="application/json",
            **self._auth(self.bob),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 1)
        self.assertEqual(response.json()["info"], "Request not found")

    def test_requests_invalid_action(self):
        req = FriendRequest.objects.create(from_user=self.charlie, to_user=self.alice, status="pending",message="",source="search",created_at=time.time())
        response = self.client.put(
            "/api/friends/request",
            data=json.dumps({"request_id": req.id, "action": "invalid_action"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid action")

    def test_manage_requests_edge_cases(self):
        response = self.client.patch("/api/friends/request", **self._auth(self.alice))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)
        
        response = self.client.post(
            "/api/friends/request",
            data="not_json",
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid JSON")
        
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({"to_user_id": "abc"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({"to_user_id": self.alice.id}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Cannot add yourself")
        
        response = self.client.put(
            "/api/friends/request",
            data="not_json",
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid JSON")
        
        response = self.client.put(
            "/api/friends/request",
            data=json.dumps({"request_id": "abc", "action": "accept"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_manage_requests_default_values(self):
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({
                "to_user_id": self.bob.id,
                "message": 12345,
                "source": "invalid_source"
            }),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        
        req = FriendRequest.objects.get(from_user=self.alice, to_user=self.bob)
        self.assertEqual(req.message, "")
        self.assertEqual(req.source, "search")

    def test_delete_friend_success_and_not_found(self):
        Friend.objects.create(user=self.alice, friend_user=self.bob)
        Friend.objects.create(user=self.bob, friend_user=self.alice)

        response = self.client.delete(f"/api/friends/{self.bob.id}", **self._auth(self.alice))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        alice_friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        bob_friends_res = self.client.get("/api/friends", **self._auth(self.bob))
        self.assertEqual(len(alice_friends_res.json()["friends"]), 0)
        self.assertEqual(len(bob_friends_res.json()["friends"]), 0)

        response = self.client.delete(f"/api/friends/{self.bob.id}", **self._auth(self.alice))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 1)
        self.assertEqual(response.json()["info"], "Friend not found")
        
    def test_delete_friend_edge_cases(self):
        response = self.client.get(f"/api/friends/{self.bob.id}", **self._auth(self.alice))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)
    
    def test_requests_reject_action(self):
        req = FriendRequest.objects.create(
            from_user=self.alice, 
            to_user=self.bob, 
            status="pending", 
            message="Hi",
            source="search",
            created_at=time.time()
        )
        
        response = self.client.put(
            "/api/friends/request",
            data=json.dumps({"request_id": req.id, "action": "reject"}),
            content_type="application/json",
            **self._auth(self.bob),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        bob_req_res = self.client.get("/api/friends/request", **self._auth(self.bob))
        self.assertEqual(len(bob_req_res.json()["requests"]), 0)

        alice_req_res = self.client.get("/api/friends/request", **self._auth(self.alice))
        self.assertEqual(len(alice_req_res.json()["sent_requests"]), 1)
        self.assertEqual(alice_req_res.json()["sent_requests"][0]["status"], "rejected")

        bob_friends_res = self.client.get("/api/friends", **self._auth(self.bob))
        alice_friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertEqual(len(bob_friends_res.json()["friends"]), 0)
        self.assertEqual(len(alice_friends_res.json()["friends"]), 0)

    def test_groups_delete_fallback_to_default(self):
        group = FriendGroup.objects.create(user=self.alice, name="室友")
        Friend.objects.create(user=self.alice, friend_user=self.bob, group=group)

        response = self.client.delete(
            "/api/friends/groups",
            data=json.dumps({"group_name": "室友"}),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        friends_res = self.client.get("/api/friends", **self._auth(self.alice))
        self.assertEqual(len(friends_res.json()["friends"]), 1)
        friend_bob = friends_res.json()["friends"][0]
        self.assertEqual(friend_bob["user_id"], self.bob.id)
        self.assertEqual(friend_bob["group"], "默认分组")

    def test_requests_source_group(self):
        response = self.client.post(
            "/api/friends/request",
            data=json.dumps({
                "to_user_id": self.bob.id,
                "message": "我们在同一个群里",
                "source": "group",
            }),
            content_type="application/json",
            **self._auth(self.alice),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        response = self.client.get("/api/friends/request", **self._auth(self.bob))
        self.assertEqual(response.status_code, 200)
        
        requests = response.json()["requests"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["from_user"]["user_id"], self.alice.id)
        self.assertEqual(requests[0]["source"], "group")
        self.assertEqual(requests[0]["message"], "我们在同一个群里")
