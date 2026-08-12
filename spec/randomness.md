# Randomness — Experimental API

Status: **implemented preview; API stability is planned for v0.2**.

Separan separates reproducible pseudo-randomness from cryptographically secure
randomness. Function names identify both the source and result semantics. There
is no overloaded `random()` function and no secure seeding API.

## Reproducible pseudo-random functions

| Function | Result |
|---|---|
| `random_seed(seed)` | resets the current interpreter PRNG; returns null |
| `random_number()` | number in `0 <= x < 1` |
| `random_int(min, max)` | integer-valued number with both endpoints included |
| `random_float(min, max)` | number satisfying `min <= x < max` |
| `random_bool()` | boolean |
| `random_pick(items)` | one element from a non-empty list |
| `random_shuffle(items)` | a new shuffled list |
| `random_sample(items, count)` | a new list sampled without replacement |

`random_shuffle` and `random_sample` never modify their input. A sample count
must be an integer from zero through the list length. Picking from an empty list
is an error.

Each interpreter owns an independent PRNG. Without `random_seed`, it is seeded
from operating-system entropy. `random_seed` accepts only an integer-valued
number and maps it to its low 64 bits. The generator is PCG-XSH-RR 32 with:

```text
multiplier = 6364136223846793005
stream increment = 109
64-bit wrapping state
```

`random_number` combines 27 and 26 output bits into a 53-bit fraction. Integer
selection uses rejection sampling rather than modulo reduction. Shuffle uses
descending Fisher–Yates. These details are normative so the same seed produces
the same sequence across conforming implementations.

The pseudo-random functions are suitable for tests, games, simulations, and
ordinary draws. They must not be used for passwords, tokens, keys, or nonces.

## Secure random functions

| Function | Result |
|---|---|
| `secure_random_bytes(length)` | `bytes` containing exactly `length` random bytes |
| `secure_random_int(min, max)` | securely selected integer with both endpoints included |
| `secure_random_string(length)` | URL-safe string of exactly `length` characters |

Secure functions use the operating system's cryptographic random source. They
have no deterministic seed operation and are never affected by `random_seed`.
`secure_random_string` uses exactly this 64-character alphabet:

```text
ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-
```

Secure byte and string lengths must be integer-valued numbers between zero and
1,048,576. This resource limit is part of the preview API.

## `bytes` type

`secure_random_bytes` introduces a distinct immutable `bytes` type. It is not a
list of numbers and is not implicitly converted to string. `len(bytes)` returns
the byte count. Explicit `string(bytes)` and `print bytes` use canonical
lowercase hexadecimal with a `0x` prefix. No bytes literal is defined yet.

## Diagnostics

| Code | Category |
|---|---|
| `E501` | Invalid random range |
| `E502` | Empty random population |
| `E503` | Invalid sample size |
| `E504` | Invalid secure random length |

Argument type and count failures continue to use the common `E201` and `E207`
diagnostics. All random and secure-random function names are reserved.

## Deferred functions

Probability distributions such as `random_normal(mean, stddev)` are deferred.
Any future distribution function must name its distribution and document its
algorithm if seeded reproducibility is promised.

