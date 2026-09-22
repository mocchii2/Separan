# Explicit Type Declarations — v0.2 Design

Separan normally infers a variable's fixed type from its first assignment. An
explicit declaration states that same fixed type in source and checks the
initializer immediately.

```separan
number count = 0
string name = "Separan"
boolean enabled = true
list<number> values = []
list<list<number>> matrix = [[1, 2], [3, 4, 5]]
const string version = "0.2"
```

Every declaration requires `= value`. A bare declaration such as
`string name` is invalid because it cannot distinguish an intentional missing
value from a forgotten initializer. An explicitly missing initial value is
written as `string name = EMPTY`.

The initializer must have exactly the declared type. Separan performs no
conversion. Typed lists require an element type even when initialized with an
empty list; later assignments retain that element type. List types are
recursive, and nested rows may be jagged. `EMPTYS` retains every row length and
the complete recursive element type.

```separan
list<number> values = []
values = [1, 2]       # valid
values = ["one"]      # E201
```

An explicit declaration creates a new binding. Redeclaring a name in the same
scope is an error. Ordinary later assignment updates the binding under its
fixed declared type. `const type name = value` creates a typed constant.

Function parameter annotations put the name first so the parameter remains the
primary readable unit:

```separan
SEP:show_age(age: number, labels: list<string>)
...
end_SEP:show_age
```

A typed parameter accepts `EMPTY`; an untyped parameter can accept only an
EMPTY value that already retains a type from its source binding. A raw EMPTY
argument cannot establish an inferred parameter type.

Object blocks use the same declaration form as variables:

```separan
object:user
string name = EMPTY
number age = 30
end_object:user
```
