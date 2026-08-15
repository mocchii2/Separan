"""High-level authentication primitives; no user-defined cryptography surface."""

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
from urllib.parse import quote_plus, urlencode, urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

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


PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


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


def _secret_from_environment(arguments, named, position, runtime):
    name = arguments[0]
    if type(name) is not str or not name or "\0" in name:
        runtime.type_error(position, "non-empty environment name", runtime.type_name(name), "secret_from_environment() requires a safe environment variable name.")
    runtime.capabilities.environment(name, False, position)
    value = runtime.environment_variables.get(name)
    if value is None: raise error("E871", "Secret unavailable", "The requested environment variable does not exist.", position, actual=name)
    if type(value) is not str: raise error("E871", "Secret unavailable", "Environment secret values must be strings.", position, actual=name)
    return SecretValue(value.encode("utf-8"))


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
    password = secret_bytes(arguments[0], "password_hash() password", position, runtime)
    return PASSWORD_HASHER.hash(password)


def _password_verify(arguments, named, position, runtime):
    password, encoded = arguments
    if type(encoded) is not str: runtime.type_error(position, "password hash string", runtime.type_name(encoded), "password_verify() hash must be a string.")
    password_bytes = secret_bytes(password, "password_verify() password", position, runtime)
    if encoded.startswith("$argon2id$"):
        try: return PASSWORD_HASHER.verify(encoded, password_bytes)
        except (InvalidHashError, VerificationError): return False
    # v0.1 generated scrypt hashes remain verifiable during the alpha migration.
    try:
        prefix, scheme, params, salt_text, digest_text = encoded.rsplit("$", 4)
        if prefix != "$separan" or scheme != "scrypt" or params != "n=16384,r=8,p=1": return False
        salt = base64.b64decode(salt_text, validate=True); expected = base64.b64decode(digest_text, validate=True)
        actual = hashlib.scrypt(password_bytes, salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, binascii.Error): return False


def _oauth_scope_is_valid(scope):
    if type(scope) is not str or not scope: return False
    return all(token and all(char == "!" or "#" <= char <= "[" or "]" <= char <= "~" for char in token) for token in scope.split(" "))


def _oauth_token_endpoint(token_url, position):
    if type(token_url) is not str:
        raise error("E877", "oauth_error", "OAuth token endpoint must be a string URL.", position)
    try: parsed = urlsplit(token_url)
    except ValueError: raise error("E877", "oauth_error", "OAuth token endpoint is not a valid URL.", position)
    if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise error("E877", "oauth_error", "OAuth token endpoint must be an absolute HTTPS URL without embedded credentials or a fragment.", position)
    return token_url


def _oauth_client_auth(client_id, client_secret, position, runtime):
    if type(client_id) is not str or not client_id or any(ord(char) < 32 or ord(char) == 127 for char in client_id):
        runtime.type_error(position, "non-empty string client ID", runtime.type_name(client_id), "OAuth client ID must be a non-empty string.")
    try: secret_text = secret_bytes(client_secret, "OAuth client secret", position, runtime).decode("utf-8")
    except UnicodeDecodeError: raise error("E877", "oauth_error", "OAuth client secret must be valid UTF-8 text.", position)
    if not secret_text or any(ord(char) < 32 or ord(char) == 127 for char in secret_text):
        raise error("E877", "oauth_error", "OAuth client secret must be non-empty text without control characters.", position)
    encoded_id = quote_plus(client_id, safe="")
    encoded_secret = quote_plus(secret_text, safe="")
    token = base64.b64encode(f"{encoded_id}:{encoded_secret}".encode("ascii"))
    return HttpAuthValue("basic", "Authorization", SecretValue(b"Basic " + token))


def _oauth_payload(response, position):
    if response.text is None:
        raise error("E877", "oauth_error", f"OAuth token endpoint returned unusable status {response.status}.", position, actual=str(response.status))
    try: payload = json.loads(response.text)
    except json.JSONDecodeError:
        if not 200 <= response.status < 300:
            raise error("E877", "oauth_error", f"OAuth token endpoint rejected the request with status {response.status}.", position, actual=str(response.status))
        raise error("E877", "oauth_error", "OAuth token response is not valid JSON.", position)
    if type(payload) is not dict:
        raise error("E877", "oauth_error", "OAuth token response must be a JSON object.", position)
    if not 200 <= response.status < 300:
        oauth_code = payload.get("error")
        if type(oauth_code) is str and oauth_code and len(oauth_code) <= 128 and all(char.isascii() and (char.isalnum() or char in "_-.") for char in oauth_code):
            raise error("E877", "oauth_error", f"OAuth token endpoint rejected the request: {oauth_code}.", position, actual=oauth_code)
        raise error("E877", "oauth_error", f"OAuth token endpoint rejected the request with status {response.status}.", position, actual=str(response.status))
    return payload


def _oauth_client_credentials(arguments, named, position, runtime):
    token_url, client_id, client_secret = arguments; scope = named.get("scope")
    token_url = _oauth_token_endpoint(token_url, position)
    if scope is not None and not _oauth_scope_is_valid(scope):
        raise error("E877", "oauth_error", "OAuth scope must contain one or more space-separated visible ASCII scope tokens.", position)
    form = [("grant_type", "client_credentials")]
    if scope is not None: form.append(("scope", scope))
    headers = ObjectValue.create({"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    from .http_client import _request
    response = _request([token_url], {"method": "POST", "headers": headers, "body": urlencode(form), "auth": _oauth_client_auth(client_id, client_secret, position, runtime)}, position, runtime)
    payload = _oauth_payload(response, position)
    token, token_type = payload.get("access_token"), payload.get("token_type")
    expires, returned_scope = payload.get("expires_in"), payload.get("scope")
    if type(token) is not str or not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise error("E877", "oauth_error", "OAuth response requires a non-empty visible-ASCII access_token.", position)
    if type(token_type) is not str or token_type.casefold() != "bearer":
        raise error("E877", "oauth_error", "OAuth client credentials currently accepts only the Bearer token type.", position)
    if expires is not None and (type(expires) is not int or expires < 0): raise error("E877", "oauth_error", "OAuth expires_in must be a non-negative integer.", position)
    if returned_scope is not None and not _oauth_scope_is_valid(returned_scope): raise error("E877", "oauth_error", "OAuth response scope is invalid.", position)
    if "refresh_token" in payload: raise error("E877", "oauth_error", "OAuth client credentials response must not contain a refresh token.", position)
    return OAuthTokenValue(SecretValue(token.encode("ascii")), "Bearer", expires, returned_scope)


AUTH_BUILTINS = (
    UtilityFunction("secret_get", 1, 1, _secret_get), UtilityFunction("secret_from_environment", 1, 1, _secret_from_environment),
    UtilityFunction("basic_auth", 2, 2, _basic_auth),
    UtilityFunction("bearer_auth", 1, 1, _bearer_auth), UtilityFunction("api_key_auth", 2, 2, _api_key_auth, ("location",)),
    UtilityFunction("hmac_sha256", 2, 2, _hmac_sha256), UtilityFunction("jwt_sign", 2, 2, _jwt_sign, ("algorithm",)),
    UtilityFunction("jwt_verify", 2, 2, _jwt_verify, ("algorithm",)), UtilityFunction("password_hash", 1, 1, _password_hash),
    UtilityFunction("password_verify", 2, 2, _password_verify),
    UtilityFunction("oauth_client_credentials", 3, 3, _oauth_client_credentials, ("scope",)),
)
