"""Deterministic regex, glob, environment, and command-line built-ins."""

from dataclasses import dataclass
from pathlib import Path, PurePath
import os
import re

from .errors import error


MAX_REGEX_PATTERN = 4096
MAX_REGEX_INPUT = 1_048_576


@dataclass(frozen=True)
class RegexMatchValue:
    text: str
    start: int
    end: int
    groups: tuple


class UtilityFunction:
    def __init__(self, name, minimum, maximum, implementation, named=()):
        self.name, self.minimum_arguments, self.maximum_arguments = name, minimum, maximum
        self.implementation, self.named = implementation, frozenset(named)

    def call(self, arguments, position, runtime, named=None):
        named = named or {}
        unknown = set(named) - self.named
        if unknown:
            value = sorted(unknown)[0]
            raise error("E207", "Unknown named argument", f"{self.name}() does not accept named argument '{value}'.", position, actual=value)
        if not self.minimum_arguments <= len(arguments) <= self.maximum_arguments:
            expected = str(self.minimum_arguments) if self.minimum_arguments == self.maximum_arguments else f"{self.minimum_arguments}..{self.maximum_arguments}"
            raise error("E207", "Argument count mismatch", f"Built-in function '{self.name}' requires {expected} positional argument(s).", position, expected=expected, actual=str(len(arguments)))
        return self.implementation(arguments, named, position, runtime)


def _strings(name, values, position, runtime):
    for index, value in enumerate(values, 1):
        if type(value) is not str:
            runtime.type_error(position, "string", f"argument {index}: {runtime.type_name(value)}", f"{name}() accepts string arguments.")


def _flag_options(named, position, runtime):
    flags = 0
    for name, flag in (("ignore_case", re.IGNORECASE), ("multiline", re.MULTILINE), ("dot_all", re.DOTALL)):
        value = named.get(name, False)
        if type(value) is not bool:
            runtime.type_error(position, "boolean named flags", runtime.type_name(value), f"{name} must be boolean.")
        if value: flags |= flag
    return flags


def _compile(pattern, value, named, position, runtime):
    _strings("regex", (pattern, value), position, runtime)
    if len(pattern) > MAX_REGEX_PATTERN or len(value) > MAX_REGEX_INPUT:
        raise error("E832", "Regex size limit", "Regex pattern or input exceeds the deterministic processing limit.", position)
    try: return re.compile(pattern, _flag_options(named, position, runtime))
    except re.error as exc:
        raise error("E830", "Regex error", str(exc), position, actual=pattern)


def _match_value(match):
    return RegexMatchValue(match.group(0), match.start(), match.end(), tuple(match.groups()))


def _regex_boolean(full):
    def impl(args, named, position, runtime):
        pattern, value = args; compiled = _compile(pattern, value, named, position, runtime)
        return (compiled.fullmatch(value) if full else compiled.search(value)) is not None
    return impl


def _regex_find(args, named, position, runtime):
    pattern, value = args; found = _compile(pattern, value, named, position, runtime).search(value)
    return None if found is None else _match_value(found)


def _regex_find_all(args, named, position, runtime):
    pattern, value = args
    return [_match_value(found) for found in _compile(pattern, value, named, position, runtime).finditer(value)]


def _replacement(value, position):
    # Separan uses $n; Python's engine uses \g<n>.
    out, index = [], 0
    while index < len(value):
        if value[index] != "$": out.append(value[index]); index += 1; continue
        if index + 1 < len(value) and value[index + 1] == "$": out.append("$"); index += 2; continue
        end = index + 1
        while end < len(value) and value[end].isdigit(): end += 1
        if end == index + 1: raise error("E831", "Invalid regex replacement", "A '$' must be followed by '$' or a capture number.", position, actual=value)
        out.append(r"\g<" + value[index + 1:end] + ">")
        index = end
    return "".join(out)


def _regex_replace(args, named, position, runtime):
    pattern, replacement, value = args; _strings("regex_replace", args, position, runtime)
    compiled = _compile(pattern, value, named, position, runtime)
    try: return compiled.sub(_replacement(replacement, position), value)
    except (re.error, IndexError) as exc: raise error("E831", "Invalid regex replacement", str(exc), position, actual=replacement)


def _regex_split(args, named, position, runtime):
    pattern, value = args; compiled = _compile(pattern, value, named, position, runtime)
    if compiled.search("") is not None: raise error("E833", "Empty regex delimiter", "regex_split() pattern cannot match an empty string.", position, actual=pattern)
    return compiled.split(value)


def _require_match(args, name, position, runtime):
    value = args[0]
    if not isinstance(value, RegexMatchValue): runtime.type_error(position, "regex_match_result", runtime.type_name(value), f"{name}() requires a regex match result.")
    return value


def _regex_text(args, named, position, runtime): return _require_match(args, "regex_text", position, runtime).text
def _regex_start(args, named, position, runtime): return _require_match(args, "regex_start", position, runtime).start
def _regex_end(args, named, position, runtime): return _require_match(args, "regex_end", position, runtime).end


def _regex_group(args, named, position, runtime):
    match = _require_match(args, "regex_group", position, runtime); index = args[1]
    if type(index) is not int or index < 0: runtime.type_error(position, "non-negative integer", runtime.type_name(index), "regex_group() index must be a non-negative integer.")
    if index == 0: return match.text
    if index > len(match.groups): raise error("E834", "Regex group out of range", "The requested capture group does not exist.", position, expected=f"0..{len(match.groups)}", actual=str(index))
    return match.groups[index - 1]


def _glob(args, named, position, runtime):
    pattern = args[0]; _strings("glob", args, position, runtime)
    runtime.capabilities.require(runtime.capabilities.discover_paths, "discover paths", position)
    if Path(pattern).is_absolute() or ".." in PurePath(pattern.replace("\\", "/")).parts:
        raise error("E840", "Invalid glob pattern", "glob() requires a project-relative pattern without '..'.", position, actual=pattern)
    root = runtime.capabilities.root
    try:
        results = []
        for item in root.glob(pattern):
            resolved = item.resolve()
            if resolved != root and root not in resolved.parents:
                raise error("E841", "Glob root escape", "A glob result escaped the project root.", position, actual=str(item))
            results.append(item.relative_to(root).as_posix())
        return sorted(set(results))
    except (OSError, ValueError) as exc: raise error("E840", "Glob error", str(exc), position, actual=pattern)


def _environment_key(environment, name):
    if os.name != "nt": return name
    folded = name.casefold()
    return next((key for key in environment if key.casefold() == folded), name)


def _env_get(args, named, position, runtime):
    name = args[0]; _strings("env_get", args, position, runtime)
    runtime.capabilities.environment(name, False, position)
    if "default" in named and type(named["default"]) is not str:
        runtime.type_error(position, "string default", runtime.type_name(named["default"]), "env_get() default must be a string.")
    return runtime.environment_variables.get(_environment_key(runtime.environment_variables, name), named.get("default"))


def _env_exists(args, named, position, runtime): _strings("env_exists", args, position, runtime); runtime.capabilities.environment(args[0], False, position); return _environment_key(runtime.environment_variables, args[0]) in runtime.environment_variables
def _env_set(args, named, position, runtime):
    _strings("env_set", args, position, runtime); runtime.capabilities.environment(args[0], True, position); key = _environment_key(runtime.environment_variables, args[0]); runtime.environment_variables[key] = args[1]; return None
def _env_remove(args, named, position, runtime): _strings("env_remove", args, position, runtime); runtime.capabilities.environment(args[0], True, position); runtime.environment_variables.pop(_environment_key(runtime.environment_variables, args[0]), None); return None
def _command_args(args, named, position, runtime): return list(runtime.command_arguments)
def _script_path(args, named, position, runtime): return runtime.script_path


def _arg_exists(args, named, position, runtime):
    _strings("arg_exists", args, position, runtime); before = runtime.command_arguments[:runtime.command_arguments.index("--")] if "--" in runtime.command_arguments else runtime.command_arguments
    return any(name in before for name in args)


def _arg_value(args, named, position, runtime):
    name = args[0]; _strings("arg_value", args, position, runtime)
    if "default" in named and type(named["default"]) is not str:
        runtime.type_error(position, "string default", runtime.type_name(named["default"]), "arg_value() default must be a string.")
    before = runtime.command_arguments[:runtime.command_arguments.index("--")] if "--" in runtime.command_arguments else runtime.command_arguments
    found = []
    for index, value in enumerate(before):
        if value == name:
            if index + 1 >= len(before) or before[index + 1].startswith("-"):
                raise error("E860", "Missing option value", f"Option '{name}' requires a value.", position, actual=name)
            found.append(before[index + 1])
        elif value.startswith(name + "="): found.append(value[len(name) + 1:])
    if len(found) > 1: raise error("E861", "Repeated option", f"Option '{name}' may appear only once.", position, actual=name)
    return found[0] if found else named.get("default")


FLAGS = ("ignore_case", "multiline", "dot_all")
UTILITY_BUILTINS = (
    UtilityFunction("regex_match", 2, 2, _regex_boolean(True), FLAGS), UtilityFunction("regex_search", 2, 2, _regex_boolean(False), FLAGS),
    UtilityFunction("regex_find", 2, 2, _regex_find, FLAGS), UtilityFunction("regex_find_all", 2, 2, _regex_find_all, FLAGS),
    UtilityFunction("regex_replace", 3, 3, _regex_replace, FLAGS), UtilityFunction("regex_split", 2, 2, _regex_split, FLAGS),
    UtilityFunction("regex_text", 1, 1, _regex_text), UtilityFunction("regex_start", 1, 1, _regex_start), UtilityFunction("regex_end", 1, 1, _regex_end), UtilityFunction("regex_group", 2, 2, _regex_group),
    UtilityFunction("glob", 1, 1, _glob), UtilityFunction("env_get", 1, 1, _env_get, ("default",)), UtilityFunction("env_exists", 1, 1, _env_exists),
    UtilityFunction("env_set", 2, 2, _env_set), UtilityFunction("env_remove", 1, 1, _env_remove), UtilityFunction("command_args", 0, 0, _command_args),
    UtilityFunction("script_path", 0, 0, _script_path), UtilityFunction("arg_exists", 1, 32, _arg_exists), UtilityFunction("arg_value", 1, 1, _arg_value, ("default",)),
)
