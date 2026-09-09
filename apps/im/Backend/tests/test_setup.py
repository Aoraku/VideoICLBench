import sys
from django.test import SimpleTestCase, Client
from Backend.wsgi import application as wsgi_app
from Backend.asgi import application as asgi_app
import manage

class CoreSetupTests(SimpleTestCase):
    def test_wsgi_loads(self):
        self.assertIsNotNone(wsgi_app)

    def test_asgi_loads(self):
        self.assertIsNotNone(asgi_app)

    def test_urls_admin_loads(self):
        client = Client()
        response = client.get('/admin/login/')
        # 如果路由配置正确，将会得到 200 或 302 响应
        self.assertIn(response.status_code, [200, 302])

    def test_manage_main(self):
        # 模拟执行一次 manage.py check，验证 manage.py 的正常逻辑分支
        old_argv = sys.argv
        sys.argv = ['manage.py', 'check']
        try:
            manage.main()
        finally:
            sys.argv = old_argv
