# Modules, Data, I/O, and Errors — v0.2 Design

Status: **partially implemented preview**. Labeled objects/lists, member access,
non-mutating object APIs, namespaced imports, labeled errors, standard streams,
high-level file I/O, deterministic JSON, and root/environment capabilities are
available.

This design sequences features that depend on each other. The first two stages
and error handling now have previews:

```text
object/block-list values → namespaced imports → I/O and JSON → labeled error handling
```

Implementations must not expose file or JSON failures before the language has a
structured value model and a catchable error model.

Capability-gated HTTP follows named arguments, objects, and labeled catchable
errors. See the separate [HTTP design](http.md).

External processes follow the same host-capability model and are specified in
the separate [process execution design](process-execution.md).

## Constants

Constants are implemented now:

```separan
const pi = 3.14159
const app_name = "Separan"
```

A name without `const` is mutable. A constant cannot be assigned again in its
own scope. Duplicate mutable/constant declarations in the same scope are errors.
Global and function-local scopes remain separate, so a local binding may shadow
a global constant without mutating it. `const` is shallow: once object/list values
exist, the binding cannot point elsewhere, while value-level immutability will
be specified separately.

## Labeled data blocks

Separan source does not adopt JSON's `{}` and `[]` notation. Human-authored
structured data uses named blocks, like every other Separan structure:

```separan
object:user
name = "Alice"
age = 30
active = true

object:address
city = "Tokyo"
zip = "100-0001"
end_object:address
end_object:user

list:users
"Alice"
"Bob"
"Carol"
end_list:users
```

A top-level or function-body `object:user` creates the `user` binding. Nested
`object:address` and `list:roles` blocks populate fields with those names. Every
closing label must exactly match its opener; indentation remains decorative.

Initial rules:

- object field names are unique identifiers; object fields may have different types;
- block lists remain homogeneous and zero-based;
- an object or list cannot refer to itself before its closing label;
- `user.name` accesses an existing identifier field; a missing field is an error;
- arbitrary JSON string keys use `object_get(value, key)` and `object_has`, so
  keys such as `x-api-key` remain representable;
- update APIs are non-mutating and duplicate source fields are errors;
- `{}` is reserved from both control and data syntax. Removing existing `[]`
  expression lists requires a separate compatibility decision, but block lists
  are the canonical multiline notation.

This is not alternate JSON syntax. Objects and lists are language values; JSON
exists only as an explicit boundary conversion.

## Namespaced imports

The initial module syntax is deliberately singular:

```separan
import "utils/math.sep" as math
result = math.add(10, 20)
```

- `as alias` is mandatory; unqualified imports are forbidden.
- Imports occur only at top level and before executable top-level statements.
- Paths are UTF-8 strings, resolved relative to the importing file.
- The `.sep` extension is mandatory.
- Absolute paths and `..` path traversal are rejected initially.
- A module exposes top-level functions and constants. Mutable globals remain
  private in the first implementation.
- Imported bindings are accessed through the namespace; copying names into the
  caller scope is deferred.
- Loading is cached by canonical path, so a module executes at most once.

Circular imports are errors and show the full canonical chain:

```text
SEPARAN E701: Circular import

a.sep
→ b.sep
→ a.sep
```

Import resolution must accept an explicit project root in embedding and CLI
APIs. It must not search arbitrary working-directory or environment paths.

## Standard input and output

```separan
name = input("Name: ")
print name
print_error "Invalid value"
```

`input(prompt)` writes the prompt to standard output without a newline and
returns one line without its line terminator. End-of-input is an `io_error`, not
an empty string. `print_error` is a statement, parallel to `print`, and writes a
newline to standard error. Streams must be injectable for deterministic tests.

## High-level file I/O

The initial API avoids handles:

```separan
text = read_text("config.txt")
write_text("output.txt", text)
append_text("log.txt", "hello\n")

data = read_bytes("image.bin")
write_bytes("copy.bin", data)
lines = read_lines("log.txt")

if file_exists("config.txt") :config_exists
print file_size("config.txt")
endif:config_exists

copy_file("a.txt", "b.txt")
move_file("b.txt", "archive/b.txt")
delete_file("archive/b.txt")
```

- Text is UTF-8; invalid UTF-8 is an `io_error` with a specific diagnostic.
- Text writes use UTF-8 without BOM.
- Paths are resolved against an explicit capability root supplied by the host.
- Absolute paths and escape from that root are forbidden.
- `write_text` and `write_bytes` use replace-via-temporary-file semantics where
  the platform supports it; they do not expose partial writes as success.
- None of these functions performs implicit string/bytes conversion.
- Low-level file handles are deferred.
- `copy_file` and `move_file` never silently overwrite an existing destination.
- `read_lines` removes line terminators and preserves other text.
- `create_directory` creates missing parents; `delete_directory` removes only an
  empty directory. Recursive deletion is deliberately absent.
- `list_directory` returns entry names in deterministic Unicode order.
- `file_name`, `file_extension`, `parent_directory`, and `absolute_path` use the
  same capability-relative validation. Extensions omit the leading dot.

Embedding hosts may disable file I/O entirely. Lack of capability is a distinct
`permission_error`, not a missing-file error.

## JSON

JSON follows object/list implementation. The API names emphasize conversion:

```separan
data = json_decode(text)
text = json_encode(data)
```

- JSON object → `object`
- JSON array → homogeneous `list`; heterogeneous arrays are rejected initially
- JSON number → `number`
- JSON string, boolean, and null map directly
- duplicate object keys are `parse_error`
- non-finite numbers are rejected
- `json_encode` is deterministic: object keys are emitted in Unicode code-point
  order with no insignificant whitespace
- cyclic values cannot exist through the initial non-mutating API

This initial JSON subset deliberately rejects valid-but-heterogeneous arrays
rather than weakening Separan's list type. Decoding JSON does not provide a
source-code emitter. JSON is a wire format, not Separan's human-authored syntax.

## Labeled error handling

```separan
try :load_config
text = read_text("app.json")
data = json_decode(text)

catch io_error :load_config
print_error "Could not read app.json"

catch parse_error :load_config
print_error "Invalid JSON"

finally:load_config
print "done"
endtry:load_config
```

Rules:

- every `catch`, `finally`, and `endtry` label matches the opening `try`;
- zero or more catches are allowed, followed by at most one `finally`;
- `catch any` must be last;
- duplicate catch types are errors;
- `finally` always runs after entry into the try block, including after return or
  a new error;
- if `finally` throws, that new error becomes active and retains the prior error
  as related diagnostic context;
- errors propagate until a matching catch is found; no error is silently
  converted to null or a default value.

Initial catchable categories form a hierarchy:

```text
runtime_error
├─ type_error
├─ value_error
├─ index_error
├─ io_error
├─ parse_error
├─ import_error
├─ regex_error
├─ glob_error
├─ argument_error
└─ permission_error
```

`catch runtime_error` catches all listed runtime categories. `catch any` also
catches future user-defined categories. Parser and compile-time diagnostics are
not catchable by program code.

User-thrown built-in errors use explicit constructors:

```separan
throw value_error("invalid age")
```

`throw` is a statement and requires an error value. Throwing a string directly
is forbidden.

Custom errors use empty labeled top-level declarations:

```separan
error:payment_error
end_error:payment_error

throw payment_error("card declined")
```

Names end in `_error` and cannot collide with built-in categories, functions,
or other errors. A custom error is caught by its category, `runtime_error`, or
`any`. Fields and declared inheritance remain future work.

## Planned diagnostics

| Range | Area |
|---|---|
| `E701`–`E709` | import and module errors |
| `E720`–`E729` | I/O and capability errors |
| `E740`–`E749` | JSON errors |
| `E760`–`E769` | try/catch/finally and throw errors |

Final individual codes must be assigned before implementation and remain stable
after the relevant preview is released.
