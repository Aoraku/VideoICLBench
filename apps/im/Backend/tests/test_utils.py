from django.test import TestCase
from django.http import JsonResponse
import json
from unittest import mock

from accounts.utils import (
    json_body, error_response, success_response, bad_method_response,
    invalid_field_response, get_bearer_token, validate_username,
    validate_password, validate_email, validate_phone, validate_avatar
)

class RequestMock:
    def __init__(self, method='POST', body=b''):
        self.method = method
        self._body = body
        self.headers = {}
    
    @property
    def body(self):
        return self._body

class UtilsTest(TestCase):
    def test_json_body(self):
        # Empty body
        req = RequestMock(body=b'')
        self.assertEqual(json_body(req), {})
        
        # Valid JSON
        req = RequestMock(body=b'{"key": "value"}')
        self.assertEqual(json_body(req), {"key": "value"})
        
        # Invalid JSON
        with self.assertRaisesMessage(ValueError, "Invalid JSON"):
            req = RequestMock(body=b'not json')
            json_body(req)

    def test_responses(self):
        resp = error_response(-1, "test error", 400)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content), {"code": -1, "info": "test error"})
        
        resp = success_response({"user_id": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), {"code": 0, "info": "Succeed", "user_id": 1})
        
        resp = bad_method_response()
        self.assertEqual(resp.status_code, 405)
        
        resp = invalid_field_response("username")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)["info"], "Invalid field: username")

    def test_get_bearer_token(self):
        req = RequestMock()
        self.assertIsNone(get_bearer_token(req))
        
        req.headers["Authorization"] = "Bearer token123"
        self.assertEqual(get_bearer_token(req), "token123")
        
        req.headers["Authorization"] = "Basic notbearer"
        self.assertIsNone(get_bearer_token(req))

    def test_validators(self):
        self.assertTrue(validate_username("test_user_1"))
        self.assertFalse(validate_username("test user")) # spaces not allowed
        self.assertFalse(validate_username("a" * 51))
        
        self.assertTrue(validate_password("123456"))
        self.assertFalse(validate_password("short"))
        self.assertFalse(validate_password("thispasswordiswaytoolongtobevalid"))
        
        self.assertTrue(validate_email("test@example.com"))
        self.assertFalse(validate_email("test@.com"))
        
        self.assertTrue(validate_phone("1234567890"))
        self.assertTrue(validate_avatar("some_base64_or_url"))

class UtilsEnterpriseStressTest(TestCase):
    def test_regex_dos_prevention(self):
        """正则表达式拒绝服务攻击(ReDoS)企业级拦截防护测试与注入脏数据"""
        from accounts.utils import validate_username, validate_email

        # 恶意产生极其长的超长字符串打爆内存
        super_long_username = "a" * 100000 
        self.assertFalse(validate_username(super_long_username), "Should fail fast on 100000 char username limit without blocking")

        # Catastrophic Backtracking Prevention (灾难性回溯探测)
        # 用大量重复但末尾没命中点的字符串来检测 email regex 是否有 ReDoS 风险
        catastrophic_backtracking_email = "a" * 50000 + "@" + "b" * 50000 # Missing the literal .ext at the end
        self.assertFalse(validate_email(catastrophic_backtracking_email), "Should reject non-domain email fast without CPU spin")

        # 正常长电邮能否扛住校验
        valid_long_email = "a" * 1000 + "@" + "b" * 1000 + ".com"
        self.assertTrue(validate_email(valid_long_email))

    def test_deeply_nested_json_exploit(self):
        """JSON 反序列化递归炸弹防御 / Payload 爆破测试"""
        from accounts.utils import json_body
        
        # 嵌套炸弹模拟：[[[[...]]]] => 消耗Python内存和栈深度导致系统核心宕机
        try:
            deep_json = "[" * 2000 + "]" * 2000
            req = RequestMock(body=deep_json.encode())
            with self.assertRaises(ValueError):
                # We expect a ValueError because list [] is not a dict as per json_body requirements
                json_body(req)
        except RecursionError:
            self.fail("JSON parser recursion limit hit! System is vulnerable to JSON Depth bombs.")

        # 并行巨大的字典嵌套压测
        try:
            huge_flat_payload_str = b'{"' + b'a": {"' * 500 + b'x": 1' + b'}' * 500 + b'}'
            req2 = RequestMock(body=huge_flat_payload_str)
            self.assertTrue(isinstance(json_body(req2), dict))
        except RecursionError:
            self.fail("Failed on deep dictionary payloads.")

    def test_auth_token_null_pointers_and_revocations_fuzzing(self):
        """补充完全覆盖的极品测试路径：针对异常的Token和无效签名的数据库校验请求"""
        from accounts.utils import authenticate_request
        from accounts.models import RevokedToken
        from django.contrib.auth.models import User
        from accounts.jwt_utils import generate_jwt

        # 1. 没有 Token - 期望拦下返回 None
        req = RequestMock()
        self.assertIsNone(authenticate_request(req))

        # 2. 伪造/打乱格式的烂Token - 期望拦下返回 None
        req.headers["Authorization"] = "Bearer JustATerribleGarbageToken"
        self.assertIsNone(authenticate_request(req))

        # 3. Token是好的，但该用户被删除了 (脏数据/幽灵Token情况) - 期望拦下返回 None
        fake_user_id = 9999999
        ghost_token = generate_jwt(fake_user_id)
        req.headers["Authorization"] = f"Bearer {ghost_token}"
        self.assertIsNone(authenticate_request(req), "Should return None because sub (user) does not exist in DB")

        # 4. Token是好的，用户也是真的，但已经被注销 (加入撤销名单)
        real_user = User.objects.create_user(username="temp_user", password="pwd")
        token = generate_jwt(real_user.id)
        
        from accounts.jwt_utils import decode_jwt
        payload = decode_jwt(token)
        # 将这个好的 jti 加进撤销黑名单 (如同注销后行为)
        RevokedToken.objects.create(jti=payload["jti"], user=real_user, expires_at=payload["exp"])
        
        req.headers["Authorization"] = f"Bearer {token}"
        self.assertIsNone(authenticate_request(req), "Should return None. Token was good but was revoked.")

    def test_edge_case_validate_group_name(self):
        """覆盖正则与乱码组名的Fuzzing"""
        from accounts.utils import validate_group_name
        self.assertFalse(validate_group_name(None))
        self.assertFalse(validate_group_name({"dict": "group"}))
        self.assertTrue(validate_group_name("中国风_群-1"))
        # 超过限制三十位
        self.assertFalse(validate_group_name("中国风_群"*10))
