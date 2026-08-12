"""Temporal value model for the Separan v0.2 preview."""

from dataclasses import dataclass
from datetime import datetime as PyDateTime, timedelta, timezone as py_timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import error


UTC = py_timezone.utc
EPOCH = PyDateTime(1970, 1, 1, tzinfo=UTC)
MIN_MILLIS = -(2**63)
MAX_MILLIS = 2**63 - 1
DATETIME_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$"
)
LOCAL_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d{1,3}))?$"
)
OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):(\d{2})$")
DURATION_COMPONENT = re.compile(r"(\d+)(ms|d|h|m|s)")
DURATION_FACTORS = {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1_000, "ms": 1}
DURATION_ORDER = {"d": 0, "h": 1, "m": 2, "s": 3, "ms": 4}


@dataclass(frozen=True, eq=False)
class TimezoneValue:
    name: str
    tzinfo: object

    def __eq__(self, other):
        return isinstance(other, TimezoneValue) and self.name == other.name


@dataclass(frozen=True, eq=False)
class DatetimeValue:
    instant_utc: PyDateTime
    zone: TimezoneValue

    def __eq__(self, other):
        return isinstance(other, DatetimeValue) and self.instant_utc == other.instant_utc

    def __lt__(self, other): return self.instant_utc < other.instant_utc
    def __le__(self, other): return self.instant_utc <= other.instant_utc
    def __gt__(self, other): return self.instant_utc > other.instant_utc
    def __ge__(self, other): return self.instant_utc >= other.instant_utc


@dataclass(frozen=True, eq=False)
class LocalDatetimeValue:
    value: PyDateTime

    def __eq__(self, other): return isinstance(other, LocalDatetimeValue) and self.value == other.value
    def __lt__(self, other): return self.value < other.value
    def __le__(self, other): return self.value <= other.value
    def __gt__(self, other): return self.value > other.value
    def __ge__(self, other): return self.value >= other.value


@dataclass(frozen=True, order=True)
class DurationValue:
    milliseconds: int


def _fraction_micros(text):
    return int((text or "0").ljust(3, "0")) * 1000


def _calendar(parts, position, code, category, source):
    try:
        values = [int(part) for part in parts[:6]]
        if values[0] == 0 or values[5] == 60:
            raise ValueError
        return PyDateTime(*values, microsecond=_fraction_micros(parts[6]))
    except ValueError:
        raise error(code, category, f"{source} contains an invalid calendar date or clock time.", position, actual=repr(source))


def parse_timezone(text, position):
    if type(text) is not str:
        raise error("E201", "Type error", "timezone() requires a string.", position, expected="string", actual=public_type(text))
    if text == "UTC":
        return TimezoneValue("UTC", UTC)
    offset = OFFSET_PATTERN.fullmatch(text)
    if offset:
        sign, hours_text, minutes_text = offset.groups()
        hours, minutes = int(hours_text), int(minutes_text)
        if minutes > 59 or hours > 14 or (hours == 14 and minutes != 0) or text == "-00:00":
            raise error("E403", "Invalid timezone", "Fixed offset must be between -14:00 and +14:00; -00:00 is forbidden.", position, actual=repr(text))
        total = (hours * 60 + minutes) * (1 if sign == "+" else -1)
        if total == 0:
            return TimezoneValue("UTC", UTC)
        return TimezoneValue(text, py_timezone(timedelta(minutes=total), name=text))
    try:
        zone = ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError):
        raise error("E403", "Unknown timezone", f"Timezone '{text}' is not available in the implementation timezone database.", position, actual=repr(text))
    return TimezoneValue(getattr(zone, "key", text), zone)


def parse_datetime(text, position):
    if type(text) is not str:
        raise error("E201", "Type error", "datetime() requires a string.", position, expected="string", actual=public_type(text))
    match = DATETIME_PATTERN.fullmatch(text)
    if not match:
        code = "E402" if LOCAL_PATTERN.fullmatch(text) else "E401"
        category = "Missing timezone" if code == "E402" else "Invalid datetime text"
        raise error(code, category, "datetime() requires YYYY-MM-DDTHH:MM:SS[.fff](Z|+HH:MM|-HH:MM).", position, actual=repr(text))
    parts = match.groups()
    local = _calendar(parts, position, "E401", "Invalid datetime text", text)
    zone = parse_timezone("UTC" if parts[7] == "Z" else parts[7], position)
    aware = local.replace(tzinfo=zone.tzinfo)
    try:
        return DatetimeValue(aware.astimezone(UTC), zone)
    except (OverflowError, ValueError):
        raise error("E401", "Datetime overflow", "The datetime instant is outside supported years 0001 through 9999 after offset conversion.", position, actual=repr(text))


def parse_local_datetime(text, position):
    if type(text) is not str:
        raise error("E201", "Type error", "local_datetime() requires a string.", position, expected="string", actual=public_type(text))
    match = LOCAL_PATTERN.fullmatch(text)
    if not match:
        code = "E402" if DATETIME_PATTERN.fullmatch(text) else "E404"
        category = "Forbidden timezone" if code == "E402" else "Invalid local datetime text"
        raise error(code, category, "local_datetime() requires YYYY-MM-DDTHH:MM:SS[.fff] without a timezone.", position, actual=repr(text))
    return LocalDatetimeValue(_calendar(match.groups(), position, "E404", "Invalid local datetime text", text))


def parse_duration(text, position):
    if type(text) is not str:
        raise error("E201", "Type error", "duration() requires a string.", position, expected="string", actual=public_type(text))
    sign = -1 if text.startswith("-") else 1
    body = text[1:] if sign < 0 else text
    cursor, previous, total = 0, -1, 0
    while cursor < len(body):
        match = DURATION_COMPONENT.match(body, cursor)
        if not match:
            break
        amount_text, unit = match.groups()
        order = DURATION_ORDER[unit]
        if order <= previous:
            break
        previous = order
        total += int(amount_text) * DURATION_FACTORS[unit]
        cursor = match.end()
    total *= sign
    if not body or cursor != len(body):
        raise error("E407", "Invalid duration text", "duration() requires ordered, non-repeating integer units: d, h, m, s, ms.", position, actual=repr(text))
    if not MIN_MILLIS <= total <= MAX_MILLIS:
        raise error("E407", "Duration overflow", "duration() exceeds the signed 64-bit millisecond range.", position, actual=repr(text))
    return DurationValue(total)


def datetime_from_local(local, zone, position):
    if not isinstance(local, LocalDatetimeValue) or not isinstance(zone, TimezoneValue):
        raise error("E201", "Type error", "datetime_from_local() requires local_datetime and timezone.", position, expected="local_datetime, timezone", actual=f"{public_type(local)}, {public_type(zone)}")
    candidates = []
    for fold in (0, 1):
        aware = local.value.replace(tzinfo=zone.tzinfo, fold=fold)
        try:
            instant = aware.astimezone(UTC)
            roundtrip = instant.astimezone(zone.tzinfo).replace(tzinfo=None)
        except (OverflowError, ValueError):
            raise error("E401", "Datetime overflow", "The resolved instant is outside supported years 0001 through 9999.", position, actual=format_local(local))
        if roundtrip == local.value and instant not in candidates:
            candidates.append(instant)
    if not candidates:
        raise error("E406", "Nonexistent local datetime", f"The local datetime does not exist in timezone {zone.name} because of an offset transition.", position, actual=format_local(local))
    if len(candidates) > 1:
        raise error("E405", "Ambiguous local datetime", f"The local datetime occurs more than once in timezone {zone.name}; use an offset-bearing datetime() value.", position, actual=format_local(local))
    return DatetimeValue(candidates[0], zone)


def from_unix_milliseconds(milliseconds, zone, position):
    if type(milliseconds) is not int or not isinstance(zone, TimezoneValue):
        raise error("E201", "Type error", "datetime_from_unix_milliseconds() requires an integer number and timezone.", position, expected="integer number, timezone", actual=f"{public_type(milliseconds)}, {public_type(zone)}")
    try:
        instant = EPOCH + timedelta(milliseconds=milliseconds)
    except OverflowError:
        raise error("E401", "Datetime overflow", "Unix milliseconds are outside the supported datetime range.", position, actual=str(milliseconds))
    return DatetimeValue(instant, zone)


def unix_milliseconds(value):
    delta = value.instant_utc - EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def duration_scaled(value, number, divide, position):
    if type(number) not in (int, float) or type(number) is bool:
        raise error("E201", "Type error", "Duration scaling requires a number.", position, expected="number", actual=public_type(number))
    if divide and number == 0:
        raise error("E301", "Division by zero", "A duration cannot be divided by zero.", position, actual="0")
    try:
        result = Decimal(value.milliseconds) / Decimal(str(number)) if divide else Decimal(value.milliseconds) * Decimal(str(number))
    except (InvalidOperation, ZeroDivisionError):
        raise error("E409", "Temporal precision loss", "Duration scaling did not produce a finite millisecond value.", position)
    if result != result.to_integral_value():
        raise error("E409", "Temporal precision loss", "Duration scaling must produce an exact whole number of milliseconds.", position, actual=str(result))
    millis = int(result)
    if not MIN_MILLIS <= millis <= MAX_MILLIS:
        raise error("E407", "Duration overflow", "Duration result exceeds the signed 64-bit millisecond range.", position, actual=str(millis))
    return DurationValue(millis)


def format_datetime(value):
    local = value.instant_utc.astimezone(value.zone.tzinfo)
    fraction = f".{local.microsecond // 1000:03d}" if local.microsecond else ""
    offset = local.utcoffset()
    if offset == timedelta(0):
        suffix = "Z"
    else:
        minutes = int(offset.total_seconds() // 60)
        sign = "+" if minutes >= 0 else "-"
        minutes = abs(minutes)
        suffix = f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"
    return f"{local.year:04d}-{local.month:02d}-{local.day:02d}T{local.hour:02d}:{local.minute:02d}:{local.second:02d}" + fraction + suffix


def format_local(value):
    fraction = f".{value.value.microsecond // 1000:03d}" if value.value.microsecond else ""
    local = value.value
    return f"{local.year:04d}-{local.month:02d}-{local.day:02d}T{local.hour:02d}:{local.minute:02d}:{local.second:02d}" + fraction


def format_duration(value):
    millis = value.milliseconds
    if millis == 0:
        return "0ms"
    sign = "-" if millis < 0 else ""
    remaining, parts = abs(millis), []
    for unit in ("d", "h", "m", "s", "ms"):
        factor = DURATION_FACTORS[unit]
        amount, remaining = divmod(remaining, factor)
        if amount:
            parts.append(f"{amount}{unit}")
    return sign + "".join(parts)


def public_type(value):
    if isinstance(value, DatetimeValue): return "datetime"
    if isinstance(value, LocalDatetimeValue): return "local_datetime"
    if isinstance(value, TimezoneValue): return "timezone"
    if isinstance(value, DurationValue): return "duration"
    if value is None: return "null"
    if type(value) is bool: return "boolean"
    if type(value) in (int, float): return "number"
    if type(value) is str: return "string"
    if type(value) is list: return "list"
    return "unknown"


def timezone_database_version():
    try:
        return "tzdata " + version("tzdata")
    except PackageNotFoundError:
        return "system timezone database"
