# HTTP Client — v0.2 Design

Status: **experimental preview implemented**. `http_get`, `http_request`,
`http_profile`, fixed-shape responses, and scheme/host/port/private-network/
size/timeout capabilities are available. Sessions, cookies, streaming, and
browser automation remain separate and unimplemented.

> HTTP retrieval is not browser automation.

Separan provides a small text-first convenience API and a separate detailed
response API. JavaScript execution, DOM state, navigator properties, browser
cookies, viewport behavior, and browser fingerprinting belong to a future
`browser_*` module and are never implied by `http_*` functions.

## Simple API

```separan
html = http_get("https://example.com")
```

`http_get` performs an HTTP GET and returns the decoded response body as a
string. A non-success status, unsupported encoding, invalid text, response-size
limit, redirect violation, TLS failure, timeout, or network failure raises a
catchable `http_error` subtype. It never returns an error page as success.

The complete signature uses named arguments:

```separan
html = http_get(
    "https://example.com",
    profile = http_profile("desktop", language = "ja-JP"),
    timeout = duration("10s"),
    headers = {"X-Request-ID": "example"}
)
```

Named arguments are required for options so a duration, boolean, or object cannot
be mistaken for another option after reordering. Positional arguments must come
first, names are unique, and unknown names are parser errors.

## Detailed API

```separan
response = http_request(
    "https://example.com/api",
    method = "GET",
    timeout = duration("10s")
)

print response.status
print response.url
print response.text
print response.headers
```

`http_request` returns an immutable `http_response` value, not a generic object.
The initial fields are:

| Field | Type | Meaning |
|---|---|---|
| `status` | number | integer HTTP status |
| `url` | string | final URL after redirects |
| `headers` | `object` | normalized response headers, accessed with the object key API |
| `bytes` | bytes | raw decoded-transfer body |
| `text` | string or null | decoded text when decoding succeeds |
| `encoding` | string or null | selected character encoding |
| `redirects` | list[string] | visited redirect URLs, excluding initial URL |

Member access is introduced for fixed-shape values such as `http_response` and
fixed-shape values. Arbitrary header keys use
`object_get(response.headers, "content-type")`.

`http_request` does not raise solely because of a 4xx or 5xx status; callers can
inspect `status`. `http_get` requires `200 <= status < 300`. This distinction is
intentional and visible in the function name.

## Request options and defaults

| Option | Default | Rule |
|---|---|---|
| `method` | `"GET"` | uppercase `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, or `DELETE` |
| `timeout` | `duration("30s")` | positive duration, maximum `5m` |
| `redirect` | true | boolean |
| `max_redirects` | 10 | integer `0..20` |
| `encoding` | `"auto"` | `auto`, `utf-8`, or an explicitly supported encoding |
| `profile` | `http_profile("separan")` | explicit `http_profile` value |
| `headers` | empty object | string-to-string object |
| `body` | null | string, bytes, or null |
| `max_bytes` | 10,485,760 | integer `0..67,108,864` after decompression |

Method/body compatibility is strict. `GET` and `HEAD` reject a body in the
initial API. `HEAD` returns empty bytes and null text. Request bodies are never
created by implicit JSON or form conversion; future helpers such as
`http_post_json` must name the serialization.

Header names and values reject control characters and line breaks. The caller
cannot set `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, or
proxy-authentication headers. The runtime owns those transport headers.

## Text decoding

`encoding = "auto"` follows a deterministic order:

1. a valid supported `charset` in the response `Content-Type`;
2. UTF-8 otherwise.

There is no locale-dependent fallback and no silent replacement of malformed
bytes. Invalid bytes raise `http_decode_error`. BOM handling and the exact
supported encoding registry must be versioned before implementation. Binary
consumers use `response.bytes`, never `http_get`.

Content compression may be accepted, but `max_bytes` applies to the body after
decompression to limit decompression bombs.

## HTTP profiles

```separan
profile = http_profile(
    "desktop",
    language = "ja-JP",
    user_agent = "ExampleClient/1.0"
)
```

An `http_profile` is immutable configuration for HTTP headers. Initial fields:

```text
name
user_agent
accept
accept_language
accept_encoding
```

Built-in names are `separan`, `desktop`, and `mobile`. Their exact header values
are versioned as part of the runtime release and can be inspected with
`http_profile_headers(profile)`.

Profiles do not claim to emulate Chrome, Firefox, Safari, Windows, Android, or
another browser/OS unless a real compatible browser transport exists. Sending a
Chrome-looking User-Agent does not reproduce its TLS fingerprint, client hints,
cookie behavior, or JavaScript environment. Therefore names such as
`desktop_chrome` are reserved for the future browser subsystem and are not
provided by the HTTP client.

`os`, `screen_width`, and `screen_height` are not HTTP profile fields. Ordinary
HTTP does not transmit screen dimensions. They belong to a future
`browser_profile` used by `browser_open`. The HTTP client must not invent custom
headers for them. Likewise, `Sec-CH-UA*` headers are omitted unless supplied by
a future coherent browser implementation.

The default `separan` profile identifies itself honestly:

```text
User-Agent: Separan/<runtime-version>
Accept: text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8
Accept-Language: en
Accept-Encoding: gzip, deflate
```

System language is not used implicitly because it would make requests
environment-dependent. Callers select language explicitly.

## Network capability and SSRF protection

HTTP is disabled unless the CLI or embedding host grants a `network_capability`.
The capability defines:

- allowed schemes (`https` by default; `http` only when explicitly enabled);
- allowed host names or suffixes;
- allowed ports;
- whether loopback, private, link-local, multicast, and reserved IP ranges are
  reachable;
- maximum request and response sizes;
- optional request count and total-time budgets.

DNS results are checked against the capability before connection. Every redirect
target is parsed, resolved, and checked again. A public URL redirecting to
`127.0.0.1`, metadata endpoints, or a private address is rejected unless that
range was explicitly granted. User-info in URLs is forbidden. URL fragments are
not sent. Only `http` and `https` schemes are recognized.

TLS certificate and hostname verification is mandatory. The initial API has no
`verify = false` option. Proxy use and environment proxy variables are disabled
unless explicitly enabled by the host capability.

## Redirects and sensitive headers

- Redirect loops are errors.
- `max_redirects` counts followed redirects.
- `301`, `302`, and `303` may change POST to GET according to the documented
  HTTP policy; `307` and `308` preserve method and body.
- `Authorization`, `Cookie`, and other credential headers are removed when the
  origin changes.
- HTTPS-to-HTTP downgrade redirects are rejected unless capability explicitly
  permits both downgrade and destination.

The initial client has no persistent cookie jar. Each call is isolated. A future
`http_session` must make cookie and connection state explicit.

## Error hierarchy

Network errors are runtime errors and integrate with labeled catches:

```text
runtime_error
└─ http_error
   ├─ http_timeout_error
   ├─ http_dns_error
   ├─ http_tls_error
   ├─ http_redirect_error
   ├─ http_status_error       (`http_get` only)
   ├─ http_decode_error
   ├─ http_limit_error
   └─ permission_error
```

Planned diagnostics use `E780`–`E799`. Diagnostics must redact URL user-info,
authorization, cookies, and other secret headers. They include method, sanitized
URL, elapsed duration when known, and the redirect chain when relevant.

## Browser boundary

Future browser automation starts with separate names and value types:

```separan
profile = browser_profile(
    browser = "chromium",
    os = "windows",
    screen_width = 1920,
    screen_height = 1080,
    language = "ja-JP"
)
page = browser_open("https://example.com", profile = profile)
```

That subsystem may execute JavaScript and expose DOM, cookies, viewport, and
navigator state. It requires an actual browser engine. `http_get` and
`http_request` will never acquire these behaviors implicitly.

## Implementation order

1. named arguments and non-mutating object APIs;
2. catchable runtime-error values and network capability injection;
3. URL parser, redirect policy, body limits, and injectable transport;
4. `http_response`, `http_profile`, and deterministic fake-transport tests;
5. real HTTPS adapter and conformance tests against a local controlled server;
6. browser subsystem as a separate later module.

The conformance suite must not depend on public internet services.
