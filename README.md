<p align="center">
  <img src="logo/separan_logo.png" alt="Separan" width="720">
</p>

# Separan

> **Structure should be named, not guessed.**
>
> Free programmers from indentation and bracket ambiguity.

[日本語](docs/README.ja.md) | English

## Run it in 30 seconds

```console
git clone https://github.com/mocchii2/Separan.git && cd Separan
python -m pip install -e .
python -m separan examples/hello.sep
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

Expected:
endif:check

Actual:
endif:wrong
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

if name != null :name_exists
print "Hello, " + name
endif:name_exists

end_function:main
```

Separan rejects structural mistakes before they can silently succeed:

```separan
if user.active :active_user
print "active"
endif:admin_user
```

```text
SEPARAN E104: Block label mismatch

Expected:
endif:active_user

Actual:
endif:admin_user
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
Modify only :active_user
```

The current parser already verifies that the opening and closing structure
agree. The planned AI edit-scope verifier extends that same identity to the
diff boundary:

```text
Future Separan verification:
No other block was modified.
```

The label is simultaneously human documentation, parser-checked structure, and
a future machine-verifiable edit boundary.

## v0.1.0-alpha.1

The current Python reference implementation includes strict label validation,
detailed diagnostics, fixed inferred types, homogeneous lists, functions,
`main` auto-start, conditionals, loops, comments, AST output, and a basic VS
Code TextMate grammar.

The standard library now covers explicit type conversion, Unicode string and
homogeneous-list processing, immutable bytes, datetime and duration values,
reproducible and secure randomness, filesystem and process utilities, HTTP
client/server previews, authentication, cookies, and parameter-bound SQLite.
Built-ins use the same strict argument and type diagnostics as user-defined
functions; implicit coercion remains forbidden.

String processing includes `trim`, `upper`, `lower`, `contains`, `starts_with`,
`ends_with`, `split`, `join`, `replace`, and code-point-based `substring`.

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

Authentication uses high-level primitives rather than user-built cryptography.
Host-provided secrets are a distinct automatically redacted type; HTTP auth,
OAuth client credentials, HMAC-SHA256, HS256 JWT, and scrypt password hashing
have experimental reference implementations.

HTTP supports one-shot cookies and explicit stateful Cookie Jars. Cookie values,
jar display, and received response cookies are redacted; domain, path, expiry,
and Secure attributes control transmission.

Lists are homogeneous and zero-based. Operations such as `list_append`,
`list_remove`, `slice`, `reverse`, and `sort` return new lists; v0.1 exposes no
mutating collection API.

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

```console
python -m pip install -e .
separan examples/hello.sep
separan --ast examples/if.sep
python -m unittest discover -s tests -v
```

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

Brand assets are available as the full [Separan logo](logo/separan_logo.png)
and square [Separan mark](logo/separan_mark.png). The original PNG files are
kept unchanged in the repository. A separately optimized 128px derivative is
used as the [VS Code extension icon](vscode/images/icon.png).

Read the [language specification](spec/README.md), the [design philosophy](docs/philosophy.md),
the [AI integration model](docs/ai-integration.md), the
[temporal-type specification](spec/temporal-types.md), and the [roadmap](ROADMAP.md).
The experimental [database standard](spec/database.md) documents the common API
and official SQLite, PostgreSQL, MySQL, Oracle, and SQL Server adapters.
The [reserved system context](spec/system-context.md) defines normalized,
read-only execution metadata and its namespace boundary.

## Status

Separan is experimental software at **v0.1.0-alpha.1**. The syntax and diagnostics
may change before v1.0. It is ready for exploration, not production use.

## License

Separan is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE)
for attribution information.
