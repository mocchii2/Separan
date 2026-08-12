"""Transport-independent HTTP application dispatcher for Separan routes."""

from dataclasses import dataclass, field
import mimetypes
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote_to_bytes, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import SecretValue
from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction


@dataclass(frozen=True)
class ServerRequest:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class ServerResponse:
    status: int
    headers: dict
    body: bytes
    cookies: tuple = ()


class HttpReturned(Exception):
    def __init__(self, response): self.response = response


def _context(runtime, position):
    if runtime.http_request_context is None: raise error("E893", "No HTTP request context", "Request API can only run inside an HTTP route.", position)
    return runtime.http_request_context


def _request_method(args, named, position, runtime): return _context(runtime, position)["request"].method
def _request_path(args, named, position, runtime): return _context(runtime, position)["request"].path


def _request_header(args, named, position, runtime):
    name = args[0]
    if type(name) is not str: runtime.type_error(position, "string", runtime.type_name(name), "request_header() name must be a string.")
    return _context(runtime, position)["request"].headers.get(name.lower())


def _request_param(args, named, position, runtime):
    name = args[0]
    if type(name) is not str: runtime.type_error(position, "string", runtime.type_name(name), "request_param() name must be a string.")
    return _context(runtime, position)["params"].get(name)


def _request_query(args, named, position, runtime):
    name = args[0]
    if type(name) is not str: runtime.type_error(position, "string", runtime.type_name(name), "request_query() name must be a string.")
    values = _context(runtime, position)["request"].query.get(name); return None if not values else values[0]


def _request_body(args, named, position, runtime):
    request = _context(runtime, position)["request"]
    try: return request.body.decode(named.get("encoding", "utf-8"))
    except (UnicodeError, LookupError): raise error("E894", "HTTP request decode error", "Request body cannot be decoded with the selected encoding.", position)


def _request_cookie(args, named, position, runtime):
    name = args[0]; header = _context(runtime, position)["request"].headers.get("cookie", "")
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name: return SecretValue(value.encode("ascii"))
    return None


def _response(args, named, position, runtime):
    status = named.get("status", 200); body = named.get("body", ""); content_type = named.get("content_type", "text/plain; charset=utf-8")
    if type(status) is not int or not 100 <= status <= 599: raise error("E895", "Invalid HTTP response status", "status must be integer 100..599.", position, actual=repr(status))
    if type(body) is str: raw = body.encode("utf-8")
    elif isinstance(body, BytesValue): raw = body.value
    else: runtime.type_error(position, "string or bytes", runtime.type_name(body), "HTTP response body must be string or bytes.")
    headers = {"Content-Type": content_type}
    custom = named.get("headers")
    if custom is not None:
        if not isinstance(custom, ObjectValue): runtime.type_error(position, "object", runtime.type_name(custom), "response headers must be an object.")
        headers.update(custom.fields)
    context = _context(runtime, position); raise HttpReturned(ServerResponse(status, headers, raw, tuple(context["response_cookies"])))


def _redirect(args, named, position, runtime):
    location = args[0]; status = named.get("status", 302)
    if type(location) is not str or status not in (301, 302, 303, 307, 308): raise error("E895", "Invalid HTTP redirect", "redirect requires a string location and redirect status.", position)
    raise HttpReturned(ServerResponse(status, {"Location": location}, b""))


def _set_cookie(args, named, position, runtime):
    name, value = args
    if type(name) is not str or not name or any(character in name for character in "()<>@,;:\\\"/[]?={} \t\r\n"):
        raise error("E895", "Invalid response cookie", "Cookie name contains an invalid character.", position, actual=repr(name))
    raw = value.value if isinstance(value, SecretValue) else value.encode("ascii") if type(value) is str else None
    if raw is None: runtime.type_error(position, "secret or string", runtime.type_name(value), "http_set_cookie() value must be secret or string.")
    try: text = raw.decode("ascii")
    except UnicodeDecodeError: raise error("E895", "Invalid response cookie", "Cookie values must be ASCII.", position)
    if any(character in text for character in ";\r\n"):
        raise error("E895", "Invalid response cookie", "Cookie value contains an invalid character.", position)
    path = named.get("path", "/"); same_site = named.get("same_site", "Lax")
    if type(path) is not str or not path.startswith("/") or "\r" in path or "\n" in path: raise error("E895", "Invalid response cookie", "Cookie path must be an absolute HTTP path.", position)
    if same_site not in (None, "Lax", "Strict", "None"): raise error("E895", "Invalid response cookie", "same_site must be Lax, Strict, None, or null.", position)
    parts = [name + "=" + text, "Path=" + path]
    if named.get("secure", False): parts.append("Secure")
    if named.get("http_only", True): parts.append("HttpOnly")
    if same_site: parts.append("SameSite=" + same_site)
    _context(runtime, position)["response_cookies"].append("; ".join(parts)); return None


def _http_host(args, named, position, runtime):
    host, port = named.get("host", "127.0.0.1"), named.get("port", 8080); capability = runtime.capabilities
    capability.require(capability.host_http, "host HTTP server", position)
    if type(host) is not str or host not in capability.http_bind_hosts: raise error("E897", "Denied HTTP bind host", "Bind host is outside the host capability.", position, actual=repr(host))
    if type(port) is not int or not 1 <= port <= 65535 or (capability.http_bind_ports is not None and port not in capability.http_bind_ports): raise error("E897", "Denied HTTP bind port", "Bind port is invalid or outside the host capability.", position, actual=repr(port))
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            length = int(self.headers.get("Content-Length", "0")); body = self.rfile.read(length)
            parsed = urlsplit(self.path); headers = {key.lower(): value for key, value in self.headers.items()}
            response = runtime.dispatch_http(ServerRequest(self.command, parsed.path, parse_qs(parsed.query), headers, body))
            self.send_response(response.status)
            for key, value in response.headers.items(): self.send_header(key, str(value))
            for cookie in response.cookies: self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(response.body))); self.end_headers()
            if self.command != "HEAD": self.wfile.write(response.body)
        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = handle_request
        def log_message(self, format, *args): pass
    try: ThreadingHTTPServer((host, port), Handler).serve_forever()
    except OSError as exc: raise error("E897", "HTTP host error", str(exc), position, actual=f"{host}:{port}")


def _http_static(args, named, position, runtime):
    url, directory = named.get("url"), named.get("directory")
    if type(url) is not str or not url.startswith("/") or not url.endswith("/") or "?" in url or "#" in url:
        raise error("E898", "Invalid static URL", "Static URL prefix must start and end with '/'.", position, actual=repr(url))
    if type(directory) is not str:
        runtime.type_error(position, "string directory", runtime.type_name(directory), "http_static() directory must be a string.")
    runtime.capabilities.require(runtime.capabilities.read_files, "read static files", position)
    root = runtime.capabilities.path(directory, "http_static", position)
    if not root.is_dir(): raise error("E898", "Invalid static directory", "Static directory does not exist or is not a directory.", position, actual=directory)
    if any(prefix == url for prefix, _ in runtime.http_static_mounts):
        raise error("E899", "Duplicate static mount", "Static URL prefixes must be unique.", position, actual=url)
    runtime.http_static_mounts.append((url, root.resolve()))
    return None


SERVER_BUILTINS = (
    UtilityFunction("request_method", 0, 0, _request_method), UtilityFunction("request_path", 0, 0, _request_path),
    UtilityFunction("request_header", 1, 1, _request_header), UtilityFunction("request_param", 1, 1, _request_param),
    UtilityFunction("request_query", 1, 1, _request_query), UtilityFunction("request_body", 0, 0, _request_body, ("encoding",)),
    UtilityFunction("request_cookie", 1, 1, _request_cookie),
    UtilityFunction("return_http", 0, 0, _response, ("status", "content_type", "headers", "body")),
    UtilityFunction("redirect_http", 1, 1, _redirect, ("status",)),
    UtilityFunction("http_set_cookie", 2, 2, _set_cookie, ("path", "secure", "http_only", "same_site")),
    UtilityFunction("http_host", 0, 0, _http_host, ("host", "port")),
    UtilityFunction("http_static", 0, 0, _http_static, ("url", "directory")),
)


def compile_path(pattern):
    parts, names = [], set()
    for segment in pattern.strip("/").split("/") if pattern != "/" else []:
        if segment.startswith(":"):
            name = segment[1:]
            if not name or name in names: raise ValueError("invalid or duplicate route parameter")
            names.add(name); parts.append((True, name))
        else: parts.append((False, segment))
    return parts


def match_path(compiled, path):
    values = path.strip("/").split("/") if path != "/" else []
    if len(values) != len(compiled): return None
    params = {}
    for (dynamic, value), actual in zip(compiled, values):
        if dynamic: params[value] = actual
        elif value != actual: return None
    return params


def static_response(request, mounts):
    if request.method not in ("GET", "HEAD"): return None
    for prefix, root in sorted(mounts, key=lambda item: len(item[0]), reverse=True):
        if not request.path.startswith(prefix): continue
        encoded = request.path[len(prefix):]
        try: decoded = unquote_to_bytes(encoded).decode("utf-8")
        except UnicodeDecodeError: return ServerResponse(400, {"Content-Type": "text/plain; charset=utf-8"}, b"Bad Request")
        relative = PurePosixPath(decoded)
        if "\\" in decoded or "\0" in decoded or relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            return ServerResponse(404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found")
        if decoded == "": relative = PurePosixPath("index.html")
        candidate = (root / Path(*relative.parts)).resolve()
        if candidate != root and root not in candidate.parents: return ServerResponse(404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found")
        if not candidate.is_file(): return ServerResponse(404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found")
        try: body = candidate.read_bytes()
        except OSError: return ServerResponse(404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found")
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json", "image/svg+xml"):
            content_type += "; charset=utf-8"
        return ServerResponse(200, {"Content-Type": content_type}, body)
    return None
