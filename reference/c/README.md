# Separan native C core

This directory contains the native structural core for Separan. It validates the same named-boundary rules used by the Python reference implementation: block labels, nested block structure, branch identity, and unmatched or duplicate open labels.

The native runtime must remain an independent C implementation. Shipping or
embedding CPython, launching the Python reference runtime, and delegating
language or built-in behavior to Python are outside the parity design.

The C CLI executes the current language statement and expression surface:
assignments, typed declarations, `SEP` functions, labeled control flow,
errors, transactions, imports, HTTP routes, object/list blocks, member access,
EMPTY/EMPTYS, and the current operator set. It includes native list,
collection, object, string, math, deterministic and secure random, SHA-2/SHA-3,
bytes, JSON, XML escaping, fixed-offset date/time, CLI argument, environment,
standard-input, and root-scoped file built-ins.
The file built-ins currently cover text and bytes reads/writes, directory and
file discovery (including globbing), copying, moving, and removal. The complete
15-function database surface is available through the public
`separan_database_adapter` host interface. It supports connection lifecycle,
queries, scalar and execute results, transactions, metadata, and stable
E900--E907 error classes while keeping database credentials and native handles
inside the host driver. SQLite, PostgreSQL, MySQL, and Oracle adapters therefore
share one UTF-8 JSON boundary without Python delegation. The four process APIs
(`exec`, `exec_checked`, `shell_exec`, and `command_exists`) are likewise
available through `separan_process_adapter`, including binary output, duration,
timeout state, and E800--E809 process error classes.
The public `separan_host_adapter` covers the capability-gated HTTP client and
server, authentication, mail, cookie storage, embedded hardware, networking,
network service, cryptography, regex, YAML, and XML APIs. Calls use one JSON
request containing positional `arguments` and `named` arguments; hosts return a
JSON value or a stable Separan error code and message. This keeps operating
system, TLS, device, and service dependencies outside the language runtime.
Hosts embedding the C library can call `separan_run_source_with_options` with
`separan_runtime_options` to set a filesystem root, deny read, write, or
path-discovery and environment capabilities, and supply the script path and command arguments.
They can also retain parsed state with `separan_runtime_create`, call named
Separan functions through `separan_runtime_invoke_json`, and dispatch labeled
HTTP routes through `separan_runtime_dispatch_http_json`. Both invocation APIs
use allocated UTF-8 JSON results released by `separan_runtime_release_string`.
Native HTTP dispatch implements route validation and duplicate detection,
path parameters, query/header/body/cookie access, HEAD fallback, responses,
redirects, and response cookies without a Python process or web framework.
The `separan-gw` gateway worker provides line-oriented JSON stdio, FastCGI stdio,
POSIX Unix/TCP listeners, and a Windows named-pipe listener over the same HTTP
dispatch API. POSIX listeners and Windows named pipes support worker pools with
request/memory recycling, restart backoff, and graceful drain. See the gateway
guide for configuration and platform limits.
See [docs/separan-gw.md](../../docs/separan-gw.md) for the gateway contract,
process model, and nginx/Apache adapter direction.
The CLI enables the three local filesystem capabilities within the source
file's directory and forwards arguments after the source path.
Its parser builds and executes a native AST without CPython. `--check` uses the
same lexer, parser, declaration validation, and label validation without
executing top-level statements or `main`; host adapters are therefore not
required for syntax checking.
Cross-implementation lexer, structure, and execution checks live in
`tests/test_c_conformance.py`.
`python reference/c/generate_unicode_tables.py --check` verifies that the
checked-in lexer tables match the Unicode database bundled with Python.
Run `python reference/c/parity_status.py` from the repository root to list
Python built-ins that have no C dispatch yet. This is a name inventory, not a
semantic equivalence claim.

## Path to runtime parity

1. Extend the cross-implementation checks to compare parser, diagnostics,
   stdout, stderr, exit status, and observable side effects.
2. Keep lexer and parser conformance aligned as the grammar evolves. Both
   execution and `--check` use generated Unicode 15.1 identifier,
   combining-class, and composition tables and validate NFC labels, comment
   delimiters, and semantic tag paths without a runtime dependency.
3. Close the remaining value-level edge cases. The runtime preserves arbitrary
   precision integers separately from floating-point values across literals,
   JSON, comparisons, formatting, core arithmetic, base conversion, aggregate
   sums, factorial, GCD, and LCM. Fixed-width host APIs continue to validate
   their documented bounds before converting an integer.
4. Port capability-gated system APIs and language tooling, using the existing
   specification and Python tests as the behavior contract.

Phase 4's runtime API surface is now connected through the database, process,
and general host adapters. The C registry is checked against the Python
reference signatures so newly added or changed host APIs fail conformance tests
until the native boundary is updated.

The executable parser is also checked against the shared negative language
corpus. All cases that do not require a configured host value currently match
the Python E-code. Regex adapter results are validated and retained as native
`regex_match_result` values with `text`, `start`, `end`, and `group()` access;
malformed fixed-shape results are rejected at the adapter boundary.
HTTP responses, mail addresses, and mail send results are likewise validated,
retain their public Separan type names, and expose only their documented
members instead of becoming unrestricted generic objects.

The native registry now covers all 504 Python reference built-in names. The
final core additions include all public error constructors and the mutating
`list_insert`, `list_remove_horizontal`, and `list_remove_vertical` shape
operations. Name coverage remains an inventory; cross-implementation tests are
the semantic parity gate.

The executable parser/runtime also supports labeled `try`, ordered `catch`,
`finally`, `throw`, and top-level custom `error` declarations. Explicit error
values preserve category inheritance for the authentication, cryptography,
mail, YAML, XML, and network families; an uncaught explicit error exits with
E760. Native type, value, index, file, JSON, database, process, and general host
adapter failures enter the same catch path while retaining their original
E-code when they remain uncaught.

`print_error` writes a value and newline to the configured error stream. A
labeled `transaction connection :label` block begins a database transaction,
commits after normal completion (including `return`), and rolls back when the
body raises or throws before control reaches `end_transaction:label`.

Explicit scalar and recursive `list<type>` declarations are checked by the C
runtime for variables, constants, function parameters, and object fields.
Typed `EMPTY`, `is EMPTY`, `is not EMPTY`, `EMPTYS`, and indexed list
assignment retain declared slot types and container shapes.
JSON `null` values cross the native JSON boundary as EMPTY values. Mixed and
all-null arrays preserve or adopt their element type, and encode back to
`null` without losing list shape.
The executable expression layer includes right-associative `??`, membership
with `in` and `not in`, numeric and list compound assignments, and the
`front`/`back` selectors used by list shape operations.

Namespaced imports support relative `.sep` modules, exported functions,
constants, and custom error constructors. Module `main` functions are not run
on import, canonical module instances are cached for the execution, and import
order, traversal, cycles, and private members produce E701--E706 diagnostics.
Embedding hosts enable this separately with the `import_modules` option.

## Coverage

The current C core checks the structural contract that the Python implementation enforces:

- `SEP:name` / `END_SEP:name`
- `if ... :label` / `elseif ... :label` / `else:label` / `endif:label`
- `while ... :label` / `endwhile:label`
- `for ... :label` / `endfor:label`
- object/list/try/error/http_route/transaction block validation
- duplicate open labels (`E109`)
- mismatched closer labels (`E104`)
- unexpected closers and unclosed blocks (`E107`, `E106`)
- multiline comment scoping

## Build

Use a C compiler such as GCC or Clang to build the CLI or the reusable native library:

```console
gcc -O1 -std=c11 -Wall -Wextra -Iinclude src/main.c src/separan_core.c src/separan_lexer.c src/separan_files.c src/separan_runtime.c -o separan_core -lm
make all
```

The native library is exported as `libseparan.a` and exposes the public result API in `include/separan_core.h`.
`separan_validate_source` and `separan_validate_path` use the same native parser as
the CLI `--check` command and return its first structured diagnostic.
For labeled function, branch, and block closer mismatches, `expected` and
`actual` carry the complete closer text (for example, `END_SEP:main` and
`END_SEP:wrong`, or `endif:active` and `endif:wrong`); related position points
to the original block label.
The result also exposes one-based primary and related line/column positions.
E105 block-kind and nesting mismatches include the expected closer, actual
closer, and the innermost opening block location. E107 unexpected closers
include their actual closer text and primary position without an expected or
related location. E106 unclosed blocks report the expected closer and opening
position; E109 duplicate labels report the duplicated label and the original
opener position. E100 expected-expression errors expose the Python-compatible
category and description, plus the offending token as `actual` and its
one-based source position. E100 trailing-token errors expose the matching
`Unexpected token` category, statement-boundary description, actual token, and
position. Missing closing delimiters for grouped expressions, function
parameters, and direct/member calls; list/index brackets; typed-list angle
brackets; function, constant, import, and loop separators; block opener and
closer punctuation; missing declaration names; and catch/branch labels expose
Python-compatible `Syntax error` categories and descriptions. Unexpected
same-line tokens after function headers and statements expose the matching
`Unexpected token` category, statement-boundary description, actual token, and
source position. E128 invalid `is` operands and EMPTY/EMPTYS equality
comparisons expose state-test guidance, expected form, actual token, and source
position. E112 duplicate parameters, E113 duplicate named arguments, E114
positional arguments after named arguments, E116 duplicate object fields, and
E117-E119 invalid try-handler cases expose Python-compatible categories and
descriptions; argument, parameter, catch, and field errors also expose the
offending name and primary position where applicable. E120 nested error
declarations, E121 invalid error names, E122 duplicate error names, E123
unknown declared types, and E124 missing typed initializers expose matching
categories, descriptions, expected forms, actual values, and source positions.
The E122 `:end` editor-completion diagnostic also reports the expected complete
block closer and actual `:end` token.
E216 tags outside functions, E217 tags after executable statements, and E218
duplicate function tags expose matching categories, descriptions, actual tag
values, and primary positions.
E214 immutable system members and E215 reserved context bindings likewise
expose the read-only context category, description, actual binding or member,
and primary position.
E108 invalid if branches and E110 invalid top-level statements expose their
Python-compatible category, description, offending token, and primary position.
E204 duplicate functions, E205 invalid `main` signatures, and E209 reserved
function names expose matching categories, descriptions, expected signatures
where applicable, actual names, and declaration positions.
E702 late imports and E703 nested imports expose the matching import-order
category, description, and primary position.
E890 nested HTTP routes, E891 invalid route methods, and E892 invalid route
paths expose matching categories, descriptions, actual values where relevant,
and primary positions.
E896 duplicate HTTP routes expose the unique method/path requirement and actual
route identity at the duplicate declaration position.
Runtime invocations and HTTP dispatches can retrieve their last structured
failure detail through `separan_runtime_get_diagnostic()` without changing the
existing return-code or error-stream behavior.
Runtime E301 division failures expose the operator-specific description and
zero actual value; execute-body E127 VOID-use, E129 EMPTY-type, and E130
constant failures likewise populate runtime category, description, actual, and
source position fields.
`separan_analyze_source` and `separan_analyze_path` remain legacy structural-only
scanner entry points for ABI compatibility; new callers should use `separan_validate_*`.

```c
#include "separan_core.h"

separan_result result = separan_validate_source("SEP:main\nEND_SEP:main\n");
if (!result.ok) {
    printf("%s\n", result.errors[0].code);
}
```

## Portable download bundles

### Windows ZIP

For a quick no-install path on Windows, build:

```console
make zip
```

This creates `dist/separan-portable.zip` containing:

- `separan.exe`
- `separan.cmd`
- `README.md`

Users can extract the ZIP anywhere and run the bundled command directly via `separan.cmd` or `separan.exe`.

### Linux tar.gz

For Linux, build the portable archive with:

```console
make linux-tarball
```

This creates `dist/separan-linux-x86_64.tar.gz` containing a portable Linux bundle that can be extracted and run directly.

## Run

```console
./separan_core testdata/hello.sep
./separan_core --check testdata/hello.sep
```

This is a native validation layer intended to mirror the current Python-based structural specification while remaining lightweight enough to build and run on Windows and other hosts.
