import uuid
import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework_simplejwt.tokens import RefreshToken

from chat.models import (
    User, UserPrivacy, TokenBlacklist,
    Friendship, FriendRequest, FriendGroup, Blacklist, Whitelist,
    Conversation, ConversationMember, Message,
    MessageDeletion, Reaction, ReactionEvent, Bookmark,
    GroupInvitation, GroupAnnouncement, UploadedFile,
    CalendarEvent, CalendarParticipant,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def make_user(username, password='Test1234', email='', phone=''):
    user = User.objects.create_user(
        username=username, password=password, email=email, phone=phone
    )
    UserPrivacy.objects.create(user=user)
    return user


def auth_client(user):
    """SimpleBearerAuthentication: access-{user_id}-{hex}"""
    client = APIClient()
    token = f'access-{user.id}-{uuid.uuid4().hex}'
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


# ──────────────────────────────────────────────
# 1. Auth — RegisterView
# ──────────────────────────────────────────────

class RegisterViewTest(TestCase):
    URL = '/api/auth/register'

    def test_success(self):
        r = self.client.post(self.URL, {
            'username': 'alice', 'password': 'Test1234',
            'email': 'alice@example.com', 'phone': '13800138000',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['username'], 'alice')
        self.assertTrue(UserPrivacy.objects.filter(user__username='alice').exists())

    def test_missing_username(self):
        r = self.client.post(self.URL, {'password': 'Test1234'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_invalid_username_short(self):
        r = self.client.post(self.URL, {'username': 'ab', 'password': 'Test1234'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_invalid_username_chars(self):
        r = self.client.post(self.URL, {'username': 'ali ce!', 'password': 'Test1234'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_password_too_short(self):
        r = self.client.post(self.URL, {'username': 'alice', 'password': 'Ab1'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_password_must_have_two_character_categories(self):
        r = self.client.post(self.URL, {'username': 'alice', 'password': 'lowercaseonly'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'INVALID_PARAMS')

    def test_invalid_email(self):
        r = self.client.post(self.URL, {
            'username': 'alice', 'password': 'Test1234', 'email': 'notanemail'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_invalid_phone(self):
        r = self.client.post(self.URL, {
            'username': 'alice', 'password': 'Test1234', 'phone': '12345'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_duplicate_username(self):
        make_user('alice')
        r = self.client.post(self.URL, {'username': 'alice', 'password': 'Test1234'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'USERNAME_EXISTS')

    def test_duplicate_email(self):
        make_user('alice', email='alice@example.com')
        r = self.client.post(self.URL, {
            'username': 'bob', 'password': 'Test1234', 'email': 'alice@example.com'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'EMAIL_EXISTS')


# ──────────────────────────────────────────────
# 2. Auth — LoginView
# ──────────────────────────────────────────────

class LoginViewTest(TestCase):
    URL = '/api/auth/login'

    def setUp(self):
        self.user = make_user('alice', password='Test1234')

    def test_success(self):
        r = self.client.post(self.URL, {
            'login_type': 'username', 'identifier': 'alice', 'password': 'Test1234'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)
        self.assertEqual(len(data['access_token'].split('.')), 3)
        self.assertEqual(len(data['refresh_token'].split('.')), 3)
        self.user.refresh_from_db()
        self.assertEqual(self.user.presence, 'online')

    def test_missing_fields(self):
        r = self.client.post(self.URL, {'login_type': 'username', 'identifier': 'alice'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_invalid_login_type(self):
        r = self.client.post(self.URL, {
            'login_type': 'wechat', 'identifier': 'alice', 'password': 'Test1234'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_wrong_password(self):
        r = self.client.post(self.URL, {
            'login_type': 'username', 'identifier': 'alice', 'password': 'wrong'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_user_not_found(self):
        r = self.client.post(self.URL, {
            'login_type': 'username', 'identifier': 'nobody', 'password': 'Test1234'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_login_by_email(self):
        make_user('bob', email='bob@example.com')
        r = self.client.post(self.URL, {
            'login_type': 'email', 'identifier': 'bob@example.com', 'password': 'Test1234'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)


# ──────────────────────────────────────────────
# 3. Auth — RefreshTokenView
# ──────────────────────────────────────────────

class RefreshTokenViewTest(TestCase):
    URL = '/api/auth/refresh'

    def setUp(self):
        self.user = make_user('alice')
        self.refresh_token = f'refresh-{self.user.id}-{uuid.uuid4().hex}'

    def test_missing_token(self):
        r = self.client.post(self.URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_blacklisted_token(self):
        TokenBlacklist.objects.create(
            token=self.refresh_token, user=self.user,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        r = self.client.post(self.URL, {'refresh_token': self.refresh_token},
                             content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_invalid_token_format(self):
        r = self.client.post(self.URL, {'refresh_token': 'bad.token.here'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_valid_refresh(self):
        r = self.client.post(self.URL, {'refresh_token': self.refresh_token},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access_token', r.json())

    def test_valid_jwt_refresh(self):
        refresh_token = str(RefreshToken.for_user(self.user))
        r = self.client.post(self.URL, {'refresh_token': refresh_token},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['access_token'].split('.')), 3)


# ──────────────────────────────────────────────
# 4. Auth — LogoutView
# ──────────────────────────────────────────────

class LogoutViewTest(TestCase):
    URL = '/api/auth/logout'

    def setUp(self):
        self.user = make_user('alice')
        self.client = auth_client(self.user)
        self.refresh_token = f'refresh-{self.user.id}-{uuid.uuid4().hex}'

    def test_logout_with_token(self):
        r = self.client.post(self.URL, {'refresh_token': self.refresh_token},
                             content_type='application/json')
        self.assertEqual(r.status_code, 204)
        self.assertTrue(TokenBlacklist.objects.filter(token=self.refresh_token).exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.presence, 'offline')

    def test_logout_without_token(self):
        r = self.client.post(self.URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 204)

    @patch('chat.views.auth.send_to_user')
    def test_logout_notifies_websocket_disconnect(self, send_mock):
        r = self.client.post(self.URL, {}, content_type='application/json')

        self.assertEqual(r.status_code, 204)
        send_mock.assert_called_with(self.user.id, 'force_disconnect', {'reason': 'logout'})


# ──────────────────────────────────────────────
# 5. Auth — DeleteAccountView
# ──────────────────────────────────────────────

class DeleteAccountViewTest(TestCase):
    URL = '/api/auth/account'

    def setUp(self):
        self.user = make_user('alice', password='Test1234')
        self.api = auth_client(self.user)

    def test_wrong_password(self):
        r = self.api.delete(self.URL, {'password': 'wrong'},
                            content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_success(self):
        other = make_user('bob')
        Friendship.objects.create(user=self.user, friend=other)
        Friendship.objects.create(user=other, friend=self.user)
        user_id = self.user.id
        r = self.api.delete(self.URL, {'password': 'Test1234'},
                            content_type='application/json')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_owner_must_transfer_or_dissolve_groups_first(self):
        Conversation.objects.create(type='group', name='Owned', owner=self.user)

        r = self.api.delete(self.URL, {'password': 'Test1234'},
                            content_type='application/json')

        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'OWNED_GROUP_EXISTS')
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_group_member_delete_emits_leave_system_message(self):
        conv = Conversation.objects.create(type='group', name='Class')
        ConversationMember.objects.create(conversation=conv, user=self.user)
        user_id = self.user.id

        r = self.api.delete(self.URL, {'password': 'Test1234'},
                            content_type='application/json')

        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        system_message = Message.objects.get(conversation=conv, type='system')
        self.assertIsNone(system_message.sender)
        self.assertEqual(system_message.content['system_type'], 'member_left')


# ──────────────────────────────────────────────
# 6. Users — CurrentUserView
# ──────────────────────────────────────────────

class CurrentUserViewTest(TestCase):
    URL = '/api/users/me'

    def setUp(self):
        self.user = make_user('alice', password='Test1234', email='alice@example.com')
        self.api = auth_client(self.user)

    def test_get(self):
        r = self.api.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['username'], 'alice')
        self.assertIn('status', r.json())
        self.assertIn('privacy', r.json())

    def test_put_username(self):
        r = self.api.put(self.URL, {'username': 'alice_new'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'alice_new')

    def test_put_invalid_username(self):
        r = self.api.put(self.URL, {'username': 'a!'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_put_rejects_non_string_profile_fields(self):
        for payload in (
            {'username': 123},
            {'phone': 123},
            {'email': 123},
            {'password': 123, 'old_password': 'Test1234'},
            {'phone': '13900139000', 'old_password': 123},
        ):
            r = self.api.put(self.URL, payload, content_type='application/json')
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.json()['error']['code'], 'INVALID_PARAMS')

    def test_put_duplicate_username(self):
        make_user('bob')
        r = self.api.put(self.URL, {'username': 'bob'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 409)

    def test_put_phone(self):
        r = self.api.put(self.URL, {'phone': '13900139000', 'old_password': 'Test1234'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '13900139000')

    def test_put_phone_requires_password(self):
        r = self.api.put(self.URL, {'phone': '13900139000'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'OLD_PASSWORD_REQUIRED')

    def test_put_phone_wrong_password(self):
        r = self.api.put(self.URL, {'phone': '13900139000', 'old_password': 'wrong'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'WRONG_PASSWORD')

    def test_put_duplicate_phone(self):
        make_user('bob', phone='13900139000')
        r = self.api.put(self.URL, {'phone': '13900139000', 'old_password': 'Test1234'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'PHONE_EXISTS')

    def test_put_invalid_phone(self):
        r = self.api.put(self.URL, {'phone': '12345'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_put_email_requires_password(self):
        r = self.api.put(self.URL, {'email': 'new@example.com'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'OLD_PASSWORD_REQUIRED')

    def test_put_email_wrong_password(self):
        r = self.api.put(self.URL, {'email': 'new@example.com', 'old_password': 'wrong'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'WRONG_PASSWORD')

    def test_put_email_with_password(self):
        r = self.api.put(self.URL, {'email': 'new@example.com', 'old_password': 'Test1234'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')

    def test_put_duplicate_email(self):
        make_user('bob', email='new@example.com')
        r = self.api.put(self.URL, {'email': 'new@example.com', 'old_password': 'Test1234'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'EMAIL_EXISTS')

    def test_put_password_wrong_old(self):
        r = self.api.put(self.URL, {'old_password': 'wrong', 'password': 'NewPass1'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_put_password_no_old(self):
        r = self.api.put(self.URL, {'password': 'NewPass1'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'OLD_PASSWORD_REQUIRED')

    def test_put_password_success(self):
        r = self.api.put(self.URL, {'old_password': 'Test1234', 'password': 'NewPass1'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass1'))

    def test_put_no_fields(self):
        r = self.api.put(self.URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 200)


# ──────────────────────────────────────────────
# 8. Users — AvatarUploadView
# ──────────────────────────────────────────────

class AvatarUploadViewTest(TestCase):
    URL = '/api/users/me/avatar'

    def setUp(self):
        self.user = make_user('alice')
        self.api = auth_client(self.user)

    def test_no_file(self):
        r = self.api.post(self.URL, {})
        self.assertEqual(r.status_code, 400)

    def test_success(self):
        img = SimpleUploadedFile('avatar.png', b'\x89PNG\r\n', content_type='image/png')
        r = self.api.post(self.URL, {'file': img}, format='multipart')
        self.assertEqual(r.status_code, 200)
        self.assertIn('avatar', r.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)


# ──────────────────────────────────────────────
# 9. Users — UserSearchView
# ──────────────────────────────────────────────

class UserSearchViewTest(TestCase):
    URL = '/api/users/search'

    def setUp(self):
        self.user = make_user('alice')
        self.api = auth_client(self.user)
        make_user('bob_jones')
        make_user('bobby')

    def test_no_keyword(self):
        r = self.api.get(self.URL)
        self.assertEqual(r.status_code, 400)

    def test_search_by_username(self):
        r = self.api.get(self.URL + '?keyword=bob')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['total'], 2)
        self.assertIn('status', data['results'][0])

    def test_search_respects_username_privacy(self):
        bob = User.objects.get(username='bob_jones')
        bob.privacy.allow_search_by_username = False
        bob.privacy.save(update_fields=['allow_search_by_username'])

        r = self.api.get(self.URL + '?keyword=bob_jones')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)

    def test_pagination(self):
        r = self.api.get(self.URL + '?keyword=bob&page=1&page_size=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['results']), 1)

    def test_excludes_self(self):
        r = self.api.get(self.URL + '?keyword=alice')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)


# ──────────────────────────────────────────────
# 10. Friends — FriendRequestSendView
# ──────────────────────────────────────────────

class FriendRequestSendViewTest(TestCase):
    URL = '/api/friends/request'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)

    def test_no_target(self):
        r = self.api.post(self.URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_user_not_found(self):
        r = self.api.post(self.URL, {'target_user_id': 9999},
                          content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_self_request(self):
        r = self.api.post(self.URL, {'target_user_id': self.alice.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'SELF_REQUEST')

    def test_blacklisted(self):
        Blacklist.objects.create(user=self.bob, blocked_user=self.alice)
        r = self.api.post(self.URL, {'target_user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'USER_BLOCKED')

    def test_already_friends(self):
        Friendship.objects.create(user=self.alice, friend=self.bob)
        r = self.api.post(self.URL, {'target_user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 409)

    def test_request_already_pending(self):
        FriendRequest.objects.create(from_user=self.alice, to_user=self.bob)
        r = self.api.post(self.URL, {'target_user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 409)

    def test_success(self):
        r = self.api.post(self.URL, {'target_user_id': self.bob.id, 'message': 'hi'},
                          content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['message'], 'hi')
        self.assertEqual(r.json()['source'], 'search')
        self.assertTrue(FriendRequest.objects.filter(
            from_user=self.alice, to_user=self.bob).exists())

    def test_group_source_respects_target_privacy(self):
        conv = Conversation.objects.create(type='group', name='Class')
        ConversationMember.objects.create(conversation=conv, user=self.alice)
        ConversationMember.objects.create(conversation=conv, user=self.bob)
        self.bob.privacy.allow_add_from_group = False
        self.bob.privacy.save(update_fields=['allow_add_from_group'])

        r = self.api.post(self.URL, {
            'target_user_id': self.bob.id,
            'source': f'group:{conv.id}',
        }, content_type='application/json')

        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'PRIVACY_DENIED')

    def test_whitelist_skips_group_privacy(self):
        conv = Conversation.objects.create(type='group', name='Class')
        ConversationMember.objects.create(conversation=conv, user=self.alice)
        ConversationMember.objects.create(conversation=conv, user=self.bob)
        self.bob.privacy.allow_add_from_group = False
        self.bob.privacy.save(update_fields=['allow_add_from_group'])
        Whitelist.objects.create(user=self.bob, whitelisted_user=self.alice)

        r = self.api.post(self.URL, {
            'target_user_id': self.bob.id,
            'source': f'group:{conv.id}',
        }, content_type='application/json')

        self.assertEqual(r.status_code, 201)


# ──────────────────────────────────────────────
# 11. Friends — FriendRequestListView
# ──────────────────────────────────────────────

class FriendRequestListViewTest(TestCase):
    URL = '/api/friends/requests'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)
        FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        FriendRequest.objects.create(from_user=self.alice, to_user=self.bob,
                                     status='accepted')

    def test_list_received(self):
        r = self.api.get(self.URL + '?type=received')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 1)
        row = r.json()['results'][0]
        self.assertEqual(row['from_user']['user_id'], self.bob.id)
        self.assertEqual(row['from_user']['username'], 'bob')
        self.assertEqual(row['from_user_id'], self.bob.id)

    def test_list_sent(self):
        r = self.api.get(self.URL + '?type=sent&status=all')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 1)

    def test_list_all_status(self):
        r = self.api.get(self.URL + '?type=received&status=all')
        self.assertEqual(r.status_code, 200)

    def test_invalid_query_params(self):
        r = self.api.get(self.URL + '?type=bad')
        self.assertEqual(r.status_code, 400)
        r = self.api.get(self.URL + '?status=bad')
        self.assertEqual(r.status_code, 400)
        r = self.api.get(self.URL + '?page=bad')
        self.assertEqual(r.status_code, 400)


# ──────────────────────────────────────────────
# 12. Friends — FriendRequestHandleView
# ──────────────────────────────────────────────

class FriendRequestHandleViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.req = FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.api = auth_client(self.alice)

    def url(self, rid):
        return f'/api/friends/requests/{rid}'

    def test_not_found(self):
        r = self.api.put(self.url(9999), {'action': 'accept'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['error']['code'], 'REQUEST_NOT_FOUND')

    def test_invalid_action(self):
        r = self.api.put(self.url(self.req.id), {'action': 'ignore'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_accept(self):
        r = self.api.put(self.url(self.req.id), {'action': 'accept'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('updated_at', r.json())
        self.assertTrue(Friendship.objects.filter(user=self.alice, friend=self.bob).exists())
        self.assertTrue(Friendship.objects.filter(user=self.bob, friend=self.alice).exists())

    def test_reject(self):
        r = self.api.put(self.url(self.req.id), {'action': 'reject'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'rejected')

    def test_not_recipient(self):
        charlie = make_user('charlie')
        api = auth_client(charlie)
        r = api.put(self.url(self.req.id), {'action': 'accept'},
                    content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'NOT_RECIPIENT')

    def test_already_handled(self):
        self.req.status = 'accepted'
        self.req.save(update_fields=['status'])
        r = self.api.put(self.url(self.req.id), {'action': 'accept'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'REQUEST_ALREADY_HANDLED')


# ──────────────────────────────────────────────
# 13. Friends — FriendListView & FriendDeleteView
# ──────────────────────────────────────────────

class FriendListAndDeleteViewTest(TestCase):
    LIST_URL = '/api/friends/'

    def delete_url(self, uid):
        return f'/api/friends/{uid}'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        Friendship.objects.create(user=self.alice, friend=self.bob)
        Friendship.objects.create(user=self.bob, friend=self.alice)
        self.api = auth_client(self.alice)

    def test_list(self):
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 1)
        friend = r.json()['results'][0]
        self.assertIn('is_blocked', friend)
        self.assertIn('added_at', friend)
        self.assertEqual(r.json()['results'][0]['username'], 'bob')

    def test_invisible_friend_shows_invisible(self):
        self.bob.presence = 'invisible'
        self.bob.save(update_fields=['presence'])

        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['results'][0]['status']['presence'], 'invisible')

    def test_delete_not_found(self):
        r = self.api.delete(self.delete_url(9999))
        self.assertEqual(r.status_code, 404)

    def test_delete_success(self):
        r = self.api.delete(self.delete_url(self.bob.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Friendship.objects.filter(user=self.alice, friend=self.bob).exists())
        self.assertFalse(Friendship.objects.filter(user=self.bob, friend=self.alice).exists())


# ──────────────────────────────────────────────
# 14. Friends — FriendGroup
# ──────────────────────────────────────────────

class FriendGroupViewTest(TestCase):
    LIST_URL = '/api/friends/groups'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        Friendship.objects.create(user=self.alice, friend=self.bob)
        self.api = auth_client(self.alice)

    def test_list_groups(self):
        FriendGroup.objects.create(user=self.alice, name='同学')
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['groups']), 1)
        self.assertEqual(r.json()['ungrouped_count'], 1)

    def test_create_no_name(self):
        r = self.api.post(self.LIST_URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_create_duplicate(self):
        FriendGroup.objects.create(user=self.alice, name='同学')
        r = self.api.post(self.LIST_URL, {'name': '同学'},
                          content_type='application/json')
        self.assertEqual(r.status_code, 409)

    def test_create_success(self):
        r = self.api.post(self.LIST_URL, {'name': '同事'},
                          content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['name'], '同事')

    def test_put_rename(self):
        g = FriendGroup.objects.create(user=self.alice, name='旧名')
        r = self.api.put(f'{self.LIST_URL}/{g.id}', {'name': '新名'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.name, '新名')

    def test_put_not_found(self):
        r = self.api.put(f'{self.LIST_URL}/9999', {'name': 'x'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_put_add_and_remove_friends(self):
        g = FriendGroup.objects.create(user=self.alice, name='同学')
        self.api.put(f'{self.LIST_URL}/{g.id}',
                     {'add_friend_ids': [self.bob.id]},
                     content_type='application/json')
        fs = Friendship.objects.get(user=self.alice, friend=self.bob)
        self.assertEqual(fs.group, g)

        self.api.put(f'{self.LIST_URL}/{g.id}',
                     {'remove_friend_ids': [self.bob.id]},
                     content_type='application/json')
        fs.refresh_from_db()
        self.assertIsNone(fs.group)

    def test_delete_group(self):
        g = FriendGroup.objects.create(user=self.alice, name='同学')
        fs = Friendship.objects.get(user=self.alice, friend=self.bob)
        fs.group = g
        fs.save()
        r = self.api.delete(f'{self.LIST_URL}/{g.id}')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(FriendGroup.objects.filter(pk=g.id).exists())
        fs.refresh_from_db()
        self.assertIsNone(fs.group)

    def test_delete_group_not_found(self):
        r = self.api.delete(f'{self.LIST_URL}/9999')
        self.assertEqual(r.status_code, 404)


# ──────────────────────────────────────────────
# 15. Users — UserDetailView
# ──────────────────────────────────────────────

class UserDetailViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)

    def url(self, uid):
        return f'/api/users/{uid}'

    def test_user_not_found(self):
        r = self.api.get(self.url(9999))
        self.assertEqual(r.status_code, 404)

    def test_not_friend(self):
        r = self.api.get(self.url(self.bob.id))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['is_friend'])

    def test_is_friend(self):
        Friendship.objects.create(user=self.alice, friend=self.bob, remark='Bob同学')
        r = self.api.get(self.url(self.bob.id))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['is_friend'])
        self.assertEqual(r.json()['remark'], 'Bob同学')
        self.assertIn('created_at', r.json())

    def test_invisible_shows_invisible(self):
        self.bob.presence = 'invisible'
        self.bob.save()
        r = self.api.get(self.url(self.bob.id))
        self.assertEqual(r.json()['status']['presence'], 'invisible')

    def test_is_blocked(self):
        Blacklist.objects.create(user=self.alice, blocked_user=self.bob)
        r = self.api.get(self.url(self.bob.id))
        self.assertTrue(r.json()['is_blocked'])


# ──────────────────────────────────────────────
# 16. Users — PrivacySettingsView
# ──────────────────────────────────────────────

class PrivacySettingsViewTest(TestCase):
    URL = '/api/users/me/privacy'

    def setUp(self):
        self.user = make_user('alice')
        self.api = auth_client(self.user)

    def test_get(self):
        r = self.api.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertIn('allow_search_by_username', r.json())

    def test_put_success(self):
        r = self.api.put(self.URL, {'allow_search_by_email': False},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['allow_search_by_email'])

    def test_put_no_fields(self):
        r = self.api.put(self.URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 200)


# ──────────────────────────────────────────────
# 17. Users — UserStatusView
# ──────────────────────────────────────────────

class UserStatusViewTest(TestCase):
    URL = '/api/users/me/status'

    def setUp(self):
        self.user = make_user('alice')
        self.api = auth_client(self.user)

    def test_set_presence(self):
        r = self.api.put(self.URL, {'presence': 'busy'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.presence, 'busy')

    def test_invalid_presence(self):
        r = self.api.put(self.URL, {'presence': 'gaming'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_rejects_non_string_status_fields(self):
        for payload in (
            {'presence': 1},
            {'status_text': 123},
            {'status_emoji': 123},
        ):
            r = self.api.put(self.URL, payload, content_type='application/json')
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.json()['error']['code'], 'INVALID_PARAMS')

    def test_set_status_text(self):
        r = self.api.put(self.URL, {'status_text': '开会中'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.status_text, '开会中')

    def test_set_emoji(self):
        r = self.api.put(self.URL, {'status_emoji': '🔥'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)


class UserAIKeyViewTest(TestCase):
    URL = '/api/users/me/ai-key'

    def setUp(self):
        self.user = make_user('alice')
        self.api = auth_client(self.user)

    def test_get_ai_key_status(self):
        r = self.api.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['configured'])
        self.assertEqual(r.json()['masked_key'], '')

    def test_set_and_clear_ai_key(self):
        r = self.api.put(self.URL, {'api_key': 'QC-test-secret-key'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['configured'])
        self.assertNotIn('QC-test-secret-key', r.content.decode('utf-8'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.ai_api_key, 'QC-test-secret-key')

        r = self.api.delete(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['configured'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.ai_api_key, '')

    def test_reject_invalid_ai_key(self):
        r = self.api.put(self.URL, {'api_key': 'short'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)


# ──────────────────────────────────────────────
# 18. Friends — FriendRemarkView
# ──────────────────────────────────────────────

class FriendRemarkViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        Friendship.objects.create(user=self.alice, friend=self.bob)
        self.api = auth_client(self.alice)

    def url(self, uid):
        return f'/api/friends/{uid}/remark'

    def test_not_found(self):
        r = self.api.put(self.url(9999), {'remark': 'test'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_remark_too_long(self):
        r = self.api.put(self.url(self.bob.id), {'remark': 'x' * 31},
                         content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_success(self):
        r = self.api.put(self.url(self.bob.id), {'remark': '老板'},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['remark'], '老板')
        fs = Friendship.objects.get(user=self.alice, friend=self.bob)
        self.assertEqual(fs.remark, '老板')

    def test_clear_remark(self):
        r = self.api.put(self.url(self.bob.id), {'remark': ''},
                         content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['remark'], '')


# ──────────────────────────────────────────────
# 19. Friends — BlacklistView
# ──────────────────────────────────────────────

class BlacklistViewTest(TestCase):
    LIST_URL = '/api/friends/blacklist'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)

    def test_get_empty(self):
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)

    def test_post_no_user_id(self):
        r = self.api.post(self.LIST_URL, {}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_post_self(self):
        r = self.api.post(self.LIST_URL, {'user_id': self.alice.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], 'SELF_BLOCK')

    def test_post_not_found(self):
        r = self.api.post(self.LIST_URL, {'user_id': 9999},
                          content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_post_success(self):
        r = self.api.post(self.LIST_URL, {'user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('blocked_at', r.json())
        self.assertTrue(Blacklist.objects.filter(user=self.alice, blocked_user=self.bob).exists())

    def test_post_duplicate(self):
        Blacklist.objects.create(user=self.alice, blocked_user=self.bob)
        r = self.api.post(self.LIST_URL, {'user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error']['code'], 'ALREADY_BLOCKED')

    def test_get_with_entry(self):
        Blacklist.objects.create(user=self.alice, blocked_user=self.bob)
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.json()['total'], 1)
        self.assertEqual(r.json()['results'][0]['username'], 'bob')

    def test_delete_success(self):
        Blacklist.objects.create(user=self.alice, blocked_user=self.bob)
        r = self.api.delete(f'{self.LIST_URL}/{self.bob.id}')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Blacklist.objects.filter(user=self.alice, blocked_user=self.bob).exists())

    def test_delete_not_found(self):
        r = self.api.delete(f'{self.LIST_URL}/9999')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['error']['code'], 'NOT_IN_BLACKLIST')


# ──────────────────────────────────────────────
# 20. Friends — WhitelistView
# ──────────────────────────────────────────────

class WhitelistViewTest(TestCase):
    LIST_URL = '/api/friends/whitelist'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)

    def test_get_empty(self):
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)

    def test_post_self(self):
        r = self.api.post(self.LIST_URL, {'user_id': self.alice.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_post_not_found(self):
        r = self.api.post(self.LIST_URL, {'user_id': 9999},
                          content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_post_success(self):
        r = self.api.post(self.LIST_URL, {'user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('added_at', r.json())

    def test_post_duplicate(self):
        from chat.models import Whitelist
        Whitelist.objects.create(user=self.alice, whitelisted_user=self.bob)
        r = self.api.post(self.LIST_URL, {'user_id': self.bob.id},
                          content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_get_with_entry(self):
        from chat.models import Whitelist
        Whitelist.objects.create(user=self.alice, whitelisted_user=self.bob)
        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.json()['total'], 1)

    def test_delete_success(self):
        from chat.models import Whitelist
        Whitelist.objects.create(user=self.alice, whitelisted_user=self.bob)
        r = self.api.delete(f'{self.LIST_URL}/{self.bob.id}')
        self.assertEqual(r.status_code, 204)

    def test_delete_not_found(self):
        r = self.api.delete(f'{self.LIST_URL}/9999')
        self.assertEqual(r.status_code, 404)


# ──────────────────────────────────────────────
# 21. Conversations — list/create/update/read/search
# ──────────────────────────────────────────────

class ConversationViewTest(TestCase):
    LIST_URL = '/api/conversations/'

    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.charlie = make_user('charlie')
        self.api = auth_client(self.alice)

        Friendship.objects.create(user=self.alice, friend=self.bob)
        Friendship.objects.create(user=self.bob, friend=self.alice)
        Friendship.objects.create(user=self.alice, friend=self.charlie)
        Friendship.objects.create(user=self.charlie, friend=self.alice)

    def test_private_create_list_conflict_and_membership_ops(self):
        r = self.api.post(self.LIST_URL, {
            'type': 'private', 'peer_user_id': self.bob.id,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        conv_id = r.json()['conversation_id']

        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['total'], 1)

        r = self.api.post(self.LIST_URL, {
            'type': 'private', 'peer_user_id': self.bob.id,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 409)

        r = self.api.put(f'/api/conversations/{conv_id}', {
            'is_pinned': True,
            'is_muted': False,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)

        Message.objects.create(
            conversation_id=conv_id,
            sender=self.bob,
            type='text',
            content={'text': 'hello from bob'},
        )

        r = self.api.put(f'/api/conversations/{conv_id}/read', {}, content_type='application/json')
        self.assertEqual(r.status_code, 204)

        r = self.api.delete(f'/api/conversations/{conv_id}')
        self.assertEqual(r.status_code, 204)

        cm = ConversationMember.objects.get(conversation_id=conv_id, user=self.alice)
        self.assertTrue(cm.is_deleted)

    def test_group_create_and_search(self):
        r = self.api.post(self.LIST_URL, {
            'type': 'group',
            'name': '项目组',
            'member_ids': [self.bob.id, self.charlie.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        conv_id = r.json()['conversation_id']

        Message.objects.create(
            conversation_id=conv_id,
            sender=self.bob,
            type='text',
            content={'text': '会议纪要 v1'},
        )

        r = self.api.get('/api/conversations/search?keyword=会议')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['total'], 1)

        r = self.api.get(f'/api/conversations/search?keyword=会议&conversation_id={conv_id}')
        self.assertEqual(r.status_code, 200)

    def test_unread_count_ignores_messages_from_other_conversations(self):
        target = Conversation.objects.create(type='private', name='')
        target_member = ConversationMember.objects.create(
            conversation=target,
            user=self.alice,
            role='member',
        )
        ConversationMember.objects.create(conversation=target, user=self.bob, role='member')

        other = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=other, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=other, user=self.charlie, role='member')

        first_read = Message.objects.create(
            conversation=target,
            sender=self.bob,
            type='text',
            content={'text': 'already read'},
        )
        target_member.read_index = first_read.id
        target_member.save(update_fields=['read_index'])

        for i in range(5):
            Message.objects.create(
                conversation=other,
                sender=self.charlie,
                type='text',
                content={'text': f'interleaved {i}'},
            )

        Message.objects.create(
            conversation=target,
            sender=self.bob,
            type='text',
            content={'text': 'actually unread'},
        )

        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        row = next(item for item in r.json()['results'] if item['conversation_id'] == target.id)
        self.assertEqual(row['unread_count'], 1)

        r = self.api.get(f'/api/conversations/{target.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['unread_count'], 1)

    def test_unread_count_ignores_messages_sent_by_self(self):
        conv = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=conv, user=self.bob, role='member')

        Message.objects.create(
            conversation=conv,
            sender=self.alice,
            type='text',
            content={'text': 'sent by me'},
        )
        Message.objects.create(
            conversation=conv,
            sender=self.alice,
            type='text',
            content={'text': 'also sent by me'},
        )

        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        row = next(item for item in r.json()['results'] if item['conversation_id'] == conv.id)
        self.assertEqual(row['unread_count'], 0)

        r = self.api.get(f'/api/conversations/{conv.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['unread_count'], 0)

        Message.objects.create(
            conversation=conv,
            sender=self.bob,
            type='text',
            content={'text': 'sent by peer'},
        )

        r = self.api.get(self.LIST_URL)
        self.assertEqual(r.status_code, 200)
        row = next(item for item in r.json()['results'] if item['conversation_id'] == conv.id)
        self.assertEqual(row['unread_count'], 1)

# ──────────────────────────────────────────────
# 22. Messages — send/list/reply/read/delete/recall/forward/reaction/bookmark
# ──────────────────────────────────────────────

class MessageViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.alice.ai_api_key = 'QC-test-secret-key'
        self.alice.save(update_fields=['ai_api_key'])
        self.bob = make_user('bob')
        self.charlie = make_user('charlie')
        self.api = auth_client(self.alice)

        Friendship.objects.create(user=self.alice, friend=self.bob)
        Friendship.objects.create(user=self.bob, friend=self.alice)
        Friendship.objects.create(user=self.alice, friend=self.charlie)
        Friendship.objects.create(user=self.charlie, friend=self.alice)

        self.private = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=self.private, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=self.private, user=self.bob, role='member')

        self.group = Conversation.objects.create(type='group', name='技术群', owner=self.alice)
        ConversationMember.objects.create(conversation=self.group, user=self.alice, role='owner')
        ConversationMember.objects.create(conversation=self.group, user=self.bob, role='member')
        ConversationMember.objects.create(conversation=self.group, user=self.charlie, role='member')

    def test_send_list_reply_read_delete_recall(self):
        r = self.api.post(f'/api/conversations/{self.private.id}/messages', {
            'type': 'text',
            'content': {'text': 'hello'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        msg_id = r.json()['msg_id']

        r = self.api.post(f'/api/conversations/{self.private.id}/messages', {
            'type': 'text',
            'content': {'text': 'reply'},
            'reply_to_msg_id': msg_id,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        reply_id = r.json()['msg_id']

        r = self.api.get(f'/api/conversations/{self.private.id}/messages')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['total'], 2)
        first_message = r.json()['results'][0]
        self.assertIn('sender', first_message)
        self.assertIn('reply_count', first_message)
        self.assertIn('mentions', first_message)

        r = self.api.get(f'/api/conversations/{self.private.id}/messages/{msg_id}/replies')
        self.assertEqual(r.status_code, 200)

        r = self.api.get(f'/api/conversations/{self.private.id}/messages/{msg_id}/read-status')
        self.assertEqual(r.status_code, 200)
        self.assertIn('peer_is_read', r.json())

        r = self.api.delete(f'/api/conversations/{self.private.id}/messages/{reply_id}')
        self.assertEqual(r.status_code, 204)
        self.assertTrue(MessageDeletion.objects.filter(user=self.alice, message_id=reply_id).exists())

        r = self.api.post(f'/api/conversations/{self.private.id}/messages/{msg_id}/recall', {}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        recalled = Message.objects.get(id=msg_id, is_recalled=True)
        self.assertEqual(recalled.recalled_by_id, self.alice.id)

    def test_reaction_forward_bookmark_and_blocked(self):
        base_msg = Message.objects.create(
            conversation=self.group,
            sender=self.bob,
            type='text',
            content={'text': 'need reaction'},
        )

        r = self.api.post(f'/api/conversations/{self.group.id}/messages/{base_msg.id}/reactions', {
            'emoji': '👍'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['user_id'], self.alice.id)
        self.assertTrue(Reaction.objects.filter(message=base_msg, user=self.alice, emoji='👍').exists())
        self.assertTrue(ReactionEvent.objects.filter(message=base_msg, user=self.alice, emoji='👍', action='add').exists())

        r = self.api.get(f'/api/conversations/{self.group.id}/messages')
        self.assertEqual(r.status_code, 200)
        reaction = r.json()['results'][0]['reactions'][0]
        self.assertEqual(reaction['emoji'], '👍')
        self.assertEqual(reaction['users'], [self.alice.id])
        self.assertTrue(reaction['is_me'])

        r = self.api.delete(f'/api/conversations/{self.group.id}/messages/{base_msg.id}/reactions/👍')
        self.assertEqual(r.status_code, 204)
        self.assertTrue(ReactionEvent.objects.filter(message=base_msg, user=self.alice, emoji='👍', action='remove').exists())

        target = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=target, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=target, user=self.bob, role='member')

        r = self.api.post('/api/messages/forward', {
            'mode': 'individual',
            'source_conv_id': self.group.id,
            'msg_ids': [base_msg.id],
            'target_conv_ids': [target.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data['target_conversations'][0]['conversation_id'], target.id)
        self.assertEqual(len(data['target_conversations'][0]['msg_ids']), 1)

        r = self.api.post('/api/bookmarks', {
            'msg_id': base_msg.id,
            'conversation_id': self.group.id,
            'note': 'important',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        bookmark_payload = r.json()
        bookmark_id = bookmark_payload['bookmark_id']
        self.assertFalse(bookmark_payload['is_archived'])
        self.assertGreater(bookmark_payload['position'], 0)

        r = self.api.get('/api/bookmarks')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['total'], 1)
        self.assertIn('position', r.json()['results'][0])

        r = self.api.put(f'/api/bookmarks/{bookmark_id}', {
            'is_archived': True,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['is_archived'])

        r = self.api.get('/api/bookmarks?archived=true')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['results'][0]['bookmark_id'], bookmark_id)

        r = self.api.delete(f'/api/bookmarks/{bookmark_id}')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Bookmark.objects.filter(id=bookmark_id).exists())

        Blacklist.objects.create(user=self.bob, blocked_user=self.alice)
        r = self.api.post(f'/api/conversations/{self.private.id}/messages', {
            'type': 'text',
            'content': {'text': 'blocked message'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 403)

    @patch('chat.views.ai._call_llm', return_value='群聊 AI 回复')
    def test_group_message_can_mention_ai(self, mocked_call):
        from chat.views.ai import _get_ai_user

        ai_user = _get_ai_user()
        r = self.api.post(f'/api/conversations/{self.group.id}/messages', {
            'type': 'text',
            'content': {'text': '@AI 请总结一下'},
            'mentions': [ai_user.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            Message.objects.filter(
                conversation=self.group,
                sender=ai_user,
                content__text='群聊 AI 回复',
            ).exists()
        )
        mocked_call.assert_called_once()

    @patch('chat.views.ai._call_llm', return_value='群聊 AI 文本触发回复')
    def test_group_message_can_trigger_ai_by_text(self, mocked_call):
        from chat.views.ai import _get_ai_user

        ai_user = _get_ai_user()
        r = self.api.post(f'/api/conversations/{self.group.id}/messages', {
            'type': 'text',
            'content': {'text': '@AI 请总结一下'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            Message.objects.filter(
                conversation=self.group,
                sender=ai_user,
                content__text='群聊 AI 文本触发回复',
            ).exists()
        )
        mocked_call.assert_called_once()

    def test_group_ai_requires_user_key(self):
        self.alice.ai_api_key = ''
        self.alice.save(update_fields=['ai_api_key'])
        r = self.api.post(f'/api/conversations/{self.group.id}/messages', {
            'type': 'text',
            'content': {'text': '@AI 请总结一下'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'AI_API_KEY_REQUIRED')


# ──────────────────────────────────────────────
# 23. Groups — info/avatar/member/admin/owner/invitation/announcement/dissolve
# ──────────────────────────────────────────────

class GroupViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.charlie = make_user('charlie')
        self.david = make_user('david')

        self.api_owner = auth_client(self.alice)
        self.api_admin = auth_client(self.bob)
        self.api_member = auth_client(self.charlie)

        Friendship.objects.create(user=self.alice, friend=self.david)
        Friendship.objects.create(user=self.david, friend=self.alice)

        self.group = Conversation.objects.create(type='group', name='初始群', owner=self.alice)
        ConversationMember.objects.create(conversation=self.group, user=self.alice, role='owner')
        ConversationMember.objects.create(conversation=self.group, user=self.bob, role='admin')
        ConversationMember.objects.create(conversation=self.group, user=self.charlie, role='member')

    def test_group_info_update_announcement_and_member_ops(self):
        r = self.api_owner.get(f'/api/conversations/{self.group.id}/group')
        self.assertEqual(r.status_code, 200)
        self.assertIn('my_group_nickname', r.json())

        r = self.api_owner.put(f'/api/conversations/{self.group.id}/group', {
            'name': '重命名群'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)

        r = self.api_owner.post(f'/api/conversations/{self.group.id}/group/announcements', {
            'content': '周五开会'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(GroupAnnouncement.objects.filter(conversation=self.group).exists())

        r = self.api_owner.get(f'/api/conversations/{self.group.id}/group/announcements')
        self.assertEqual(r.status_code, 200)

        r = self.api_member.put(f'/api/conversations/{self.group.id}/group/my-nickname', {
            'nickname': '前端同学'
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)

        r = self.api_owner.get(f'/api/conversations/{self.group.id}/group/members')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['total'], 3)
        self.assertIn('status', r.json()['results'][0])

        r = self.api_admin.delete(f'/api/conversations/{self.group.id}/group/members/{self.charlie.id}')
        self.assertEqual(r.status_code, 204)
        self.assertTrue(
            ConversationMember.objects.get(conversation=self.group, user=self.charlie).is_removed
        )

        r = self.api_owner.post(f'/api/conversations/{self.group.id}/messages', {
            'type': 'text',
            'content': {'text': 'hello after removal'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            ConversationMember.objects.get(conversation=self.group, user=self.charlie).is_removed
        )

    @override_settings(MEDIA_ROOT=tempfile.gettempdir(), MEDIA_URL='/media/')
    def test_group_avatar_admin_owner_invitation_and_dissolve(self):
        image = SimpleUploadedFile('group.png', b'\x89PNG\r\n', content_type='image/png')
        r = self.api_owner.post(
            f'/api/conversations/{self.group.id}/group/avatar',
            {'file': image},
            format='multipart'
        )
        self.assertEqual(r.status_code, 200)

        # owner 给成员设置管理员
        r = self.api_owner.post(f'/api/conversations/{self.group.id}/group/admins', {
            'user_id': self.charlie.id
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201 if r.status_code == 201 else 200)

        # owner 取消 bob 管理员
        r = self.api_owner.delete(f'/api/conversations/{self.group.id}/group/admins/{self.bob.id}')
        self.assertIn(r.status_code, (204, 409))

        # owner 邀请好友入群
        r = self.api_owner.post(f'/api/conversations/{self.group.id}/group/invitations', {
            'user_ids': [self.david.id]
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        invitation_id = r.json()['invitations'][0]['invitation_id']
        self.assertTrue(GroupInvitation.objects.filter(id=invitation_id).exists())

        # admin/owner 获取邀请列表并审核
        r = self.api_owner.get(f'/api/conversations/{self.group.id}/group/invitations?status=pending')
        self.assertEqual(r.status_code, 200)

        r = self.api_owner.put(
            f'/api/conversations/{self.group.id}/group/invitations/{invitation_id}',
            {'action': 'approve'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)

        # 转让群主给 bob
        r = self.api_owner.put(f'/api/conversations/{self.group.id}/group/owner', {
            'new_owner_id': self.bob.id
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)

        # 新群主解散群聊
        r = self.api_admin.delete(f'/api/conversations/{self.group.id}/group', {
            'confirm': True,
        }, content_type='application/json')
        self.assertEqual(r.status_code, 204)

        r = self.api_admin.post(f'/api/conversations/{self.group.id}/messages', {
            'type': 'text',
            'content': {'text': 'should not send'},
        }, content_type='application/json')
        self.assertEqual(r.status_code, 404)

        r = self.api_admin.get(f'/api/conversations/{self.group.id}/messages')
        self.assertEqual(r.status_code, 200)

# ──────────────────────────────────────────────
# 24. Coverage boost — edge cases for auth/conversations/messages/groups
# ──────────────────────────────────────────────

class CoverageBoostEdgeCaseTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.charlie = make_user('charlie')
        self.david = make_user('david')

        self.api_alice = auth_client(self.alice)
        self.api_bob = auth_client(self.bob)
        self.api_charlie = auth_client(self.charlie)

        Friendship.objects.create(user=self.alice, friend=self.bob)
        Friendship.objects.create(user=self.bob, friend=self.alice)

        self.private = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=self.private, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=self.private, user=self.bob, role='member')

        self.group = Conversation.objects.create(type='group', name='edge-group', owner=self.alice)
        ConversationMember.objects.create(conversation=self.group, user=self.alice, role='owner')
        ConversationMember.objects.create(conversation=self.group, user=self.bob, role='admin')
        ConversationMember.objects.create(conversation=self.group, user=self.charlie, role='member')

    def test_auth_invalid_bearer_tokens(self):
        client = APIClient()

        client.credentials(HTTP_AUTHORIZATION='Bearer bad-token')
        r = client.get('/api/users/me')
        self.assertIn(r.status_code, (401, 403))

        client.credentials(HTTP_AUTHORIZATION='Bearer access-abc-xyz')
        r = client.get('/api/users/me')
        self.assertIn(r.status_code, (401, 403))

        client.credentials(HTTP_AUTHORIZATION='Bearer access-999999-xyz')
        r = client.get('/api/users/me')
        self.assertIn(r.status_code, (401, 403))

    def test_conversation_create_validation_errors(self):
        r = self.api_alice.post('/api/conversations/', {'type': 'unknown'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/conversations/', {'type': 'private'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/conversations/', {'type': 'private', 'peer_user_id': 'abc'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/conversations/', {'type': 'private', 'peer_user_id': self.alice.id}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/conversations/', {'type': 'private', 'peer_user_id': self.charlie.id}, content_type='application/json')
        self.assertEqual(r.status_code, 403)

        r = self.api_alice.post('/api/conversations/', {
            'type': 'group',
            'name': 'x',
            'member_ids': ['bad-id'],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_conversation_update_read_and_search_validation(self):
        r = self.api_alice.get(f'/api/conversations/{self.private.id}')
        self.assertEqual(r.status_code, 200)

        r = self.api_alice.put(
            f'/api/conversations/{self.private.id}',
            {'is_pinned': 'yes'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.put(
            f'/api/conversations/{self.private.id}',
            {'is_muted': 'no'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.put(f'/api/conversations/{self.private.id}/read', {'last_read_msg_id': 'bad'}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.put(f'/api/conversations/{self.private.id}/read', {'last_read_msg_id': -1}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.put(f'/api/conversations/{self.private.id}/read', {'last_read_msg_id': 999999}, content_type='application/json')
        self.assertEqual(r.status_code, 404)

        r = self.api_alice.get('/api/conversations/search')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.get('/api/conversations/search?keyword=x&conversation_id=bad')
        self.assertEqual(r.status_code, 400)

        outsider_conv = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=outsider_conv, user=self.bob, role='member')
        ConversationMember.objects.create(conversation=outsider_conv, user=self.charlie, role='member')
        r = self.api_alice.get(f'/api/conversations/search?keyword=x&conversation_id={outsider_conv.id}')
        self.assertEqual(r.status_code, 403)

    def test_message_send_and_recall_validation(self):
        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages',
            {'type': 'invalid', 'content': {'text': 'x'}},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages',
            {'type': 'text', 'content': {}},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages',
            {'type': 'text', 'content': {'text': 'ok'}, 'reply_to_msg_id': 'bad'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages',
            {'type': 'text', 'content': {'text': 'ok'}, 'mentions': 'not-a-list'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages',
            {'type': 'text', 'content': {'text': 'ok'}, 'mentions': [self.bob.id]},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        msg_by_bob = Message.objects.create(
            conversation=self.private,
            sender=self.bob,
            type='text',
            content={'text': 'from bob'},
        )
        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages/{msg_by_bob.id}/recall',
            {},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 403)

        msg_recalled = Message.objects.create(
            conversation=self.private,
            sender=self.alice,
            type='text',
            content={'text': 'already recalled'},
            is_recalled=True,
        )
        r = self.api_alice.post(
            f'/api/conversations/{self.private.id}/messages/{msg_recalled.id}/recall',
            {},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 409)

    def test_message_forward_reaction_and_bookmark_validation(self):
        source_msg = Message.objects.create(
            conversation=self.group,
            sender=self.bob,
            type='text',
            content={'text': 'forward source'},
        )

        r = self.api_alice.post('/api/messages/forward', {
            'mode': 'bad',
            'source_conv_id': self.group.id,
            'msg_ids': [source_msg.id],
            'target_conv_ids': [self.private.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/messages/forward', {
            'mode': 'individual',
            'source_conv_id': self.group.id,
            'msg_ids': [],
            'target_conv_ids': [self.private.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post('/api/messages/forward', {
            'mode': 'individual',
            'source_conv_id': self.group.id,
            'msg_ids': [source_msg.id, source_msg.id],
            'target_conv_ids': [self.private.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.group.id}/messages/{source_msg.id}/reactions',
            {'emoji': '👍'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 201)

        r = self.api_alice.post(
            f'/api/conversations/{self.group.id}/messages/{source_msg.id}/reactions',
            {'emoji': '👍'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 409)

        r = self.api_alice.post('/api/bookmarks', {
            'msg_id': source_msg.id,
            'conversation_id': self.group.id,
            'note': 'edge',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)

        r = self.api_alice.post('/api/bookmarks', {
            'msg_id': source_msg.id,
            'conversation_id': self.group.id,
            'note': 'dup',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 409)

        r = self.api_alice.post('/api/bookmarks', {
            'title': '手动待办',
            'note': '自己添加',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['title'], '手动待办')
        self.assertIsNone(r.json()['message'])

    def test_group_permission_and_validation_errors(self):
        r = self.api_charlie.put(
            f'/api/conversations/{self.group.id}/group',
            {'name': 'member rename'},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 403)

        r = self.api_alice.delete(
            f'/api/conversations/{self.group.id}/group',
            {'confirm': False},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_bob.post(
            f'/api/conversations/{self.group.id}/group/admins',
            {'user_id': self.charlie.id},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 403)

        r = self.api_alice.put(
            f'/api/conversations/{self.group.id}/group/owner',
            {'new_owner_id': self.alice.id},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

        r = self.api_charlie.delete(f'/api/conversations/{self.group.id}/group/members/{self.charlie.id}')
        self.assertEqual(r.status_code, 403)

        r = self.api_charlie.get(f'/api/conversations/{self.group.id}/group/invitations?status=all')
        self.assertEqual(r.status_code, 403)

        r = self.api_alice.get(f'/api/conversations/{self.group.id}/group/invitations?status=unknown')
        self.assertEqual(r.status_code, 400)

        r = self.api_alice.post(
            f'/api/conversations/{self.group.id}/group/announcements',
            {'content': ''},
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)


# ──────────────────────────────────────────────
# 25. Upload — files and media metadata
# ──────────────────────────────────────────────

class UploadViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.api = auth_client(self.alice)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir(), MEDIA_URL='/media/')
    def test_upload_image_returns_metadata(self):
        image = SimpleUploadedFile(
            'avatar.png',
            (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                b'\x00\x00\x00\x01\x00\x00\x00\x01'
                b'\x08\x02\x00\x00\x00\x90wS\xde'
                b'\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xe2\x8a\xb3'
                b'\x00\x00\x00\x00IEND\xaeB`\x82'
            ),
            content_type='image/png',
        )
        r = self.api.post('/api/upload', {
            'purpose': 'message',
            'file': image,
        }, format='multipart')
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data['mime_type'], 'image/png')
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertIsNotNone(data['thumbnail_url'])
        self.assertTrue(UploadedFile.objects.filter(file_id=data['file_id']).exists())

    def test_upload_requires_file_and_valid_purpose(self):
        r = self.api.post('/api/upload', {'purpose': 'message'}, format='multipart')
        self.assertEqual(r.status_code, 400)

        file = SimpleUploadedFile('note.txt', b'hello', content_type='text/plain')
        r = self.api.post('/api/upload', {
            'purpose': 'unknown',
            'file': file,
        }, format='multipart')
        self.assertEqual(r.status_code, 400)

    @patch('chat.views.upload.shutil.which', return_value='/usr/bin/ffprobe')
    @patch('chat.views.upload.subprocess.run')
    def test_media_metadata_uses_ffprobe(self, run_mock, _which_mock):
        from chat.views.upload import _extract_media_metadata

        run_mock.return_value.stdout = (
            '{"streams":[{"width":1920,"height":1080,"duration":"3.6"}],'
            '"format":{"duration":"3.6"}}'
        )

        width, height, duration = _extract_media_metadata('/tmp/video.mp4')

        self.assertEqual(width, 1920)
        self.assertEqual(height, 1080)
        self.assertEqual(duration, 4)


# ──────────────────────────────────────────────
# 26. Sync — offline incremental messages
# ──────────────────────────────────────────────

class SyncMessagesViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.api = auth_client(self.alice)
        self.conversation = Conversation.objects.create(type='private', name='')
        ConversationMember.objects.create(conversation=self.conversation, user=self.alice, role='member')
        ConversationMember.objects.create(conversation=self.conversation, user=self.bob, role='member')

    def test_sync_messages_since_timestamp(self):
        since = timezone.now()
        message = Message.objects.create(
            conversation=self.conversation,
            sender=self.bob,
            type='text',
            content={'text': 'offline hello'},
        )

        r = self.api.get('/api/sync/messages', {
            'since': since.isoformat(),
            'limit': 10,
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data['has_more'])
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['msg_id'], message.id)
        self.assertEqual(data['messages'][0]['content']['text'], 'offline hello')

    def test_sync_includes_friend_and_group_events(self):
        since = timezone.now()
        request = FriendRequest.objects.create(
            from_user=self.bob,
            to_user=self.alice,
            message='add me',
        )
        group = Conversation.objects.create(type='group', name='Class')
        ConversationMember.objects.create(conversation=group, user=self.alice, role='admin')
        invitation = GroupInvitation.objects.create(
            conversation=group,
            inviter=self.alice,
            invitee=self.bob,
        )
        announcement = GroupAnnouncement.objects.create(
            conversation=group,
            publisher=self.alice,
            content='Welcome',
        )

        r = self.api.get('/api/sync/messages', {
            'since': since.isoformat(),
            'limit': 10,
        })

        self.assertEqual(r.status_code, 200)
        events = r.json()['events']
        event_types = {event['type'] for event in events}
        self.assertIn('friend_request', event_types)
        self.assertIn('group_invitation', event_types)
        self.assertIn('group_announcement', event_types)
        event_ids = {(event['type'], event['id']) for event in events}
        self.assertIn(('friend_request', request.id), event_ids)
        self.assertIn(('group_invitation', invitation.id), event_ids)
        self.assertIn(('group_announcement', announcement.id), event_ids)

    def test_sync_includes_recall_reaction_and_group_update_events(self):
        since = timezone.now()
        message = Message.objects.create(
            conversation=self.conversation,
            sender=self.bob,
            type='text',
            content={'text': 'old message'},
        )
        Message.objects.filter(id=message.id).update(created_at=since - timedelta(minutes=5))
        message.refresh_from_db()
        message.is_recalled = True
        message.recalled_at = timezone.now()
        message.recalled_by = self.alice
        message.save(update_fields=['is_recalled', 'recalled_at', 'recalled_by'])

        ReactionEvent.objects.create(
            message=message,
            user=self.alice,
            emoji='👍',
            action='remove',
            current_count=0,
        )

        group = Conversation.objects.create(type='group', name='Old', owner=self.alice)
        ConversationMember.objects.create(conversation=group, user=self.alice, role='owner')
        group.name = 'New'
        group.save(update_fields=['name', 'updated_at'])

        r = self.api.get('/api/sync/messages', {
            'since': since.isoformat(),
            'limit': 10,
        })

        self.assertEqual(r.status_code, 200)
        events = r.json()['events']
        event_types = {event['type'] for event in events}
        self.assertIn('message_recalled', event_types)
        self.assertIn('reaction_update', event_types)
        self.assertIn('group_updated', event_types)
        recall_event = next(event for event in events if event['type'] == 'message_recalled')
        self.assertEqual(recall_event['data']['recalled_by']['user_id'], self.alice.id)
        reaction_event = next(event for event in events if event['type'] == 'reaction_update')
        self.assertEqual(reaction_event['data']['action'], 'remove')

    def test_sync_validation_and_limit(self):
        r = self.api.get('/api/sync/messages')
        self.assertEqual(r.status_code, 400)

        since = timezone.now().isoformat()
        for i in range(3):
            Message.objects.create(
                conversation=self.conversation,
                sender=self.bob,
                type='text',
                content={'text': f'msg {i}'},
            )

        r = self.api.get('/api/sync/messages', {
            'since': since,
            'limit': 2,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['has_more'])
        self.assertEqual(len(r.json()['messages']), 2)

    def test_sync_has_more_when_events_exceed_limit(self):
        since = timezone.now()
        FriendRequest.objects.create(from_user=self.bob, to_user=self.alice, message='one')
        FriendRequest.objects.create(from_user=self.bob, to_user=self.alice, message='two', source='contact_card:1')

        r = self.api.get('/api/sync/messages', {
            'since': since.isoformat(),
            'limit': 1,
        })

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['has_more'])
        self.assertEqual(len(r.json()['events']), 1)


# ──────────────────────────────────────────────
# 26b. Calendar — events, invitations, availability
# ──────────────────────────────────────────────

class CalendarViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        Friendship.objects.create(user=self.alice, friend=self.bob)
        Friendship.objects.create(user=self.bob, friend=self.alice)
        self.api_alice = auth_client(self.alice)
        self.api_bob = auth_client(self.bob)

    def test_create_invite_accept_and_query_availability(self):
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=1)
        r = self.api_alice.post('/api/calendar/events', {
            'title': '需求评审',
            'description': '确认范围',
            'start_at': start.isoformat(),
            'end_at': end.isoformat(),
            'invitee_ids': [self.bob.id],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        event_id = r.json()['event_id']
        participant = CalendarParticipant.objects.get(event_id=event_id, user=self.bob)
        self.assertEqual(participant.status, 'pending')
        self.assertTrue(Message.objects.filter(type='calendar_invite', content__participant_id=participant.id).exists())

        r = self.api_bob.get('/api/calendar/events', {
            'start_at': start.isoformat(),
            'end_at': end.isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)

        r = self.api_bob.put(f'/api/calendar/invitations/{participant.id}', {
            'action': 'accept',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        participant.refresh_from_db()
        self.assertEqual(participant.status, 'accepted')

        r = self.api_alice.get('/api/calendar/availability', {
            'user_ids': str(self.bob.id),
            'start_at': start.isoformat(),
            'end_at': end.isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['results'][0]['has_conflict'])

        r = self.api_bob.get('/api/calendar/events', {
            'start_at': start.isoformat(),
            'end_at': end.isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['results'][0]['event_id'], event_id)


# ──────────────────────────────────────────────
# 27. AI — conversations and mocked completions
# ──────────────────────────────────────────────

class ManualViewTest(TestCase):
    def test_get_manual(self):
        r = APIClient().get('/api/manual')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['title'], 'ChatGLMJ 帮助文档')
        self.assertTrue(data['sections'])
        self.assertIn('日历与日程', data['text'])


class AIViewTest(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.alice.ai_api_key = 'QC-test-secret-key'
        self.alice.save(update_fields=['ai_api_key'])
        self.api = auth_client(self.alice)

    def test_create_ai_conversation(self):
        r = self.api.post('/api/ai/conversations', {
            'name': '我的AI助手',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data['type'], 'ai')
        self.assertEqual(data['name'], '我的AI助手')
        self.assertTrue(
            ConversationMember.objects.filter(
                conversation_id=data['conversation_id'],
                user=self.alice,
            ).exists()
        )

    @patch('chat.views.ai._call_llm', return_value='你好，我是 AI。')
    def test_send_ai_message_non_stream(self, mocked_call):
        conv = Conversation.objects.create(type='ai', name='AI')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')

        r = self.api.post(f'/api/ai/conversations/{conv.id}/messages?stream=false', {
            'content': '你好',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['user_message']['content']['text'], '你好')
        self.assertEqual(data['ai_message']['content']['text'], '你好，我是 AI。')
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 2)
        mocked_call.assert_called_once()
        context = mocked_call.call_args.args[0]
        self.assertEqual(context[-1]['role'], 'user')
        self.assertEqual(context[-1]['content'], '你好')

    @patch('chat.views.ai._call_llm', return_value='可以在日历页创建日程并邀请好友。')
    def test_send_ai_usage_question_includes_manual(self, mocked_call):
        conv = Conversation.objects.create(type='ai', name='AI')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')

        r = self.api.post(f'/api/ai/conversations/{conv.id}/messages?stream=false', {
            'content': '怎么使用日历邀请好友？',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        context = mocked_call.call_args.args[0]
        self.assertTrue(any('ChatGLMJ 帮助文档' in item['content'] for item in context))
        self.assertTrue(any('日历与日程' in item['content'] for item in context))

    def test_ai_context_includes_code_and_markdown_file_preview(self):
        from chat.views.ai import _build_context

        conv = Conversation.objects.create(type='group', name='研发群')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')
        Message.objects.create(
            conversation=conv,
            sender=self.alice,
            type='code',
            content={'language': 'python', 'code': 'print("hi")'},
        )

        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            rel_path = 'uploads/files/f_md.md'
            full_path = f'{media_root}/{rel_path}'
            import os
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as handle:
                handle.write('# 标题\n正文')
            UploadedFile.objects.create(
                uploader=self.alice,
                file_id='f_md',
                url=f'/media/{rel_path}',
                filename='note.md',
                size=20,
                mime_type='text/markdown',
                purpose='message',
            )
            Message.objects.create(
                conversation=conv,
                sender=self.alice,
                type='file',
                content={
                    'file_id': 'f_md',
                    'url': f'/media/{rel_path}',
                    'filename': 'note.md',
                    'mime_type': 'text/markdown',
                },
            )
            text = '\n'.join(item['content'] for item in _build_context(conv))
            self.assertIn('```python', text)
            self.assertIn('print("hi")', text)
            self.assertIn('# 标题', text)

    @patch('chat.views.ai._stream_llm', return_value=iter(['你', '好']))
    def test_send_ai_message_streams_and_saves_answer(self, mocked_stream):
        conv = Conversation.objects.create(type='ai', name='AI')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')

        r = self.api.post(f'/api/ai/conversations/{conv.id}/messages', {
            'content': '你好',
        }, content_type='application/json')

        self.assertEqual(r.status_code, 200)
        body = b''.join(r.streaming_content).decode('utf-8')
        self.assertIn('"type": "delta"', body)
        self.assertIn('"full_content": "你好"', body)
        ai_message = Message.objects.filter(conversation=conv, sender__username='ai_assistant').latest('id')
        self.assertEqual(ai_message.content['text'], '你好')
        mocked_stream.assert_called_once()

    def test_send_ai_message_requires_user_key(self):
        self.alice.ai_api_key = ''
        self.alice.save(update_fields=['ai_api_key'])
        conv = Conversation.objects.create(type='ai', name='AI')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')

        r = self.api.post(f'/api/ai/conversations/{conv.id}/messages?stream=false', {
            'content': '你好',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'AI_API_KEY_REQUIRED')

    def test_send_ai_message_validation(self):
        r = self.api.post('/api/ai/conversations/999/messages', {
            'content': 'hello',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 404)

        conv = Conversation.objects.create(type='ai', name='AI')
        ConversationMember.objects.create(conversation=conv, user=self.alice, role='member')
        r = self.api.post(f'/api/ai/conversations/{conv.id}/messages', {
            'content': '',
        }, content_type='application/json')
        self.assertEqual(r.status_code, 400)
