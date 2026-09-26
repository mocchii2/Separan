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

The current binary also accepts `--config <path>`. The config parser supports
`source = <path>` and `transport = stdio`; unknown keys are rejected rather
than silently ignored. `workers`, `max_memory`, listener sockets, and restart
limits belong to the planned supervisor and are not accepted by the current
worker.

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

On Linux, install the supervisor configuration at
`/etc/separan-gw/separan-gw.conf` and keep the runtime socket at
`/run/separan-gw/separan-gw.sock`.

The systemd unit belongs at `/etc/systemd/system/separan-gw.service`. On
Red Hat-family systems, service environment overrides conventionally live at
`/etc/sysconfig/separan-gw`; Debian-family packages may use the equivalent
`/etc/default/separan-gw` file. The unit should load that environment file and
pass the configured application and listener paths to the future supervisor.

Planned Linux layout:

```text
/etc/systemd/system/separan-gw.service
/etc/separan-gw/separan-gw.conf
/etc/sysconfig/separan-gw
/run/separan-gw/separan-gw.sock
/var/log/separan-gw/                 # supervisor-managed logs
```

Packaging templates are kept under
`reference/c/packaging/systemd/separan-gw.service` and
`reference/c/packaging/sysconfig/separan-gw`. They target the future
`separan-gw-supervisor`; the current released stdio binary does not claim to
implement this service unit yet.

The worker should load the application once, serve multiple requests, and exit
nonzero after an unrecoverable application or transport error. A supervisor
should restart it after failure and perform graceful replacement for upgrades.

The supervisor configuration contract is documented in
[`docs/separan-gw.conf.example`](separan-gw.conf.example), while the current
worker example contains only supported settings. Planned supervisor limits
are:

- `workers`: desired number of runtime workers;
- `max_memory`: per-worker RSS drain threshold;
- `max_requests`: per-worker request recycle threshold;
- `restart_grace`: time allowed for an in-flight request to finish;
- `restart_backoff`: delay after repeated worker failure.

The released stdio worker does not parse these supervisor settings yet. It
accepts one application and one transport stream; adding a setting without the
corresponding process supervision would create a misleading deployment
contract.

## nginx and Apache direction

The final nginx configuration will use a FastCGI adapter socket:

```nginx
location / {
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME /srv/app/app.sep;
    fastcgi_pass unix:/run/separan-gw/separan-gw.sock;
}
```

Apache will use the equivalent `mod_proxy_fcgi` backend. These snippets are
design targets until the FastCGI adapter is implemented; the current released
worker accepts stdio JSON only.
