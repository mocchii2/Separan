# separan-gw

`separan-gw` is the Separan Gateway Worker. It keeps a parsed Separan
application resident and dispatches HTTP request objects through its
`http_route` declarations.

## Current transport

The first transport is line-oriented JSON over stdio:

```console
separan-gw --source app.sep --stdio
```

The worker reads one request object per input line and writes one response
object per output line.

Request example:

```json
{"method":"GET","path":"/health"}
```

Response example:

```json
{"body":"ok","cookies":[],"headers":{"Content-Type":"text/plain"},"status":200}
```

The stdio transport is deliberately transport-neutral. It is suitable for
supervisors, tests, and an adapter process, but it is not itself a FastCGI
listener.

## Gateway contract

The worker owns application loading, route dispatch, route parameters, query
values, headers, cookies, request bodies, response headers, response cookies,
redirects, and status codes. A front-end adapter owns protocol framing and
connection lifecycle.

The planned adapters are:

- FastCGI records for nginx `fastcgi_pass` and Apache `mod_proxy_fcgi`;
- Unix-domain socket supervision for native deployments;
- Windows named-pipe supervision where Unix sockets are unavailable.

Each adapter must preserve one request/one response semantics and must not
reinterpret Separan values as generic template data.

## Process model

Recommended deployment names:

```text
separan-gw
separan-gw.service
separan-gw.conf
separan-gw.sock
```

The worker should load the application once, serve multiple requests, and exit
nonzero after an unrecoverable application or transport error. A supervisor
should restart it after failure and perform graceful replacement for upgrades.

## nginx and Apache direction

The final nginx configuration will use a FastCGI adapter socket:

```nginx
location / {
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME /srv/app/app.sep;
    fastcgi_pass unix:/run/separan/separan-gw.sock;
}
```

Apache will use the equivalent `mod_proxy_fcgi` backend. These snippets are
design targets until the FastCGI adapter is implemented; the current released
worker accepts stdio JSON only.
