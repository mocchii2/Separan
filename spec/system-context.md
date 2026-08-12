# Reserved system context

> Reserved values describe the execution context. Dynamic operations remain functions.

`system` is a runtime-provided, read-only value in a reserved namespace. It
cannot be assigned, declared as a constant, used as a function or parameter
name, used as an import alias, or shadowed by a data block or loop variable.
Member assignment is not part of Separan's immutable object model and receives
an explicit diagnostic.

| Member | Meaning |
|---|---|
| `system.version` | Separan language/runtime release |
| `system.engine` | implementation identifier (`python-reference`) |
| `system.script_path` | absolute script path, or null for source without a path |
| `system.script_name` | final script filename, or null |
| `system.script_dir` | absolute containing directory, or null |
| `system.working_dir` | stable process working directory snapshot |
| `system.args` | command arguments excluding the script path |
| `system.arg_count` | number of entries in `system.args` |
| `system.os` | `windows`, `linux`, `macos`, or `unknown` |
| `system.arch` | normalized `x86_64`, `arm64`, `x86`, or host fallback |
| `system.hostname` | hostname snapshot |
| `system.pid` | process identifier |
| `system.runtime` | runtime family (`python` in the reference engine) |
| `system.cpu_count` | available logical CPU count, at least one |

The context is captured when an interpreter is created. `system.args` never
contains the script filename. `system` itself displays only
`system:[READONLY]`, so printing the whole context does not accidentally expose
arguments or host details.

Time and randomness are operations and therefore remain `datetime_now()` and
the random functions. HTTP request data belongs to the request context. Database
connections remain explicit values. Cloud-specific flags belong to extension
namespaces rather than the core `system` value.

The existing `command_args()` and `script_path()` functions remain compatibility
aliases during v0.x; new code should prefer the reserved context for stable
execution metadata.
