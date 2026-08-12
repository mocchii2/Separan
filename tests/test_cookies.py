import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError
from separan.http_client import HttpTransportResponse


class FakeTransport:
    def __init__(self, responses): self.responses, self.requests = list(responses), []
    def __call__(self, request): self.requests.append(request); return self.responses.pop(0)


class CookieTests(unittest.TestCase):
    def setUp(self):
        self.capability = replace(RuntimeCapabilities.local(ROOT), network=True,
            network_schemes=frozenset({"https", "http"}), network_hosts=frozenset({"example.test"}))

    def test_single_request_cookies(self):
        transport = FakeTransport([HttpTransportResponse(200, "https://example.test/", {}, b"ok")])
        source = '''object:cookies
session = "abc123"
lang = "ja"
end_object:cookies
print http_get("https://example.test/", cookies = cookies)
'''
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "ok\n")
        self.assertEqual(transport.requests[0]["headers"]["Cookie"], "session=abc123; lang=ja")

    def test_cookie_jar_login_then_request(self):
        transport = FakeTransport([
            HttpTransportResponse(200, "https://example.test/login", {}, b"logged in", ("session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax",)),
            HttpTransportResponse(200, "https://example.test/data", {}, b"data"),
        ])
        source = '''function:main
jar = cookie_jar()
login = http_request("https://example.test/login", cookie_jar = jar)
print object_get(login.cookies, "session")
print object_has(login.headers, "set-cookie")
print cookie_get(jar, "session")
print http_get("https://example.test/data", cookie_jar = jar)
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "[REDACTED]\nfalse\n[REDACTED]\ndata\n")
        self.assertNotIn("Cookie", transport.requests[0]["headers"])
        self.assertEqual(transport.requests[1]["headers"]["Cookie"], "session=abc123")

    def test_manual_mutation_and_clear(self):
        source = '''function:main
jar = cookie_jar()
cookie_set(jar, "session", "abc")
print cookie_get(jar, "session")
print object_has(cookie_all(jar), "session")
cookie_remove(jar, "session")
print cookie_get(jar, "session")
cookie_set(jar, "a", "1")
cookie_clear(jar)
print length(object_keys(cookie_all(jar)))
end_function:main
'''
        self.assertEqual(execute(source)[1], "[REDACTED]\ntrue\nnull\n0\n")

    def test_domain_path_secure_and_expiry_rules(self):
        transport = FakeTransport([
            HttpTransportResponse(200, "https://example.test/app/login", {}, b"ok", ("app=x; Path=/app; Secure", "gone=x; Max-Age=0; Path=/")),
            HttpTransportResponse(200, "http://example.test/app/data", {}, b"ok"),
            HttpTransportResponse(200, "https://example.test/other", {}, b"ok"),
        ])
        source = '''function:main
jar = cookie_jar()
http_get("https://example.test/app/login", cookie_jar = jar)
http_get("http://example.test/app/data", cookie_jar = jar)
http_get("https://example.test/other", cookie_jar = jar)
end_function:main
'''
        execute(source, capabilities=self.capability, http_transport=transport)
        self.assertNotIn("Cookie", transport.requests[1]["headers"])
        self.assertNotIn("Cookie", transport.requests[2]["headers"])

    def test_invalid_cookie_is_rejected(self):
        with self.assertRaises(SeparanError) as caught: execute('function:main\njar = cookie_jar()\ncookie_set(jar, "bad name", "x")\nend_function:main\n')
        self.assertEqual(caught.exception.code, "E880")
        transport = FakeTransport([HttpTransportResponse(200, "https://example.test/", {}, b"ok", ("x=1; Domain=other.test",))])
        with self.assertRaises(SeparanError) as caught: execute('jar = cookie_jar()\nprint http_get("https://example.test/", cookie_jar = jar)\n', capabilities=self.capability, http_transport=transport)
        self.assertEqual(caught.exception.code, "E881")


if __name__ == "__main__": unittest.main()
