"""Non-mutating list operations for Separan."""

from .errors import error


def require_list(value, function, position, runtime):
    if type(value) is not list:
        runtime.type_error(position, "list", runtime.type_name(value), f"{function}() requires a list.")


def require_index(value, function, position, runtime):
    if type(value) is not int or value < 0:
        runtime.type_error(position, "non-negative integer", repr(value), f"{function}() indexes must be non-negative integers.")


def _element_type(values, runtime):
    return None if not values else runtime.type_name(values[0])


def _compatible_search(values, value, function, position, runtime):
    expected = _element_type(values, runtime)
    actual = runtime.type_name(value)
    if expected is not None and expected != "null" and value is not None and expected != actual:
        runtime.type_error(position, expected, actual, f"{function}() search value must match the list element type.")


def list_append(arguments, position, runtime):
    values, value = arguments
    require_list(values, "list_append", position, runtime)
    expected = _element_type(values, runtime)
    actual = runtime.type_name(value)
    if expected is not None and expected != actual:
        runtime.type_error(position, expected, actual, "list_append() value must match the list element type.")
    return [*values, value]


def prepend(arguments, position, runtime):
    values, value = arguments
    require_list(values, "prepend", position, runtime)
    expected = _element_type(values, runtime); actual = runtime.type_name(value)
    if expected is not None and expected != actual:
        runtime.type_error(position, expected, actual, "prepend() value must match the list element type.")
    return [value, *values]


def list_remove(arguments, position, runtime):
    values, value = arguments
    require_list(values, "list_remove", position, runtime)
    _compatible_search(values, value, "list_remove", position, runtime)
    try:
        index = values.index(value)
    except ValueError:
        raise error("E604", "List value not found", "list_remove() removes the first matching value, but no match exists.", position, actual=runtime.display(value))
    return values[:index] + values[index + 1:]


def remove_at(arguments, position, runtime):
    values, index = arguments
    require_list(values, "remove_at", position, runtime); require_index(index, "remove_at", position, runtime)
    if index >= len(values):
        raise error("E603", "List index out of range", "remove_at() index must be smaller than the list length.", position, expected=f"0..{len(values) - 1}", actual=str(index))
    return values[:index] + values[index + 1:]


def unique(arguments, position, runtime):
    values = arguments[0]; require_list(values, "unique", position, runtime); result = []
    for value in values:
        if value not in result: result.append(value)
    return result


def size(arguments, position, runtime):
    values = arguments[0]; require_list(values, "size", position, runtime); return len(values)


def first(arguments, position, runtime):
    values = arguments[0]; require_list(values, "first", position, runtime)
    if not values:
        raise error("E602", "Empty list access", "first() cannot read from an empty list.", position, expected="non-empty list", actual="[]")
    return values[0]


def last(arguments, position, runtime):
    values = arguments[0]; require_list(values, "last", position, runtime)
    if not values:
        raise error("E602", "Empty list access", "last() cannot read from an empty list.", position, expected="non-empty list", actual="[]")
    return values[-1]


def contains(arguments, position, runtime):
    values, value = arguments
    require_list(values, "contains", position, runtime)
    _compatible_search(values, value, "contains", position, runtime)
    return value in values


def index_of(arguments, position, runtime):
    values, value = arguments
    require_list(values, "index_of", position, runtime)
    _compatible_search(values, value, "index_of", position, runtime)
    try:
        return values.index(value)
    except ValueError:
        return None


def last_index_of(arguments, position, runtime):
    values, value = arguments
    require_list(values, "last_index_of", position, runtime)
    _compatible_search(values, value, "last_index_of", position, runtime)
    for index in range(len(values) - 1, -1, -1):
        if values[index] == value:
            return index
    return None


def slice_list(arguments, position, runtime):
    values, start, end = arguments
    require_list(values, "slice", position, runtime)
    require_index(start, "slice", position, runtime); require_index(end, "slice", position, runtime)
    if start > end or end > len(values):
        raise error("E603", "Invalid list range", "slice() requires 0 <= start <= end <= list length.", position, expected=f"0 <= start <= end <= {len(values)}", actual=f"start={start}, end={end}")
    return values[start:end]


def reverse(arguments, position, runtime):
    values = arguments[0]; require_list(values, "reverse", position, runtime); return list(reversed(values))


def sort_list(arguments, position, runtime):
    values = arguments[0]; require_list(values, "sort", position, runtime)
    element_type = _element_type(values, runtime)
    if element_type not in (None, "number", "string"):
        runtime.type_error(position, "list[number] or list[string]", f"list[{element_type}]", "sort() supports only number and string lists.")
    return sorted(values)
