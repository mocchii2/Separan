"""Honest, capability-gated HTTP client with an injectable transport."""

from dataclasses import dataclass
import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction
from .temporal import DurationValue
from .auth import HttpAuthValue
from .cookies import CookieJarValue, cookie_header, receive_cookies, _safe_name, _safe_value


@dataclass(frozen=True)
class HttpProfileValue:
    name: str
    user_agent: str
    accept: str
    accept_language: str
    accept_encoding: str


@dataclass(frozen=True)
class HttpTransportResponse:
    status: int
    url: str
    headers: dict
    body: bytes
    set_cookies: tuple = ()


@dataclass(frozen=True)
class HttpResponseValue:
    status: int
    url: str
    headers: ObjectValue
    bytes: BytesValue
    text: str | None
    encoding: str | None
    redirects: list
    cookies: ObjectValue


PROFILES = {
    "separan": ("Separan/0.1-alpha", "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "en", "identity"),
    "desktop": ("Separan-Desktop/0.1-alpha", "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "en", "identity"),
    "mobile": ("Separan-Mobile/0.1-alpha", "text/html,application/json;q=0.9,*/*;q=0.8", "en", "identity"),
}


def _profile(arguments, named, position, runtime):
    name = arguments[0]
    if type(name) is not str or name not in PROFILES: raise error("E781", "Invalid HTTP profile", "Profile must be separan, desktop, or mobile.", position, actual=repr(name))
    user_agent, accept, language, compression = PROFILES[name]
    values = {"user_agent": user_agent, "accept": accept, "language": language, "accept_encoding": compression}
    values.update(named)
    for key, value in values.items():
        if type(value) is not str or "\r" in value or "\n" in value: runtime.type_error(position, "safe string", runtime.type_name(value), f"HTTP profile {key} must be a string without line breaks.")
    return HttpProfileValue(name, values["user_agent"], values["accept"], values["language"], values["accept_encoding"])


def _profile_headers(arguments, named, position, runtime):
    profile = arguments[0]
    if not isinstance(profile, HttpProfileValue): runtime.type_error(position, "http_profile", runtime.type_name(profile), "http_profile_headers() requires an HTTP profile.")
    return ObjectValue.create({"User-Agent": profile.user_agent, "Accept": profile.accept, "Accept-Language": profile.accept_language, "Accept-Encoding": profile.accept_encoding})


def _validate_url(url, position, runtime, resolve=True):
    if type(url) is not str: runtime.type_error(position, "string URL", runtime.type_name(url), "HTTP URL must be a string.")
    capability = runtime.capabilities; capability.require(capability.network, "access network", position)
    parsed = urlsplit(url)
    if parsed.scheme not in capability.network_schemes or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise error("E780", "Invalid or denied URL", "URL scheme, host, user-info, or fragment violates network capability.", position, actual=url)
    host = parsed.hostname.lower()
    if capability.network_hosts is not None and not any(host == allowed or host.endswith("." + allowed) for allowed in capability.network_hosts):
        raise error("E780", "Denied HTTP host", "URL host is outside the network capability.", position, actual=host)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if capability.network_ports is not None and port not in capability.network_ports: raise error("E780", "Denied HTTP port", "URL port is outside the network capability.", position, actual=str(port))
    if resolve and not capability.allow_private_network:
        try: addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc: raise error("E783", "http_dns_error", str(exc), position, actual=host)
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global: raise error("E780", "Denied private network", "Network capability rejects non-public destination addresses.", position, actual=str(ip))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def urllib_transport(request):
    opener = build_opener(_NoRedirect)
    req = Request(request["url"], data=request["body"], headers=request["headers"], method=request["method"])
    try:
        response = opener.open(req, timeout=request["timeout"])
        return HttpTransportResponse(response.status, response.url, dict(response.headers.items()), response.read(request["max_bytes"] + 1), tuple(response.headers.get_all("Set-Cookie", [])))
    except HTTPError as response:
        return HttpTransportResponse(response.code, response.url, dict(response.headers.items()), response.read(request["max_bytes"] + 1), tuple(response.headers.get_all("Set-Cookie", [])))
    except URLError as exc: raise RuntimeError(str(exc.reason))


OPTIONS = ("method", "timeout", "redirect", "max_redirects", "encoding", "profile", "headers", "body", "max_bytes", "auth", "cookies", "cookie_jar")
FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization"}


def _request(arguments, named, position, runtime):
    url = arguments[0]; capability = runtime.capabilities
    method = named.get("method", "GET")
    if method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"): raise error("E781", "Invalid HTTP method", "HTTP method is unsupported or not uppercase.", position, actual=repr(method))
    timeout = named.get("timeout", DurationValue(30_000))
    if not isinstance(timeout, DurationValue) or timeout.milliseconds <= 0 or timeout.milliseconds > capability.max_http_timeout_ms: raise error("E782", "Invalid HTTP timeout", "Timeout must be a positive duration within the host limit.", position)
    redirect = named.get("redirect", True); max_redirects = named.get("max_redirects", 10)
    if type(redirect) is not bool or type(max_redirects) is not int or not 0 <= max_redirects <= 20: raise error("E785", "Invalid redirect option", "redirect must be boolean and max_redirects must be 0..20.", position)
    encoding_option = named.get("encoding", "auto")
    if type(encoding_option) is not str: runtime.type_error(position, "string", runtime.type_name(encoding_option), "HTTP encoding must be a string.")
    max_bytes = named.get("max_bytes", min(10_485_760, capability.max_http_response_bytes))
    if type(max_bytes) is not int or max_bytes < 0 or max_bytes > capability.max_http_response_bytes: raise error("E787", "http_limit_error", "max_bytes exceeds the network capability.", position, actual=repr(max_bytes))
    profile = named.get("profile", _profile(["separan"], {}, position, runtime))
    if not isinstance(profile, HttpProfileValue): runtime.type_error(position, "http_profile", runtime.type_name(profile), "profile must be an HTTP profile.")
    headers = dict(_profile_headers([profile], {}, position, runtime).fields)
    custom = named.get("headers")
    if custom is not None:
        if not isinstance(custom, ObjectValue): runtime.type_error(position, "object<string,string>", runtime.type_name(custom), "HTTP headers must be an object.")
        for key, value in custom.fields.items():
            if type(value) is not str or not key or any(ord(char) < 32 for char in key + value) or key.lower() in FORBIDDEN_HEADERS: raise error("E781", "Invalid HTTP header", "Header is unsafe or controlled by the transport.", position, actual=key)
            headers[key] = value
    body = named.get("body")
    if method in ("GET", "HEAD") and body is not None: raise error("E781", "Invalid HTTP body", "GET and HEAD cannot carry a body in Separan.", position)
    if body is None: body_bytes = None
    elif type(body) is str: body_bytes = body.encode("utf-8")
    elif isinstance(body, BytesValue): body_bytes = body.value
    else: runtime.type_error(position, "string, bytes, or null", runtime.type_name(body), "HTTP body has an invalid type.")
    auth = named.get("auth")
    if auth is not None:
        if not isinstance(auth, HttpAuthValue): runtime.type_error(position, "http_auth", runtime.type_name(auth), "auth must come from an authentication constructor.")
        try: auth_text = auth.value.value.decode("ascii")
        except UnicodeError: raise error("E872", "Invalid HTTP authentication", "Authentication value must be ASCII-safe.", position)
        if auth.location == "header":
            if auth.name.lower() in (key.lower() for key in headers): raise error("E872", "Duplicate authentication header", "auth conflicts with an explicitly supplied header.", position, actual=auth.name)
            headers[auth.name] = auth_text
        else:
            parsed_auth_url = urlsplit(url); query = parse_qsl(parsed_auth_url.query, keep_blank_values=True)
            if any(key == auth.name for key, _ in query): raise error("E872", "Duplicate authentication query", "auth conflicts with an existing query parameter.", position, actual=auth.name)
            query.append((auth.name, auth_text)); url = urlunsplit((parsed_auth_url.scheme, parsed_auth_url.netloc, parsed_auth_url.path, urlencode(query), parsed_auth_url.fragment))
    jar = named.get("cookie_jar")
    if jar is not None and not isinstance(jar, CookieJarValue): runtime.type_error(position, "cookie_jar", runtime.type_name(jar), "cookie_jar option requires a cookie jar.")
    explicit_cookies = named.get("cookies"); explicit = {}
    if explicit_cookies is not None:
        if not isinstance(explicit_cookies, ObjectValue): runtime.type_error(position, "object cookies", runtime.type_name(explicit_cookies), "cookies option requires an object.")
        for name, value in explicit_cookies.fields.items(): _safe_name(name, position); explicit[name] = _safe_value(value, "HTTP cookie", position, runtime).decode("ascii")
    redirects, current = [], _validate_url(url, position, runtime, resolve=runtime.http_transport is urllib_transport)
    visited = {current}
    initial_origin = (urlsplit(current).scheme, urlsplit(current).hostname, urlsplit(current).port)
    received = {}
    for count in range(max_redirects + 1):
        request_headers = dict(headers); cookie_values = {}
        if jar is not None:
            for part in filter(None, cookie_header(jar, current).split("; ")): cookie_values[part.split("=", 1)[0]] = part.split("=", 1)[1]
        origin = (urlsplit(current).scheme, urlsplit(current).hostname, urlsplit(current).port)
        if origin == initial_origin: cookie_values.update(explicit)
        if cookie_values: request_headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookie_values.items())
        request = {"url": current, "method": method, "headers": request_headers, "body": body_bytes, "timeout": timeout.milliseconds / 1000, "max_bytes": max_bytes}
        try: raw = runtime.http_transport(request)
        except Exception as exc: raise error("E784", "http_error", str(exc), position, actual=current)
        if len(raw.body) > max_bytes: raise error("E787", "http_limit_error", "HTTP response exceeded max_bytes.", position, actual=str(len(raw.body)))
        set_cookie_values = list(raw.set_cookies)
        if not set_cookie_values:
            set_cookie_values = [value for key, value in raw.headers.items() if key.lower() == "set-cookie"]
        if set_cookie_values:
            target_jar = jar if jar is not None else CookieJarValue()
            parsed_received = receive_cookies(target_jar, current, set_cookie_values, position)
            received.update(parsed_received.fields)
        if raw.status in (301, 302, 303, 307, 308) and redirect:
            location = next((value for key, value in raw.headers.items() if key.lower() == "location"), None)
            if not location: break
            if count >= max_redirects: raise error("E785", "http_redirect_error", "HTTP redirect count exceeded max_redirects.", position)
            previous = urlsplit(current)
            target = _validate_url(urljoin(current, location), position, runtime, resolve=runtime.http_transport is urllib_transport)
            parsed_target = urlsplit(target)
            if previous.scheme == "https" and parsed_target.scheme == "http": raise error("E785", "http_redirect_error", "HTTPS to HTTP redirect downgrade is forbidden.", position, actual=target)
            if target in visited: raise error("E785", "http_redirect_error", "HTTP redirect loop detected.", position, actual=target)
            if (previous.scheme, previous.hostname, previous.port) != (parsed_target.scheme, parsed_target.hostname, parsed_target.port):
                headers = {key: value for key, value in headers.items() if key.lower() not in ("authorization", "cookie", "proxy-authorization")}
            current = target; visited.add(current)
            redirects.append(current)
            if raw.status in (301, 302, 303) and method not in ("GET", "HEAD"): method, body_bytes = "GET", None
            continue
        break
    normalized = {key.lower(): value for key, value in raw.headers.items()}
    normalized.pop("set-cookie", None)
    selected = None if method == "HEAD" else "utf-8"
    if selected and encoding_option != "auto": selected = encoding_option
    if selected and encoding_option == "auto":
        content_type = normalized.get("content-type", "")
        for part in content_type.split(";")[1:]:
            if part.strip().lower().startswith("charset="): selected = part.split("=", 1)[1].strip().strip('"').lower()
    try: text = None if selected is None else raw.body.decode(selected)
    except (UnicodeError, LookupError): text = None
    return HttpResponseValue(raw.status, raw.url, ObjectValue.create(normalized), BytesValue(raw.body), text, selected if text is not None else None, redirects, ObjectValue.create(received))


def _get(arguments, named, position, runtime):
    named = dict(named); named["method"] = "GET"
    response = _request(arguments, named, position, runtime)
    if not 200 <= response.status < 300: raise error("E786", "http_status_error", f"HTTP GET returned status {response.status}.", position, actual=str(response.status))
    if response.text is None: raise error("E788", "http_decode_error", "HTTP response is not valid text in the selected encoding.", position)
    return response.text


HTTP_BUILTINS = (
    UtilityFunction("http_profile", 1, 1, _profile, ("language", "user_agent", "accept", "accept_encoding")),
    UtilityFunction("http_profile_headers", 1, 1, _profile_headers), UtilityFunction("http_request", 1, 1, _request, OPTIONS),
    UtilityFunction("http_get", 1, 1, _get, tuple(name for name in OPTIONS if name not in ("method", "body"))),
)
