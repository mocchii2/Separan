"""Strict built-in functions for the Separan v0.2 alpha reference runtime."""

from dataclasses import dataclass
from datetime import datetime as PyDateTime, timezone as py_timezone
from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import Callable

from .errors import ErrorValue, error
from .temporal import (
    DatetimeValue, DurationValue, LocalDatetimeValue, TimezoneValue,
    datetime_from_local, format_datetime, format_duration, format_local,
    from_unix_milliseconds, parse_datetime, parse_duration,
    parse_local_datetime, parse_timezone, unix_milliseconds,
)
from .randomness import (
    BytesValue, require_integer, require_list, require_number, secure_bytes,
    secure_integer, secure_length, secure_string,
)
from .list_ops import (
    contains as list_contains, first as list_first, index_of as list_index_of,
    last as list_last, last_index_of as list_last_index_of, list_append, list_remove, prepend as list_prepend,
    remove_at as list_remove_at, reverse as list_reverse, size as list_size, slice_list,
    sort_by, sort_by_descending, sort_descending, sort_ignore_case, sort_ignore_case_descending,
    sort_list, sort_natural, sort_natural_descending, sort_natural_ignore_case,
    sort_natural_ignore_case_descending, unique as list_unique,
)
from .system_utilities import UTILITY_BUILTINS, UtilityFunction
from .objects import object_get, object_has, object_keys, object_remove, object_set, object_values
from .io_json import (
    absolute_path, append_text, copy_file, create_directory, delete_directory, delete_file,
    directory_exists, file_exists, file_extension, file_name, file_size, json_decode, json_encode,
    list_directory, move_file, parent_directory, read_bytes, read_lines, read_text, write_bytes, write_text,
)
from .processes import PROCESS_BUILTINS
from .http_client import HTTP_BUILTINS
from .bytes_ops import BYTES_BUILTINS
from .auth import AUTH_BUILTINS, SecretValue
from .crypto_ops import CRYPTO_BUILTINS
from .cookies import COOKIE_BUILTINS
from .cookie_store import COOKIE_STORE_BUILTINS
from .http_server import SERVER_BUILTINS
from .database import DB_BUILTINS
from .collection_ops import average, count as count_values, filter_list, flatten, map_list, reduce_list, sum_list
from .math_ops import MATH_BUILTINS
from .mail import MAIL_BUILTINS
from .structured_data import STRUCTURED_DATA_BUILTINS


MAX_TEXT_LENGTH = 1_048_576


@dataclass(frozen=True)
class BuiltinFunction:
    name: str
    minimum_arguments: int
    maximum_arguments: int
    implementation: Callable

    def call(self, arguments, position, runtime, named=None):
        if named:
            raise error("E207", "Unsupported named argument", f"Built-in function '{self.name}' does not accept named arguments.", position, actual=next(iter(named)))
        count = len(arguments)
        if not self.minimum_arguments <= count <= self.maximum_arguments:
            expected = (
                str(self.minimum_arguments)
                if self.minimum_arguments == self.maximum_arguments
                else f"{self.minimum_arguments}..{self.maximum_arguments}"
            )
            raise error(
                "E207", "Argument count mismatch",
                f"Built-in function '{self.name}' requires {expected} argument(s).",
                position, expected=expected, actual=str(count),
            )
        return self.implementation(arguments, position, runtime)


def _len(arguments, position, runtime):
    value = arguments[0]
    if isinstance(value, BytesValue):
        return len(value.value)
    if type(value) not in (str, list):
        runtime.type_error(position, "string, list, or bytes", runtime.type_name(value), "len() accepts only a string, list, or bytes.")
    return len(value)


def _length(arguments, position, runtime):
    value = arguments[0]
    if isinstance(value, BytesValue): return len(value.value)
    if type(value) not in (str, list):
        runtime.type_error(position, "string, list, or bytes", runtime.type_name(value), "length() accepts only string, list, or bytes.")
    return len(value)


def _is_empty(arguments, position, runtime):
    value = arguments[0]
    if isinstance(value, BytesValue): return len(value.value) == 0
    if type(value) not in (str, list):
        runtime.type_error(position, "string, list, or bytes", runtime.type_name(value), "is_empty() accepts only string, list, or bytes.")
    return len(value) == 0


def _type(arguments, position, runtime):
    return runtime.type_name(arguments[0])


def _is_null(arguments, position, runtime): return arguments[0] is None


def _is_type(expected):
    return lambda arguments, position, runtime: runtime.type_name(arguments[0]) == expected


def _abs(arguments, position, runtime):
    value = arguments[0]
    if not runtime.is_number(value):
        runtime.type_error(position, "number", runtime.type_name(value), "abs() accepts only a number.")
    return abs(value)


def _numeric(name, implementation):
    def call(arguments, position, runtime):
        value = arguments[0]
        if not runtime.is_number(value): runtime.type_error(position, "number", runtime.type_name(value), f"{name}() accepts only a number.")
        try: result = implementation(value)
        except (ValueError, OverflowError): raise error("E308", "Math domain error", f"{name}() input is outside its defined numeric domain.", position, actual=repr(value))
        if type(result) is float and not math.isfinite(result): raise error("E308", "Math domain error", f"{name}() result must be finite.", position, actual=repr(result))
        return result
    return call


def _round(arguments, position, runtime):
    value = arguments[0]
    if not runtime.is_number(value): runtime.type_error(position, "number", runtime.type_name(value), "round() accepts only a number.")
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _minimum_or_maximum(name, choose):
    def implementation(arguments, position, runtime):
        if not all(runtime.is_number(value) for value in arguments):
            runtime.type_error(position, "number arguments", ", ".join(runtime.type_name(value) for value in arguments), f"{name}() accepts only numbers.")
        return choose(arguments)
    return implementation


def _pow(arguments, position, runtime):
    base, exponent = arguments
    if not runtime.is_number(base) or not runtime.is_number(exponent):
        runtime.type_error(position, "number arguments", f"{runtime.type_name(base)}, {runtime.type_name(exponent)}", "pow() accepts only numbers.")
    try: result = base ** exponent
    except (ValueError, OverflowError, ZeroDivisionError): raise error("E308", "Math domain error", "pow() operands are outside the supported real, finite domain.", position, actual=f"{base}, {exponent}")
    if type(result) is complex or (type(result) is float and not math.isfinite(result)):
        raise error("E308", "Math domain error", "pow() result must be real and finite.", position, actual=repr(result))
    return result


def _reverse(arguments, position, runtime):
    value = arguments[0]
    if type(value) is str: return value[::-1]
    return list_reverse(arguments, position, runtime)


def _char_at(arguments, position, runtime):
    value, index = arguments
    if type(value) is not str:
        runtime.type_error(position, "string", runtime.type_name(value), "char_at() requires a string.")
    if type(index) is not int or index < 0:
        runtime.type_error(position, "non-negative integer", repr(index), "char_at() index must be a non-negative integer.")
    if index >= len(value):
        raise error("E302", "Index out of range", "char_at() index must be smaller than the string length.", position, expected=f"0..{len(value) - 1}", actual=str(index))
    return value[index]


def _find_all(arguments, position, runtime):
    _require_strings("find_all", arguments, position, runtime)
    value, search = arguments
    if search == "":
        raise error("E305", "Empty search string", "find_all() search string cannot be empty.", position, expected="non-empty string", actual='""')
    result, start = [], 0
    while True:
        found = value.find(search, start)
        if found < 0: return result
        result.append(found); start = found + len(search)


def _range(arguments, position, runtime):
    if not all(type(value) is int for value in arguments):
        actual = ", ".join(runtime.type_name(value) for value in arguments)
        runtime.type_error(position, "integer number arguments", actual, "range() requires integer-valued numbers.")
    if len(arguments) == 1:
        start, stop, step = 0, arguments[0], 1
    elif len(arguments) == 2:
        start, stop, step = arguments[0], arguments[1], 1
    else:
        start, stop, step = arguments
    if step == 0:
        raise error("E303", "Invalid range step", "range() step cannot be zero.", position, expected="non-zero integer", actual="0")
    return list(range(start, stop, step))


NUMBER_TEXT = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")


def _number(arguments, position, runtime):
    value = arguments[0]
    if runtime.is_number(value):
        return value
    if type(value) is not str:
        runtime.type_error(position, "number or decimal string", runtime.type_name(value), "number() accepts only a number or strict decimal string.")
    if not NUMBER_TEXT.fullmatch(value):
        raise error("E304", "Conversion error", "number() could not parse the string as a decimal number.", position, expected="-?[0-9]+ or -?[0-9]+.[0-9]+", actual=repr(value))
    return float(value) if "." in value else int(value)


def _string(arguments, position, runtime):
    value = arguments[0]
    if type(value) is list or isinstance(value, (BytesValue, SecretValue)):
        runtime.type_error(position, "number, string, boolean, or null", runtime.type_name(value), "string() does not serialize structured or binary values.")
    return runtime.display(value)


def _boolean(arguments, position, runtime):
    value = arguments[0]
    if type(value) is bool:
        return value
    if type(value) is not str:
        runtime.type_error(position, 'boolean or string "true"/"false"', runtime.type_name(value), "boolean() does not use truthy or falsy conversion.")
    if value == "true":
        return True
    if value == "false":
        return False
    raise error("E304", "Conversion error", 'boolean() accepts only the exact strings "true" and "false".', position, expected='"true" or "false"', actual=repr(value))


def _input(arguments, position, runtime):
    prompt = arguments[0] if arguments else ""
    if type(prompt) is not str: runtime.type_error(position, "string prompt", runtime.type_name(prompt), "input() prompt must be a string.")
    runtime.output.write(prompt)
    value = runtime.input_stream.readline()
    if value == "": raise error("E724", "I/O error", "input() reached end-of-input.", position)
    return value.rstrip("\r\n")


def _require_strings(name, arguments, position, runtime):
    for index, value in enumerate(arguments, 1):
        if type(value) is not str:
            runtime.type_error(position, "string arguments", f"argument {index}: {runtime.type_name(value)}", f"{name}() accepts only string arguments.")


def _trim(arguments, position, runtime):
    _require_strings("trim", arguments, position, runtime)
    return arguments[0].strip()


def _upper(arguments, position, runtime):
    _require_strings("upper", arguments, position, runtime)
    return arguments[0].upper()


def _lower(arguments, position, runtime):
    _require_strings("lower", arguments, position, runtime)
    return arguments[0].lower()


def _contains(arguments, position, runtime):
    if type(arguments[0]) is list:
        return list_contains(arguments, position, runtime)
    _require_strings("contains", arguments, position, runtime)
    return arguments[1] in arguments[0]


def _starts_with(arguments, position, runtime):
    _require_strings("starts_with", arguments, position, runtime)
    return arguments[0].startswith(arguments[1])


def _ends_with(arguments, position, runtime):
    _require_strings("ends_with", arguments, position, runtime)
    return arguments[0].endswith(arguments[1])


def _split(arguments, position, runtime):
    _require_strings("split", arguments, position, runtime)
    value, delimiter = arguments
    if delimiter == "":
        raise error("E305", "Empty delimiter", "split() delimiter cannot be empty.", position, expected="non-empty string", actual='""')
    return value.split(delimiter)


def _join(arguments, position, runtime):
    values, separator = arguments
    if type(values) is not list:
        runtime.type_error(position, "list of strings", runtime.type_name(values), "join() first argument must be a list of strings.")
    if type(separator) is not str:
        runtime.type_error(position, "string separator", runtime.type_name(separator), "join() separator must be a string.")
    for index, value in enumerate(values):
        if type(value) is not str:
            runtime.type_error(position, "list of strings", f"element {index}: {runtime.type_name(value)}", "join() does not convert list elements implicitly.")
    return separator.join(values)


def _replace(arguments, position, runtime):
    _require_strings("replace", arguments, position, runtime)
    value, old, new = arguments
    if old == "":
        raise error("E305", "Empty search string", "replace() search string cannot be empty.", position, expected="non-empty string", actual='""')
    return value.replace(old, new)


def _substring(arguments, position, runtime):
    value, start = arguments[0], arguments[1]
    if type(value) is not str:
        runtime.type_error(position, "string as argument 1", runtime.type_name(value), "substring() first argument must be a string.")
    indexes = arguments[1:]
    if not all(type(index) is int and index >= 0 for index in indexes):
        actual = ", ".join(repr(index) for index in indexes)
        runtime.type_error(position, "non-negative integer indexes", actual, "substring() indexes must be non-negative integers.")
    end = arguments[2] if len(arguments) == 3 else len(value)
    if start > end or end > len(value):
        raise error("E306", "Invalid string range", "substring() requires 0 <= start <= end <= string length.", position, expected=f"0 <= start <= end <= {len(value)}", actual=f"start={start}, end={end}")
    return value[start:end]


def _compare(ignore_case=False):
    def implementation(arguments, position, runtime):
        _require_strings("compare_ignore_case" if ignore_case else "compare", arguments, position, runtime)
        left, right = arguments
        if ignore_case: left, right = left.casefold(), right.casefold()
        return -1 if left < right else 1 if left > right else 0
    return implementation


def _search_part(after):
    def implementation(arguments, position, runtime):
        name = "substring_after" if after else "substring_before"
        _require_strings(name, arguments, position, runtime); value, search = arguments
        if search == "": raise error("E305", "Empty search string", f"{name}() search string cannot be empty.", position, expected="non-empty string", actual='""')
        found = value.find(search)
        if found < 0: return None
        return value[found + len(search):] if after else value[:found]
    return implementation


def _count_occurrences(arguments, position, runtime):
    _require_strings("count_occurrences", arguments, position, runtime); value, search = arguments
    if search == "": raise error("E305", "Empty search string", "count_occurrences() search string cannot be empty.", position, expected="non-empty string", actual='""')
    return value.count(search)


def _format(arguments, position, runtime):
    template, values = arguments[0], arguments[1:]
    if type(template) is not str: runtime.type_error(position, "string template", runtime.type_name(template), "format() first argument must be a string.")
    result, index, value_index = [], 0, 0
    while index < len(template):
        pair = template[index:index + 2]
        if pair in ("{{", "}}"): result.append(pair[0]); index += 2; continue
        if pair == "{}":
            if value_index >= len(values): raise error("E307", "Format argument mismatch", "format() has more placeholders than values.", position)
            result.append(runtime.display(values[value_index])); value_index += 1; index += 2; continue
        if template[index] in "{}": raise error("E307", "Invalid format template", "Use '{}' placeholders and '{{' or '}}' for literal braces.", position, actual=template)
        result.append(template[index]); index += 1
    if value_index != len(values): raise error("E307", "Format argument mismatch", "format() has more values than placeholders.", position, expected=str(value_index), actual=str(len(values)))
    text = "".join(result)
    if len(text) > MAX_TEXT_LENGTH: raise error("E607", "Text size limit", f"format() result cannot exceed {MAX_TEXT_LENGTH} Unicode code points.", position)
    return text


def _index_of(arguments, position, runtime):
    if type(arguments[0]) is list:
        return list_index_of(arguments, position, runtime)
    _require_strings("index_of", arguments, position, runtime)
    if arguments[1] == "":
        raise error("E305", "Empty search string", "index_of() search string cannot be empty.", position, expected="non-empty string", actual='""')
    found = arguments[0].find(arguments[1])
    return found if found >= 0 else None


def _last_index_of(arguments, position, runtime):
    if type(arguments[0]) is list:
        return list_last_index_of(arguments, position, runtime)
    _require_strings("last_index_of", arguments, position, runtime)
    if arguments[1] == "":
        raise error("E305", "Empty search string", "last_index_of() search string cannot be empty.", position, expected="non-empty string", actual='""')
    found = arguments[0].rfind(arguments[1])
    return found if found >= 0 else None


def _repeat(arguments, position, runtime):
    value, count = arguments
    if type(value) is not str:
        runtime.type_error(position, "string", runtime.type_name(value), "repeat() requires a string.")
    if type(count) is not int or count < 0:
        runtime.type_error(position, "non-negative integer", repr(count), "repeat() count must be a non-negative integer.")
    result_length = len(value) * count
    if result_length > MAX_TEXT_LENGTH:
        raise error("E607", "Text size limit", f"repeat() result cannot exceed {MAX_TEXT_LENGTH} Unicode code points.", position, expected=f"0..{MAX_TEXT_LENGTH}", actual=str(result_length))
    return value * count


def _pad(direction):
    def implementation(arguments, position, runtime):
        value, target = arguments[0], arguments[1]
        fill = arguments[2] if len(arguments) == 3 else " "
        if type(value) is not str:
            runtime.type_error(position, "string", runtime.type_name(value), f"pad_{direction}() requires a string.")
        if type(target) is not int or target < 0:
            runtime.type_error(position, "non-negative integer target length", repr(target), f"pad_{direction}() target length must be a non-negative integer.")
        if type(fill) is not str or len(fill) != 1:
            raise error("E606", "Invalid padding character", f"pad_{direction}() fill must contain exactly one Unicode code point.", position, expected="one-code-point string", actual=repr(fill))
        if target > MAX_TEXT_LENGTH:
            raise error("E607", "Text size limit", f"pad_{direction}() result cannot exceed {MAX_TEXT_LENGTH} Unicode code points.", position, expected=f"0..{MAX_TEXT_LENGTH}", actual=str(target))
        count = max(0, target - len(value)); padding = fill * count
        return padding + value if direction == "left" else value + padding
    return implementation


def _datetime(arguments, position, runtime): return parse_datetime(arguments[0], position)
def _local_datetime(arguments, position, runtime): return parse_local_datetime(arguments[0], position)
def _timezone(arguments, position, runtime): return parse_timezone(arguments[0], position)
def _duration(arguments, position, runtime): return parse_duration(arguments[0], position)


def _datetime_construct(arguments, named, position, runtime):
    if len(arguments) == 1:
        if named: raise error("E207", "Invalid datetime arguments", "Text datetime construction does not accept a timezone argument because the offset is required in the text.", position)
        return parse_datetime(arguments[0], position)
    if len(arguments) != 6:
        raise error("E207", "Argument count mismatch", "datetime() requires one offset-bearing string or six integer calendar fields plus named timezone.", position, expected="1 or 6", actual=str(len(arguments)))
    if not all(type(value) is int for value in arguments):
        runtime.type_error(position, "six integer calendar fields", ", ".join(runtime.type_name(value) for value in arguments), "datetime() numeric fields must be integers.")
    zone = named.get("timezone")
    if type(zone) is str: zone = parse_timezone(zone, position)
    if not isinstance(zone, TimezoneValue): runtime.type_error(position, "named timezone string or value", runtime.type_name(zone), "datetime() calendar construction requires timezone = ...")
    try: local = LocalDatetimeValue(PyDateTime(*arguments))
    except ValueError: raise error("E401", "Invalid datetime fields", "datetime() fields do not form a valid calendar date and clock time.", position, actual=repr(arguments))
    return datetime_from_local(local, zone, position)


def _datetime_from_local(arguments, position, runtime):
    return datetime_from_local(arguments[0], arguments[1], position)


def _datetime_in_timezone(arguments, position, runtime):
    value, zone = arguments
    if not isinstance(value, DatetimeValue) or not isinstance(zone, TimezoneValue):
        runtime.type_error(position, "datetime, timezone", f"{runtime.type_name(value)}, {runtime.type_name(zone)}", "datetime_in_timezone() requires datetime and timezone.")
    return DatetimeValue(value.instant_utc, zone)


def _datetime_now(arguments, position, runtime):
    zone = TimezoneValue("UTC", py_timezone.utc) if not arguments else arguments[0]
    if type(zone) is str: zone = parse_timezone(zone, position)
    if not isinstance(zone, TimezoneValue): runtime.type_error(position, "timezone or timezone string", runtime.type_name(zone), "datetime_now() accepts a timezone value or name.")
    instant = runtime.current_time()
    return DatetimeValue(instant, zone)


def _datetime_valid(arguments, position, runtime):
    if not all(type(value) is int for value in arguments):
        runtime.type_error(position, "integer year, month, day", ", ".join(runtime.type_name(value) for value in arguments), "datetime_valid() requires integer calendar fields.")
    try:
        PyDateTime(*arguments)
        return True
    except ValueError: return False


def _datetime_format(arguments, position, runtime):
    value, pattern = arguments
    if not isinstance(value, DatetimeValue) or type(pattern) is not str:
        runtime.type_error(position, "datetime, string pattern", f"{runtime.type_name(value)}, {runtime.type_name(pattern)}", "datetime_format() requires datetime and a pattern string.")
    local = value.instant_utc.astimezone(value.zone.tzinfo); offset = local.utcoffset()
    offset_minutes = int(offset.total_seconds() // 60); sign = "+" if offset_minutes >= 0 else "-"; absolute = abs(offset_minutes)
    tokens = {
        "yyyy": f"{local.year:04d}", "MM": f"{local.month:02d}", "dd": f"{local.day:02d}",
        "HH": f"{local.hour:02d}", "mm": f"{local.minute:02d}", "ss": f"{local.second:02d}",
        "SSS": f"{local.microsecond // 1000:03d}", "XXX": "Z" if offset_minutes == 0 else f"{sign}{absolute // 60:02d}:{absolute % 60:02d}",
    }
    result, index = [], 0
    while index < len(pattern):
        token = next((item for item in ("yyyy", "SSS", "XXX", "MM", "dd", "HH", "mm", "ss") if pattern.startswith(item, index)), None)
        if token: result.append(tokens[token]); index += len(token); continue
        if pattern[index].isalpha(): raise error("E410", "Invalid datetime format", "Unknown or incomplete datetime format token.", position, actual=pattern[index:])
        result.append(pattern[index]); index += 1
    return "".join(result)


def _unix_time(arguments, position, runtime):
    if arguments: return _unix_seconds_from_datetime(arguments, position, runtime)
    now = DatetimeValue(runtime.current_time(), TimezoneValue("UTC", py_timezone.utc))
    return _unix_seconds_from_datetime([now], position, runtime)


def _datetime_from_unix(arguments, position, runtime):
    seconds = arguments[0]
    zone = arguments[1] if len(arguments) == 2 else TimezoneValue("UTC", py_timezone.utc)
    if type(zone) is str: zone = parse_timezone(zone, position)
    return _datetime_from_unix_seconds([seconds, zone], position, runtime)


def _unix_milliseconds_from_datetime(arguments, position, runtime):
    value = arguments[0]
    if not isinstance(value, DatetimeValue):
        runtime.type_error(position, "datetime", runtime.type_name(value), "unix_milliseconds_from_datetime() requires datetime.")
    return unix_milliseconds(value)


def _unix_seconds_from_datetime(arguments, position, runtime):
    millis = _unix_milliseconds_from_datetime(arguments, position, runtime)
    return millis // 1000 if millis % 1000 == 0 else millis / 1000


def _datetime_from_unix_milliseconds(arguments, position, runtime):
    return from_unix_milliseconds(arguments[0], arguments[1], position)


def _datetime_from_unix_seconds(arguments, position, runtime):
    seconds, zone = arguments
    if not runtime.is_number(seconds) or not isinstance(zone, TimezoneValue):
        runtime.type_error(position, "number, timezone", f"{runtime.type_name(seconds)}, {runtime.type_name(zone)}", "datetime_from_unix_seconds() requires number and timezone.")
    milliseconds = Decimal(str(seconds)) * 1000
    if milliseconds != milliseconds.to_integral_value():
        raise error("E409", "Temporal precision loss", "Unix seconds must resolve to exact milliseconds.", position, actual=str(seconds))
    return from_unix_milliseconds(int(milliseconds), zone, position)


def _require_temporal(value, expected, kind, position, runtime):
    if not isinstance(value, kind):
        runtime.type_error(position, expected, runtime.type_name(value), f"Expected {expected} temporal value.")


def _datetime_offset(arguments, position, runtime):
    value = arguments[0]; _require_temporal(value, "datetime", DatetimeValue, position, runtime)
    offset = value.instant_utc.astimezone(value.zone.tzinfo).utcoffset()
    return DurationValue(int(offset.total_seconds() * 1000))


def _datetime_timezone(arguments, position, runtime):
    value = arguments[0]; _require_temporal(value, "datetime", DatetimeValue, position, runtime); return value.zone


def _datetime_field(field):
    def implementation(arguments, position, runtime):
        value = arguments[0]; _require_temporal(value, "datetime", DatetimeValue, position, runtime)
        local = value.instant_utc.astimezone(value.zone.tzinfo)
        if field == "millisecond": return local.microsecond // 1000
        if field == "isoweekday": return local.isoweekday()
        return getattr(local, field)
    return implementation


def _duration_milliseconds(arguments, position, runtime):
    value = arguments[0]; _require_temporal(value, "duration", DurationValue, position, runtime); return value.milliseconds


def _random_seed(arguments, position, runtime):
    seed = arguments[0]
    require_integer(seed, "random_seed", position, runtime)
    runtime.random.seed(seed)
    return None


def _random_number(arguments, position, runtime): return runtime.random.number()


def _random_int(arguments, position, runtime):
    minimum, maximum = arguments
    require_integer(minimum, "random_int", position, runtime); require_integer(maximum, "random_int", position, runtime)
    if minimum > maximum:
        raise error("E501", "Invalid random range", "random_int() requires min <= max and includes both endpoints.", position, expected="min <= max", actual=f"{minimum}..{maximum}")
    return runtime.random.integer(minimum, maximum)


def _random_float(arguments, position, runtime):
    minimum, maximum = arguments
    require_number(minimum, "random_float", position, runtime); require_number(maximum, "random_float", position, runtime)
    if not minimum < maximum:
        raise error("E501", "Invalid random range", "random_float() requires min < max and excludes the upper endpoint.", position, expected="min < max", actual=f"{minimum}..{maximum}")
    return runtime.random.floating(minimum, maximum)


def _random_bool(arguments, position, runtime): return bool(runtime.random.next_u32() & 1)


def _random_pick(arguments, position, runtime):
    values = arguments[0]; require_list(values, "random_pick", position, runtime)
    if not values:
        raise error("E502", "Empty random population", "random_pick() cannot choose from an empty list.", position, expected="non-empty list", actual="[]")
    return values[runtime.random.below(len(values))]


def _random_shuffle(arguments, position, runtime):
    values = arguments[0]; require_list(values, "random_shuffle", position, runtime)
    return runtime.random.shuffled(values)


def _random_sample(arguments, position, runtime):
    values, count = arguments
    require_list(values, "random_sample", position, runtime); require_integer(count, "random_sample", position, runtime)
    if count < 0 or count > len(values):
        raise error("E503", "Invalid sample size", "random_sample() count must be between zero and the list length.", position, expected=f"0..{len(values)}", actual=str(count))
    return runtime.random.sample(values, count)


def _secure_random_bytes(arguments, position, runtime):
    length = arguments[0]; secure_length(length, "secure_random_bytes", position, runtime); return secure_bytes(length)


def _secure_random_integer(arguments, position, runtime, name):
    minimum, maximum = arguments
    require_integer(minimum, name, position, runtime); require_integer(maximum, name, position, runtime)
    if minimum > maximum:
        raise error("E501", "Invalid secure random range", f"{name}() requires min <= max and includes both endpoints.", position, expected="min <= max", actual=f"{minimum}..{maximum}")
    return secure_integer(minimum, maximum)


def _secure_random_int(arguments, position, runtime): return _secure_random_integer(arguments, position, runtime, "secure_random_int")
def _secure_random_number(arguments, position, runtime): return _secure_random_integer(arguments, position, runtime, "secure_random_number")


def _secure_random_string(arguments, position, runtime):
    length = arguments[0]; secure_length(length, "secure_random_string", position, runtime); return secure_string(length)


def _error_constructor(category):
    def implementation(arguments, position, runtime):
        if type(arguments[0]) is not str: runtime.type_error(position, "string message", runtime.type_name(arguments[0]), f"{category}() requires a string message.")
        return ErrorValue(category, arguments[0])
    return implementation


BUILTINS = {
    function.name: function
    for function in (
        BuiltinFunction("len", 1, 1, _len),
        BuiltinFunction("length", 1, 1, _length),
        BuiltinFunction("is_empty", 1, 1, _is_empty),
        BuiltinFunction("type", 1, 1, _type),
        BuiltinFunction("type_of", 1, 1, _type),
        BuiltinFunction("is_null", 1, 1, _is_null),
        BuiltinFunction("is_number", 1, 1, _is_type("number")),
        BuiltinFunction("is_string", 1, 1, _is_type("string")),
        BuiltinFunction("is_boolean", 1, 1, _is_type("boolean")),
        BuiltinFunction("is_list", 1, 1, _is_type("list")),
        BuiltinFunction("is_object", 1, 1, _is_type("object")),
        BuiltinFunction("is_bytes", 1, 1, _is_type("bytes")),
        BuiltinFunction("is_datetime", 1, 1, _is_type("datetime")),
        BuiltinFunction("is_duration", 1, 1, _is_type("duration")),
        BuiltinFunction("is_secret", 1, 1, _is_type("secret")),
        BuiltinFunction("abs", 1, 1, _abs),
        BuiltinFunction("ceil", 1, 1, _numeric("ceil", math.ceil)),
        BuiltinFunction("floor", 1, 1, _numeric("floor", math.floor)),
        BuiltinFunction("round", 1, 1, _round),
        BuiltinFunction("min", 1, 64, _minimum_or_maximum("min", min)),
        BuiltinFunction("max", 1, 64, _minimum_or_maximum("max", max)),
        BuiltinFunction("sqrt", 1, 1, _numeric("sqrt", math.sqrt)),
        BuiltinFunction("sin", 1, 1, _numeric("sin", math.sin)),
        BuiltinFunction("cos", 1, 1, _numeric("cos", math.cos)),
        BuiltinFunction("tan", 1, 1, _numeric("tan", math.tan)),
        BuiltinFunction("log", 1, 1, _numeric("log", math.log)),
        BuiltinFunction("log10", 1, 1, _numeric("log10", math.log10)),
        BuiltinFunction("log2", 1, 1, _numeric("log2", math.log2)),
        BuiltinFunction("exp", 1, 1, _numeric("exp", math.exp)),
        BuiltinFunction("pow", 2, 2, _pow),
        BuiltinFunction("range", 1, 3, _range),
        BuiltinFunction("number", 1, 1, _number),
        BuiltinFunction("string", 1, 1, _string),
        BuiltinFunction("boolean", 1, 1, _boolean),
        BuiltinFunction("input", 0, 1, _input),
        BuiltinFunction("trim", 1, 1, _trim),
        BuiltinFunction("upper", 1, 1, _upper),
        BuiltinFunction("lower", 1, 1, _lower),
        BuiltinFunction("contains", 2, 2, _contains),
        BuiltinFunction("starts_with", 2, 2, _starts_with),
        BuiltinFunction("ends_with", 2, 2, _ends_with),
        BuiltinFunction("split", 2, 2, _split),
        BuiltinFunction("join", 2, 2, _join),
        BuiltinFunction("replace", 3, 3, _replace),
        BuiltinFunction("substring", 2, 3, _substring),
        BuiltinFunction("char_at", 2, 2, _char_at),
        BuiltinFunction("find_all", 2, 2, _find_all),
        BuiltinFunction("compare", 2, 2, _compare()),
        BuiltinFunction("compare_ignore_case", 2, 2, _compare(True)),
        BuiltinFunction("substring_after", 2, 2, _search_part(True)),
        BuiltinFunction("substring_before", 2, 2, _search_part(False)),
        BuiltinFunction("count_occurrences", 2, 2, _count_occurrences),
        BuiltinFunction("format", 1, 64, _format),
        BuiltinFunction("local_datetime", 1, 1, _local_datetime),
        BuiltinFunction("timezone", 1, 1, _timezone),
        BuiltinFunction("duration", 1, 1, _duration),
        BuiltinFunction("datetime_from_local", 2, 2, _datetime_from_local),
        BuiltinFunction("datetime_in_timezone", 2, 2, _datetime_in_timezone),
        BuiltinFunction("datetime_now", 0, 1, _datetime_now),
        BuiltinFunction("datetime_parse", 1, 1, _datetime),
        BuiltinFunction("datetime_valid", 3, 3, _datetime_valid),
        BuiltinFunction("datetime_format", 2, 2, _datetime_format),
        BuiltinFunction("unix_time", 0, 1, _unix_time),
        BuiltinFunction("datetime_from_unix", 1, 2, _datetime_from_unix),
        BuiltinFunction("unix_milliseconds_from_datetime", 1, 1, _unix_milliseconds_from_datetime),
        BuiltinFunction("unix_seconds_from_datetime", 1, 1, _unix_seconds_from_datetime),
        BuiltinFunction("datetime_from_unix_milliseconds", 2, 2, _datetime_from_unix_milliseconds),
        BuiltinFunction("datetime_from_unix_seconds", 2, 2, _datetime_from_unix_seconds),
        BuiltinFunction("datetime_offset", 1, 1, _datetime_offset),
        BuiltinFunction("datetime_timezone", 1, 1, _datetime_timezone),
        BuiltinFunction("datetime_year", 1, 1, _datetime_field("year")),
        BuiltinFunction("datetime_month", 1, 1, _datetime_field("month")),
        BuiltinFunction("datetime_day", 1, 1, _datetime_field("day")),
        BuiltinFunction("datetime_hour", 1, 1, _datetime_field("hour")),
        BuiltinFunction("datetime_minute", 1, 1, _datetime_field("minute")),
        BuiltinFunction("datetime_second", 1, 1, _datetime_field("second")),
        BuiltinFunction("datetime_millisecond", 1, 1, _datetime_field("millisecond")),
        BuiltinFunction("datetime_weekday", 1, 1, _datetime_field("isoweekday")),
        BuiltinFunction("duration_milliseconds", 1, 1, _duration_milliseconds),
        BuiltinFunction("random_seed", 1, 1, _random_seed),
        BuiltinFunction("random_number", 0, 0, _random_number),
        BuiltinFunction("random_int", 2, 2, _random_int),
        BuiltinFunction("random_float", 2, 2, _random_float),
        BuiltinFunction("random_bool", 0, 0, _random_bool),
        BuiltinFunction("random_pick", 1, 1, _random_pick),
        BuiltinFunction("random_shuffle", 1, 1, _random_shuffle),
        BuiltinFunction("random_sample", 2, 2, _random_sample),
        BuiltinFunction("secure_random_bytes", 1, 1, _secure_random_bytes),
        BuiltinFunction("secure_random_int", 2, 2, _secure_random_int),
        BuiltinFunction("secure_random_number", 2, 2, _secure_random_number),
        BuiltinFunction("secure_random_string", 1, 1, _secure_random_string),
        BuiltinFunction("list_append", 2, 2, list_append),
        BuiltinFunction("append", 2, 2, list_append),
        BuiltinFunction("prepend", 2, 2, list_prepend),
        BuiltinFunction("list_remove", 2, 2, list_remove),
        BuiltinFunction("remove", 2, 2, list_remove),
        BuiltinFunction("remove_at", 2, 2, list_remove_at),
        BuiltinFunction("size", 1, 1, list_size),
        BuiltinFunction("first", 1, 1, list_first),
        BuiltinFunction("last", 1, 1, list_last),
        BuiltinFunction("index_of", 2, 2, _index_of),
        BuiltinFunction("last_index_of", 2, 2, _last_index_of),
        BuiltinFunction("slice", 3, 3, slice_list),
        BuiltinFunction("reverse", 1, 1, _reverse),
        BuiltinFunction("sort", 1, 1, sort_list),
        BuiltinFunction("sort_descending", 1, 1, sort_descending),
        BuiltinFunction("sort_ignore_case", 1, 1, sort_ignore_case),
        BuiltinFunction("sort_ignore_case_descending", 1, 1, sort_ignore_case_descending),
        BuiltinFunction("sort_natural", 1, 1, sort_natural),
        BuiltinFunction("sort_natural_descending", 1, 1, sort_natural_descending),
        BuiltinFunction("sort_natural_ignore_case", 1, 1, sort_natural_ignore_case),
        BuiltinFunction("sort_natural_ignore_case_descending", 1, 1, sort_natural_ignore_case_descending),
        BuiltinFunction("sort_by", 2, 2, sort_by),
        BuiltinFunction("sort_by_descending", 2, 2, sort_by_descending),
        BuiltinFunction("unique", 1, 1, list_unique),
        BuiltinFunction("map", 2, 2, map_list),
        BuiltinFunction("filter", 2, 2, filter_list),
        BuiltinFunction("reduce", 3, 3, reduce_list),
        BuiltinFunction("flatten", 1, 1, flatten),
        BuiltinFunction("sum", 1, 1, sum_list),
        BuiltinFunction("average", 1, 1, average),
        BuiltinFunction("count", 2, 2, count_values),
        BuiltinFunction("repeat", 2, 2, _repeat),
        BuiltinFunction("pad_left", 2, 3, _pad("left")),
        BuiltinFunction("pad_right", 2, 3, _pad("right")),
        BuiltinFunction("object_get", 2, 2, object_get),
        BuiltinFunction("object_has", 2, 2, object_has),
        BuiltinFunction("object_set", 3, 3, object_set),
        BuiltinFunction("object_remove", 2, 2, object_remove),
        BuiltinFunction("object_keys", 1, 1, object_keys),
        BuiltinFunction("object_values", 1, 1, object_values),
        BuiltinFunction("read_text", 1, 1, read_text),
        BuiltinFunction("write_text", 2, 2, write_text),
        BuiltinFunction("append_text", 2, 2, append_text),
        BuiltinFunction("read_bytes", 1, 1, read_bytes),
        BuiltinFunction("write_bytes", 2, 2, write_bytes),
        BuiltinFunction("file_exists", 1, 1, file_exists),
        BuiltinFunction("file_size", 1, 1, file_size),
        BuiltinFunction("copy_file", 2, 2, copy_file),
        BuiltinFunction("move_file", 2, 2, move_file),
        BuiltinFunction("delete_file", 1, 1, delete_file),
        BuiltinFunction("read_lines", 1, 1, read_lines),
        BuiltinFunction("directory_exists", 1, 1, directory_exists),
        BuiltinFunction("create_directory", 1, 1, create_directory),
        BuiltinFunction("delete_directory", 1, 1, delete_directory),
        BuiltinFunction("list_directory", 1, 1, list_directory),
        BuiltinFunction("file_name", 1, 1, file_name),
        BuiltinFunction("file_extension", 1, 1, file_extension),
        BuiltinFunction("parent_directory", 1, 1, parent_directory),
        BuiltinFunction("absolute_path", 1, 1, absolute_path),
        BuiltinFunction("json_decode", 1, 1, json_decode),
        BuiltinFunction("json_encode", 1, 1, json_encode),
        *(BuiltinFunction(category, 1, 1, _error_constructor(category)) for category in (
            "runtime_error", "type_error", "value_error", "index_error", "io_error",
            "parse_error", "import_error", "regex_error", "glob_error", "argument_error", "permission_error"
            , "auth_error", "secret_error", "oauth_error"
            , "crypto_error", "crypto_authentication_error"
            , "mail_error", "mail_address_error", "mail_attachment_error", "mail_provider_error", "mail_connection_error", "mail_authentication_error", "mail_send_error"
            , "yaml_error", "yaml_parse_error", "yaml_encode_error", "yaml_type_error", "yaml_limit_error"
            , "xml_error", "xml_parse_error", "xml_model_error", "xml_security_error", "xml_limit_error", "xml_path_error", "xml_escape_error"
            , "cookie_error"
            , "db_connection_error", "db_auth_error", "db_query_error", "db_constraint_error", "db_timeout_error", "db_transaction_error", "db_driver_error"
        )),
    ) + MATH_BUILTINS + (UtilityFunction("datetime", 1, 6, _datetime_construct, ("timezone",)),) + UTILITY_BUILTINS + PROCESS_BUILTINS + HTTP_BUILTINS + BYTES_BUILTINS + AUTH_BUILTINS + CRYPTO_BUILTINS + MAIL_BUILTINS + STRUCTURED_DATA_BUILTINS + COOKIE_BUILTINS + COOKIE_STORE_BUILTINS + SERVER_BUILTINS + DB_BUILTINS
}
