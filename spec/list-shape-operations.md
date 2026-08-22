# List Shape Operations — v0.2 Preview

Status: **implemented in the reference interpreter**.

Separan treats a list's values and its slot shape as separate concepts:

- `value = EMPTY` clears one value while retaining its slot and element type.
- `container = EMPTYS` clears every effective value while retaining all nested
  slot counts, jagged shape, and element types.
- `list_insert` adds slots initialized to typed `EMPTY`.
- the three-argument `list_remove` removes slots.

```separan
list<number> values = [10, 20, 30]
values[1] = EMPTY                 # [10, EMPTY, 30], length 3
values = EMPTYS                   # [EMPTY, EMPTY, EMPTY], length 3
list_remove(values, front, 3)     # [], length 0
```

An explicit element type permits an all-EMPTY shape:

```separan
list<number> values = [EMPTY, EMPTY, EMPTY]
values[0] = 100
values[2] = 300
```

The inferred declaration `values = [EMPTY, EMPTY, EMPTY]` is rejected because
there is no element type to retain.

## Position selectors

Shape APIs accept `front`, a zero-based non-negative integer, or `back`.
`front` and `back` are contextual selectors, not ordinary values; `x = front`
is `E136`. For insertion, `back` means `length(values)`. For removal it selects
the final `count` slots. `count` must be a positive integer, and every range is
validated before mutation.

## One-dimensional operations

```separan
list_insert(values, position, count) -> VOID
list_remove(values, position, count) -> VOID
```

Both APIs require a direct mutable list binding or indexed row. They cannot be
used on constants, temporary expressions, or as assigned values. Examples:

```separan
list<number> values = [10, 20, 30]
list_insert(values, 1, 2)         # [10, EMPTY, EMPTY, 20, 30]
list_remove(values, back, 2)      # [10, EMPTY, EMPTY]
```

The existing two-argument `list_remove(values, value) -> list` remains a
non-mutating compatibility operation. Supplying three arguments unambiguously
selects the mutating shape operation.

## Nested and jagged lists

Nested declarations are recursive and rows may have different lengths:

```separan
list<list<number>> values = [[1, 2], [3, 4, 5], [6]]
values[1][1] = EMPTY
values[1] = EMPTYS
values = EMPTYS
```

The final `EMPTYS` retains three rows with lengths 2, 3, and 1. Applying
`list_insert` or `list_remove` to the outer list changes rows; applying it to
`values[row]` changes only that row. A newly inserted outer slot is
`EMPTY<list<number>>`; no inner shape is guessed.

## Directional removal

```separan
list_remove_horizontal(values, row, column, count) -> VOID
list_remove_vertical(values, row, column, count) -> VOID
```

Horizontal removal deletes slots from one row and shifts later values left.
It is equivalent in effect to applying the one-dimensional removal to that
row, while making the intended direction explicit.

Vertical removal shifts only one column upward from `row`, then fills the
vacated bottom cells with typed `EMPTY`. It preserves the outer and inner slot
counts; it is a column value-slot shift, not a row deletion. Every affected
row of a jagged list must contain the selected column. Separan validates the
complete operation first, so a shape error never leaves a partially modified
list.

Vertical insertion is deferred until its jagged-list growth semantics are
fixed. Separan does not infer or pad a rectangle.

## Diagnostics

| Code | Meaning |
|---|---|
| `E134` | inserted EMPTY slots have no known element type |
| `E136` | `front` or `back` used outside a position context |
| `E211` | attempted mutation of a `const` binding |
| `E603` | invalid position, count, row, column, or range |
| `E605` | target is not a direct mutable list, or jagged validation failed |

