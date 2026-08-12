"""High-level authentication primitives; no user-defined cryptography surface."""

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
import os
from urllib.parse import urlencode

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction


@dataclass(frozen=True)
class SecretValue:
    value: bytes


@dataclass(frozen=True)
class HttpAuthValue:
    kind: str
    name: str
    value: SecretValue
    location: str = "header"


@dataclass(frozen=True)
class OAuthTokenValue:
    access_token: SecretValue
    token_type: str
    expires_in: int | None
    scope: str | None


def secret_bytes(value, name, position, runtime):
    if isinstance(value, SecretValue): return value.value
    if isinstance(value, BytesValue): return value.value
    if type(value) is str: return value.encode("utf-8")
    runtime.type_error(position, "secret, bytes, or string", runtime.type_name(value), f"{name} requires secret-compatible input.")


def _secret_get(arguments, named, position, runtime):
    name = arguments[0]
    if type(name) is not str or not name: runtime.type_error(position, "non-empty string", runtime.type_name(name), "secret_get() requires a secret name.")
    capability = runtime.capabilities; capability.require(capability.read_secrets, "read secrets", position)
    if capability.allowed_secrets is not None and name not in capability.allowed_secrets: raise error("E870", "Permission error", "Secret name is outside the host allowlist.", position, actual=name)
    if runtime.secret_provider is None: raise error("E871", "Secret unavailable", "No host secret provider is configured.", position, actual=name)
    try: value = runtime.secret_provider(name)
    except Exception as exc: raise error("E871", "Secret unavailable", str(exc), position, actual=name)
    if value is None: raise error("E871", "Secret unavailable", "The requested secret does not exist.", position, actual=name)
    if type(value) is str: value = value.encode("utf-8")
    if type(value) is not bytes: raise error("E871", "Secret provider error", "Host secret provider must return string, bytes, or null.", position, actual=name)
    return SecretValue(value)


def _basic_auth(arguments, named, position, runtime):
    username = arguments[0]
    if type(username) is not str or ":" in username: raise error("E872", "Invalid Basic auth username", "Username must be a string without ':'.", position)
    password = secret_bytes(arguments[1], "basic_auth() password", position, runtime)
    token = base64.b64encode(username.encode("utf-8") + b":" + password)
    return HttpAuthValue("basic", "Authorization", SecretValue(b"Basic " + token))


def _bearer_auth(arguments, named, position, runtime):
    token = secret_bytes(arguments[0], "bearer_auth() token", position, runtime)
    if not token or any(byte < 33 or byte > 126 for byte in token): raise error("E872", "Invalid bearer token", "Bearer token must contain visible ASCII bytes only.", position)
    return HttpAuthValue("bearer", "Authorization", SecretValue(b"Bearer " + token))


def _api_key_auth(arguments, named, position, runtime):
    name, value = arguments; location = named.get("location", "header")
    if type(name) is not str or not name or any(ord(char) < 33 for char in name): raise error("E872", "Invalid API key name", "API key name must be a safe non-empty string.", position)
    if location not in ("header", "query"): raise error("E872", "Invalid API key location", "API key location must be header or query.", position, actual=repr(location))
    return HttpAuthValue("api_key", name, SecretValue(secret_bytes(value, "api_key_auth() value", position, runtime)), location)


def _hmac_sha256(arguments, named, position, runtime):
    key = secret_bytes(arguments[0], "hmac_sha256() key", position, runtime); message = secret_bytes(arguments[1], "hmac_sha256() message", position, runtime)
    return BytesValue(hmac.new(key, message, hashlib.sha256).digest())


def _json_value(value, position):
    if isinstance(value, ObjectValue): return {key: _json_value(item, position) for key, item in value.fields.items()}
    if type(value) is list: return [_json_value(item, position) for item in value]
    if value is None or type(value) in (str, bool, int, float): return value
    raise error("E875", "Invalid JWT claim", "JWT claims must be JSON-compatible and cannot contain secrets or bytes.", position)


def _b64url(value): return base64.urlsafe_b64encode(value).rstrip(b"=")
def _b64url_decode(value): return base64.urlsafe_b64decode(value + b"=" * ((4 - len(value) % 4) % 4))


def _jwt_sign(arguments, named, position, runtime):
    claims, key = arguments; algorithm = named.get("algorithm", "HS256")
    if algorithm != "HS256": raise error("E873", "Unsupported JWT algorithm", "Only explicit HS256 is supported in the preview.", position, actual=repr(algorithm))
    if not isinstance(claims, ObjectValue): runtime.type_error(position, "object claims", runtime.type_name(claims), "jwt_sign() claims must be an object.")
    key_bytes = secret_bytes(key, "jwt_sign() key", position, runtime)
    if len(key_bytes) < 32: raise error("E873", "Weak JWT key", "HS256 keys must contain at least 32 bytes.", position)
    header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64url(json.dumps(_json_value(claims, position), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signing = header + b"." + payload; signature = _b64url(hmac.new(key_bytes, signing, hashlib.sha256).digest())
    return signing.decode("ascii") + "." + signature.decode("ascii")


def _jwt_verify(arguments, named, position, runtime):
    token, key = arguments; algorithm = named.get("algorithm", "HS256")
    if type(token) is not str or algorithm != "HS256": raise error("E873", "Unsupported or invalid JWT", "JWT must be a string and algorithm must be HS256.", position)
    try:
        header_text, payload_text, signature_text = token.encode("ascii").split(b".")
        header = json.loads(_b64url_decode(header_text)); payload = json.loads(_b64url_decode(payload_text))
        key_bytes = secret_bytes(key, "jwt_verify() key", position, runtime)
        if len(key_bytes) < 32: raise ValueError("weak key")
        expected = _b64url(hmac.new(key_bytes, header_text + b"." + payload_text, hashlib.sha256).digest())
    except Exception: raise error("E874", "JWT verification error", "JWT is malformed.", position)
    if header != {"alg": "HS256", "typ": "JWT"} or not hmac.compare_digest(expected, signature_text): raise error("E874", "JWT verification error", "JWT signature or protected header is invalid.", position)
    if type(payload) is not dict: raise error("E874", "JWT verification error", "JWT claims must be an object.", position)
    now = runtime.current_time().timestamp()
    for claim in ("exp", "nbf"):
        if claim in payload and (type(payload[claim]) not in (int, float) or type(payload[claim]) is bool): raise error("E874", "JWT verification error", f"JWT {claim} claim must be a number.", position)
    if "exp" in payload and now >= payload["exp"]: raise error("E874", "JWT verification error", "JWT has expired.", position)
    if "nbf" in payload and now < payload["nbf"]: raise error("E874", "JWT verification error", "JWT is not active yet.", position)
    from .io_json import _from_json
    return _from_json(payload, position)


def _password_hash(arguments, named, position, runtime):
    password = secret_bytes(arguments[0], "password_hash() password", position, runtime); salt = os.urandom(16)
    digest = hashlib.scrypt(password, salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "$separan$scrypt$n=16384,r=8,p=1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def _password_verify(arguments, named, position, runtime):
    password, encoded = arguments
    if type(encoded) is not str: runtime.type_error(position, "password hash string", runtime.type_name(encoded), "password_verify() hash must be a string.")
    try:
        prefix, scheme, params, salt_text, digest_text = encoded.rsplit("$", 4)
        if prefix != "$separan" or scheme != "scrypt" or params != "n=16384,r=8,p=1": return False
        salt = base64.b64decode(salt_text, validate=True); expected = base64.b64decode(digest_text, validate=True)
        actual = hashlib.scrypt(secret_bytes(password, "password_verify() password", position, runtime), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, binascii.Error): return False


def _oauth_client_credentials(arguments, named, position, runtime):
    token_url, client_id, client_secret = arguments; scope = named.get("scope")
    if type(token_url) is not str or type(client_id) is not str: runtime.type_error(position, "string token URL and client ID", f"{runtime.type_name(token_url)}, {runtime.type_name(client_id)}", "OAuth token URL and client ID must be strings.")
    if scope is not None and type(scope) is not str: runtime.type_error(position, "string or null scope", runtime.type_name(scope), "OAuth scope must be a string or null.")
    form = [("grant_type", "client_credentials")]
    if scope is not None: form.append(("scope", scope))
    headers = ObjectValue.create({"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    from .http_client import _request
    response = _request([token_url], {"method": "POST", "headers": headers, "body": urlencode(form), "auth": _basic_auth([client_id, client_secret], {}, position, runtime)}, position, runtime)
    if not 200 <= response.status < 300 or response.text is None: raise error("E877", "oauth_error", f"OAuth token endpoint returned unusable status {response.status}.", position, actual=str(response.status))
    try: payload = json.loads(response.text)
    except json.JSONDecodeError: raise error("E877", "oauth_error", "OAuth token response is not valid JSON.", position)
    token, token_type = payload.get("access_token"), payload.get("token_type")
    expires, returned_scope = payload.get("expires_in"), payload.get("scope")
    if type(token) is not str or not token or type(token_type) is not str: raise error("E877", "oauth_error", "OAuth response requires string access_token and token_type.", position)
    if expires is not None and (type(expires) is not int or expires < 0): raise error("E877", "oauth_error", "OAuth expires_in must be a non-negative integer.", position)
    if returned_scope is not None and type(returned_scope) is not str: raise error("E877", "oauth_error", "OAuth scope must be a string.", position)
    return OAuthTokenValue(SecretValue(token.encode("utf-8")), token_type, expires, returned_scope)


AUTH_BUILTINS = (
    UtilityFunction("secret_get", 1, 1, _secret_get), UtilityFunction("basic_auth", 2, 2, _basic_auth),
    UtilityFunction("bearer_auth", 1, 1, _bearer_auth), UtilityFunction("api_key_auth", 2, 2, _api_key_auth, ("location",)),
    UtilityFunction("hmac_sha256", 2, 2, _hmac_sha256), UtilityFunction("jwt_sign", 2, 2, _jwt_sign, ("algorithm",)),
    UtilityFunction("jwt_verify", 2, 2, _jwt_verify, ("algorithm",)), UtilityFunction("password_hash", 1, 1, _password_hash),
    UtilityFunction("password_verify", 2, 2, _password_verify),
    UtilityFunction("oauth_client_credentials", 3, 3, _oauth_client_credentials, ("scope",)),
)
