# Lists — Non-mutating Operations

Status: **implemented in the reference interpreter**.

Separan v0.1 uses one variable-length collection type: `list`. Array and list
are not separate concepts. Lists use zero-based indexing and contain values of
one public type only.

```separan
numbers = [10, 20, 30]
names = ["alice", "bob", "carol"]
first_number = numbers[0]
```

`[1, "a", true]` is a type error. An empty list has an unknown element type;
its type becomes known when a non-empty value is assigned through an operation
such as `list_append`.

## Non-mutating API

All list operations return values without modifying their input list. v0.1 has
no mutating list function and no indexed assignment.

| Function | Result |
|---|---|
| `list_append(items, value)` | new list with `value` at the end |
| `list_remove(items, value)` | new list with the first matching value removed |
| `length(items)` | list element count; preferred common name |
| `size(items)` | list-specific compatibility alias for `length` |
| `is_empty(items)` | whether the list contains no elements |
| `first(items)` | first element |
| `last(items)` | last element |
| `contains(items, value)` | whether a matching value exists |
| `index_of(items, value)` | first matching zero-based index, or null |
| `last_index_of(items, value)` | last matching zero-based index, or null |
| `slice(items, start, end)` | new list for half-open range `[start, end)` |
| `reverse(items)` | new list in reverse order |
| `sort(items)` | new ascending, stable sorted list |

`list_append` requires the new value to match the known element type.
`list_remove` removes only the first match and reports an error when no match
exists; it never silently returns an unchanged list. Search arguments must match
the element type, except that null may be searched under the general null
comparison rule.

`first` and `last` reject empty lists. `index_of` and `last_index_of` return null
when absence is a normal query result, allowing explicit control flow:

```separan
index = index_of(items, target)
if index != null :target_found
print index
endif:target_found
```

Slice indexes must satisfy `0 <= start <= end <= length(items)`. Negative,
floating-point, reversed, and out-of-range indexes are errors. `sort` supports
only homogeneous number or string lists in v0.1. Number sorting is numeric;
string sorting compares Unicode code points. Sorting is stable.

`contains` is deliberately shared with strings because its boolean membership
meaning is identical. It does not convert either operand.

## Loop integration

```separan
for item in items :each_item
print item
endfor:each_item
```

The loop variable belongs to the current function or global scope. Iteration
does not create a new scope and does not mutate the list.

## Diagnostics

| Code | Category |
|---|---|
| `E302` | Index out of range for `items[index]` |
| `E602` | Empty list access |
| `E603` | Invalid list range |
| `E604` | List value not found |

Element-type violations use the common `E201` type diagnostic. Mutating APIs,
method-call syntax, and a distinct fixed-length array type are deferred.
