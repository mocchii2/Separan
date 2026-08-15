# Separan Language Specification — v0.2.0-alpha.7

This document is the concise normative description of the current language.
The executable behavior is covered by the conformance tests in `tests/`.

## Core rule

Whitespace never determines block structure. A block is identified by its kind
and label. The closing kind and label must match the most recently opened block.

```separan
if condition :label
...
endif:label
```

The same rule applies to `while`/`endwhile`, `for`/`endfor`, and function names
in `function:name`/`end_function:name`. All currently open structure identifiers
share one namespace and must be unique. Closed labels may be reused.

## v0.2 alpha syntax

- UTF-8 source files use the `.sep` extension.
- One line contains one statement; semicolons have no meaning.
- Identifiers match `[A-Za-z_][A-Za-z0-9_]*`. Explicit block labels,
  multiline-comment labels, and function tags may instead be NFC-normalized Unicode identifiers. They are
  case-sensitive; emoji, spaces, punctuation, and non-normalized labels are invalid.
- Types are `number`, `string`, `boolean`, `list`, and `null`.
- Variables keep the type inferred by their first assignment.
- Function parameter types are fixed by the function's first call.
- Lists are homogeneous. Indexes are zero-based, non-negative integers.
- Conditions require booleans; there is no truthy/falsy conversion.
- Implicit conversion between strings, numbers, and booleans is forbidden.
- Comparison operators cannot be chained; use `&&` explicitly.
- `main()` is invoked automatically and must have no parameters.
- Without `main`, top-level assignments and `print` statements execute in order.
- `const name = value` creates a non-reassignable binding in the current scope.

## Operators

Operators never perform implicit conversion. Precedence from low to high is
`??`, `||`, `&&`, equality, ordered/membership comparison, `+ -`,
`* / // %`, unary `! not -`, and `**`. Power is right-associative; `??` is
right-associative and evaluates its right operand only when the left is null.

| Operators | Rule |
|---|---|
| `+ - * / %` | number arithmetic; `+` also concatenates matching strings, bytes, and homogeneous lists |
| `//` | integer-only floor division; negative results round toward negative infinity |
| `**` | real, finite numeric power |
| `== != < <= > >=` | strict comparison without conversion; comparisons cannot chain |
| `&& || ! not` | boolean-only logic with short-circuiting for `&&` and `||` |
| `??` | null-only fallback with short-circuiting; false, zero, and empty values are retained |
| `in`, `not in` | strict containment for string, list, object field names, and bytes |

Compound assignment supports `+=`, `-=`, `*=`, `/=`, `//=`, `%=`, and `**=`.
It is exactly the corresponding operation followed by assignment, so constants
remain immutable and the binding's fixed type still applies. `??=` is
intentionally absent because changing a null-typed binding to another type would
violate fixed first-assignment typing. `++` and `--` are not defined.

For membership, string search requires string operands. List search must match
the homogeneous element type. Object membership checks a string field name.
Bytes membership accepts either bytes subsequences or an integer byte from 0
through 255. Missing membership is a normal `false`; an incompatible search
type is a type error rather than silently returning false.

## Built-in functions

Built-in names are reserved and cannot be redefined by source programs.

| Function | Accepted values | Result |
|---|---|---|
| `length(value)` | string, list, or bytes | Unicode code points, elements, or bytes |
| `is_empty(value)` | string, list, or bytes | whether length is zero |
| `len(value)` | string, list, or bytes | compatibility alias for `length` |
| `type(value)` | any value | public type name as a string |
| `type_of(value)` | any value | readable alias returning the public type name |
| `is_null(value)` | any value | whether the value is exactly null |
| `is_number/string/boolean/list/object(value)` | any value | exact public-type test |
| `is_bytes/datetime/duration/secret(value)` | any value | exact public-type test |
| `abs(value)` | number | absolute numeric value |
| `ceil(value)` / `floor(value)` | number | integer ceiling or floor |
| `round(value)` | number | nearest integer; exact halves round away from zero |
| `min(values...)` / `max(values...)` | one or more numbers | smallest or largest number |
| `sqrt(value)` | non-negative number | finite square root |
| `sin(value)` / `cos(value)` / `tan(value)` | number in radians | finite trigonometric result |
| `log(value)` | positive number | natural logarithm |
| `log10(value)` / `log2(value)` | positive number | base-10 or base-2 logarithm |
| `exp(value)` | number | finite `e` raised to `value` |
| `pow(base, exponent)` | numbers | finite real exponentiation result |
| `range(stop)` | integer-valued number | list from zero up to, excluding, `stop` |
| `range(start, stop)` | integer-valued numbers | list from `start` up to, excluding, `stop` |
| `range(start, stop, step)` | integer-valued numbers; non-zero `step` | stepped number list |
| `number_range(...)` | same strict arguments as `range` | readable compatibility name for a number list |
| `number(value)` | number or strict decimal string | number |
| `string(value)` | number, string, boolean, or null | canonical string representation |
| `boolean(value)` | boolean or exact string `"true"`/`"false"` | boolean |

`range` follows the direction of `step`; a direction that cannot reach `stop`
produces an empty list. Floating-point values and booleans are rejected even
though integers and floating-point values share the public `number` type.

Conversions are explicit and strict. `number` accepts decimal strings matching
`-?[0-9]+(?:\.[0-9]+)?` without surrounding whitespace, a leading plus sign, or
exponent notation. `boolean` never applies truthiness: numbers, null, lists, and
strings other than exact lowercase `"true"` and `"false"` are errors. `string`
does not serialize lists in v0.1. Invalid textual conversions produce `E304`.

A future fallible conversion such as `try_number(value) -> number | null` is
preferred over default-on-failure conversion, because failure remains explicit
in the program's control flow.

The expanded [readable mathematics specification](mathematics.md) defines
descriptive function names, strict statistics, base conversion, and grouped
binary/octal/hexadecimal literals. Short mathematical names remain compatibility aliases.

### String functions

All positions and lengths operate on Unicode code points. No function converts
non-string arguments implicitly.

| Function | Result |
|---|---|
| `trim(value)` | removes Unicode whitespace from both ends |
| `upper(value)` | Unicode uppercase mapping |
| `lower(value)` | Unicode lowercase mapping |
| `contains(value, search)` | whether `search` occurs in `value` |
| `starts_with(value, prefix)` | whether `value` begins with `prefix` |
| `ends_with(value, suffix)` | whether `value` ends with `suffix` |
| `split(value, delimiter)` | homogeneous string list split on a non-empty delimiter |
| `join(values, separator)` | joins a list containing only strings |
| `replace(value, search, replacement)` | replaces every occurrence of non-empty `search` |
| `substring(value, start)` | code points from `start` to the end |
| `substring(value, start, end)` | code points in the half-open range `[start, end)` |
| `reverse(value)` | string reversed by Unicode code point; also accepts a list |
| `char_at(value, index)` | one-code-point string at a valid zero-based index |
| `find_all(value, search)` | non-overlapping literal-match indexes; empty list when absent |
| `compare(left, right)` | exactly `-1`, `0`, or `1` by Unicode code-point order |
| `compare_ignore_case(left, right)` | case-folded comparison returning exactly `-1`, `0`, or `1` |
| `substring_before(value, search)` | text before the first match, or null |
| `substring_after(value, search)` | text after the first match, or null |
| `count_occurrences(value, search)` | number of non-overlapping matches |
| `format(template, values...)` | positional `{}` formatting; `{{` and `}}` escape braces |
| `index_of(value, search)` | first code-point index, or null |
| `last_index_of(value, search)` | last code-point index, or null |
| `repeat(value, count)` | string repeated a non-negative integer count |
| `pad_left(value, length[, fill])` | left-padded string of at least target length |
| `pad_right(value, length[, fill])` | right-padded string of at least target length |

Substring indexes must satisfy `0 <= start <= end <= len(value)`. Negative,
floating-point, reversed, and out-of-range indexes are errors. Empty delimiters
and empty replacement search strings produce `E305`; invalid substring ranges
produce `E306`.

String search indexes are Unicode code-point indexes. Missing singular searches
return null rather than `-1`; `find_all` returns an empty list. Empty search
strings are rejected with `E305`. Padding
uses a one-code-point fill string, defaulting to a space. Repeat and padding
results are limited to 1,048,576 code points and report `E607` rather than
attempting unbounded allocation.

## Blocks

```separan
if condition :decision
elseif other_condition :decision
else:decision
endif:decision

while condition :loop
endwhile:loop

for item in items :items_loop
endfor:items_loop

function:add(a, b)
@math
return a + b
end_function:add
```

## Comments

`#` begins a line comment at the start of a line or after code. A `#` inside a
string remains string data. Exact matching `##label` lines delimit a
non-nestable multiline comment; an unlabeled `##`/`##` form is also valid.
Decorative runs such as `################################` are ordinary line comments.

`:` is reserved for structural identity. `@tag` lines in a function's initial
metadata area attach semantic identity without runtime behavior. Tags may be
Unicode, must be NFC-normalized, and cannot be duplicated or placed after the
first executable statement. See [symbols, tags, and strings](symbols-tags.md).

Normal strings support `\\`, `\"`, `\n`, `\r`, `\t`, `\0`, `\uXXXX`, and
`\UXXXXXXXX`. Unknown, incomplete, surrogate, and out-of-range escapes are
errors. `r"..."` is a raw string and preserves backslashes literally.

## Diagnostics

Diagnostics carry a stable code, category, file, line, Unicode code-point column,
source line, pointer, description, expected and actual syntax when applicable,
and the related opening block. A generic `SyntaxError` is insufficient.

LSP behavior and AI edit enforcement remain outside the stable language
semantics. The [VS Code/LSP specification](vscode-extension.md) records the
implemented editor preview and its safety boundaries. The following extensions, including objects, are
implemented experimentally but are not yet stable.

## Experimentally implemented extensions

- [Temporal types](temporal-types.md): distinct `datetime`, `local_datetime`,
  `timezone`, and `duration` values. The API may change before a stable release.
- [Randomness](randomness.md): reproducible PCG32 functions, operating-system-backed
  secure functions, and an immutable `bytes` type.
- [Lists](lists.md): homogeneous, zero-based lists with non-mutating operations.
- [Bytes](bytes.md): immutable binary values with explicit text, hex, and Base64 conversion.
- [Authentication](authentication.md): redacted secrets and purpose-specific HTTP, HMAC, JWT, OAuth, and password APIs.
- [Cryptography](cryptography.md): readable SHA-2/SHA-3, HMAC and encoding boundaries plus Argon2id and versioned AES-256-GCM safe paths.
- [Mail](mail.md): provider-independent UTF-8 message composition with capability-gated SMTP and optional Amazon SES transports.
- [YAML and XML](structured-data.md): strict ordered YAML data conversion and a safe, explicit XML document model.
- [Cookies](cookies.md): one-shot cookies and redacted, stateful Cookie Jars.
- [Modules, data, I/O, and errors](modules-data-errors.md): labeled objects/lists,
  imports, capability-based I/O, JSON, constants, and labeled error handling.
- [HTTP client](http.md): text-first retrieval, detailed immutable responses,
  honest profiles, and network capabilities. The boundary from browser
  automation is fixed by the specification.
- [External process execution](process-execution.md): direct argv execution,
  checked execution, explicit shell risk, bounded output, and host capabilities.
- [Regex, glob, environment, and command line](system-utilities.md): explicit
  search absence, deterministic file discovery, scoped environment mutation,
  and script-name-free arguments.
- [Structural AI workflows](structural-ai.md): parser-backed block identities,
  AST-aware diffs, structural and semantic-tag scope verification, JSON review metadata, and CI exit codes.
- [Browser automation boundary](browser-automation.md): a separate real-engine
  adapter contract with no fake HTTP-client fallback.
- [Structure Explorer](structure-explorer.md): human-readable block hierarchy,
  direct reads/writes/calls, navigation, and Git structural state.
- [Embedded board mapping](embedded-board-mapping.md): logical pins, reviewed
  Tier 1 board profiles, capability-aware bus validation, and a host-adapter boundary.
