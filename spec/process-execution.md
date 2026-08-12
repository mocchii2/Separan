# External Process Execution — v0.2 Design

Status: **experimental preview implemented**. `exec`, `exec_checked`,
`shell_exec`, `command_exists`, and fixed-shape results are available. Full
process-tree termination, streaming output enforcement, and portable shell IDs
remain stabilization work for v0.2.

> Prefer `exec` over `shell_exec`.

Separan makes direct process execution the standard operation. Shell parsing is
a separate, visibly dangerous operation with a stronger capability requirement.

## Direct execution

```separan
result = exec("git", ["status"])

print result.exit_code
print result.stdout
print result.stderr
```

`exec(command, args, ...)` invokes one executable directly. It never joins
arguments into a command string and never interprets pipes, redirection,
wildcards, variable expansion, command substitution, `&`, `;`, or shell quoting.

```separan
filename = input("file: ")
result = exec("tool", [filename])
```

If `filename` contains `&`, `;`, `*`, `$()`, or spaces, the entire value remains
one argument. This property is normative and must hold on every platform.

The initial signature uses named options:

```separan
result = exec(
    "python",
    ["script.py"],
    cwd = "work",
    timeout = duration("30s"),
    env = {"MODE": "test", "LANG": "ja_JP.UTF-8"},
    input = "c\na\nb\n"
)
```

`command` and every argument are strings. Empty command names and strings
containing NUL are errors. The argument list is homogeneous and is passed as an
argv vector without conversion.

## Result type

All normal process termination, including a nonzero exit code, returns an
immutable `exec_result`:

| Field | Type | Meaning |
|---|---|---|
| `exit_code` | number | integer exit code |
| `stdout` | string or null | decoded standard output, or null on decode failure |
| `stderr` | string or null | decoded standard error, or null on decode failure |
| `stdout_bytes` | bytes | exact captured standard output |
| `stderr_bytes` | bytes | exact captured standard error |
| `timed_out` | boolean | whether timeout termination was required |
| `duration` | duration | elapsed monotonic time |
| `command` | string | resolved executable path, sanitized for display |

`stdout` and `stderr` are null rather than string when byte decoding fails under
the selected encoding. The raw bytes remain available. Output streams are kept
separate and their cross-stream write order is not promised.

Signal termination or platform-specific abnormal termination uses a dedicated
negative `exit_code` mapping documented by each platform adapter. It is not
reported as successful exit code zero.

## Checked execution

```separan
try :run_git
result = exec_checked("git", ["pull"])
print result.stdout

catch command_error :run_git
print_error "git failed"
endtry:run_git
```

`exec_checked` has the same options and execution semantics as `exec`, but raises
`command_error` when the exit code is nonzero, and its subtype
`command_timeout_error` when the process times out. The
error contains the complete `exec_result`, accessible as `error.result` inside a
future catch-binding design. Executable-not-found, permission, spawn, encoding,
and resource-limit failures are errors for both `exec` and `exec_checked` because
no process result exists.

## Options and defaults

| Option | Default | Rule |
|---|---|---|
| `cwd` | capability working directory | relative path inside the capability root |
| `timeout` | `duration("30s")` | positive duration, maximum capability limit |
| `env` | empty object | explicit string-to-string additions/replacements |
| `inherit_env` | false | requires separate capability permission when true |
| `input` | null | string, bytes, or null |
| `encoding` | `"utf-8"` | output text decoding; no locale fallback |
| `max_stdout_bytes` | 1,048,576 | bounded by capability |
| `max_stderr_bytes` | 1,048,576 | bounded by capability |

The default environment is deliberately minimal rather than inherited. It
contains only runtime-required platform variables supplied by the adapter. The
caller-provided `env` is overlaid on that base. Environment names and values
containing NUL are rejected; name comparison follows platform rules but duplicate
names after platform normalization are errors.

When `inherit_env = true`, secrets from the host environment may become visible
to child processes, so both source code and host capability must opt in.

`input` is written to standard input and then closed. String input is encoded
with the selected encoding. No newline is appended. Child stdin is empty and
closed when input is null.

## Executable resolution

The process capability specifies one or more allowed executable identities:

- an exact canonical executable path; or
- a command name mapped by the host to an exact canonical path.

Separan does not search the current directory implicitly. Arbitrary host PATH
search is disabled by default. A capability may provide a fixed, ordered search
path; the resolved canonical path must still match its allowlist. Windows file
extension probing and script associations are disabled unless explicitly
configured by the adapter.

`command_exists(name)` uses exactly the same resolution and capability rules as
`exec` and returns a boolean. It does not reveal executables that exist but are
outside the granted capability.

```separan
if command_exists("git") :git_available
print "git found"
endif:git_available
```

There is no implicit fallback from a missing executable to shell lookup.

## Working directory and paths

`cwd` is resolved against the process capability root. Absolute paths and `..`
escape are rejected initially. The host may grant a narrower set of working
directories. An executable receives arguments exactly as strings; Separan does
not reinterpret path-looking arguments or promise they remain inside the root.
Filesystem isolation beyond `cwd` requires an operating-system sandbox and is a
separate host responsibility.

This distinction must be visible in documentation: allowlisting an executable
does not by itself confine what that executable can read, write, or access over
the network.

## Timeout, cancellation, and process trees

Processes start in a runtime-owned process group/job when supported. On timeout:

1. the runtime requests graceful termination of the whole owned process tree;
2. waits a fixed grace period, default two seconds;
3. forcefully terminates remaining owned processes;
4. drains bounded output pipes;
5. returns `timed_out = true` from `exec`, or throws `command_error` from
   `exec_checked`.

If the platform cannot guarantee tree termination, the process capability must
declare that limitation and execution is rejected unless the host explicitly
permits weak process isolation. Async execution, detached processes, interactive
TTYs, and background jobs are deferred.

## Output limits

Stdout and stderr are consumed concurrently to avoid pipe deadlocks. Limits are
measured in bytes before text decoding. Exceeding either limit terminates the
process tree and raises `command_limit_error`; output is never silently
truncated. A future streaming API will use a separate name and capability.

Text decoding is strict. Invalid byte sequences leave the corresponding text
field null in `exec`; `exec_checked` follows the same rule and does not fail only
because output is binary. Callers requiring text can use a future explicit
`require_stdout_text(result)` helper or inspect bytes.

## Shell execution

```separan
result = shell_exec("dir | findstr sep")
```

`shell_exec(command, ...)` passes one string to an explicitly selected shell.
It requires a separate `shell_capability`; ordinary process capability is not
sufficient. The API is disabled by default in CLI safe mode and embedding.

Named option `shell` is mandatory in the stable API unless the host capability
defines exactly one shell:

```separan
result = shell_exec(
    "printf '%s\\n' *.sep",
    shell = "posix_sh",
    timeout = duration("10s")
)
```

Planned portable shell identifiers are `posix_sh`, `powershell`, and
`cmd_windows`. Their syntax is intentionally not portable. A source file using
`shell_exec` should declare its platform expectation in project metadata.

`shell_exec` never interpolates Separan variables automatically. Concatenating
untrusted data into its command string is a shell-injection risk:

```separan
: Safe: filename is one argv item
exec("tool", [filename])

: Dangerous: filename becomes shell syntax
shell_exec("tool " + filename, shell = "posix_sh")
```

Static tooling should warn when `shell_exec` receives a non-constant expression.
There is intentionally no `shell_exec_checked`; callers can inspect the result
or use a future generic `require_success(result)`. Keeping the shell surface
small discourages accidental use.

## Capability model

Process execution is disabled unless the host grants `process_capability`.
Shell execution additionally requires `shell_capability`. Capabilities bound:

- executable paths and command aliases;
- working-directory roots;
- environment inheritance and allowed variable names;
- maximum arguments and aggregate argv bytes;
- timeout and process-count limits;
- stdin and captured-output byte limits;
- whether weak process-tree isolation is acceptable;
- whether child network access is sandboxed by the host.

Capabilities are runtime values supplied by the host, not constructible from
Separan source. Imported modules do not gain broader process rights than their
caller.

## Error hierarchy and diagnostics

```text
runtime_error
└─ process_error
   ├─ command_not_found_error
   ├─ command_permission_error
   ├─ command_spawn_error
   ├─ command_limit_error
   └─ command_error             (`exec_checked` nonzero exit)
      └─ command_timeout_error  (`exec_checked` timeout)
```

Planned diagnostics use `E800`–`E819`. Diagnostics include the sanitized
resolved executable, argument index for invalid argv, cwd, timeout, and exit
code when available. Environment values, stdin, and arguments marked secret by
the host must be redacted. Diagnostics never print a reconstructed shell command
for direct `exec`, because doing so falsely suggests shell parsing.

## Implementation and test requirements

1. named arguments, non-mutating object APIs, bytes, duration, and fixed-shape member
   access;
2. catchable runtime errors and process/shell capability injection;
3. an injectable process transport for deterministic unit tests;
4. platform adapters with argv round-trip tests containing spaces and shell
   metacharacters;
5. concurrent output-limit and timeout-tree tests;
6. real-process conformance tests using repository-owned helper executables,
   never arbitrary system tools.

The core conformance suite must not require `git`, `python`, `ping`, or a shell
to be installed under a particular name.
