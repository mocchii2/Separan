"""Immutable Separan object values and their non-mutating API."""

from dataclasses import dataclass
from types import MappingProxyType

from .errors import error


@dataclass(frozen=True)
class ObjectValue:
    fields: object
    field_types: object

    @classmethod
    def create(cls, fields, field_types=None):
        inferred = {} if field_types is None else dict(field_types)
        return cls(MappingProxyType(dict(fields)), MappingProxyType(inferred))


def require_object(value, name, position, runtime):
    if not isinstance(value, ObjectValue):
        runtime.type_error(position, "object", runtime.type_name(value), f"{name}() requires an object.")
    return value


def object_get(arguments, position, runtime):
    value = require_object(arguments[0], "object_get", position, runtime); key = arguments[1]
    if type(key) is not str: runtime.type_error(position, "string key", runtime.type_name(key), "object_get() key must be a string.")
    if key not in value.fields: raise error("E212", "Missing object field", f"Object field '{key}' does not exist.", position, actual=key)
    return value.fields[key]


def object_has(arguments, position, runtime):
    value = require_object(arguments[0], "object_has", position, runtime); key = arguments[1]
    if type(key) is not str: runtime.type_error(position, "string key", runtime.type_name(key), "object_has() key must be a string.")
    return key in value.fields


def object_set(arguments, position, runtime):
    value = require_object(arguments[0], "object_set", position, runtime); key, field = arguments[1], arguments[2]
    if type(key) is not str: runtime.type_error(position, "string key", runtime.type_name(key), "object_set() key must be a string.")
    field_types = dict(value.field_types)
    expected = field_types.get(key)
    if expected is None and key in value.fields:
        expected = (runtime.type_name(value.fields[key]), None)
    field = runtime.prepare_object_field(key, expected, field, position, value.fields.get(key), key in value.fields)
    result = dict(value.fields); result[key] = field
    if expected is not None: field_types[key] = expected
    return ObjectValue.create(result, field_types)


def object_remove(arguments, position, runtime):
    value = require_object(arguments[0], "object_remove", position, runtime); key = arguments[1]
    if type(key) is not str: runtime.type_error(position, "string key", runtime.type_name(key), "object_remove() key must be a string.")
    if key not in value.fields: raise error("E212", "Missing object field", f"Object field '{key}' does not exist.", position, actual=key)
    result = dict(value.fields); del result[key]
    field_types = dict(value.field_types); field_types.pop(key, None)
    return ObjectValue.create(result, field_types)


def object_keys(arguments, position, runtime): return sorted(require_object(arguments[0], "object_keys", position, runtime).fields)
def object_values(arguments, position, runtime):
    value = require_object(arguments[0], "object_values", position, runtime)
    return [value.fields[key] for key in sorted(value.fields)]
