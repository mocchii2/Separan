# EMPTY, EMPTYS, and VOID — staged v0.2 specification

Separan separates three states that legacy `null` previously blurred:

- `EMPTY`: one typed value slot currently has no value;
- `EMPTYS`: a typed container retains its structure but has no effective values;
- `VOID`: a function completed without producing a value.

`EmptyValue` and `VoidResult` are distinct runtime representations. Function
fallthrough and bare `return` produce `VOID`. `VOID` cannot be assigned,
printed, passed as an argument, stored in a list, or used by an operator.

EMPTY is tested only with dedicated state syntax:

```separan
if value is EMPTY :value_missing
print "No value"
endif:value_missing

if value is not EMPTY :value_present
print value
endif:value_present
```

`is` is not a general equality operator. `value is 1`, `value is null`, and
chained state/comparison expressions are syntax errors. Ordinary value equality
continues to use `==` and `!=`.

Typed variables may start in the EMPTY state and later receive only their
declared type. Assigning EMPTY to an existing mutable binding clears its value
without clearing its type. An untyped first assignment cannot infer a type from
EMPTY, and constants cannot be EMPTY.

```separan
number age = EMPTY
age = 30
age = EMPTY
age = 31       # valid; age is still number
```

Typed parameters and typed object fields follow the same rule. Reading the
state with `is EMPTY` or the retained type with `type_of()` is valid. Printing,
arithmetic, indexing, conditions, and APIs requiring concrete values raise
`E131` until a value is assigned.

The remaining migration is intentionally staged: list elements and EMPTYS,
JSON null conversion, standard API migration, and finally removal of
source-level `null`.
