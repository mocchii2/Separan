<p align="center">
  <img src="https://raw.githubusercontent.com/mocchii2/Separan/main/logo/separan_logo.png" alt="Separan" width="640">
</p>

# Separan

> **Structure should be named, not guessed.**
>
> Free programmers from indentation and bracket ambiguity.

> **AI may write the code. Humans still need to understand it.**

[日本語](https://github.com/mocchii2/Separan/blob/main/docs/README.ja.md) | English

[![PyPI](https://img.shields.io/pypi/v/separan?label=PyPI)](https://pypi.org/project/separan/)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/separan.separan-language?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

Separan makes AI-written code easier for people to read, understand, and
review. Labels turn otherwise anonymous control flow into visible intent:
`:validate_payment`, `:write_audit_log`, and `:retry_connection` become part of
the program's checked structure. A reviewer can understand what a block is for,
navigate its exact boundary, and verify where an AI made changes without first
reconstructing indentation or counting brackets.

This is not only about restricting AI. It is about making generated code
explain its structure to the human who remains responsible for it.

## Run it in 30 seconds

```console
git clone https://github.com/mocchii2/Separan.git && cd Separan
python -m pip install separan
separan examples/hello.sep
```

Python 3.10 or newer is required.

## Try it in five minutes

First, run a valid labeled block:

```separan
if true :check
print "ok"
endif:check
```

Then run the intentionally broken example:

```console
python -m separan examples/label_mismatch.sep
```

The closer names a different structure:

```separan
if true :check
print "ok"
endif:wrong
```

Separan points to the structural mistake and tells you the exact closer it
expected:

```text
SEPARAN E104: Block label mismatch

 --> demo.sep:3:7
  |
3 | endif:wrong
  |       ^^^^^

The closing or branch label must match its opening block.

Expected:
endif:check

Actual:
endif:wrong

Opened here:
 --> demo.sep:1:10
  |
1 | if true :check
  |          ^
```

That diagnostic is the language in miniature: structure is named and verified,
not inferred from indentation or bracket counting.

Separan is a label-structured scripting language designed for code that humans,
AI systems, and development tools can inspect without guessing where a block
ends. Indentation is decoration. Every block carries an explicit identity, and
its opener and closer must agree.

```separan
function:main
name = "Separan"

if name != null :名前あり
print "Hello, " + name
endif:名前あり

end_function:main
```

Block and multiline-comment labels accept NFC-normalized Unicode identifiers.
Program identifiers such as variables and function names remain ASCII-only.

Separan rejects structural mistakes before they can silently succeed:

```separan
if user.active :active_user
print "active"
endif:admin_user
```

```text
SEPARAN E104: Block label mismatch

 --> demo.sep:3:7
  |
3 | endif:admin_user
  |       ^^^^^^^^^^

The closing or branch label must match its opening block.

Expected:
endif:active_user

Actual:
endif:admin_user

Opened here:
 --> demo.sep:1:17
  |
1 | if user.active :active_user
  |                 ^
```

## The 30-second demo

Separan gives a meaningful name to the structure an AI is allowed to edit:

```separan
if user.active :active_user
print "active user"
endif:active_user
```

Give the AI a structural instruction instead of a line-number range:

```text
Modify only Separan scope function:main#1/if:active_user#1
```

The parser verifies that the opening and closing structure agree. The v0.4
review tool extends that identity to the diff boundary:

```text
PASS: AI edit scope verified.
Allowed changes 1, violations 0
```

The label is simultaneously human documentation, parser-checked structure, and
a machine-verifiable edit boundary.

Function tags add a second, semantic dimension when related code is separated:

```separan
function:send_notification
@notification
@aws
send_message()
end_function:send_notification
```

`@notification` is AST metadata, so tools can enumerate the exact function set
instead of asking an AI to guess what “notification-related” means.

```console
separan-structure diff before.sep after.sep
separan-structure verify before.sep after.sep --allow active_user
separan-structure inspect . --tag notification
separan-structure verify before.sep after.sep --allow-tag notification
```

Use `--json` for CI and review bots. The VS Code v0.4 extension can compare the
active file against Git `HEAD` and verify the label under the cursor. See the
[structural AI workflow](https://github.com/mocchii2/Separan/blob/main/spec/structural-ai.md).

## v0.2.0-alpha.13

The current Python reference implementation includes strict label validation,
detailed diagnostics, fixed inferred types, homogeneous lists, functions,
`main` auto-start, conditionals, loops, `#`/`##` comments, strict escaped and raw
strings, Function Tag metadata, and AST output. The v0.4
tooling layer adds a dependency-free LSP, rich VS Code support, structural
diffs, and enforced AI edit scopes without changing v0.1 language semantics.

The standard library now covers explicit type conversion, Unicode string and
homogeneous-list processing, immutable bytes, datetime and duration values,
reproducible and secure randomness, filesystem and process utilities, HTTP
client/server previews, authentication, capability-gated mail, YAML/XML structured data, cookies,
parameter-bound SQLite, native interface/DHCP/DNS/TCP/UDP networking, capability-checked embedded board profiles,
and Pico/Pico 2 C++ firmware generation with Pico SDK ELF/UF2/HEX builds.
Built-ins use the same strict argument and type diagnostics as user-defined
functions; implicit coercion remains forbidden.

This release also adds the experimental [AWS Lambda runtime](spec/aws-lambda.md):
host JSON is converted to immutable Separan values, parsed applications are
cached across warm invocations, explicit `aws_*` adapters form the capability
boundary, and `separan lambda-package` builds Linux-compatible ZIP artifacts.
The [monitor sample](examples/monitor/README.md) now keeps its Lambda routing,
suppression, and state decisions in Separan source.

## Native LAN, Wi-Fi, DNS, TCP, and UDP

The `0.2.0-alpha.13` reference runtime provides a capability-gated native network
layer for desktop and server scripts. It uses dedicated `ip_address`,
`network_interface`, `tcp_connection`, and `udp_socket` values rather than
passing ambiguous strings through every operation.

```separan
function:main

@network
@diagnostics

interfaces = network_interfaces()

for interface in interfaces :show_interfaces
print interface.name
print interface.kind
print interface.connected
print interface.ip_address
endfor:show_interfaces

end_function:main
```

Run the inspection sample with explicit host permission:

```console
separan examples/network.sep --allow-network-inspection
```

DNS returns every validated address deterministically. TCP and UDP return
bytes, so decoding remains explicit:

```separan
addresses = dns_resolve("example.com")

connection = tcp_connect(
    "example.com",
    80,
    timeout = duration("5s")
)

tcp_send(connection, "GET / HTTP/1.0\r\nHost: example.com\r\n\r\n")
reply = tcp_receive(connection, 65536)
print string_from_bytes(reply)
tcp_close(connection)
```

DHCP, static addressing, and IPv4 link-local are one common IP layer shared by
Ethernet and Wi-Fi adapters:

```separan
function:main

lan = ethernet_open()
network_use_dhcp(lan)

if network_wait_until_addressed(lan, duration("10s")) :address_ready
print network_ip_address(lan)
else:address_ready
print "DHCP failed"
endif:address_ready

end_function:main
```

Embedded adapters can now expose Wi-Fi AP, IPv4 DHCP-server, and simple local
DNS-server services without confusing them with the DHCP client API. AP
passwords require the redacted `secret` type, DHCP pools are bounded and
validated before startup, and captive-portal DNS behavior is explicit:

```separan
wifi = wifi_open()
setup_password = secret_from_environment("SEPARAN_SETUP_PASSWORD")
wifi_start_access_point(wifi, ssid = "Separan-Device", password = setup_password, channel = 6)

dhcp = dhcp_server_start(wifi, server_address = "192.168.4.1", prefix = 24, pool_start = "192.168.4.10", pool_end = "192.168.4.50", gateway = "192.168.4.1", dns_servers = ["192.168.4.1"], lease_time = duration("1h"))
```

The runtime API and adapter validation are implemented; Pico W/ESP32 adapters
still need to connect the contract to lwIP/Pico SDK/ESP-IDF. See the
[AP/DHCP/DNS sample](examples/network_access_point.sep) and
[network specification](spec/network.md).

Network inspection, address configuration, outbound destinations,
private-address access, and UDP binding are separate host capabilities.
Configuration requires `--allow-network-configuration` and an explicit adapter;
the default native inspector never escalates privileges or invokes a hidden
system configurator. See the [native network specification](spec/network.md).

## One source, multiple embedded boards

The embedded preview supports Raspberry Pi Pico/Pico W/Pico 2/Pico 2 W and
Arduino Nano/Nano Every through reviewed board profiles. The portable Blink
example names the board LED instead of copying a physical pin number:

```separan
function:main

@embedded
@gpio
@sample

gpio_set_mode(pin.LED_BUILTIN, "output")

while true :blink_loop
gpio_write(pin.LED_BUILTIN, true)
delay_milliseconds(500)
gpio_write(pin.LED_BUILTIN, false)
delay_milliseconds(500)
endwhile:blink_loop

end_function:main
```

The source stays identical; only the build target changes. Pico and Pico 2 now
run the complete C++ generation and official Pico SDK compile pipeline:

```console
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico_2
```

Each build emits a reviewable C++/CMake project and requires ELF, UF2, and HEX
outputs. Install the official Raspberry Pi Pico VS Code extension or pass the
SDK/tool paths explicitly. `--emit-only` generates without compiling, and
`--validate-only` keeps Pico W and Nano profiles available without pretending
that they already have firmware backends.

BOOTSEL deployment is explicit and refuses an unrecognized directory:

```console
separan flash build/01_blink-raspberry_pi_pico/build/separan_app_01_blink.uf2 --device E:\
```

`pin.LED_BUILTIN` resolves to GPIO25 for both non-wireless firmware targets.
Pico W CYW43 control and Arduino Core generation remain pending rather than
silently using an incorrect GPIO or backend.

The official [embedded examples](examples/embedded) now cover portable Blink,
button input, PWM fade, analog input, UART echo, and I²C scanning. The separate
[`01_blink_d13.sep`](examples/embedded/01_blink_d13.sep) example is intentionally
board-specific: use `pin.LED_BUILTIN` for portable code and `pin.D13` only when
the target profile defines D13 with the required capability.

Higher-order collection processing uses explicit `function` values:
`map`, `filter`, and initial-value-required `reduce` preserve strict callback
contracts. One-level `flatten`, `sum`, `average`, and value `count` complete the
core aggregates. [Readable mathematics](spec/mathematics.md) includes explicit
root/log names, statistics, moving averages, base conversion, and grouped
binary/octal/hexadecimal literals, with domain errors instead of silent
NaN/Infinity results.

String processing includes `trim`, `upper`, `lower`, `contains`, `starts_with`,
`ends_with`, `split`, `join`, `replace`, code-point-based `substring`/`char_at`,
non-overlapping literal `find_all`, and a string/list-shared `reverse`.

The experimental temporal implementation provides distinct `datetime`,
`local_datetime`, `timezone`, and `duration` values. It requires explicit zones,
rejects ambiguous DST wall times, and keeps Unix units visible in function names.
Run `separan --timezone-version` to inspect the active timezone database.

Randomness is split by purpose: seeded `random_*` functions use a reproducible
language-defined PCG32 stream, while `secure_random_*` functions use the
operating system's cryptographic source. Secure bytes have a distinct `bytes`
type rather than masquerading as a number list.

Binary values are immutable and never convert to strings implicitly. Explicit
UTF encodings, strict hex/Base64 codecs, slicing, byte lookup, and binary
concatenation are available in the reference preview.

Authentication and cryptography use safe-purpose APIs rather than user-built
cipher constructions. Host-provided secrets are a distinct automatically
redacted type; HTTP auth, OAuth client credentials, HMAC, HS256 JWT, and
Argon2id password hashing have experimental reference implementations.

```separan
client_secret = secret_from_environment("OAUTH_CLIENT_SECRET")
token = oauth_client_credentials("https://auth.example.com/oauth/token", "monitor-client", client_secret, scope = "monitor.read")
response = http_request(api_url, auth = bearer_auth(token.access_token))
```

OAuth token exchange is HTTPS-only, keeps access tokens redacted, and accepts
only explicit Bearer responses. Interactive browser login remains a separate
future subsystem.

The [cryptography preview](spec/cryptography.md) adds SHA-2/SHA-3 digests,
SHA-256/SHA-512 HMAC, explicit bytes-to-hex/Base64 conversion, constant-time
comparison, Argon2id key derivation, and versioned AES-256-GCM authenticated
encryption. Keys cannot be strings, nonces are generated internally, decrypted
secrets remain redacted, and obsolete or unauthenticated ciphers are omitted.

The [mail preview](spec/mail.md) composes provider-independent UTF-8 messages
with To/Cc/Bcc, text/HTML bodies, file or bytes attachments, and inline content.
An explicit sender selects verified STARTTLS/implicit-TLS SMTP or optional
Amazon SES; credentials stay `secret`, Bcc never enters MIME headers, and a
separate host capability controls mail delivery and address allowlists.

The [structured-data preview](spec/structured-data.md) adds strict YAML 1.2-style
data conversion and a separate XML document model. YAML preserves object order,
rejects duplicate keys and heterogeneous sequences, and supports multi-document
streams. XML keeps elements, attributes, namespaces, and text explicit while
rejecting DTD and entity declarations by default.

HTTP supports one-shot cookies and explicit stateful Cookie Jars. Cookie values,
jar display, and received response cookies are redacted; domain, path, expiry,
and Secure attributes control transmission.

Lists are homogeneous and zero-based. Operations such as `list_append`,
`list_remove`, `slice`, `reverse`, and every sort return new lists; v0.1 exposes
no mutating collection API. Stable sorting includes descending, Unicode
case-folded, natural-number, and object-field variants. See the
[list specification](https://github.com/mocchii2/Separan/blob/main/spec/lists.md).

`length(value)` and `is_empty(value)` work consistently across strings, lists,
and bytes. String search, repetition, and padding operate on Unicode code points;
failed `index_of` and `last_index_of` searches return null.

`const name = value` creates an immutable binding while ordinary assignment
remains mutable. Labeled object/list data blocks, namespaced imports,
capability-based I/O, explicit JSON boundary conversion, and labeled
`try`/`catch`/`finally` handling are all available experimentally in the
reference interpreter.

The accepted HTTP design keeps `http_get` lightweight and puts detailed status,
headers, and bytes in `http_request`. It explicitly does not impersonate a
browser: JavaScript, DOM, viewport, and navigator state belong to a future
`browser_open` subsystem.
The reference preview implements both APIs behind an explicit network
capability with host, scheme, port, redirect, timeout, and body-size checks.
Labeled HTTP routes and a separately capability-gated development host are also
available as a server preview. The dispatcher is transport-independent so a
future Lambda or production adapter can reuse the same `.sep` application.
The database preview separates its common API from official SQLite, PostgreSQL,
MySQL, Oracle, and Microsoft SQL Server adapters. SQLite is built in; the other
four are optional extras. Safe `?` placeholder scanning, strict single-row and scalar APIs,
labeled transactions, common metadata, and redacted connections are available.
Stable execution metadata is available through the reserved read-only `system`
context; dynamic values such as time, requests, randomness, and database state
remain explicit functions or scoped values.

The v0.5 Structure Explorer turns the active `.sep` file into a navigable block
tree. Each named structure shows its direct parameters, reads, writes, and
calls, plus added/modified/removed state against Git `HEAD`. Selecting a block
jumps to its opener; moving the cursor tracks the deepest enclosing scope. The
analysis is parser-backed and never executes the program. See the
[Structure Explorer specification](https://github.com/mocchii2/Separan/blob/main/spec/structure-explorer.md).

The Language Server preview is available as `separan-lsp`. It provides parser
and simple fixed-type diagnostics, mismatch Quick Fixes, typed Semantic Tokens,
Hover, definition, scope-safe label rename, matching highlights, completion,
signature help, inlay hints, labeled symbols/folding, and AST-preserving
formatting. See the [VS Code/LSP specification](https://github.com/mocchii2/Separan/blob/main/spec/vscode-extension.md).

The strict operator set includes power, integer floor division, null fallback,
compound assignment, and typed membership. See
[`examples/operators.sep`](https://github.com/mocchii2/Separan/blob/main/examples/operators.sep) and the
[language specification](https://github.com/mocchii2/Separan/blob/main/spec/README.md#operators).

External commands follow the same explicitness rule: `exec` passes a program and
argv directly, `exec_checked` turns nonzero exit into a catchable error, and the
separately gated `shell_exec` is the only API that interprets shell syntax.
These process APIs now have an experimental capability-gated implementation.

The utility implementation provides versioned Unicode regexes, deterministic
capability-gated `glob`, process-scoped environment access, and command-line
helpers that keep `script_path()` separate from `command_args()`.
An experimental implementation of these APIs and named function arguments is
available in the reference interpreter.

Labeled `object:name` and `list:name` data blocks, `user.name` member access,
namespaced imports, and labeled `try`/`catch`/`finally`/`throw` also have
experimental reference implementations.

## Deployable monitoring sample

The [Separan Monitor sample](https://github.com/mocchii2/Separan/tree/main/examples/monitor)
now includes one upload-ready CloudFormation YAML for up to five EC2 instances
and five RDS DB instances. Its inline `notify`, `log2`, `status`, and config-bootstrap
Lambda programs connect CloudWatch alarms, Windows/RDS logs, EventBridge state
events, Email/SMS/Teams delivery, S3 suppression schedules, and 30-day DynamoDB
history. The `.sep` modules remain executable as an AWS-free decision-core model.

```console
python -m pip install -e .
separan examples/hello.sep
separan --ast examples/if.sep
python -m unittest discover -s tests -v
```

The suite currently contains more than 1,900 tests. Its dedicated negative
conformance corpus checks syntax, structure, type and runtime failures, plus
too few, too many, and unknown named arguments across every registered built-in.

Python 3.10 or newer is required.

## Repository

```text
Separan/
├─ spec/        Language specification
├─ reference/   Python reference implementation
├─ tests/       Conformance and diagnostic tests
├─ examples/    .sep programs
├─ vscode/      VS Code extension
├─ docs/        Philosophy and AI integration
├─ logo/        Official Separan logo and mark
├─ ROADMAP.md
└─ LICENSE
```

Brand assets are available as the full [Separan logo](https://github.com/mocchii2/Separan/blob/main/logo/separan_logo.png)
and square [Separan mark](https://github.com/mocchii2/Separan/blob/main/logo/separan_mark.png). The display-ready PNG logo uses compact outer spacing, while a separately optimized 128px derivative is
used as the [VS Code extension icon](https://github.com/mocchii2/Separan/blob/main/vscode/images/icon.png).

Read the [language specification](https://github.com/mocchii2/Separan/blob/main/spec/README.md), the [design philosophy](https://github.com/mocchii2/Separan/blob/main/docs/philosophy.md),
the [AI integration model](https://github.com/mocchii2/Separan/blob/main/docs/ai-integration.md), the
[temporal-type specification](https://github.com/mocchii2/Separan/blob/main/spec/temporal-types.md), and the [roadmap](https://github.com/mocchii2/Separan/blob/main/ROADMAP.md).
The experimental [database standard](https://github.com/mocchii2/Separan/blob/main/spec/database.md) documents the common API
and official SQLite, PostgreSQL, MySQL, Oracle, and SQL Server adapters.
The [reserved system context](https://github.com/mocchii2/Separan/blob/main/spec/system-context.md) defines normalized,
read-only execution metadata and its namespace boundary.
The experimental [embedded board mapping](https://github.com/mocchii2/Separan/blob/main/spec/embedded-board-mapping.md)
adds reviewed logical-pin profiles for Raspberry Pi Pico/Pico 2 and Arduino Nano/Nano Every,
plus static validation and a Pico/Pico 2 C++ → Pico SDK → ELF/UF2/HEX firmware pipeline.

## Status

Separan is experimental software at **v0.2.0-alpha.13**. The syntax and diagnostics
may change before v1.0. It is ready for exploration, not production use.

## License

Separan is licensed under the [Apache License 2.0](https://github.com/mocchii2/Separan/blob/main/LICENSE). See [NOTICE](https://github.com/mocchii2/Separan/blob/main/NOTICE)
for attribution information.
