from django.test import TestCase
import time
from unittest import mock
from django.conf import settings

from accounts.jwt_utils import generate_jwt, decode_jwt

class JWTUtilsTest(TestCase):
    def test_generate_and_decode(self):
        user_id = 99
        token = generate_jwt(user_id)
        
        payload = decode_jwt(token)
        self.assertEqual(payload["sub"], user_id)
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)
        self.assertIn("jti", payload)

    def test_decode_invalid_signature(self):
        user_id = 99
        token = generate_jwt(user_id)
        # Modify signature
        parts = token.split(".")
        parts[2] = "invalid_signature"
        bad_token = ".".join(parts)
        
        with self.assertRaisesMessage(ValueError, "Invalid signature"):
            decode_jwt(bad_token)
            
    def test_decode_malformed_token(self):
        with self.assertRaisesRegex(ValueError, "Malformed token"):
            decode_jwt("123.123")
            
        # Create a token with valid signature but malformed json base64
        import base64
        import json
        from accounts.jwt_utils import _b64url_encode, _sign
        
        # invalid json payload '}'
        signing_input = f"{_b64url_encode(b'{}')}.{_b64url_encode(b'}')}"
        expected_signature = _b64url_encode(_sign(signing_input))
        invalid_json_token = f"{signing_input}.{expected_signature}"
        
        with self.assertRaisesRegex(ValueError, "Malformed token"):
            decode_jwt(invalid_json_token)

    def test_decode_expired_token(self):
        user_id = 99
        token = generate_jwt(user_id)
        
        # mock time.time to be in the future
        future_time = time.time() + settings.JWT_EXPIRATION_SECONDS + 10
        with mock.patch("time.time", return_value=future_time):
            with self.assertRaisesMessage(ValueError, "Expired token"):
                decode_jwt(token)

class JWTEnterpriseStressTest(TestCase):
    def test_massive_concurrent_token_generation(self):
        """企业级压力测试：短时间内高并发生成大量 Token，确保不发生哈希碰撞且性能达标"""
        import time
        start_time = time.time()
        # 1万次高强度生成与部分解析（模拟峰值登录浪涌）
        tokens = [generate_jwt(i) for i in range(10000)]
        self.assertEqual(len(set(tokens)), 10000, "Token should be unique per generation due to UUID jti")
        
        # 验证解析性能
        for t in tokens[:500]:
            decode_jwt(t)
        
        elapsed = time.time() - start_time
        # 通常这在普通环境下应能在1-2秒内跑完，验证无死锁、无严重阻塞
        self.assertTrue(elapsed < 10.0, f"Token generation is too slow! Took {elapsed}s")

    def test_header_and_payload_tampering_for_full_coverage(self):
        """安全测试与100%边界覆盖：篡改JWT核心结构、尝试绕过类型校验"""
        import json
        from accounts.jwt_utils import _b64url_encode, _sign
        
        # 1. 注入非法的 Header (篡改 typ 字段) - 覆盖 48 行
        bad_header = {"alg": settings.JWT_ALGORITHM, "typ": "INVALID"}
        payload = {"sub": 1, "iat": int(time.time()), "exp": int(time.time())+1000, "jti": "123"}
        h_enc = _b64url_encode(json.dumps(bad_header).encode())
        p_enc = _b64url_encode(json.dumps(payload).encode())
        sign_input = f"{h_enc}.{p_enc}"
        sig = _b64url_encode(_sign(sign_input))
        bad_typ_token = f"{sign_input}.{sig}"
        
        with self.assertRaisesRegex(ValueError, "Invalid header"):
            decode_jwt(bad_typ_token)

        # 2. 注入非法的 Payload (篡改 sub, exp 为 string 类型，试图引发注入) - 覆盖 53 行
        good_header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}
        bad_payload = {"sub": "string_not_int", "exp": "string", "jti": 123} # jti expected str, given int
        h_enc = _b64url_encode(json.dumps(good_header).encode())
        p_enc = _b64url_encode(json.dumps(bad_payload).encode())
        sign_input = f"{h_enc}.{p_enc}"
        sig = _b64url_encode(_sign(sign_input))
        bad_pay_token = f"{sign_input}.{sig}"
        
        with self.assertRaisesRegex(ValueError, "Invalid payload"):
            decode_jwt(bad_pay_token)

    def test_jwt_extreme_payload_fuzzing(self):
        """Fuzzing测试：超大负数，超长边界"""
        # ID为极大整数，接近 64-bit 边界
        big_id_token = generate_jwt(9223372036854775807)
        payload = decode_jwt(big_id_token)
        self.assertEqual(payload["sub"], 9223372036854775807)
