"""Readable, strict mathematics built-ins for Separan."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import math
import statistics

from .errors import error
from .system_utilities import UtilityFunction


MAX_FACTORIAL = 1000
MAX_ROUND_DIGITS = 100
BASE_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _number(value, name, position, runtime):
    if not runtime.is_number(value):
        runtime.type_error(position, "number", runtime.type_name(value), f"{name}() requires a number.")
    return value


def _finite(value, name, position):
    if type(value) is float and not math.isfinite(value):
        raise error("E308", "Math domain error", f"{name}() requires a finite number.", position, actual=repr(value))
    return value


def _finite_result(value, name, position):
    if type(value) is complex or (type(value) is float and not math.isfinite(value)):
        raise error("E308", "Math domain error", f"{name}() result must be real and finite.", position, actual=repr(value))
    return value


def _integer(value, name, position, runtime):
    _number(value, name, position, runtime)
    if type(value) is int:
        return value
    if not math.isfinite(value) or not value.is_integer():
        runtime.type_error(position, "integer-valued number", runtime.type_name(value), f"{name}() requires an integer-valued number.")
    return int(value)


def _unary(name, implementation):
    def call(arguments, named, position, runtime):
        value = _finite(_number(arguments[0], name, position, runtime), name, position)
        try:
            return _finite_result(implementation(value), name, position)
        except (ValueError, OverflowError, ZeroDivisionError):
            raise error("E308", "Math domain error", f"{name}() input is outside its defined numeric domain.", position, actual=repr(value))
    return call


def _binary(name, implementation):
    def call(arguments, named, position, runtime):
        first = _finite(_number(arguments[0], name, position, runtime), name, position)
        second = _finite(_number(arguments[1], name, position, runtime), name, position)
        try:
            return _finite_result(implementation(first, second), name, position)
        except (ValueError, OverflowError, ZeroDivisionError):
            raise error("E308", "Math domain error", f"{name}() operands are outside its defined numeric domain.", position, actual=f"{first}, {second}")
    return call


def _round(arguments, named, position, runtime):
    value = _finite(_number(arguments[0], "round", position, runtime), "round", position)
    digits = 0 if len(arguments) == 1 else _integer(arguments[1], "round", position, runtime)
    if not -MAX_ROUND_DIGITS <= digits <= MAX_ROUND_DIGITS:
        raise error("E308", "Math range error", f"round() digits must be between {-MAX_ROUND_DIGITS} and {MAX_ROUND_DIGITS}.", position, expected=f"{-MAX_ROUND_DIGITS}..{MAX_ROUND_DIGITS}", actual=str(digits))
    try:
        decimal_value = Decimal(str(value))
        with localcontext() as context:
            context.prec = max(50, len(decimal_value.as_tuple().digits) + abs(digits) + 4)
            rounded = decimal_value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise error("E308", "Math domain error", "round() could not represent the requested precision.", position, actual=f"{value}, {digits}")
    if digits <= 0:
        return int(rounded)
    try:
        converted = float(rounded)
    except OverflowError:
        converted = math.inf
    if math.isfinite(converted):
        return converted
    if rounded == rounded.to_integral_value():
        return int(rounded)
    raise error("E308", "Math domain error", "round() result is outside the finite floating-point range.", position, actual=str(rounded))


def _minimum_or_maximum(name, choose):
    def call(arguments, named, position, runtime):
        values = arguments[0] if len(arguments) == 1 and type(arguments[0]) is list else arguments
        if not values:
            raise error("E602", "Empty collection", f"{name}() requires at least one number.", position)
        for value in values:
            _finite(_number(value, name, position, runtime), name, position)
        return choose(values)
    return call


def _clamp(arguments, named, position, runtime):
    value, minimum, maximum = (_finite(_number(item, "clamp", position, runtime), "clamp", position) for item in arguments)
    if minimum > maximum:
        raise error("E308", "Math range error", "clamp() requires minimum <= maximum.", position, expected="minimum <= maximum", actual=f"{minimum}..{maximum}")
    return min(max(value, minimum), maximum)


def _sign(arguments, named, position, runtime):
    value = _finite(_number(arguments[0], "sign", position, runtime), "sign", position)
    return -1 if value < 0 else 1 if value > 0 else 0


def _cube_root(arguments, named, position, runtime):
    value = _finite(_number(arguments[0], "cube_root", position, runtime), "cube_root", position)
    result = math.pow(abs(value), 1.0 / 3.0)
    return -result if value < 0 else result


def _power(arguments, named, position, runtime):
    return _binary("power", lambda base, exponent: base ** exponent)(arguments, named, position, runtime)


def _integer_pair(name, implementation):
    def call(arguments, named, position, runtime):
        first = _integer(arguments[0], name, position, runtime)
        second = _integer(arguments[1], name, position, runtime)
        return implementation(first, second)
    return call


def _factorial(arguments, named, position, runtime):
    value = _integer(arguments[0], "factorial", position, runtime)
    if not 0 <= value <= MAX_FACTORIAL:
        raise error("E308", "Math range error", f"factorial() requires a value between 0 and {MAX_FACTORIAL}.", position, expected=f"0..{MAX_FACTORIAL}", actual=str(value))
    return math.factorial(value)


def _predicate(name, predicate):
    def call(arguments, named, position, runtime):
        value = _number(arguments[0], name, position, runtime)
        return predicate(value)
    return call


def _is_close(arguments, named, position, runtime):
    left = _number(arguments[0], "is_close", position, runtime)
    right = _number(arguments[1], "is_close", position, runtime)
    try:
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=0.0)
    except OverflowError:
        difference = Decimal(abs(left - right))
        scale = Decimal(max(abs(left), abs(right)))
        return difference <= Decimal("1e-9") * scale


def _number_list(value, name, position, runtime, minimum_length=1):
    if type(value) is not list:
        runtime.type_error(position, "list<number>", runtime.type_name(value), f"{name}() requires a list of numbers.")
    if len(value) < minimum_length:
        raise error("E602", "Empty or insufficient collection", f"{name}() requires at least {minimum_length} value(s).", position, expected=f"length >= {minimum_length}", actual=str(len(value)))
    for item in value:
        _finite(_number(item, name, position, runtime), name, position)
    return value


def _statistic(name, implementation, minimum_length=1):
    def call(arguments, named, position, runtime):
        values = _number_list(arguments[0], name, position, runtime, minimum_length)
        try:
            return _finite_result(implementation(values), name, position)
        except statistics.StatisticsError as exc:
            raise error("E602", "Insufficient collection", str(exc), position)
    return call


def _percentile(arguments, named, position, runtime):
    values = sorted(_number_list(arguments[0], "percentile", position, runtime))
    percent = _finite(_number(arguments[1], "percentile", position, runtime), "percentile", position)
    if not 0 <= percent <= 100:
        raise error("E308", "Math range error", "percentile() percent must be between 0 and 100.", position, expected="0..100", actual=str(percent))
    rank = (len(values) - 1) * percent / 100
    lower = math.floor(rank); upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    fraction = rank - lower
    return _finite_result(values[lower] + (values[upper] - values[lower]) * fraction, "percentile", position)


def _moving_average(arguments, named, position, runtime):
    values = _number_list(arguments[0], "moving_average", position, runtime)
    window = _integer(arguments[1], "moving_average", position, runtime)
    if not 1 <= window <= len(values):
        raise error("E308", "Math range error", "moving_average() window must be between 1 and the list length.", position, expected=f"1..{len(values)}", actual=str(window))
    return [sum(values[index:index + window]) / window for index in range(len(values) - window + 1)]


def _base(value, name, position, runtime):
    base = _integer(value, name, position, runtime)
    if not 2 <= base <= len(BASE_DIGITS):
        raise error("E308", "Math range error", f"{name}() base must be between 2 and {len(BASE_DIGITS)}.", position, expected=f"2..{len(BASE_DIGITS)}", actual=str(base))
    return base


def _convert_number_to_base(value, base_value, name, position, runtime):
    value = _integer(value, name, position, runtime)
    base = _base(base_value, name, position, runtime)
    if value == 0:
        return "0"
    negative = value < 0; remaining = abs(value); digits = []
    while remaining:
        remaining, digit = divmod(remaining, base)
        digits.append(BASE_DIGITS[digit])
    return ("-" if negative else "") + "".join(reversed(digits))


def _number_to_base(arguments, named, position, runtime):
    return _convert_number_to_base(arguments[0], arguments[1], "number_to_base", position, runtime)


def _convert_base_to_number(text, base_value, name, position, runtime):
    if type(text) is not str:
        runtime.type_error(position, "string", runtime.type_name(text), f"{name}() requires text as its first argument.")
    base = _base(base_value, name, position, runtime)
    negative = text.startswith("-"); digits = text[1:] if negative else text
    valid = digits and not digits.startswith("_") and not digits.endswith("_") and "__" not in digits
    normalized = digits.replace("_", "").lower()
    valid = valid and all(character in BASE_DIGITS[:base] for character in normalized)
    if not valid:
        raise error("E304", "Conversion error", f"{name}() text is not a valid base-{base} integer.", position, actual=repr(text))
    value = int(normalized, base)
    return -value if negative else value


def _base_to_number(arguments, named, position, runtime):
    return _convert_base_to_number(arguments[0], arguments[1], "base_to_number", position, runtime)


def _fixed_number_to_base(name, base):
    def call(arguments, named, position, runtime):
        return _convert_number_to_base(arguments[0], base, name, position, runtime)
    return call


def _fixed_base_to_number(name, base):
    def call(arguments, named, position, runtime):
        return _convert_base_to_number(arguments[0], base, name, position, runtime)
    return call


MATH_BUILTINS = tuple(
    UtilityFunction(name, minimum, maximum, implementation)
    for name, minimum, maximum, implementation in (
        ("absolute", 1, 1, _unary("absolute", abs)),
        ("minimum", 1, 64, _minimum_or_maximum("minimum", min)),
        ("maximum", 1, 64, _minimum_or_maximum("maximum", max)),
        ("round", 1, 2, _round),
        ("truncate", 1, 1, _unary("truncate", math.trunc)),
        ("clamp", 3, 3, _clamp),
        ("sign", 1, 1, _sign),
        ("square_root", 1, 1, _unary("square_root", math.sqrt)),
        ("cube_root", 1, 1, _cube_root),
        ("power", 2, 2, _power),
        ("hypotenuse", 2, 2, _binary("hypotenuse", math.hypot)),
        ("exponential", 1, 1, _unary("exponential", math.exp)),
        ("exponential_base2", 1, 1, _unary("exponential_base2", lambda value: 2.0 ** value)),
        ("natural_log", 1, 1, _unary("natural_log", math.log)),
        ("log_base2", 1, 1, _unary("log_base2", math.log2)),
        ("log_base10", 1, 1, _unary("log_base10", math.log10)),
        ("log_one_plus", 1, 1, _unary("log_one_plus", math.log1p)),
        ("arc_sin", 1, 1, _unary("arc_sin", math.asin)),
        ("arc_cos", 1, 1, _unary("arc_cos", math.acos)),
        ("arc_tan", 1, 1, _unary("arc_tan", math.atan)),
        ("arc_tan2", 2, 2, _binary("arc_tan2", math.atan2)),
        ("sinh", 1, 1, _unary("sinh", math.sinh)),
        ("cosh", 1, 1, _unary("cosh", math.cosh)),
        ("tanh", 1, 1, _unary("tanh", math.tanh)),
        ("arc_sinh", 1, 1, _unary("arc_sinh", math.asinh)),
        ("arc_cosh", 1, 1, _unary("arc_cosh", math.acosh)),
        ("arc_tanh", 1, 1, _unary("arc_tanh", math.atanh)),
        ("to_radians", 1, 1, _unary("to_radians", math.radians)),
        ("to_degrees", 1, 1, _unary("to_degrees", math.degrees)),
        ("greatest_common_divisor", 2, 2, _integer_pair("greatest_common_divisor", math.gcd)),
        ("least_common_multiple", 2, 2, _integer_pair("least_common_multiple", math.lcm)),
        ("factorial", 1, 1, _factorial),
        ("is_finite", 1, 1, _predicate("is_finite", lambda value: type(value) is int or math.isfinite(value))),
        ("is_infinite", 1, 1, _predicate("is_infinite", lambda value: type(value) is float and math.isinf(value))),
        ("is_nan", 1, 1, _predicate("is_nan", lambda value: type(value) is float and math.isnan(value))),
        ("is_close", 2, 2, _is_close),
        ("is_integer_value", 1, 1, _predicate("is_integer_value", lambda value: type(value) is int or math.isfinite(value) and value.is_integer())),
        ("median", 1, 1, _statistic("median", statistics.median)),
        ("variance", 1, 1, _statistic("variance", statistics.pvariance)),
        ("sample_variance", 1, 1, _statistic("sample_variance", statistics.variance, 2)),
        ("standard_deviation", 1, 1, _statistic("standard_deviation", statistics.pstdev)),
        ("sample_standard_deviation", 1, 1, _statistic("sample_standard_deviation", statistics.stdev, 2)),
        ("percentile", 2, 2, _percentile),
        ("moving_average", 2, 2, _moving_average),
        ("number_to_binary", 1, 1, _fixed_number_to_base("number_to_binary", 2)),
        ("number_to_octal", 1, 1, _fixed_number_to_base("number_to_octal", 8)),
        ("number_to_hexadecimal", 1, 1, _fixed_number_to_base("number_to_hexadecimal", 16)),
        ("binary_to_number", 1, 1, _fixed_base_to_number("binary_to_number", 2)),
        ("octal_to_number", 1, 1, _fixed_base_to_number("octal_to_number", 8)),
        ("hexadecimal_to_number", 1, 1, _fixed_base_to_number("hexadecimal_to_number", 16)),
        ("number_to_base", 2, 2, _number_to_base),
        ("base_to_number", 2, 2, _base_to_number),
    )
)
