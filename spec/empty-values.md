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

List slots may independently be EMPTY while retaining the list's homogeneous
element type. Index assignment is zero-based and explicit:

```separan
list<number> values = [10, 20, 30]
values[1] = EMPTY
values[1] = 25
```

A typed list literal may contain EMPTY. An inferred list must contain at least
one concrete element so its element type is knowable. Thus `[1, EMPTY]` is a
`list<number>`, while an untyped `[EMPTY, EMPTY]` is `E134`.

EMPTYS clears all effective values while preserving container structure. For a
list it preserves slot count and replaces each slot with typed EMPTY. For an
object it preserves fields, field types, and nested container shapes.

```separan
values = EMPTYS

if values is EMPTYS :no_values
print length(values)
endif:no_values
```

An empty list/object and a container whose slots/fields are all EMPTY satisfy
`is EMPTYS`. A typed `list<number> values = EMPTYS` initializes an empty typed
list. EMPTYS cannot initialize an object because no field structure exists to
preserve, and it cannot be assigned to a scalar or individual list slot.

JSON is an explicit external-format boundary. `json_decode()` converts JSON
`null` to EMPTY, including object fields and list slots. `json_encode()`
converts EMPTY back to JSON `null`. A root JSON `null` still needs a declared
Separan type before it can be stored:

```separan
string optional_name = json_decode("null")
print optional_name is EMPTY
print json_encode(optional_name)  # null
```

An all-null JSON array is accepted even though its element type is not yet
known. Its first concrete index assignment fixes that type; all retained EMPTY
slots then keep the adopted type. This exception exists only for external JSON.
The source literal `[EMPTY, EMPTY]` still requires `list<type>`.

The remaining migration is intentionally staged: standard API migration and
finally removal of source-level `null`.
