import time
from django.test import TestCase, Client
from django.contrib.auth.models import User
from accounts.models import UserProfile, EmailVerificationCode
from accounts.jwt_utils import generate_jwt

class ViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePass123!"
        self.user = User.objects.create_user(username="testuser", password=self.password, email="test@example.com")
        UserProfile.objects.create(user=self.user, created_at=time.time(), phone="123456", avatar="old_avatar")
        # Generate token for authenticated requests
        self.token = generate_jwt(self.user.id)
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_send_register_code_success(self):
        # Coverage for send_register_code success and error paths
        data = {"email": "new@example.com"}
        response = self.client.post("/api/auth/register/code", data=data, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_register_flow(self):
        # Create verification code in DB manually to test register logic
        EmailVerificationCode.objects.create(
            email="reg@example.com", code="123456", purpose="register", expires_at=time.time() + 600
        )
        data = {
            "username": "newuser",
            "password": "NewPassword123!",
            "email": "reg@example.com",
            "verification_code": "123456"
        }
        response = self.client.post("/api/auth/register", data=data, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_login_failures(self):
        # Coverage for User.DoesNotExist and Wrong password
        self.client.post("/api/auth/login", data={"username": "none", "password": "p"}, content_type="application/json")
        self.client.post("/api/auth/login", data={"username": "testuser", "password": "wrong"}, content_type="application/json")

    def test_profile_update_branches(self):
        # Massive coverage for lines 211-285 in views.py
        # Testing multiple fields update in one request
        data = {
            "username": "updated_name",
            "phone": "987654",
            "avatar": "new_avatar",
            "old_password": self.password
        }
        response = self.client.put("/api/user/profile", data=data, content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "updated_name")

    def test_search_users_pagination(self):
        # Coverage for search_users logic and pagination
        response = self.client.get("/api/user/search", {"keyword": "test", "page": "1", "page_size": "5"}, **self.headers)
        self.assertEqual(response.status_code, 200)