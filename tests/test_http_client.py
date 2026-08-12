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


class HttpClientTests(unittest.TestCase):
    def setUp(self):
        self.capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                                  network_schemes=frozenset({"https"}), network_hosts=frozenset({"example.test"}))

    def test_http_get_and_profile_headers(self):
        transport = FakeTransport([HttpTransportResponse(200, "https://example.test/", {"Content-Type": "text/plain; charset=utf-8"}, "日本語".encode())])
        source = '''profile = http_profile("desktop", language = "ja-JP")
print object_get(http_profile_headers(profile), "Accept-Language")
print http_get("https://example.test/", profile = profile)
'''
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "ja-JP\n日本語\n")
        self.assertEqual(transport.requests[0]["headers"]["Accept-Language"], "ja-JP")

    def test_detailed_response_and_headers(self):
        response = HttpTransportResponse(404, "https://example.test/missing", {"Content-Type": "application/json"}, b'{"error":true}')
        output = execute('response = http_request("https://example.test/missing")\nprint response.status\nprint response.text\nprint object_get(response.headers, "content-type")\nprint length(response.bytes)\n', capabilities=self.capability, http_transport=FakeTransport([response]))[1]
        self.assertEqual(output, '404\n{"error":true}\napplication/json\n14\n')

    def test_http_get_rejects_error_status(self):
        source = '''function:main
try :request
print http_get("https://example.test/")
catch http_status_error :request
print "status error"
endtry:request
end_function:main
'''
        transport = FakeTransport([HttpTransportResponse(500, "https://example.test/", {}, b"failure")])
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "status error\n")
        parent_source = '''function:main
try :request
print http_get("https://example.test/")
catch http_error :request
print "http parent"
endtry:request
end_function:main
'''
        transport = FakeTransport([HttpTransportResponse(503, "https://example.test/", {}, b"failure")])
        self.assertEqual(execute(parent_source, capabilities=self.capability, http_transport=transport)[1], "http parent\n")

    def test_redirect_is_revalidated_and_recorded(self):
        transport = FakeTransport([
            HttpTransportResponse(302, "https://example.test/a", {"Location": "/b"}, b""),
            HttpTransportResponse(200, "https://example.test/b", {}, b"ok"),
        ])
        output = execute('r = http_request("https://example.test/a")\nprint r.url\nprint r.redirects\n', capabilities=self.capability, http_transport=transport)[1]
        self.assertEqual(output, "https://example.test/b\n[https://example.test/b]\n")

    def test_redirect_loop_is_an_error(self):
        transport = FakeTransport([
            HttpTransportResponse(302, "https://example.test/a", {"Location": "/b"}, b""),
            HttpTransportResponse(302, "https://example.test/b", {"Location": "/a"}, b""),
        ])
        with self.assertRaises(SeparanError) as caught:
            execute('print http_request("https://example.test/a")\n', capabilities=self.capability, http_transport=transport)
        self.assertEqual(caught.exception.code, "E785")

    def test_network_denial_host_body_and_limit(self):
        with self.assertRaises(SeparanError) as caught: execute('print http_get("https://example.test/")\n', capabilities=RuntimeCapabilities.none(ROOT), http_transport=FakeTransport([]))
        self.assertEqual(caught.exception.code, "E720")
        with self.assertRaises(SeparanError) as caught: execute('print http_get("https://denied.test/")\n', capabilities=self.capability, http_transport=FakeTransport([]))
        self.assertEqual(caught.exception.code, "E780")
        with self.assertRaises(SeparanError) as caught: execute('print http_request("https://example.test/", body = "x")\n', capabilities=self.capability, http_transport=FakeTransport([]))
        self.assertEqual(caught.exception.code, "E781")
        transport = FakeTransport([HttpTransportResponse(200, "https://example.test/", {}, b"123")])
        with self.assertRaises(SeparanError) as caught: execute('print http_request("https://example.test/", max_bytes = 2)\n', capabilities=self.capability, http_transport=transport)
        self.assertEqual(caught.exception.code, "E787")


if __name__ == "__main__": unittest.main()
