"""Immutable Separan object values and their non-mutating API."""

from dataclasses import dataclass
from types import MappingProxyType

from .errors import error


@dataclass(frozen=True)
class ObjectValue:
    fields: object

    @classmethod
    def create(cls, fields): return cls(MappingProxyType(dict(fields)))


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
    result = dict(value.fields); result[key] = field; return ObjectValue.create(result)


def object_remove(arguments, position, runtime):
    value = require_object(arguments[0], "object_remove", position, runtime); key = arguments[1]
    if type(key) is not str: runtime.type_error(position, "string key", runtime.type_name(key), "object_remove() key must be a string.")
    if key not in value.fields: raise error("E212", "Missing object field", f"Object field '{key}' does not exist.", position, actual=key)
    result = dict(value.fields); del result[key]; return ObjectValue.create(result)


def object_keys(arguments, position, runtime): return sorted(require_object(arguments[0], "object_keys", position, runtime).fields)
def object_values(arguments, position, runtime):
    value = require_object(arguments[0], "object_values", position, runtime)
    return [value.fields[key] for key in sorted(value.fields)]
