import unittest

from direct_auth import forward_options


class AuthGuardTest(unittest.TestCase):
    def test_preserves_body_and_replaces_auth(self):
        body = b'{ "model": "gpt-6-astra" }'
        base = "https://example.invalid/v1"
        options = dict(content=body, headers={"authorization": "old", "X-Api-Key": "old", "X-Trace": "trace"})
        result = forward_options("POST", base+"/responses/compact", options, base_url=base, api_key="test-only")
        self.assertIs(result["content"], body)
        self.assertEqual(result["headers"], {"Authorization": "Bearer test-only", "X-Trace": "trace"})
        for path in ("https://other.invalid/v1/responses", base+"/chat/completions", base+"/responses?q=1"):
            with self.assertRaises(ValueError):
                forward_options("POST", path, options, base_url=base, api_key="test-only")
