<p align="center">
  <img src="https://raw.githubusercontent.com/mocchii2/Separan/main/logo/separan_logo.png" alt="Separan" width="720">
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

```console
separan-structure diff before.sep after.sep
separan-structure verify before.sep after.sep --allow active_user
```

Use `--json` for CI and review bots. The VS Code v0.4 extension can compare the
active file against Git `HEAD` and verify the label under the cursor. See the
[structural AI workflow](https://github.com/mocchii2/Separan/blob/main/spec/structural-ai.md).

## v0.1.0-alpha.2

The current Python reference implementation includes strict label validation,
detailed diagnostics, fixed inferred types, homogeneous lists, functions,
`main` auto-start, conditionals, loops, comments, and AST output. The v0.4
tooling layer adds a dependency-free LSP, rich VS Code support, structural
diffs, and enforced AI edit scopes without changing v0.1 language semantics.

The standard library now covers explicit type conversion, Unicode string and
homogeneous-list processing, immutable bytes, datetime and duration values,
reproducible and secure randomness, filesystem and process utilities, HTTP
client/server previews, authentication, cookies, and parameter-bound SQLite.
Built-ins use the same strict argument and type diagnostics as user-defined
functions; implicit coercion remains forbidden.

Higher-order collection processing uses explicit `function` values:
`map`, `filter`, and initial-value-required `reduce` preserve strict callback
contracts. One-level `flatten`, `sum`, `average`, and value `count` complete the
core aggregates. Math includes finite real trigonometric, logarithmic, and
exponential functions with domain errors instead of NaN/Infinity results.

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

Authentication uses high-level primitives rather than user-built cryptography.
Host-provided secrets are a distinct automatically redacted type; HTTP auth,
OAuth client credentials, HMAC-SHA256, HS256 JWT, and scrypt password hashing
have experimental reference implementations.

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

## Monitoring dogfooding model

The runnable [Separan Monitor model](https://github.com/mocchii2/Separan/tree/main/examples/monitor)
turns mock EC2, log, and job events into either simulated delivery or a
reason-bearing suppression record. It demonstrates the four-module
`notify`/`logcheck`/`status`/`normal_check` boundary, fixed suppression order,
deduplication, and complete notification-candidate history using Separan code.
AWS deployment is deliberately kept outside the example until strict YAML and
typed AWS capability adapters exist.

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

Brand assets are available as the full [Separan logo](https://github.com/mocchii2/Separan/blob/main/logo/separan_logo.png)
and square [Separan mark](https://github.com/mocchii2/Separan/blob/main/logo/separan_mark.png). The original PNG files are
kept unchanged in the repository. A separately optimized 128px derivative is
used as the [VS Code extension icon](https://github.com/mocchii2/Separan/blob/main/vscode/images/icon.png).

Read the [language specification](https://github.com/mocchii2/Separan/blob/main/spec/README.md), the [design philosophy](https://github.com/mocchii2/Separan/blob/main/docs/philosophy.md),
the [AI integration model](https://github.com/mocchii2/Separan/blob/main/docs/ai-integration.md), the
[temporal-type specification](https://github.com/mocchii2/Separan/blob/main/spec/temporal-types.md), and the [roadmap](https://github.com/mocchii2/Separan/blob/main/ROADMAP.md).
The experimental [database standard](https://github.com/mocchii2/Separan/blob/main/spec/database.md) documents the common API
and official SQLite, PostgreSQL, MySQL, Oracle, and SQL Server adapters.
The [reserved system context](https://github.com/mocchii2/Separan/blob/main/spec/system-context.md) defines normalized,
read-only execution metadata and its namespace boundary.

## Status

Separan is experimental software at **v0.1.0-alpha.2**. The syntax and diagnostics
may change before v1.0. It is ready for exploration, not production use.

## License

Separan is licensed under the [Apache License 2.0](https://github.com/mocchii2/Separan/blob/main/LICENSE). See [NOTICE](https://github.com/mocchii2/Separan/blob/main/NOTICE)
for attribution information.
