# Readable Mathematics — v0.2.0-alpha.2

Separan mathematics favors names that reveal intent during human review. No
function performs implicit conversion, every result remains a `number`, and
undefined or non-finite arithmetic raises `E308` instead of silently producing
NaN, infinity, or a complex number.

## Naming and compatibility

Readable names are the preferred spelling. Existing short names such as `abs`,
`min`, `max`, `sqrt`, `pow`, `exp`, `log`, `log2`, and `log10` remain reserved
compatibility aliases during the alpha series.

Conversion names follow `source_to_target`: for example,
`number_to_hexadecimal()` and `hexadecimal_to_number()`.

## Number literals

```separan
decimal = 1_000_000
fraction = 12_345.67_89
binary = 0b1111_0000
octal = 0o755
hexadecimal = 0xff_ff
```

Prefixes are case-insensitive. Separators may appear only between digits and
must separate valid digits for the selected base. A leading sign is the unary
`-` operator, not part of the literal. Exponent notation is not defined.

Invalid digits, missing digits, leading/trailing separators, repeated
separators, and fractional based literals are lexical `E101` errors.

## Basic numeric operations

| Function | Rule |
|---|---|
| `absolute(value)` | Absolute value |
| `minimum(values)` / `maximum(values)` | A non-empty `list<number>`; multiple positional numbers are also accepted |
| `round(value[, digits])` | Decimal rounding, exact halves away from zero; digits is an integer-valued number in `-100..100` |
| `truncate(value)` | Discard the fractional part toward zero |
| `clamp(value, minimum, maximum)` | Requires `minimum <= maximum` |
| `sign(value)` | `-1`, `0`, or `1` |

## Powers, logarithms, and angles

| Group | Functions |
|---|---|
| Roots and powers | `square_root`, `cube_root`, `power`, `hypotenuse` |
| Exponentials | `exponential`, `exponential_base2` |
| Logarithms | `natural_log`, `log_base2`, `log_base10`, `log_one_plus` |
| Circular | `sin`, `cos`, `tan`, `arc_sin`, `arc_cos`, `arc_tan`, `arc_tan2` |
| Hyperbolic | `sinh`, `cosh`, `tanh`, `arc_sinh`, `arc_cosh`, `arc_tanh` |
| Angle conversion | `to_radians`, `to_degrees` |

Trigonometric inputs and inverse results use radians. `arc_tan2(y, x)` fixes
the argument order explicitly.

## Integer-valued operations and predicates

`greatest_common_divisor(a, b)`, `least_common_multiple(a, b)`, and
`factorial(value)` require mathematically integral numbers; `5.0` is accepted.
Factorial accepts `0..1000` to keep resource use bounded.

`is_finite`, `is_infinite`, `is_nan`, `is_close`, and `is_integer_value`
require numbers and return strict booleans. `is_close(a, b)` uses relative
tolerance `1e-9` and absolute tolerance `0.0`.

## Statistics

All statistical functions require a homogeneous `list<number>` and never
mutate it.

| Function | Rule |
|---|---|
| `median(values)` | Middle value, or mean of the two middle values |
| `variance(values)` | Population variance; denominator `n` |
| `sample_variance(values)` | Sample variance; denominator `n - 1`, at least two values |
| `standard_deviation(values)` | Population standard deviation |
| `sample_standard_deviation(values)` | Sample standard deviation, at least two values |
| `percentile(values, percent)` | `percent` in `0..100`; linear interpolation at rank `(n - 1) * percent / 100` |
| `moving_average(values, window)` | Contiguous averages; `1 <= window <= length(values)` |

Empty or insufficient collections raise `E602`. Invalid percentile, window,
precision, base, factorial, or ordered range raises `E308`.

## Base conversion

`number_to_binary`, `number_to_octal`, and `number_to_hexadecimal` produce
lowercase text without a prefix. Their inverse functions accept an optional
leading `-` and separators only between digits, but no `0b`, `0o`, or `0x`
prefix because the source base is already explicit in the function name.

`number_to_base(value, base)` and `base_to_number(text, base)` support bases
2 through 36 using lowercase `0-9a-z` output and case-insensitive input.
Numeric inputs must be integer-valued. Invalid text raises `E304`.

Math constants and a `math.*` namespace are intentionally deferred until the
module/namespace policy is stable.
