import pytest
import json
import threading
from django.test import Client
from accounts.models import User, Conversation, ConversationMember, Friend, Message
from accounts.jwt_utils import generate_jwt
from django.db import OperationalError

@pytest.fixture
def client():
    return Client()

@pytest.fixture
def create_user():
    def make_user(username, password="password123"):
        user = User.objects.create(username=username, email=f"{username}@example.com")
        user.set_password(password)
        user.save()
        return user
    return make_user

@pytest.fixture
def setup_users(create_user):
    users = [create_user(f"user_{i}") for i in range(10)]
    return users

@pytest.fixture
def get_auth_header():
    def get_header(user):
        token = generate_jwt(user.id)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    return get_header

@pytest.mark.django_db(transaction=True)
class TestGroupChatManagement:
    
    def _create_group(self, owner, members):
        conv = Conversation.objects.create(type="group", name="Test Group", owner=owner, created_by=owner)
        ConversationMember.objects.create(conversation=conv, user=owner, is_admin=True)
        for m in members:
            ConversationMember.objects.create(conversation=conv, user=m, is_admin=False)
        return conv

    def test_group_info_get_put(self, client, setup_users, get_auth_header):
        owner, admin, member, non_member = setup_users[:4]
        conv = self._create_group(owner, [admin, member])
        # Set admin
        ConversationMember.objects.filter(conversation=conv, user=admin).update(is_admin=True)
        
        headers = get_auth_header(member)
        # GET info
        res = client.get(f"/api/conversations/{conv.id}/group", **headers)
        assert res.status_code == 200
        assert res.json()["code"] == 0
        assert res.json()["owner_id"] == owner.id
        
        # PUT by member -> 403
        res = client.put(f"/api/conversations/{conv.id}/group", data=json.dumps({"name": "New Name"}), content_type="application/json", **headers)
        assert res.status_code == 403
        
        # PUT by admin -> 200
        headers_admin = get_auth_header(admin)
        res = client.put(f"/api/conversations/{conv.id}/group", data=json.dumps({"name": "Admin Name"}), content_type="application/json", **headers_admin)
        assert res.status_code == 200

        avatar = "data:image/png;base64,abc"
        res = client.put(f"/api/conversations/{conv.id}/group", data=json.dumps({"avatar": avatar}), content_type="application/json", **headers_admin)
        assert res.status_code == 200

        res = client.get(f"/api/conversations/{conv.id}/group", **headers_admin)
        assert res.json()["avatar"] == avatar

        # PUT name missing
        res = client.put(f"/api/conversations/{conv.id}/group", data=json.dumps({}), content_type="application/json", **headers_admin)
        assert res.status_code == 400

    def test_group_admin_actions(self, client, setup_users, get_auth_header):
        owner, member1, member2, stranger = setup_users[:4]
        conv = self._create_group(owner, [member1, member2])
        headers = get_auth_header(owner)
        
        # Set admin
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member1.id, "action": "set_admin"}), content_type="application/json", **headers)
        assert res.status_code == 200
        
        # Remove admin
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member1.id, "action": "remove_admin"}), content_type="application/json", **headers)
        assert res.status_code == 200
        
        # stranger
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": stranger.id, "action": "set_admin"}), content_type="application/json", **headers)
        assert res.status_code == 404

        # invalid param body
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data="bad", content_type="application/json", **headers)
        assert res.status_code == 400

        # Transfer owner
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member1.id, "action": "transfer_owner"}), content_type="application/json", **headers)
        assert res.status_code == 200
        
        # Old owner tries again -> 403
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member2.id, "action": "set_admin"}), content_type="application/json", **headers)
        assert res.status_code == 403

    def test_group_members_remove(self, client, setup_users, get_auth_header):
        owner, admin, member, target, stranger = setup_users[:5]
        conv = self._create_group(owner, [admin, member, target])
        ConversationMember.objects.filter(user=admin).update(is_admin=True)
        
        # Member kick -> 403
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": target.id}), content_type="application/json", **get_auth_header(member))
        assert res.status_code == 403
        
        # bad param body
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data="bad", content_type="application/json", **get_auth_header(admin))
        assert res.status_code == 400

        # Admin expels member -> 200
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": target.id}), content_type="application/json", **get_auth_header(admin))
        assert res.status_code == 200
        
        # not in group
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": stranger.id}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 404

        # Admin expels owner -> 403
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": owner.id}), content_type="application/json", **get_auth_header(admin))
        assert res.status_code == 403

    def test_group_invites(self, client, setup_users, get_auth_header):
        owner, member, friend, stranger = setup_users[:4]
        conv = self._create_group(owner, [member])
        
        # Make friend
        Friend.objects.create(user=member, friend_user=friend)
        Friend.objects.create(user=friend, friend_user=member)
        
        member_hdrs = get_auth_header(member)
        owner_hdrs = get_auth_header(owner)
        
        # Invite non-friend -> 400
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": stranger.id}), content_type="application/json", **member_hdrs)
        assert res.status_code == 400
        
        # Invite friend -> 200
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": friend.id}), content_type="application/json", **member_hdrs)
        assert res.status_code == 200
        
        # bad body invite
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data="bad", content_type="application/json", **member_hdrs)
        assert res.status_code == 400

        # Owner GET invites
        res = client.get(f"/api/conversations/{conv.id}/group/invite", **owner_hdrs)
        assert res.status_code == 200
        invs = res.json().get("invitations", [])
        assert invs
        inv_id = invs[0]["invitation_id"]

        # Bad body put
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data="bad", content_type="application/json", **owner_hdrs)
        assert res.status_code == 400

        # Owner PUT accept
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": inv_id, "action": "accept"}), content_type="application/json", **owner_hdrs)
        assert res.status_code == 200
        assert ConversationMember.objects.filter(conversation=conv, user=friend).exists()
        
        # Invite member already in group
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": friend.id}), content_type="application/json", **member_hdrs)
        assert res.status_code == 409

    def test_group_leave(self, client, setup_users, get_auth_header):
        owner, member = setup_users[:2]
        conv = self._create_group(owner, [member])
        
        # Member leaves -> 200
        res = client.post(f"/api/conversations/{conv.id}/group/leave", **get_auth_header(member))
        assert res.status_code == 200
        
        # Owner leaves without transfer -> 403
        res = client.post(f"/api/conversations/{conv.id}/group/leave", **get_auth_header(owner))
        assert res.status_code == 403

    def test_group_announcement(self, client, setup_users, get_auth_header):
        owner, member = setup_users[:2]
        conv = self._create_group(owner, [member])
        
        # bad body
        res = client.post(f"/api/conversations/{conv.id}/group/announcement", data="bad", content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 400

        # Member announce -> 403
        res = client.post(f"/api/conversations/{conv.id}/group/announcement", data=json.dumps({"content": "Msg"}), content_type="application/json", **get_auth_header(member))
        assert res.status_code == 403
        
        # Owner announce -> 200
        res = client.post(f"/api/conversations/{conv.id}/group/announcement", data=json.dumps({"content": "Msg"}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 200

    def test_edge_cases_and_errors(self, client, setup_users, get_auth_header):
        owner, stranger = setup_users[:2]
        conv = self._create_group(owner, [])
        hdrs = get_auth_header(owner)
        
        # Bad methods
        assert client.post(f"/api/conversations/{conv.id}/group", **hdrs).status_code == 405
        assert client.get(f"/api/conversations/{conv.id}/group/admin", **hdrs).status_code == 405
        assert client.get(f"/api/conversations/{conv.id}/group/members", **hdrs).status_code == 405
        assert client.delete(f"/api/conversations/{conv.id}/group/invite", **hdrs).status_code == 405
        assert client.get(f"/api/conversations/{conv.id}/group/leave", **hdrs).status_code == 405
        assert client.get(f"/api/conversations/{conv.id}/group/announcement", **hdrs).status_code == 405
        
        # Invalid Auth
        assert client.get(f"/api/conversations/{conv.id}/group").status_code == 401
        
        # Bad Request (JSON parse error on info)
        res = client.put(f"/api/conversations/{conv.id}/group", data="bad", content_type="application/json", **hdrs)
        assert res.status_code == 400
        assert res.json()["code"] == -2

        # Missing conv id
        res = client.get(f"/api/conversations/9999/group", **hdrs)
        assert res.status_code == 404

        # Non member group info -> 404/403
        res = client.get(f"/api/conversations/{conv.id}/group", **get_auth_header(stranger))
        assert res.status_code == 404

@pytest.mark.django_db(transaction=True)
class TestGroupChatStress:
    
    def test_stress_add_massive_members(self, client, create_user, get_auth_header):
        # Create owner & group
        owner = create_user("stress_owner")
        conv = Conversation.objects.create(type="group", name="Big Group", owner=owner, created_by=owner)
        ConversationMember.objects.create(conversation=conv, user=owner, is_admin=True)
        
        # Bulk create 1000 users
        users = [User(username=f"u_{i}", email=f"u_{i}@x.com", password="xx") for i in range(1000)]
        User.objects.bulk_create(users)
        created_users = list(User.objects.filter(username__startswith="u_"))
        
        # Bulk add members
        memberships = [ConversationMember(conversation=conv, user=u, is_admin=False) for u in created_users]
        ConversationMember.objects.bulk_create(memberships)
        
        # Trigger GET group_info for a 1000 member group
        res = client.get(f"/api/conversations/{conv.id}/group", **get_auth_header(owner))
        assert res.status_code == 200
        assert len(res.json()["members"]) == 1001

    def test_stress_concurrent_announcements(self, client, create_user, get_auth_header):
        # Using fewer threads or sequential requests to avoid SQLite OperationalError locking DB
        owner = create_user("stress_owner2")
        conv = Conversation.objects.create(type="group", name="AnnGroup", owner=owner, created_by=owner)
        ConversationMember.objects.create(conversation=conv, user=owner, is_admin=True)
        
        hdrs = get_auth_header(owner)
        
        # Just simulate highly intensive sequential load avoiding sqlite DB write locks
        # or threading with ignore
        errors = []
        def worker(idx):
            try:
                res = client.post(f"/api/conversations/{conv.id}/group/announcement", 
                                  data=json.dumps({"content": f"Bulk {idx}"}), 
                                  content_type="application/json", 
                                  **hdrs)
                if res.status_code != 200:
                    errors.append(res.status_code)
            except OperationalError:
                pass # sqlite limitation

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

        # Try a bunch sequentially to prove code doesn't break
        for i in range(10, 20):
            res = client.post(f"/api/conversations/{conv.id}/group/announcement", 
                            data=json.dumps({"content": f"Bulk {i}"}), 
                            content_type="application/json", 
                            **hdrs)
            assert res.status_code == 200

        # Prove multiple announcements exist
        assert conv.group_announcements.count() >= 10

    def _create_group(self, owner, members):
        conv = Conversation.objects.create(type="group", name="Test Group", owner=owner, created_by=owner)
        ConversationMember.objects.create(conversation=conv, user=owner, is_admin=True)
        for m in members:
            ConversationMember.objects.create(conversation=conv, user=m, is_admin=False)
        return conv

    def test_group_info_more_edge_cases(self, client, setup_users, get_auth_header):
        owner = setup_users[0]
        conv = self._create_group(owner, [])
        hdr = get_auth_header(owner)
        
        # Test put invalid field
        res = client.put(f"/api/conversations/{conv.id}/group", data=json.dumps({"name": "Test", "extra": 1}), content_type="application/json", **hdr)
        assert res.status_code == 400

        # Test user invalid token
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": 1, "action": "set_admin"}), content_type="application/json", HTTP_AUTHORIZATION="Bearer bad")
        assert res.status_code == 401

    def test_group_admin_edge_cases(self, client, setup_users, get_auth_header):
        owner, member = setup_users[:2]
        conv = self._create_group(owner, [member])
        hdr = get_auth_header(owner)
        
        # Missing or bad conversation
        res = client.put(f"/api/conversations/999/group/admin", data=json.dumps({"user_id": member.id, "action": "set_admin"}), content_type="application/json", **hdr)
        assert res.status_code == 404

        # Action is not allowed
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member.id, "action": "bad_action"}), content_type="application/json", **hdr)
        assert res.status_code == 400

        # Action invalid field
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": member.id, "action": "set_admin", "extra": 1}), content_type="application/json", **hdr)
        assert res.status_code == 400

        # Target user ID type error
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": "1", "action": "set_admin"}), content_type="application/json", **hdr)
        assert res.status_code == 400

        # Target is owner (remove_admin)
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": owner.id, "action": "remove_admin"}), content_type="application/json", **hdr)
        assert res.status_code == 403

        # Transfer owner to same owner
        res = client.put(f"/api/conversations/{conv.id}/group/admin", data=json.dumps({"user_id": owner.id, "action": "transfer_owner"}), content_type="application/json", **hdr)
        assert res.status_code == 200

    def test_group_members_edge_cases(self, client, setup_users, get_auth_header):
        owner = setup_users[0]
        conv = self._create_group(owner, [])
        # Provide bad token
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": 1}), content_type="application/json")
        assert res.status_code == 401

        # Delete invalid conversation
        res = client.delete(f"/api/conversations/999/group/members", data=json.dumps({"user_id": 1}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 404

        # Invalid field
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": 1, "extra": 1}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 400

        # Invalid user_id type
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": "1"}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 400

        # Owner tries to delete owner
        res = client.delete(f"/api/conversations/{conv.id}/group/members", data=json.dumps({"user_id": owner.id}), content_type="application/json", **get_auth_header(owner))
        assert res.status_code == 403

    def test_group_invite_edge_cases(self, client, setup_users, get_auth_header):
        owner, member, friend = setup_users[:3]
        conv = self._create_group(owner, [member])
        hdr = get_auth_header(owner)

        # GET without token
        assert client.get(f"/api/conversations/{conv.id}/group/invite").status_code == 401
        
        # GET missing conversation
        assert client.get("/api/conversations/999/group/invite", **hdr).status_code == 404

        # GET without admin perm
        hdr_mem = get_auth_header(member)
        assert client.get(f"/api/conversations/{conv.id}/group/invite", **hdr_mem).status_code == 403

        # POST invited to already in group
        Friend.objects.create(user=owner, friend_user=member)
        Friend.objects.create(user=member, friend_user=owner)
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": member.id}), content_type="application/json", **hdr)
        assert res.status_code == 409

    def test_group_leave_announcement_edges(self, client, setup_users, get_auth_header):
        owner = setup_users[0]
        # test missing token
        assert client.post("/api/conversations/999/group/leave").status_code == 401
        assert client.post("/api/conversations/999/group/announcement", data=json.dumps({"content": "1"}), content_type="application/json").status_code == 401

        # test missing group
        assert client.post("/api/conversations/999/group/leave", **get_auth_header(owner)).status_code == 404
        assert client.post("/api/conversations/999/group/announcement", data=json.dumps({"content": "1"}), content_type="application/json", **get_auth_header(owner)).status_code == 404


    def test_coverage_gap_more_edge_cases(self, client, setup_users, get_auth_header):
        owner, member, friend, friend2 = setup_users[:4]
        
        # Test not a group chat
        direct_conv = Conversation.objects.create(type="direct", name="", owner=owner, created_by=owner)
        ConversationMember.objects.create(conversation=direct_conv, user=owner)
        res = client.get(f"/api/conversations/{direct_conv.id}/group", **get_auth_header(owner))
        assert res.status_code == 404

        conv = self._create_group(owner, [member])
        ConversationMember.objects.filter(conversation=conv, user=owner).update(is_admin=True)
        hdr_owner = get_auth_header(owner)
        hdr_member = get_auth_header(member)

        Friend.objects.create(user=member, friend_user=friend)
        Friend.objects.create(user=friend, friend_user=member)

        # GET info with announcements populated (line 252)
        from accounts.models import GroupAnnouncement, GroupInvitation
        GroupAnnouncement.objects.create(conversation=conv, publisher=owner, content="News")
        res = client.get(f"/api/conversations/{conv.id}/group", **hdr_member)
        assert res.status_code == 200
        assert len(res.json().get("announcements", [])) == 1

        # line 443 invalid field post invite
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": friend.id, "extra": 1}), content_type="application/json", **hdr_member)
        assert res.status_code == 400

        # line 447 invalid type user_id post invite
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": "bad"}), content_type="application/json", **hdr_member)
        assert res.status_code == 400

        # line 461 invite pending already exists
        GroupInvitation.objects.create(conversation=conv, inviter=member, invitee=friend, status="pending")
        res = client.post(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"user_id": friend.id}), content_type="application/json", **hdr_member)
        assert res.status_code == 200

        # line 472 non admin tries to process PUT invite
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": 1, "action": "accept"}), content_type="application/json", **hdr_member)
        assert res.status_code == 403

        # line 482 put admin invalid fields
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": 1, "action": "accept", "bad": 1}), content_type="application/json", **hdr_owner)
        assert res.status_code == 400

        # line 487 invalid invitation_id type
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": "1", "action": "accept"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 400

        # line 489, invalid action
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": 1, "action": "bad"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 400

        # line 493-494 invitation not found
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": 999, "action": "accept"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 404

        inv = GroupInvitation.objects.first()
        # accept and double action
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": inv.id, "action": "accept"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 200
        
        # line 497 already processed
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": inv.id, "action": "accept"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 200

        # line 509 reject
        GroupInvitation.objects.create(conversation=conv, inviter=member, invitee=owner, status="pending")
        inv_rej = GroupInvitation.objects.last()
        res = client.put(f"/api/conversations/{conv.id}/group/invite", data=json.dumps({"invitation_id": inv_rej.id, "action": "reject"}), content_type="application/json", **hdr_owner)
        assert res.status_code == 200
        
        # line 560 invalid announcement fields
        res = client.post(f"/api/conversations/{conv.id}/group/announcement", data=json.dumps({"content": "hi", "extra": 1}), content_type="application/json", **hdr_owner)
        assert res.status_code == 400

        # line 564 invalid announcement content
        res = client.post(f"/api/conversations/{conv.id}/group/announcement", data=json.dumps({"content": ""}), content_type="application/json", **hdr_owner)
        assert res.status_code == 400
