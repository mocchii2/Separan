# SEP-Local Labels

Status: **proposed**.

Separan normally uses descriptive structural labels such as `:active_user`.
When a structure needs an explicit identity but no semantic name is useful,
Separan may use a SEP-local label.

## Syntax

The canonical form is:

```text
:_<positive-decimal-integer>_
```

Examples include `:_1_`, `:_7_`, and `:_42_`. The number must be positive and
canonical: `:_0_`, `:_01_`, `:_1`, and `:_abc_` are invalid.

SEP-local labels are accepted anywhere a structural label is accepted:

```separan
SEP:main

if ready :_1_
    start()
endif:_1_

while running :_2_
    poll()
endwhile:_2_

END_SEP:main
```

Opening and closing labels must match exactly. A SEP-local label is structural
identity, not an anonymous block and not a semantic tag.

## SEP-local Identity

SEP-local numbers are unique for the lifetime of their containing `SEP`. Closing
a block does not make its number available again in that `SEP`.

```separan
SEP:main
if ready :_1_
endif:_1_

# Invalid: :_1_ was already used in this SEP.
while running :_1_
endwhile:_1_
END_SEP:main
```

The same number may be reused in another `SEP`. Descriptive labels retain their
existing behavior and namespace. SEP-local labels are represented internally as
`label_kind = sep_local`, `label_number = N`, and `source_label = "_N_"`.

Structural tooling qualifies the label with its containing SEP, for example:

```text
SEP:process#1/if:_7_#1
```

SEP-local labels participate in structural diff, rename, editor navigation, and
AI edit scopes exactly like descriptive labels. They must not be interpreted as
semantic tags or as globally unique names. Automatic forms such as `:_` and
`:auto` are not defined.

## Diagnostics and Grammar

Malformed SEP-local labels are syntax errors. A repeated number in one
`SEP` is a duplicate structural identity error. A mismatched closer continues
to use the normal block-label mismatch diagnostic.

Conceptually:

```text
sep_local_label = ":_" positive_decimal_integer "_"
positive_decimal_integer = nonzero_digit { decimal_digit }
```
