# Separan native C core

This directory contains the native structural core for Separan. It validates the same named-boundary rules used by the Python reference implementation: block labels, nested block structure, branch identity, and unmatched or duplicate open labels.

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

Use a C compiler such as GCC or Clang:

```console
gcc -std=c11 -Wall -Wextra -Iinclude src/main.c src/separan_core.c -o separan_core
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
```

This is a native validation layer intended to mirror the current Python-based structural specification while remaining lightweight enough to build and run on Windows and other hosts.
