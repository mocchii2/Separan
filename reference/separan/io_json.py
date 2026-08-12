"""Capability-gated high-level file I/O and deterministic JSON conversion."""

import json
import os
import tempfile
import shutil

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue


def _path(arguments, name, position, runtime, write=False):
    capability = runtime.capabilities
    capability.require(capability.write_files if write else capability.read_files, name, position)
    return capability.path(arguments[0], name, position)


def read_text(arguments, position, runtime):
    path = _path(arguments, "read_text", position, runtime)
    try: return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc: raise error("E722", "I/O error", str(exc), position, actual=arguments[0])


def read_bytes(arguments, position, runtime):
    path = _path(arguments, "read_bytes", position, runtime)
    try: return BytesValue(path.read_bytes())
    except OSError as exc: raise error("E722", "I/O error", str(exc), position, actual=arguments[0])


def _atomic_write(path, data, position):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".separan-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data); stream.flush()
        os.replace(temporary, path); temporary = None
    except OSError as exc: raise error("E723", "I/O error", str(exc), position, actual=str(path))
    finally:
        if temporary:
            try: os.unlink(temporary)
            except OSError: pass


def write_text(arguments, position, runtime):
    path = _path(arguments, "write_text", position, runtime, True); value = arguments[1]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "write_text() value must be a string.")
    _atomic_write(path, value.encode("utf-8"), position); return None


def append_text(arguments, position, runtime):
    path = _path(arguments, "append_text", position, runtime, True); value = arguments[1]
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), "append_text() value must be a string.")
    try:
        previous = path.read_bytes() if path.exists() else b""
        previous.decode("utf-8")
    except (OSError, UnicodeError) as exc: raise error("E723", "I/O error", str(exc), position, actual=arguments[0])
    _atomic_write(path, previous + value.encode("utf-8"), position); return None


def write_bytes(arguments, position, runtime):
    path = _path(arguments, "write_bytes", position, runtime, True); value = arguments[1]
    if not isinstance(value, BytesValue): runtime.type_error(position, "bytes", runtime.type_name(value), "write_bytes() value must be bytes.")
    _atomic_write(path, value.value, position); return None


def _discover(arguments, name, position, runtime):
    runtime.capabilities.require(runtime.capabilities.discover_paths, name, position)
    return runtime.capabilities.path(arguments[0], name, position)


def file_exists(arguments, position, runtime): return _discover(arguments, "file_exists", position, runtime).is_file()
def directory_exists(arguments, position, runtime): return _discover(arguments, "directory_exists", position, runtime).is_dir()


def file_size(arguments, position, runtime):
    path = _path(arguments, "file_size", position, runtime)
    try:
        if not path.is_file(): raise OSError("path is not a regular file")
        return path.stat().st_size
    except OSError as exc: raise error("E722", "I/O error", str(exc), position, actual=arguments[0])


def read_lines(arguments, position, runtime): return read_text(arguments, position, runtime).splitlines()


def _source_destination(arguments, name, position, runtime):
    runtime.capabilities.require(runtime.capabilities.read_files, f"{name} source", position)
    runtime.capabilities.require(runtime.capabilities.write_files, f"{name} destination", position)
    source = runtime.capabilities.path(arguments[0], name, position); destination = runtime.capabilities.path(arguments[1], name, position)
    if not source.is_file(): raise error("E722", "I/O error", f"{name} source is not a regular file.", position, actual=arguments[0])
    if destination.exists(): raise error("E725", "Destination exists", f"{name} does not overwrite an existing destination.", position, actual=arguments[1])
    return source, destination


def copy_file(arguments, position, runtime):
    source, destination = _source_destination(arguments, "copy_file", position, runtime)
    try: destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination)
    except OSError as exc: raise error("E723", "I/O error", str(exc), position, actual=arguments[1])
    return None


def move_file(arguments, position, runtime):
    source, destination = _source_destination(arguments, "move_file", position, runtime)
    try: destination.parent.mkdir(parents=True, exist_ok=True); shutil.move(source, destination)
    except OSError as exc: raise error("E723", "I/O error", str(exc), position, actual=arguments[1])
    return None


def delete_file(arguments, position, runtime):
    path = _path(arguments, "delete_file", position, runtime, True)
    try:
        if not path.is_file(): raise OSError("path is not a regular file")
        path.unlink()
    except OSError as exc: raise error("E723", "I/O error", str(exc), position, actual=arguments[0])
    return None


def create_directory(arguments, position, runtime):
    path = _path(arguments, "create_directory", position, runtime, True)
    try: path.mkdir(parents=True, exist_ok=False)
    except OSError as exc: raise error("E723", "I/O error", str(exc), position, actual=arguments[0])
    return None


def delete_directory(arguments, position, runtime):
    path = _path(arguments, "delete_directory", position, runtime, True)
    try: path.rmdir()
    except OSError as exc: raise error("E723", "I/O error", "delete_directory() removes only an existing empty directory: " + str(exc), position, actual=arguments[0])
    return None


def list_directory(arguments, position, runtime):
    path = _discover(arguments, "list_directory", position, runtime)
    try:
        if not path.is_dir(): raise OSError("path is not a directory")
        return sorted(item.name for item in path.iterdir())
    except OSError as exc: raise error("E722", "I/O error", str(exc), position, actual=arguments[0])


def file_name(arguments, position, runtime): return _discover(arguments, "file_name", position, runtime).name
def file_extension(arguments, position, runtime): return _discover(arguments, "file_extension", position, runtime).suffix.removeprefix(".")
def parent_directory(arguments, position, runtime):
    path = _discover(arguments, "parent_directory", position, runtime)
    try: return "." if path.parent == runtime.capabilities.root else path.parent.relative_to(runtime.capabilities.root).as_posix()
    except ValueError: raise error("E721", "Capability root escape", "Parent directory escapes the capability root.", position, actual=arguments[0])
def absolute_path(arguments, position, runtime): return str(_discover(arguments, "absolute_path", position, runtime))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _from_json(value, position):
    if isinstance(value, dict): return ObjectValue.create({key: _from_json(item, position) for key, item in value.items()})
    if type(value) is list:
        result = [_from_json(item, position) for item in value]
        from .interpreter import list_element_type
        list_element_type(result, position); return result
    if value is None or type(value) in (str, bool, int, float): return value
    raise error("E740", "JSON error", "JSON contains an unsupported value.", position)


def json_decode(arguments, position, runtime):
    text = arguments[0]
    if type(text) is not str: runtime.type_error(position, "string", runtime.type_name(text), "json_decode() requires a string.")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite number: {value}")))
        return _from_json(value, position)
    except (json.JSONDecodeError, ValueError) as exc: raise error("E740", "JSON parse error", str(exc), position)


def _to_json(value, position):
    if isinstance(value, ObjectValue): return {key: _to_json(value.fields[key], position) for key in sorted(value.fields)}
    if type(value) is list: return [_to_json(item, position) for item in value]
    if value is None or type(value) in (str, bool, int): return value
    if type(value) is float:
        import math
        if not math.isfinite(value): raise error("E741", "JSON encode error", "JSON cannot encode a non-finite number.", position)
        return value
    raise error("E741", "JSON encode error", f"Type '{runtime_type(value)}' is not JSON-compatible.", position)


def runtime_type(value): return type(value).__name__


def json_encode(arguments, position, runtime):
    value = _to_json(arguments[0], position)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
