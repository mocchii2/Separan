# Separan native C core

This directory contains the native structural core for Separan. It validates the same named-boundary rules used by the Python reference implementation: block labels, nested block structure, branch identity, and unmatched or duplicate open labels.

The C CLI now executes a core subset: assignments, numeric/string/boolean/list
expressions, `SEP` functions, `if`/`elseif`/`else`, `while`, `for`, `return`,
`const`, object/list blocks, member access, and `print`. It includes a small set
of list, string, conversion, numeric, bytes, JSON, and root-scoped file built-ins.
The file built-ins currently cover text and bytes reads/writes, directory and
file discovery, copying, moving, and removal. Networking, databases, process
execution, and the remaining Python APIs are not implemented.
Hosts embedding the C library can call `separan_run_source_with_options` with
`separan_runtime_options` to set a filesystem root and deny read, write, or
path-discovery capabilities. The CLI enables these three local capabilities
within the source file's directory.
Its parser builds an AST for that subset. It does not yet provide the complete
Python language or runtime APIs. Use `--check` for the older structural-only
validator; an `OK` result from that mode does not mean a program is executable.
Cross-implementation lexer, structure, and execution checks live in
`tests/test_c_conformance.py`.
Run `python reference/c/parity_status.py` from the repository root to list
Python built-ins that have no C dispatch yet. This is a name inventory, not a
semantic equivalence claim.

## Path to runtime parity

1. Extend the cross-implementation checks to compare parser, diagnostics,
   stdout, stderr, exit status, and observable side effects.
2. Complete the C lexer (full Unicode normalization and all string semantics), then expand
   the AST/parser to the remaining statements and expressions. The execution
   path uses `separan_lex`; `--check` still uses the older line scanner.
3. Expand values, environments, calls, control flow, and built-ins to the full
   Python semantics. The current number value uses a C `double` with an
   integer/float display flag, so large integer precision and integer-only API
   checks still differ. Gate each feature with the same source programs on both CLIs.
4. Port capability-gated system APIs and language tooling, using the existing
   specification and Python tests as the behavior contract.

## Coverage

The current C core checks the structural contract that the Python implementation enforces:

- `SEP:name` / `END_SEP:name`
- compatibility `function:name` / `end_function:name`
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
gcc -std=c11 -Wall -Wextra -Iinclude src/main.c src/separan_core.c src/separan_lexer.c src/separan_files.c src/separan_runtime.c -o separan_core -lm
make all
```

The native library is exported as `libseparan.a` and exposes the public result API in `include/separan_core.h`.

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
