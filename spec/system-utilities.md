# Regex, Glob, Environment, and Command Line — v0.2 Design

Status: **experimental preview implemented; APIs may change before v0.2**.

The preview implements all listed functions, named arguments, deterministic
globbing, process-local environment state, and injected command-line snapshots.
Matches provide `m.text`, `m.start`, `m.end`, and `m.group(index)`; the earlier
`regex_*` accessors remain available for compatibility. A strict regex-engine
work budget remains v0.2 stabilization work.

The shared rule is simple: absence returns `null` or an empty list when absence
is a normal search result. Invalid syntax, options, or capabilities produce an
error instead.

## Regular expressions

```separan
ok = regex_match("^[0-9]+$", "12345")
found = regex_search("error", log, ignore_case = true)
match = regex_find("([0-9]+)-([A-Z]+)", text)
matches = regex_find_all("[A-Z]+", text)
text = regex_replace("[0-9]+", "***", source)
parts = regex_split("[,;]", source)
```

`regex_match` requires a full-string match. `regex_search` reports whether a
partial match exists. `regex_find` returns the first immutable
`regex_match_result` or null; `regex_find_all` returns non-overlapping match
results. `regex_replace` replaces every match and `regex_split` returns strings.

A match result exposes `text`, Unicode-code-point `start` and `end`, and
`group(index)`. Group zero is the whole match, a valid nonparticipating group is
null, and an out-of-range group is an error.

Initial named flags are only `ignore_case`, `multiline`, and `dot_all`. There is
no magic flag string or locale-dependent mode. Replacement `$0` means the full
match, `$1` and above are captures, and `$$` is a literal dollar sign. Invalid
capture references are errors.

The Unicode-aware Separan regex subset is versioned independently of the host
engine. Lookbehind, backreferences, and recursive patterns are initially out of
scope. Invalid syntax and bounded-work exhaustion raise `regex_error`; they
never become false or null.

## File globbing

```separan
files = glob("logs/*.log")
sources = glob("src/**/*.sep")
```

- Results are project-root-relative `/`-separated strings.
- `**` is the sole recursive marker; no redundant `recursive` option exists.
- No match returns an empty list.
- Results are always sorted by Unicode code point, never filesystem order.
- Files and directories are both included initially.
- Dot entries match only when their pattern segment starts with `.`.
- Absolute paths, `..`, and symlink escape from the project root are rejected.
- The host must grant a separate `path_discovery` capability.

Invalid patterns and denied access are `glob_error` and `permission_error`, not
empty results.

## Environment variables

`env_get`, `env_exists`, `env_set`, and `env_remove` operate only on strings.
Missing `env_get` returns null unless an explicit named `default` is provided.
Mutations affect this Separan process and subsequently launched children only;
they never modify the parent process, operating-system-wide state, or persistent
user settings.

Hosts may separately allowlist readable and writable names. Denied access is a
`permission_error`, not absence. Windows lookup is case-insensitive and POSIX
lookup is case-sensitive. `env_all` is intentionally omitted initially because
bulk access can expose secrets.

## Command line

```separan
args = command_args()
script = script_path()
verbose = arg_exists("-v", "--verbose")
source = arg_value("--source")
count = number(arg_value("--count", default = "1"))
```

`command_args` excludes the script name. `script_path` returns the canonical
path, or null for stdin and embedded execution. `arg_exists` checks exact option
names before `--`. `arg_value` accepts `--name value` and `--name=value`.
Absence returns null or the explicit default; a present option without a value,
or a repeated value option, raises `argument_error`. Values always remain
strings until explicitly converted.

The host injects an immutable argument snapshot. A declarative CLI-schema block
is deferred.

## Planned diagnostics

| Range | Area |
|---|---|
| `E830`–`E839` | regex |
| `E840`–`E849` | glob and path discovery |
| `E850`–`E859` | environment |
| `E860`–`E869` | command-line arguments |
