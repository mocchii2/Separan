# Temporal Types — v0.2 Design

Status: **experimental v0.2 preview implemented ahead of schedule in the Python
reference interpreter; the API is not stable yet**.

> Time must carry its meaning.

Separan does not use strings or unitless numbers as its standard representation
of time. An instant, a wall-clock reading, a time zone, and an elapsed duration
are different concepts and therefore different types.

## Types and invariants

### `datetime`

An unambiguous instant plus the zone or fixed offset used to present it. Two
datetimes may display different local values while identifying the same instant.
The minimum v0.2 precision is one millisecond. Supported calendar years are
`0001` through `9999`.

### `local_datetime`

A calendar date and wall-clock time without a time zone. It is not an instant
and cannot be compared with, subtracted from, or silently converted to a
`datetime`.

### `timezone`

An explicit IANA time-zone identifier such as `Asia/Tokyo`, `America/New_York`,
or `UTC`. Fixed offsets such as `+09:00` are also valid timezone values. IANA
zone behavior depends on the versioned time-zone database shipped by the
implementation; the CLI must expose that version.

### `duration`

A signed, fixed elapsed length with millisecond precision. A day in a duration
is exactly 24 hours. Months and years are excluded because they are calendar
periods rather than fixed lengths.

## Construction

```separan
instant = datetime("2026-08-13T01:30:00+09:00")
constructed = datetime(2026, 8, 13, 1, 30, 0, timezone = "Asia/Tokyo")
utc = datetime("2026-08-12T16:30:00Z")
wall = local_datetime("2026-08-13T01:30:00")
tokyo = timezone("Asia/Tokyo")
wait = duration("1h30m")
```

`datetime(string)` accepts only this RFC 3339 profile:

```text
YYYY-MM-DDTHH:MM:SS[.fraction](Z|+HH:MM|-HH:MM)
```

- A time-zone offset is mandatory.
- Uppercase `T` and `Z` are mandatory where used.
- Surrounding whitespace is forbidden.
- Fractional seconds may contain one to three digits and are normalized to
  milliseconds.
- Leap seconds (`:60`) are rejected in v0.2.
- Invalid calendar dates and offsets are rejected instead of normalized.
- Numeric offsets are limited to `-14:00` through `+14:00`; at either 14-hour
  boundary the minutes must be `00`. The unknown-offset spelling `-00:00` is
  rejected.

The six-field calendar constructor requires integer year, month, day, hour,
minute, and second fields plus a named `timezone` argument. It applies the same
nonexistent/ambiguous local-time checks as `datetime_from_local`.

`local_datetime(string)` accepts the same date and time fields but forbids a
zone suffix. It uses `T`, not a space:

```text
YYYY-MM-DDTHH:MM:SS[.fraction]
```

`timezone(string)` accepts an available canonical IANA identifier, `UTC`, or a
fixed `+HH:MM`/`-HH:MM` offset. Unknown identifiers are errors. Zone names are
case-sensitive and aliases should be normalized to the implementation's
canonical identifier when possible.

## Local-time resolution

Conversion from a wall-clock value to an instant is always explicit:

```separan
instant = datetime_from_local(wall, tokyo)
```

The host machine's local zone is never consulted. If the wall-clock value occurs
zero times because of a daylight-saving transition, conversion fails with a
nonexistent-time error. If it occurs twice, conversion fails with an
ambiguous-time error. v0.2 performs no silent forward shift and chooses neither
the earlier nor later occurrence. The caller can use an offset-bearing
`datetime(...)` to state the intended instant explicitly.

Changing presentation zone does not change the instant:

```separan
in_tokyo = datetime_in_timezone(utc, tokyo)
```

## Current time

Current time accepts a timezone value or name. With no argument it uses UTC;
it never consults the host's local timezone:

```separan
tokyo = timezone("Asia/Tokyo")
now = datetime_now(tokyo)
utc_now = datetime_now()
also_tokyo = datetime_now("Asia/Tokyo")
```

Tests and embedded callers must be able to inject a clock; the conformance suite
must not depend on wall-clock time.

## Duration text

`duration(string)` uses ordered, non-repeating integer components:

```text
[-][<days>d][<hours>h][<minutes>m][<seconds>s][<milliseconds>ms]
```

At least one component is required. Examples:

```separan
duration("0s")
duration("250ms")
duration("1h30m")
duration("2d4h5m6s")
duration("-30m")
```

Whitespace, decimals, repeated units, units out of order, and unsupported units
are errors. Consequently, `1.5h`, `30m1h`, `1h20h`, `1 month`, `1mo`, and `1y`
are invalid. Components may exceed their conventional clock ranges, so `90m`
is valid and canonicalizes to `1h30m` when converted to string.
The normalized total must fit a signed 64-bit millisecond count
(`-9223372036854775808` through `9223372036854775807`).

## Operators

Only the following temporal arithmetic is defined:

| Expression | Result |
|---|---|
| `datetime + duration` | `datetime` |
| `duration + datetime` | `datetime` |
| `datetime - duration` | `datetime` |
| `datetime - datetime` | `duration` |
| `duration + duration` | `duration` |
| `duration - duration` | `duration` |
| `duration * number` | `duration` |
| `number * duration` | `duration` |
| `duration / number` | `duration` |
| `duration / duration` | `number` |

`datetime + datetime`, arithmetic involving `local_datetime` or `timezone`, and
all other combinations are type errors. Adding elapsed time preserves the
left-hand datetime's presentation zone. For an IANA zone, adding `24h` advances
the instant by exactly 24 hours and may therefore change the displayed local
hour across a daylight-saving transition.

Duration multiplication or division must produce an exact whole number of
milliseconds. Division by zero and precision-losing results are errors rather
than rounded values.

## Comparison

- `datetime` ordering and equality compare instants, not displayed local fields.
- `local_datetime` compares its calendar and clock fields only with another
  `local_datetime`.
- `duration` compares elapsed lengths.
- `timezone` equality compares normalized zone identity.
- Cross-type temporal comparison is a type error, except comparison with `null`
  under the language's existing null rule.

## Explicit Unix conversion

Unix time is an interchange format, not Separan's temporal type:

```separan
seconds = unix_seconds_from_datetime(instant)
millis = unix_milliseconds_from_datetime(instant)

a = datetime_from_unix_seconds(seconds, tokyo)
b = datetime_from_unix_milliseconds(millis, tokyo)
```

Function names always include the unit. `timestamp()`, `datetime_from_unix()`,
and other unit-ambiguous forms are avoided in the strict API. For scripting
convenience, `unix_time([datetime])` and `datetime_from_unix(seconds[, timezone])`
are defined explicitly as seconds-only aliases; omitted timezones mean UTC. Milliseconds use an integer-valued
number. Seconds may contain a fractional part of at most millisecond precision.

## Canonical string conversion

Explicit `string(value)` is extended in v0.2:

- `datetime` includes its offset; an IANA-backed value may additionally expose
  its zone through a dedicated accessor, never an ambiguous suffix.
- `local_datetime` has no offset.
- `timezone` uses its normalized identifier.
- `duration` uses a sign and normalized ordered components.

Parsing a canonical representation must reproduce an equal value of the same
type. Human-oriented locale formatting is a separate future API.

## Introspection functions

The minimal v0.2 API should include:

```text
datetime_offset(value)        -> duration
datetime_timezone(value)      -> timezone
datetime_year(value)          -> number
datetime_month(value)         -> number
datetime_day(value)           -> number
datetime_hour(value)          -> number
datetime_minute(value)        -> number
datetime_second(value)        -> number
datetime_millisecond(value)   -> number
datetime_weekday(value)       -> number (ISO Monday=1 through Sunday=7)
duration_milliseconds(value)  -> number
```

`datetime_parse(text)` is the readable alias for strict offset-bearing
`datetime(text)`. `datetime_valid(year, month, day)` validates integer calendar
fields without normalization. `datetime_format` supports only the fixed tokens
`yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, `SSS`, and `XXX`; unknown alphabetic
tokens are errors rather than host-dependent formatting directives.

Field extraction is explicit. No property syntax is required for the initial
implementation.

## Diagnostics

The temporal subsystem reserves these diagnostic concepts; final numeric codes
must remain stable once v0.2 is released:

| Code | Category |
|---|---|
| `E401` | Invalid datetime text |
| `E402` | Missing or forbidden timezone |
| `E403` | Unknown or invalid timezone |
| `E404` | Invalid local datetime text |
| `E405` | Ambiguous local datetime |
| `E406` | Nonexistent local datetime |
| `E407` | Invalid duration text |
| `E408` | Invalid temporal operation |
| `E409` | Temporal precision loss |

Every diagnostic must include the input, accepted form or operand combination,
and a correction. DST diagnostics must include the local value and zone. They
must never silently select an offset.

## Implementation requirements

- The AST continues to store ordinary call and operator nodes; runtime values
  carry distinct temporal type tags suitable for future semantic tokens.
- The reference implementation may use a standard timezone library but must not
  expose its host-language objects as Separan values.
- Datetime storage must be independent of presentation timezone and deterministic
  at millisecond precision.
- Timezone database version and update policy must be documented.
- Overflow limits must be explicit and produce Separan errors, not host-language
  exceptions.
- Conformance tests must cover DST gaps and overlaps using fixed tzdb fixtures.

## Deferred concepts

Calendar-relative months and years require a future `calendar_period` design.
Locale formatting, business calendars, timers, sleeping, scheduling, and a
fallible `try_datetime` API are outside this initial temporal specification.
