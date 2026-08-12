import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import create_application, execute
from separan.errors import SeparanError
from separan.http_server import ServerRequest


SOURCE = '''http_route GET "/user/:id" :user_page
http_set_cookie("session", "abc", secure = true)
return_http(status = 200, content_type = "text/plain", body = request_method() + " " + request_param("id") + " " + request_query("view"))
end_http_route:user_page

http_route POST "/login" :login
return_http(status = 201, body = request_body())
end_http_route:login
'''


class HttpServerTests(unittest.TestCase):
    def test_dispatches_labeled_route_and_request_data(self):
        app = create_application(SOURCE)
        response = app.dispatch_http(ServerRequest("GET", "/user/42", {"view": ["full"]}, {"cookie": "session=old"}))
        self.assertEqual((response.status, response.body), (200, b"GET 42 full"))
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.cookies, ("session=abc; Path=/; Secure; HttpOnly; SameSite=Lax",))

    def test_post_body_not_found_and_head_fallback(self):
        app = create_application(SOURCE)
        post = app.dispatch_http(ServerRequest("POST", "/login", body="日本語".encode()))
        self.assertEqual((post.status, post.body), (201, "日本語".encode()))
        self.assertEqual(app.dispatch_http(ServerRequest("GET", "/missing")).status, 404)
        self.assertEqual(app.dispatch_http(ServerRequest("HEAD", "/user/1", {"view": ["x"]})).status, 200)

    def test_redirect_and_request_context_guard(self):
        source = '''http_route GET "/old" :old
redirect_http("/new", status = 308)
end_http_route:old
'''
        response = create_application(source).dispatch_http(ServerRequest("GET", "/old"))
        self.assertEqual((response.status, response.headers["Location"]), (308, "/new"))
        with self.assertRaises(SeparanError) as caught: execute("print request_path()\n")
        self.assertEqual(caught.exception.code, "E893")

    def test_route_validation_and_host_capability(self):
        with self.assertRaises(SeparanError) as caught:
            create_application('''http_route GET "/x" :a
end_http_route:a
http_route GET "/x" :b
end_http_route:b
''')
        self.assertEqual(caught.exception.code, "E896")
        with self.assertRaises(SeparanError) as caught: execute("http_host(port = 8080)\n", capabilities=RuntimeCapabilities.none(ROOT))
        self.assertEqual(caught.exception.code, "E720")

    def test_static_files_are_capability_bounded(self):
        root = ROOT / "tests" / "fixtures" / "http_root"
        source = 'http_static(url = "/static/", directory = "public")\n'
        app = create_application(source, capabilities=RuntimeCapabilities.local(root))
        index = app.dispatch_http(ServerRequest("GET", "/static/"))
        self.assertEqual((index.status, index.body), (200, b"<h1>Separan</h1>\n"))
        self.assertEqual(index.headers["Content-Type"], "text/html; charset=utf-8")
        text = app.dispatch_http(ServerRequest("HEAD", "/static/data.txt"))
        self.assertEqual((text.status, text.body), (200, b"static data\n"))
        self.assertEqual(text.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(app.dispatch_http(ServerRequest("GET", "/static/%2e%2e/secret.txt")).status, 404)
        self.assertEqual(app.dispatch_http(ServerRequest("POST", "/static/index.html")).status, 404)

    def test_static_mount_validation_and_read_denial(self):
        root = ROOT / "tests" / "fixtures" / "http_root"
        denied = replace(RuntimeCapabilities.local(root), read_files=False)
        with self.assertRaises(SeparanError) as caught:
            create_application('http_static(url = "/static/", directory = "public")\n', capabilities=denied)
        self.assertEqual(caught.exception.code, "E720")
        with self.assertRaises(SeparanError) as caught:
            create_application('http_static(url = "static", directory = "public")\n', capabilities=RuntimeCapabilities.local(root))
        self.assertEqual(caught.exception.code, "E898")


if __name__ == "__main__": unittest.main()
