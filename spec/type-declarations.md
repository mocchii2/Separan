# Explicit Type Declarations — v0.2 Design

Separan normally infers a variable's fixed type from its first assignment. An
explicit declaration states that same fixed type in source and checks the
initializer immediately.

```separan
number count = 0
string name = "Separan"
boolean enabled = true
list<number> values = []
const string version = "0.2"
```

Every declaration requires `= value`. A bare declaration such as
`string name` is invalid because it cannot distinguish an intentional missing
value from a forgotten initializer. Once `EMPTY` is implemented, an explicitly
missing initial value will be written as `string name = EMPTY`.

The initializer must have exactly the declared type. Separan performs no
conversion. Typed lists require an element type even when initialized with an
empty list; later assignments retain that element type.

```separan
list<number> values = []
values = [1, 2]       # valid
values = ["one"]      # E201
```

An explicit declaration creates a new binding. Redeclaring a name in the same
scope is an error. Ordinary later assignment updates the binding under its
fixed declared type. `const type name = value` creates a typed constant.

