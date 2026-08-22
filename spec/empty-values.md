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

The remaining migration is intentionally staged: typed EMPTY storage, object
fields, list elements and EMPTYS, JSON null conversion, standard API migration,
and finally removal of source-level `null`.

