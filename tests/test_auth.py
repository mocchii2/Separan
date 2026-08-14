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


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.capability = replace(RuntimeCapabilities.local(ROOT), network=True,
            network_hosts=frozenset({"api.test", "auth.test"}), read_secrets=True,
            allowed_secrets=frozenset({"api/token", "jwt/key"}))

    def test_secret_get_is_redacted_and_not_string_convertible(self):
        provider = lambda name: {"api/token": "top-secret"}.get(name)
        self.assertEqual(execute('secret = secret_get("api/token")\nprint secret\nprint type(secret)\n', capabilities=self.capability, secret_provider=provider)[1], "[REDACTED]\nsecret\n")
        with self.assertRaises(SeparanError) as caught: execute('print string(secret_get("api/token"))\n', capabilities=self.capability, secret_provider=provider)
        self.assertEqual(caught.exception.code, "E201")
        with self.assertRaises(SeparanError) as caught: execute('print secret_get("denied")\n', capabilities=self.capability, secret_provider=provider)
        self.assertEqual(caught.exception.code, "E870")

    def test_basic_bearer_and_api_key_http_auth(self):
        responses = [HttpTransportResponse(200, "https://api.test/", {}, b"ok") for _ in range(3)]
        transport = FakeTransport(responses)
        source = '''print http_get("https://api.test/", auth = basic_auth("user", "pass"))
print http_get("https://api.test/", auth = bearer_auth("token123"))
print http_get("https://api.test/", auth = api_key_auth("X-API-Key", "key123"))
'''
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "ok\nok\nok\n")
        self.assertEqual(transport.requests[0]["headers"]["Authorization"], "Basic dXNlcjpwYXNz")
        self.assertEqual(transport.requests[1]["headers"]["Authorization"], "Bearer token123")
        self.assertEqual(transport.requests[2]["headers"]["X-API-Key"], "key123")

    def test_hmac_sha256_known_vector(self):
        output = execute('print hex_encode(hmac_sha256("key", "The quick brown fox jumps over the lazy dog"))\n')[1]
        self.assertEqual(output, "F7BC83F430538424B13298E6AA6FB143EF4D59A14946175997479DBC2D1A3CD8\n")

    def test_jwt_hs256_sign_verify_and_tamper(self):
        source = '''object:claims
sub = "alice"
admin = true
end_object:claims
token = jwt_sign(claims, "0123456789abcdef0123456789abcdef", algorithm = "HS256")
verified = jwt_verify(token, "0123456789abcdef0123456789abcdef", algorithm = "HS256")
print verified.sub
print verified.admin
'''
        self.assertEqual(execute(source)[1], "alice\ntrue\n")
        with self.assertRaises(SeparanError) as caught: execute('print jwt_verify("a.b.c", "0123456789abcdef0123456789abcdef", algorithm = "HS256")\n')
        self.assertEqual(caught.exception.code, "E874")
        with self.assertRaises(SeparanError) as caught: execute('object:c\na = 1\nend_object:c\nprint jwt_sign(c, "x", algorithm = "none")\n')
        self.assertEqual(caught.exception.code, "E873")
        with self.assertRaises(SeparanError) as caught: execute('object:c\na = 1\nend_object:c\nprint jwt_sign(c, "short", algorithm = "HS256")\n')
        self.assertEqual(caught.exception.code, "E873")

    def test_jwt_expiration_is_verified(self):
        source = '''object:claims
sub = "alice"
exp = 0
end_object:claims
token = jwt_sign(claims, "0123456789abcdef0123456789abcdef")
print jwt_verify(token, "0123456789abcdef0123456789abcdef")
'''
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, "E874")

    def test_password_hash_and_verify(self):
        source = '''hash = password_hash("correct horse battery staple")
print starts_with(hash, "$argon2id$")
print password_verify("correct horse battery staple", hash)
print password_verify("wrong", hash)
print password_verify("x", "malformed")
'''
        self.assertEqual(execute(source)[1], "true\ntrue\nfalse\nfalse\n")

    def test_oauth_client_credentials(self):
        transport = FakeTransport([HttpTransportResponse(200, "https://auth.test/token", {"Content-Type": "application/json"}, b'{"access_token":"abc123","token_type":"Bearer","expires_in":3600,"scope":"read"}')])
        source = '''token = oauth_client_credentials("https://auth.test/token", "client", "secret", scope = "read")
print token
print token.token_type
print token.expires_in
print token.scope
print bearer_auth(token.access_token)
'''
        self.assertEqual(execute(source, capabilities=self.capability, http_transport=transport)[1], "oauth_token:[REDACTED]\nBearer\n3600\nread\nhttp_auth:[REDACTED]\n")
        request = transport.requests[0]
        self.assertEqual(request["method"], "POST"); self.assertEqual(request["body"], b"grant_type=client_credentials&scope=read")
        self.assertEqual(request["headers"]["Authorization"], "Basic Y2xpZW50OnNlY3JldA==")


if __name__ == "__main__": unittest.main()
