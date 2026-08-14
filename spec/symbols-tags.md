# Symbols, Function Tags, and Strings

Status: **implemented preview**.

Separan assigns one role to each structural symbol:

```text
#comment       human documentation
##label ...    multiline documentation
:label         structural identity
@tag           semantic identity
```

## Comments

`#` begins a comment outside a string and continues to the end of the line.
It can appear alone, after code, or as a decorative run of number signs.

Multiline comments use either matching NFC-normalized labels or an unlabeled
pair:

```separan
##temporary
ignored source text
##temporary

##
also ignored
##
```

They cannot nest. A different delimiter while a multiline comment is open is
`E104`; reaching EOF is `E106`. The former `:` and `::label` comment forms are
breaking syntax and are no longer accepted.

## Function tags

Tags are AST metadata with no runtime effect:

```separan
function:notify
@notification
@aws
@通知
send_message()
end_function:notify
```

They are valid only in the metadata area after a function declaration and
before its first executable statement. Blank lines may surround tag lines.
Names are case-sensitive NFC-normalized identifiers without whitespace.
Duplicate tags are `E218`; a tag outside a function is `E216`; a late tag is
`E217`.

Functions sharing one exact tag form a semantic scope. `separan-structure`
can inspect that scope and verify that changes stay inside it. The initial
query model intentionally supports one exact tag rather than fuzzy inference.

## Structural completion

`:end` is an editor trigger, not language syntax. Completion lists every
currently open block from innermost to outermost, including its opening line,
and replaces the full trigger with the selected closer. If `:end` remains in a
file, the parser reports `E122` and lists the valid closers.

## String escapes

Normal strings support:

| Escape | Value |
|---|---|
| `\\` | backslash |
| `\"` | quote |
| `\n` / `\r` / `\t` | LF / carriage return / tab |
| `\0` | NUL |
| `\uXXXX` | four-digit Unicode scalar |
| `\UXXXXXXXX` | eight-digit Unicode scalar |

Unknown escapes are `E219`. Incomplete hexadecimal escapes, surrogate code
points, and values above `U+10FFFF` are `E220`.

Raw strings use `r"..."` and preserve every backslash. They remain single-line
strings and cannot contain an unescaped closing quote. Triple-quoted multiline
strings are not part of this preview.
