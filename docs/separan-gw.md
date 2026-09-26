# separan-gw

`separan-gw` is the Separan Gateway Worker. It keeps a parsed Separan
application resident and dispatches HTTP request objects through its
`http_route` declarations.

## Current transport

The default transport is line-oriented JSON over stdio:

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

The stdio JSON transport is useful for supervisors and tests. A FastCGI
responder is also available over binary stdio:

```console
separan-gw --source app.sep --fastcgi-stdio
```

It accepts FastCGI v1 responder records, maps CGI request parameters, query,
headers, and body bytes to the HTTP dispatcher, and returns CGI status/headers
and the route body in FastCGI STDOUT records. Configure
`transport = fastcgi-stdio` to select it. It handles one active request at a
time per stream.

FastCGI listeners are selected with `transport` and `listen`:

- `fastcgi-unix` with `listen = unix:<path>` binds a POSIX Unix-domain socket;
- `fastcgi-tcp` with `listen = tcp:<host>:<port>` binds a TCP socket. IPv6
    addresses use brackets, for example `tcp:[::1]:9000`;
- `fastcgi-pipe` with `listen = pipe:<name>` creates a Windows named pipe.

TCP and named-pipe listeners are single-worker by default. On POSIX, Unix and
TCP listeners can use the prefork supervisor. On Windows, named-pipe listeners
can use the process supervisor; TCP remains single-worker.

The binary accepts `--config <path>`. The parser supports `source`, all three
FastCGI listener transports, and the supervisor settings below. Unknown keys
and invalid transport/listener combinations are rejected.

## Gateway contract

The worker owns application loading, route dispatch, route parameters, query
values, headers, cookies, request bodies, response headers, response cookies,
redirects, and status codes. A front-end adapter owns protocol framing and
connection lifecycle.

The FastCGI parser is shared by stdio, socket, and named-pipe streams. The
remaining platform-specific restriction is Windows TCP supervision; its TCP
listener is available in single-worker mode. POSIX sockets and Windows named
pipes support the process supervisor.

Each worker handles one connection at a time. A POSIX supervisor shares the
bound listener across forked workers; Windows named-pipe workers create
instances with the same pipe name.

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

On Linux, install the gateway configuration at
`/etc/separan-gw/separan-gw.conf` and keep the runtime socket at
`/run/separan-gw/separan-gw.sock`.

The systemd unit belongs at `/etc/systemd/system/separan-gw.service`. On
Red Hat-family systems, service environment overrides conventionally live at
`/etc/sysconfig/separan-gw`; Debian-family packages may use the equivalent
`/etc/default/separan-gw` file. The included systemd template loads the
sysconfig file to locate the worker config.

Linux deployment layout:

```text
/etc/systemd/system/separan-gw.service
/etc/separan-gw/separan-gw.conf
/etc/sysconfig/separan-gw
/run/separan-gw/separan-gw.sock
```

The systemd unit launches `separan-gw --config`; supervisor settings in that
config start the embedded POSIX process manager. Worker output goes to the
systemd journal. Packaging templates are kept under
`reference/c/packaging/systemd/separan-gw.service` and
`reference/c/packaging/sysconfig/separan-gw`.

On POSIX, the parent loads the application and forks workers with copy-on-write
runtime state. On Windows, each named-pipe worker loads the configured app.
Workers exit after an unrecoverable transport error or a configured recycle
limit; the supervisor replaces them.

The example config uses the supported supervisor contract:

- `workers`: desired number of workers, from 1 to 256;
- `max_memory`: positive byte size, with optional `K`, `M`, or `G` suffix;
- `max_requests`: positive per-worker request recycle threshold;
- `restart_grace`: drain deadline in `ms`, `s`, or `m`;
- `restart_backoff`: fixed delay before replacing an exited worker, in `ms`, `s`, or `m`.

Supervisor settings require a FastCGI listener. POSIX workers receive SIGTERM,
finish an in-flight request, then exit; workers still alive after the grace
deadline are killed. Windows named-pipe workers receive CTRL_BREAK and are
force-stopped after the same deadline if necessary. On POSIX, send SIGHUP to
the gateway process to drain the pool and re-exec with the current config and
application source. On Windows, install the process with `--service`; SCM stop
and shutdown controls drain workers, and a service parameter-change control
replaces the pool so workers reload the config and application.
The running Windows supervisor keeps its worker-count and restart policy until
the service itself is restarted; changes to those supervisor settings require
a service restart.

Example Windows service registration from an elevated terminal:

```console
sc.exe create separan-gw binPath= "\"C:\Program Files\Separan\separan-gw.exe\" --config \"C:\ProgramData\Separan\separan-gw.conf\" --service" start= auto
sc.exe start separan-gw
```

Update the config/application files, then request a reload with:

```console
sc.exe control separan-gw paramchange
```

The service must run under an account that can read the config and app and
access the configured TCP port or named pipe.

The service name is `separan-gw`; install the executable at the path used by
the service registration command. On Linux, use `systemctl reload separan-gw`
only when a unit reload action is configured; otherwise signal the parent with
`kill -HUP <pid>` to request the in-place reload.

## nginx and Apache direction

The nginx FastCGI configuration can use the Unix socket listener and POSIX
worker pool:

```nginx
location / {
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME /srv/app/app.sep;
    fastcgi_pass unix:/run/separan-gw/separan-gw.sock;
}
```

Apache can use the equivalent `mod_proxy_fcgi` backend. For TCP, set
`transport = fastcgi-tcp` and `listen = tcp:127.0.0.1:9000`, then point the
front-end FastCGI client at that address.
