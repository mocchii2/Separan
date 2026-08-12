"""Stateful cookie jars with RFC-oriented domain/path/security matching."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlsplit

from .auth import SecretValue, secret_bytes
from .errors import error
from .objects import ObjectValue
from .system_utilities import UtilityFunction


@dataclass
class CookieRecord:
    name: str
    value: bytes
    domain: str | None
    path: str
    expires: float | None
    secure: bool
    http_only: bool
    same_site: str | None
    host_only: bool
    order: int


@dataclass
class CookieJarValue:
    cookies: list = field(default_factory=list)
    counter: int = 0


def _jar(value, name, position, runtime):
    if not isinstance(value, CookieJarValue): runtime.type_error(position, "cookie_jar", runtime.type_name(value), f"{name}() requires a cookie jar.")
    return value


def _safe_name(name, position):
    if type(name) is not str or not name or any(char in name for char in "()<>@,;:\\\"/[]?={} \t\r\n"):
        raise error("E880", "Invalid cookie name", "Cookie name contains unsafe separator or control characters.", position, actual=repr(name))


def _safe_value(value, name, position, runtime):
    raw = secret_bytes(value, f"{name} value", position, runtime)
    if any(byte < 0x21 or byte > 0x7e or byte in b';,' for byte in raw): raise error("E880", "Invalid cookie value", "Cookie values must be visible ASCII without ';' or ','.", position)
    return raw


def _cookie_jar(arguments, named, position, runtime): return CookieJarValue()


def _store(jar, record):
    jar.cookies[:] = [item for item in jar.cookies if (item.name, item.domain, item.path) != (record.name, record.domain, record.path)]
    if record.expires is None or record.expires > datetime.now(timezone.utc).timestamp(): jar.cookies.append(record)


def _cookie_set(arguments, named, position, runtime):
    jar = _jar(arguments[0], "cookie_set", position, runtime); name, value = arguments[1:]
    _safe_name(name, position); raw = _safe_value(value, "cookie_set()", position, runtime)
    domain = named.get("domain"); path = named.get("path", "/"); secure = named.get("secure", False); http_only = named.get("http_only", True); same_site = named.get("same_site", "Lax")
    if domain is not None and type(domain) is not str: runtime.type_error(position, "string or null domain", runtime.type_name(domain), "Cookie domain must be string or null.")
    if type(path) is not str or not path.startswith("/"): raise error("E880", "Invalid cookie path", "Cookie path must start with '/'.", position, actual=repr(path))
    if type(secure) is not bool or type(http_only) is not bool: runtime.type_error(position, "boolean cookie flags", "non-boolean", "secure and http_only must be boolean.")
    if same_site not in ("Strict", "Lax", "None", None): raise error("E880", "Invalid SameSite", "same_site must be Strict, Lax, None, or null.", position, actual=repr(same_site))
    if same_site == "None" and not secure: raise error("E880", "Unsafe SameSite=None", "SameSite=None cookies must be Secure.", position)
    jar.counter += 1; _store(jar, CookieRecord(name, raw, domain.lower().lstrip(".") if domain else None, path, None, secure, http_only, same_site, domain is None, jar.counter)); return None


def _cookie_get(arguments, named, position, runtime):
    jar = _jar(arguments[0], "cookie_get", position, runtime); name = arguments[1]; _safe_name(name, position)
    live = _live(jar); matches = [item for item in live if item.name == name]
    return None if not matches else SecretValue(max(matches, key=lambda item: item.order).value)


def _cookie_remove(arguments, named, position, runtime):
    jar = _jar(arguments[0], "cookie_remove", position, runtime); name = arguments[1]; _safe_name(name, position)
    jar.cookies[:] = [item for item in jar.cookies if item.name != name]; return None


def _cookie_clear(arguments, named, position, runtime): _jar(arguments[0], "cookie_clear", position, runtime).cookies.clear(); return None


def _cookie_all(arguments, named, position, runtime):
    jar = _jar(arguments[0], "cookie_all", position, runtime); result = {}
    for item in sorted(_live(jar), key=lambda value: value.order): result[item.name] = SecretValue(item.value)
    return ObjectValue.create(result)


def _live(jar):
    now = datetime.now(timezone.utc).timestamp(); jar.cookies[:] = [item for item in jar.cookies if item.expires is None or item.expires > now]; return jar.cookies


def _domain_match(host, cookie):
    if cookie.domain is None: return True
    return host == cookie.domain if cookie.host_only else host == cookie.domain or host.endswith("." + cookie.domain)


def _path_match(path, cookie_path): return path == cookie_path or path.startswith(cookie_path.rstrip("/") + "/")


def cookie_header(jar, url):
    parsed = urlsplit(url); host, path = parsed.hostname.lower(), parsed.path or "/"; selected = []
    for item in _live(jar):
        if item.domain is None: item.domain, item.host_only = host, True
        if _domain_match(host, item) and _path_match(path, item.path) and (not item.secure or parsed.scheme == "https"): selected.append(item)
    selected.sort(key=lambda item: (-len(item.path), item.order))
    return "; ".join(item.name + "=" + item.value.decode("ascii") for item in selected)


def receive_cookies(jar, url, values, position):
    parsed = urlsplit(url); host = parsed.hostname.lower(); received = {}
    default_path = parsed.path.rsplit("/", 1)[0] or "/"
    for header in values:
        parsed_cookie = SimpleCookie()
        try: parsed_cookie.load(header)
        except CookieError as exc: raise error("E881", "Invalid Set-Cookie", str(exc), position)
        for name, morsel in parsed_cookie.items():
            _safe_name(name, position)
            try: raw = morsel.value.encode("ascii", errors="strict")
            except UnicodeError: raise error("E881", "Invalid Set-Cookie value", "Cookie value must be ASCII-safe.", position)
            domain_text = morsel["domain"].lower().lstrip(".") if morsel["domain"] else host
            host_only = not bool(morsel["domain"])
            if not (host == domain_text or host.endswith("." + domain_text)): raise error("E881", "Invalid Set-Cookie domain", "Server attempted to set a cookie for an unrelated domain.", position, actual=domain_text)
            expires = None
            if morsel["max-age"]:
                try: expires = datetime.now(timezone.utc).timestamp() + int(morsel["max-age"])
                except ValueError: raise error("E881", "Invalid Set-Cookie Max-Age", "Cookie Max-Age must be an integer.", position)
            elif morsel["expires"]:
                try: expires = parsedate_to_datetime(morsel["expires"]).timestamp()
                except (TypeError, ValueError): raise error("E881", "Invalid Set-Cookie Expires", "Cookie Expires is invalid.", position)
            same_site = morsel["samesite"].capitalize() if morsel["samesite"] else None
            if same_site not in (None, "Strict", "Lax", "None"): raise error("E881", "Invalid Set-Cookie SameSite", "SameSite must be Strict, Lax, or None.", position, actual=repr(same_site))
            if same_site == "None" and not morsel["secure"]: raise error("E881", "Unsafe Set-Cookie", "SameSite=None requires Secure.", position)
            jar.counter += 1; record = CookieRecord(name, raw, domain_text, morsel["path"] or default_path, expires, bool(morsel["secure"]), bool(morsel["httponly"]), same_site, host_only, jar.counter)
            _store(jar, record); received[name] = SecretValue(raw)
    return ObjectValue.create(received)


COOKIE_BUILTINS = (
    UtilityFunction("cookie_jar", 0, 0, _cookie_jar), UtilityFunction("cookie_get", 2, 2, _cookie_get),
    UtilityFunction("cookie_set", 3, 3, _cookie_set, ("domain", "path", "secure", "http_only", "same_site")),
    UtilityFunction("cookie_remove", 2, 2, _cookie_remove), UtilityFunction("cookie_clear", 1, 1, _cookie_clear),
    UtilityFunction("cookie_all", 1, 1, _cookie_all),
)
