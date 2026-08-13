"""Strict higher-order and aggregate collection operations."""

from .errors import error


def _list(value, name, position, runtime):
    if type(value) is not list:
        runtime.type_error(position, "list", runtime.type_name(value), f"{name}() requires a list.")


def _same_type(expected, value, name, position, runtime):
    actual = runtime.type_name(value)
    if actual != expected:
        runtime.type_error(position, expected, actual, f"{name}() callback returned an inconsistent type.")


def map_list(arguments, position, runtime):
    values, callback = arguments
    _list(values, "map", position, runtime)
    runtime.validate_function_value(callback, position)
    result = [runtime.call_function_value(callback, [value], position) for value in values]
    runtime.validate_list(result, position)
    return result


def filter_list(arguments, position, runtime):
    values, predicate = arguments
    _list(values, "filter", position, runtime)
    runtime.validate_function_value(predicate, position)
    result = []
    for value in values:
        selected = runtime.call_function_value(predicate, [value], position)
        if type(selected) is not bool:
            runtime.type_error(position, "boolean", runtime.type_name(selected), "filter() predicate must return boolean.")
        if selected: result.append(value)
    return result


def reduce_list(arguments, position, runtime):
    values, callback, accumulator = arguments
    _list(values, "reduce", position, runtime)
    runtime.validate_function_value(callback, position)
    accumulator_type = runtime.type_name(accumulator)
    for value in values:
        next_value = runtime.call_function_value(callback, [accumulator, value], position)
        _same_type(accumulator_type, next_value, "reduce", position, runtime)
        accumulator = next_value
    return accumulator


def flatten(arguments, position, runtime):
    values = arguments[0]
    _list(values, "flatten", position, runtime)
    result = []
    for index, value in enumerate(values):
        if type(value) is not list:
            runtime.type_error(position, "list[list]", f"element {index}: {runtime.type_name(value)}", "flatten() removes exactly one list level.")
        result.extend(value)
    runtime.validate_list(result, position)
    return result


def sum_list(arguments, position, runtime):
    values = arguments[0]
    _list(values, "sum", position, runtime)
    if not all(runtime.is_number(value) for value in values):
        runtime.type_error(position, "list[number]", "list with non-number element", "sum() accepts only a number list.")
    return sum(values)


def average(arguments, position, runtime):
    values = arguments[0]
    _list(values, "average", position, runtime)
    if not values:
        raise error("E602", "Empty collection", "average() requires a non-empty number list.", position, expected="non-empty list[number]", actual="[]")
    if not all(runtime.is_number(value) for value in values):
        runtime.type_error(position, "list[number]", "list with non-number element", "average() accepts only a number list.")
    return sum(values) / len(values)


def count(arguments, position, runtime):
    values, search = arguments
    _list(values, "count", position, runtime)
    if values:
        expected, actual = runtime.type_name(values[0]), runtime.type_name(search)
        if expected != actual:
            runtime.type_error(position, expected, actual, "count() search value must match the list element type.")
    return values.count(search)
