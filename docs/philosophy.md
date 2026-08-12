# Design philosophy

## Structure should be named, not guessed

Most languages ask readers to infer structure from indentation, count braces,
or follow anonymous `end` markers. Separan gives a block a human-readable name
and makes that name part of syntax.

Labels are not comments. They survive in the AST, participate in validation,
and are intended to become stable handles for navigation, review, refactoring,
and AI-assisted editing.

Separan assumes that programmers and generators will make mistakes. Its job is
to reject ambiguous structure, unsafe implicit conversions, and stale labels as
early as possible—and explain the correction in terms a human can act on.

The goal is not fewer characters. The goal is less uncertainty.

This also governs conversion: if a program changes a value's type, that decision
must be visible in source as `number(...)`, `string(...)`, or `boolean(...)`.
Separan rejects implicit coercion and truthiness because convenient ambiguity is
still ambiguity.

Time follows the same rule. An instant, an unzoned wall-clock value, a timezone,
and an elapsed duration must not collapse into one string or unitless number.
The accepted [v0.2 temporal design](../spec/temporal-types.md) names each concept
with a distinct type.

Randomness must name its purpose as well. Reproducible simulation randomness and
cryptographic randomness use different function families, state, and guarantees.
Source code should make the distinction visible during review.
