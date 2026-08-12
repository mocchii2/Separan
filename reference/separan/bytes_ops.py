"""Strict operations for Separan's immutable bytes type."""

import base64
import binascii

from .errors import error
from .randomness import BytesValue
from .system_utilities import UtilityFunction


MAX_BYTES_LENGTH = 67_108_864
ENCODINGS = {"utf-8": "utf-8", "utf-16le": "utf-16-le", "utf-16be": "utf-16-be", "ascii": "ascii"}


def _bytes(value, name, position, runtime):
    if not isinstance(value, BytesValue): runtime.type_error(position, "bytes", runtime.type_name(value), f"{name}() requires bytes.")
    return value.value


def _encoding(named, position, runtime):
    value = named.get("encoding", "utf-8")
    if type(value) is not str: runtime.type_error(position, "string encoding", runtime.type_name(value), "encoding must be a string.")
    if value not in ENCODINGS: raise error("E620", "Unsupported encoding", "Supported encodings are utf-8, utf-16le, utf-16be, and ascii.", position, actual=repr(value))
    return ENCODINGS[value]


def _bytes_from_string(arguments, named, position, runtime):
    value = arguments[0]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "bytes_from_string() requires a string.")
    try: result = value.encode(_encoding(named, position, runtime), errors="strict")
    except UnicodeError as exc: raise error("E621", "Encoding error", str(exc), position)
    return BytesValue(result)


def _string_from_bytes(arguments, named, position, runtime):
    value = _bytes(arguments[0], "string_from_bytes", position, runtime)
    try: return value.decode(_encoding(named, position, runtime), errors="strict")
    except UnicodeError as exc: raise error("E621", "Decoding error", str(exc), position)


def _bytes_get(arguments, named, position, runtime):
    value = _bytes(arguments[0], "bytes_get", position, runtime); index = arguments[1]
    if type(index) is not int or index < 0: runtime.type_error(position, "non-negative integer", runtime.type_name(index), "bytes_get() index must be a non-negative integer.")
    if index >= len(value): raise error("E622", "Bytes index out of range", f"Index {index} is outside bytes of length {len(value)}.", position, expected=f"0..{len(value)-1}", actual=str(index))
    return value[index]


def _slice_bytes(arguments, named, position, runtime):
    value = _bytes(arguments[0], "slice_bytes", position, runtime); start, end = arguments[1:]
    if type(start) is not int or type(end) is not int or start < 0 or end < 0: runtime.type_error(position, "non-negative integer indexes", f"{start}, {end}", "slice_bytes() indexes must be non-negative integers.")
    if start > end or end > len(value): raise error("E623", "Invalid bytes range", "slice_bytes() requires 0 <= start <= end <= bytes length.", position, expected=f"0 <= start <= end <= {len(value)}", actual=f"{start}..{end}")
    return BytesValue(value[start:end])


def _bytes_concat(arguments, named, position, runtime):
    left = _bytes(arguments[0], "bytes_concat", position, runtime); right = _bytes(arguments[1], "bytes_concat", position, runtime)
    if len(left) + len(right) > MAX_BYTES_LENGTH: raise error("E624", "Bytes size limit", f"bytes result cannot exceed {MAX_BYTES_LENGTH} bytes.", position)
    return BytesValue(left + right)


def _hex_encode(arguments, named, position, runtime): return _bytes(arguments[0], "hex_encode", position, runtime).hex().upper()


def _hex_decode(arguments, named, position, runtime):
    value = arguments[0]
    if type(value) is not str: runtime.type_error(position, "hex string", runtime.type_name(value), "hex_decode() requires a string.")
    if len(value) % 2: raise error("E625", "Invalid hex", "Hex input must contain an even number of digits.", position, actual=value)
    try: return BytesValue(bytes.fromhex(value))
    except ValueError as exc: raise error("E625", "Invalid hex", str(exc), position, actual=value)


def _base64_encode(arguments, named, position, runtime): return base64.b64encode(_bytes(arguments[0], "base64_encode", position, runtime)).decode("ascii")


def _base64_decode(arguments, named, position, runtime):
    value = arguments[0]
    if type(value) is not str: runtime.type_error(position, "Base64 string", runtime.type_name(value), "base64_decode() requires a string.")
    try: return BytesValue(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError) as exc: raise error("E626", "Invalid Base64", str(exc), position, actual=value)


BYTES_BUILTINS = (
    UtilityFunction("bytes_from_string", 1, 1, _bytes_from_string, ("encoding",)),
    UtilityFunction("string_from_bytes", 1, 1, _string_from_bytes, ("encoding",)),
    UtilityFunction("bytes_get", 2, 2, _bytes_get), UtilityFunction("slice_bytes", 3, 3, _slice_bytes),
    UtilityFunction("bytes_concat", 2, 2, _bytes_concat), UtilityFunction("hex_encode", 1, 1, _hex_encode),
    UtilityFunction("hex_decode", 1, 1, _hex_decode), UtilityFunction("bytes_from_hex", 1, 1, _hex_decode),
    UtilityFunction("base64_encode", 1, 1, _base64_encode), UtilityFunction("base64_decode", 1, 1, _base64_decode),
)
