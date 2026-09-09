import json
import time

from django.contrib.auth.models import User
from django.test import TransactionTestCase

from accounts.jwt_utils import generate_jwt
from accounts.models import Friend

class MessagesViewsTest(TransactionTestCase):
    def setUp(self):
        self.client = self.client_class()
        
        # 1. 准备用户资源
        self.alice = User.objects.create_user(username="alice", password="pass", email="alice@example.com")
        self.bob = User.objects.create_user(username="bob", password="pass", email="bob@example.com")
        self.charlie = User.objects.create_user(username="charlie", password="pass", email="charlie@example.com")
        self.dave = User.objects.create_user(username="dave", password="pass", email="dave@example.com") # Dave是局外人

        # 2. 准备好友关系
        for u1, u2 in [(self.alice, self.bob), (self.bob, self.alice), (self.alice, self.charlie), (self.charlie, self.alice)]:
            Friend.objects.create(user=u1, friend_user=u2)

        # 3. 创建测试会话 (Group: Alice, Bob, Charlie)
        res_group = self.client.post(
            "/api/conversations",
            data=json.dumps({"name": "Test Group", "member_ids": [self.bob.id, self.charlie.id]}),
            content_type="application/json",
            **self._auth(self.alice)
        )
        self.conv_id = res_group.json().get("conversation_id", 1)
        self.msg_url = f"/api/conversations/{self.conv_id}/messages"
        self.read_url = f"/api/conversations/{self.conv_id}/read"

        # 4. 创建一个备用私聊会话用于跨会话测试
        res_private = self.client.post(
            "/api/conversations",
            data=json.dumps({"name": "Private", "member_ids": [self.bob.id]}),
            content_type="application/json",
            **self._auth(self.alice)
        )
        self.conv_id_private = res_private.json().get("conversation_id", 2)
        self.private_msg_url = f"/api/conversations/{self.conv_id_private}/messages"

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {generate_jwt(user.id)}"}

    # ================= 1. 基础异常与认证拦截测试 =================
    def test_global_auth_and_methods_and_json(self):
        # 未携带 Token
        self.assertEqual(self.client.get(self.msg_url).status_code, 401)
        self.assertEqual(self.client.post(self.msg_url, data=json.dumps({}), content_type="application/json").status_code, 401)
        self.assertEqual(self.client.post(self.read_url, data=json.dumps({}), content_type="application/json").status_code, 401)
        self.assertEqual(self.client.delete(f"{self.msg_url}/1").status_code, 401)

        # 方法不允许 (405)
        self.assertEqual(self.client.patch(self.msg_url, **self._auth(self.alice)).status_code, 405)
        self.assertEqual(self.client.put(self.read_url, **self._auth(self.alice)).status_code, 405)
        self.assertEqual(self.client.post(f"{self.msg_url}/1", **self._auth(self.alice)).status_code, 405)

        # 非法 JSON Body
        res_bad_json = self.client.post(self.msg_url, data="not json", content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res_bad_json.status_code, 400)
        self.assertEqual(res_bad_json.json()["code"], -2)

    # ================= 2. 会话权限控制测试 =================
    def test_conversation_permission_denied(self):
        """测试局外人 Dave 对所有接口的尝试均应返回 404 (代码 1)"""
        # GET messages
        res1 = self.client.get(self.msg_url, **self._auth(self.dave))
        self.assertEqual(res1.status_code, 404)
        self.assertEqual(res1.json()["code"], 1)

        # POST messages
        res2 = self.client.post(self.msg_url, data=json.dumps({"content": "Hack"}), content_type="application/json", **self._auth(self.dave))
        self.assertEqual(res2.status_code, 404)
        
        # POST read
        res3 = self.client.post(self.read_url, data=json.dumps({"last_read_id": 1}), content_type="application/json", **self._auth(self.dave))
        self.assertEqual(res3.status_code, 404)

        # DELETE message
        res4 = self.client.delete(f"{self.msg_url}/1", **self._auth(self.dave))
        self.assertEqual(res4.status_code, 404)

    # ================= 3. GET 获取与筛选机制测试 =================
    def test_get_messages_pagination_limits(self):
        """测试默认 50 条以及最大 100 条的截断逻辑"""
        # 快速制造 105 条消息
        for i in range(105):
            self.client.post(self.msg_url, data=json.dumps({"content": f"Msg {i}"}), content_type="application/json", **self._auth(self.alice))

        # 测试默认不传 limit，应返回 50
        res_default = self.client.get(self.msg_url, **self._auth(self.alice))
        self.assertEqual(len(res_default.json()["messages"]), 50)

        # 测试要求 150，应被截断为 100
        res_max = self.client.get(f"{self.msg_url}?limit=150", **self._auth(self.alice))
        self.assertEqual(len(res_max.json()["messages"]), 100)

    def test_get_messages_invalid_query_params(self):
        """测试非法类型的查询参数 (要求状态码 400)"""
        bad_urls = [
            f"{self.msg_url}?limit=abc",
            f"{self.msg_url}?before_id=xyz",
            f"{self.msg_url}?sender_id=me",
            f"{self.msg_url}?start_time=yesterday"
        ]
        for url in bad_urls:
            res = self.client.get(url, **self._auth(self.alice))
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["code"], -2)

    def test_get_messages_filters_logic(self):
        """测试时间戳、发送者与 before_id 的正确性"""
        msg_ids = []
        timestamps = []
        for user, text in [(self.alice, "M1"), (self.bob, "M2"), (self.charlie, "M3")]:
            res = self.client.post(self.msg_url, data=json.dumps({"content": text}), content_type="application/json", **self._auth(user))
            msg_ids.append(res.json()["msg_id"])
            timestamps.append(res.json()["created_at"])
            time.sleep(0.01)

        # before_id 测试
        res_before = self.client.get(f"{self.msg_url}?before_id={msg_ids[2]}", **self._auth(self.alice))
        self.assertTrue(all(m["msg_id"] < msg_ids[2] for m in res_before.json()["messages"]))

        # start_time 和 end_time 测试 (仅包含 M2)
        res_time = self.client.get(f"{self.msg_url}?start_time={timestamps[1]}&end_time={timestamps[1]}", **self._auth(self.alice))
        self.assertEqual(len(res_time.json()["messages"]), 1)
        self.assertEqual(res_time.json()["messages"][0]["msg_id"], msg_ids[1])

        # sender_id 测试
        res_sender = self.client.get(f"{self.msg_url}?sender_id={self.bob.id}", **self._auth(self.alice))
        self.assertEqual(res_sender.json()["messages"][0]["sender_id"], self.bob.id)

    def test_get_messages_multi_sender_filter_and_membership_guard(self):
        self.client.post(self.msg_url, data=json.dumps({"content": "A1"}), content_type="application/json", **self._auth(self.alice))
        self.client.post(self.msg_url, data=json.dumps({"content": "B1"}), content_type="application/json", **self._auth(self.bob))
        self.client.post(self.msg_url, data=json.dumps({"content": "C1"}), content_type="application/json", **self._auth(self.charlie))

        res_multi = self.client.get(
            f"{self.msg_url}?sender_ids={self.alice.id},{self.bob.id}",
            **self._auth(self.alice)
        )
        self.assertEqual(res_multi.status_code, 200)
        sender_ids = {m["sender_id"] for m in res_multi.json()["messages"]}
        self.assertEqual(sender_ids, {self.alice.id, self.bob.id})

        res_outside = self.client.get(
            f"{self.msg_url}?sender_ids={self.dave.id}",
            **self._auth(self.alice)
        )
        self.assertEqual(res_outside.status_code, 400)
        self.assertEqual(res_outside.json()["info"], "Invalid sender_ids")

    # ================= 4. POST 发送与回复机制测试 =================
    def test_post_message_fields_and_reply_chain(self):
        """测试回复结构的完整性 (reply_to & reply_count)"""
        # 原消息
        r1 = self.client.post(self.msg_url, data=json.dumps({"content": "A", "reply_to_id": None}), content_type="application/json", **self._auth(self.alice))
        m1_id = r1.json()["msg_id"]

        # 回复一次
        r2 = self.client.post(self.msg_url, data=json.dumps({"content": "B", "reply_to_id": m1_id}), content_type="application/json", **self._auth(self.bob))
        m2_id = r2.json()["msg_id"]

        # 再次回复同一条
        self.client.post(self.msg_url, data=json.dumps({"content": "C", "reply_to_id": m1_id}), content_type="application/json", **self._auth(self.charlie))

        messages = self.client.get(self.msg_url, **self._auth(self.alice)).json()["messages"]
        m1 = next(m for m in messages if m["msg_id"] == m1_id)
        m2 = next(m for m in messages if m["msg_id"] == m2_id)

        self.assertEqual(m1["reply_count"], 2)
        self.assertIsNone(m1["reply_to"])
        
        self.assertEqual(m2["reply_to"]["msg_id"], m1_id)
        self.assertIn("sender_name", m2["reply_to"])

    def test_post_message_invalid_inputs(self):
        """测试发消息的恶劣输入：空内容、纯空格、参数缺失"""
        invalid_bodies = [
            {"content": ""},             # 空字符串
            {"content": "   "},          # 纯空格 (业务上应拒绝)
            {"reply_to_id": None},       # 缺省 content
        ]
        for body in invalid_bodies:
            res = self.client.post(self.msg_url, data=json.dumps(body), content_type="application/json", **self._auth(self.alice))
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["code"], -2)

    def test_post_message_cross_conversation_reply(self):
        """测试回复不同会话的消息或不存在的消息"""
        r1 = self.client.post(self.msg_url, data=json.dumps({"content": "A"}), content_type="application/json", **self._auth(self.alice))
        m1_id = r1.json()["msg_id"]

        # 在私聊会话中尝试回复群聊的消息
        res_cross = self.client.post(self.private_msg_url, data=json.dumps({"content": "Cross", "reply_to_id": m1_id}), content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res_cross.status_code, 404)
        self.assertEqual(res_cross.json()["code"], 2)

        # 回复彻底不存在的 ID
        res_fake = self.client.post(self.msg_url, data=json.dumps({"content": "Fake", "reply_to_id": 999999}), content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res_fake.status_code, 404)

    # ================= 5. DELETE 删除单据与隔离测试 =================
    def test_delete_message_behavior(self):
        """测试单向删除、重复删除、删除别人的消息的影响"""
        r = self.client.post(self.msg_url, data=json.dumps({"content": "Del"}), content_type="application/json", **self._auth(self.alice))
        msg_id = r.json()["msg_id"]

        # Alice 成功删除
        del_res = self.client.delete(f"{self.msg_url}/{msg_id}", **self._auth(self.alice))
        self.assertEqual(del_res.status_code, 200)

        # Alice 再次请求，不可见
        msgs_alice = self.client.get(self.msg_url, **self._auth(self.alice)).json()["messages"]
        self.assertFalse(any(m["msg_id"] == msg_id for m in msgs_alice))

        # Bob 仍能看见（单向隔离）
        msgs_bob = self.client.get(self.msg_url, **self._auth(self.bob)).json()["messages"]
        self.assertTrue(any(m["msg_id"] == msg_id for m in msgs_bob))

        # Alice 重复删除 -> 404
        del_again = self.client.delete(f"{self.msg_url}/{msg_id}", **self._auth(self.alice))
        self.assertEqual(del_again.status_code, 404)
        self.assertEqual(del_again.json()["code"], 1)

    def test_delete_message_cross_conversation(self):
        """跨会话删除拦截"""
        r = self.client.post(self.msg_url, data=json.dumps({"content": "Group msg"}), content_type="application/json", **self._auth(self.alice))
        msg_id = r.json()["msg_id"]
        
        # 在私聊会话的 URL 里尝试删除群聊产生的 msg_id
        res = self.client.delete(f"{self.private_msg_url}/{msg_id}", **self._auth(self.alice))
        self.assertEqual(res.status_code, 404)

    # ================= 6. POST read 已读接口机制测试 =================
    def test_read_message_validation(self):
        """已读标记参数与异常类型校验"""
        # 成功调用
        res1 = self.client.post(self.read_url, data=json.dumps({"last_read_id": 999}), content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res1.status_code, 200)

        # 参数缺失
        res2 = self.client.post(self.read_url, data=json.dumps({}), content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res2.status_code, 400)

        # 参数类型错误 (字符串)
        res3 = self.client.post(self.read_url, data=json.dumps({"last_read_id": "abc"}), content_type="application/json", **self._auth(self.alice))
        self.assertEqual(res3.status_code, 400)
        
    # ================= 7. 针对 Coverage 未覆盖行的极限分支测试 =================

    def test_get_messages_individual_value_errors(self):
        res1 = self.client.get(f"{self.msg_url}?before_id=abc", **self._auth(self.alice))
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.json()["info"], "Invalid before_id")

        res2 = self.client.get(f"{self.msg_url}?sender_id=abc", **self._auth(self.alice))
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.json()["info"], "Invalid sender_id")

        res3 = self.client.get(f"{self.msg_url}?start_time=abc", **self._auth(self.alice))
        self.assertEqual(res3.status_code, 400)
        self.assertEqual(res3.json()["info"], "Invalid start_time")

        res4 = self.client.get(f"{self.msg_url}?end_time=abc", **self._auth(self.alice))
        self.assertEqual(res4.status_code, 400)
        self.assertEqual(res4.json()["info"], "Invalid end_time")

        res5 = self.client.get(f"{self.msg_url}?sender_ids=abc", **self._auth(self.alice))
        self.assertEqual(res5.status_code, 400)
        self.assertEqual(res5.json()["info"], "Invalid sender_ids")

    def test_post_message_invalid_reply_to_id_type(self):
        res_type = self.client.post(
            self.msg_url,
            data=json.dumps({"content": "Hello", "reply_to_id": "abc"}),
            content_type="application/json",
            **self._auth(self.alice)
        )
        self.assertEqual(res_type.status_code, 400)
        self.assertIn("reply_to_id", res_type.json()["info"])

        res_404 = self.client.post(
            self.msg_url,
            data=json.dumps({"content": "Hello", "reply_to_id": 999999}),
            content_type="application/json",
            **self._auth(self.alice)
        )
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.json()["info"], "Replied message not found")

    def test_delete_message_invalid_msg_id_type(self):
        from django.test import RequestFactory
        from accounts.messages_views import message_detail

        factory = RequestFactory()
        # 伪造一个目标带有非法字符串的 Request
        req = factory.delete(f"/api/conversations/{self.conv_id}/messages/abc")
        # 强行注入合法的认证 Header
        req.META['HTTP_AUTHORIZATION'] = f"Bearer {generate_jwt(self.alice.id)}"
        
        # 绕过路由，直接把字符串 "abc" 喂给视图函数
        response = message_detail(req, conversation_id=self.conv_id, msg_id="abc")
        
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.content)
        self.assertIn("msg_id", res_data["info"])

    def test_read_messages_invalid_json(self):
        res = self.client.post(
            self.read_url,
            data="this {is not a valid json:",
            content_type="application/json",
            **self._auth(self.alice)
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("body", res.json()["info"])
