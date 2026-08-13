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
| `sort_descending(items)` | new descending, stable sorted list |
| `sort_ignore_case(items)` | ascending strings using Unicode case folding |
| `sort_ignore_case_descending(items)` | descending case-insensitive string sort |
| `sort_natural(items)` | strings with ASCII digit runs compared numerically |
| `sort_natural_descending(items)` | descending natural sort |
| `sort_natural_ignore_case(items)` | case-insensitive natural sort |
| `sort_natural_ignore_case_descending(items)` | descending case-insensitive natural sort |
| `sort_by(items, field)` | object list sorted by the named field |
| `sort_by_descending(items, field)` | descending object-field sort |
| `map(items, function)` | applies a function to every element; result must be homogeneous |
| `filter(items, predicate)` | retains elements whose predicate returns boolean true |
| `reduce(items, function, initial)` | left fold with a required, type-stable initial accumulator |
| `flatten(items)` | removes exactly one nested list level |
| `sum(items)` | sum of a number list; zero for an empty list |
| `average(items)` | arithmetic mean of a non-empty number list |
| `count(items, value)` | number of exact matching elements |

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
floating-point, reversed, and out-of-range indexes are errors.

## Sorting rules

Every sort is stable, deterministic, and non-mutating. General ascending and
descending sorts accept homogeneous `number`, `string`, `datetime`,
`local_datetime`, or `duration` lists. Strings use Unicode code-point order.
Case-insensitive variants use Unicode case folding. Natural variants accept
strings only and compare each ASCII digit run numerically, so `file2` sorts
before `file10`. Equal keys preserve input order.

`sort_by` and `sort_by_descending` require an object list and a non-empty field
name. Every object must contain that field, and all field values must have one
identical orderable type. Missing, mixed-type, boolean, null, list, bytes,
secret, and other unordered keys are errors. Separan never guesses a fallback
key or silently moves missing values.

## Higher-order operations and aggregates

A bare user or built-in function name is a value of public type `function` when
passed to `map`, `filter`, or `reduce`. `map` rejects heterogeneous callback
results. `filter` requires an actual boolean result and never applies truthiness.
`reduce` always requires `initial`, returns it unchanged for an empty list, and
requires every accumulator result to keep its initial public type.

`flatten` removes one level only and verifies that the flattened result remains
homogeneous. `sum([])` is `0`; `average([])` is `E602` because an empty mean is
undefined. `count` requires the search value to match the known element type.
`zip` remains deferred until Separan has a tuple type; selector-based `*_by`
variants remain expressible by composing these smaller operations.

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
