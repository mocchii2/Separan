"""Capability-gated direct and shell process execution."""

from dataclasses import dataclass
from datetime import timedelta
import os
import subprocess
import time

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction
from .temporal import DurationValue


@dataclass(frozen=True)
class ExecResultValue:
    exit_code: int
    stdout: str | None
    stderr: str | None
    stdout_bytes: BytesValue
    stderr_bytes: BytesValue
    timed_out: bool
    duration: DurationValue
    command: str


OPTIONS = ("cwd", "timeout", "env", "inherit_env", "input", "encoding", "max_stdout_bytes", "max_stderr_bytes")


def _string_list(value, position, runtime):
    if type(value) is not list: runtime.type_error(position, "list<string>", runtime.type_name(value), "exec() arguments must be a list of strings.")
    for index, item in enumerate(value):
        if type(item) is not str or "\0" in item: runtime.type_error(position, "list<string> without NUL", f"argument {index}: {runtime.type_name(item)}", "exec() arguments must be strings without NUL.")


def _positive_integer(value, name, maximum, position, runtime):
    if type(value) is not int or value <= 0: runtime.type_error(position, "positive integer", runtime.type_name(value), f"{name} must be a positive integer.")
    if value > maximum: raise error("E805", "Process limit error", f"{name} exceeds the host capability limit.", position, expected=f"1..{maximum}", actual=str(value))
    return value


def _options(named, position, runtime):
    capability = runtime.capabilities
    cwd = capability.root
    if "cwd" in named: cwd = capability.path(named["cwd"], "process cwd", position)
    if not cwd.is_dir(): raise error("E803", "Invalid process cwd", "Process working directory does not exist.", position, actual=str(cwd))
    timeout = named.get("timeout", DurationValue(30_000))
    if not isinstance(timeout, DurationValue) or timeout.milliseconds <= 0: runtime.type_error(position, "positive duration", runtime.type_name(timeout), "Process timeout must be a positive duration.")
    if timeout.milliseconds > capability.max_process_timeout_ms: raise error("E805", "Process limit error", "Process timeout exceeds the host limit.", position, actual=str(timeout.milliseconds))
    encoding = named.get("encoding", "utf-8")
    if type(encoding) is not str: runtime.type_error(position, "string encoding", runtime.type_name(encoding), "Process encoding must be a string.")
    inherit = named.get("inherit_env", False)
    if type(inherit) is not bool: runtime.type_error(position, "boolean", runtime.type_name(inherit), "inherit_env must be boolean.")
    if inherit and not capability.inherit_process_environment: raise error("E800", "Permission error", "Host capability denies inherited process environment.", position)
    environment = dict(runtime.environment_variables) if inherit else {}
    additions = named.get("env")
    if additions is not None:
        if not isinstance(additions, ObjectValue): runtime.type_error(position, "object<string,string>", runtime.type_name(additions), "Process env must be an object.")
        for key, value in additions.fields.items():
            if type(value) is not str or "\0" in key or "\0" in value: runtime.type_error(position, "object<string,string> without NUL", runtime.type_name(value), "Process environment names and values must be strings without NUL.")
            environment[key] = value
    stdin = named.get("input")
    if stdin is None: input_bytes = b""
    elif type(stdin) is str: input_bytes = stdin.encode(encoding)
    elif isinstance(stdin, BytesValue): input_bytes = stdin.value
    else: runtime.type_error(position, "string, bytes, or null", runtime.type_name(stdin), "Process input has an invalid type.")
    stdout_limit = _positive_integer(named.get("max_stdout_bytes", capability.max_process_output_bytes), "max_stdout_bytes", capability.max_process_output_bytes, position, runtime)
    stderr_limit = _positive_integer(named.get("max_stderr_bytes", capability.max_process_output_bytes), "max_stderr_bytes", capability.max_process_output_bytes, position, runtime)
    return cwd, timeout.milliseconds / 1000, encoding, environment, input_bytes, stdout_limit, stderr_limit


def _run(command, argv, named, position, runtime, shell=False):
    cwd, timeout, encoding, environment, input_bytes, stdout_limit, stderr_limit = _options(named, position, runtime)
    started = time.monotonic(); timed_out = False
    try:
        process = subprocess.Popen(command if shell else [command, *argv], cwd=cwd, env=environment,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)
        try: stdout, stderr = process.communicate(input_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; process.kill(); stdout, stderr = process.communicate()
    except OSError as exc: raise error("E804", "Command spawn error", str(exc), position, actual=command)
    if len(stdout) > stdout_limit or len(stderr) > stderr_limit: raise error("E805", "Command limit error", "Captured process output exceeded its byte limit.", position)
    elapsed = int((time.monotonic() - started) * 1000)
    try: stdout_text = stdout.decode(encoding)
    except (UnicodeError, LookupError): stdout_text = None
    try: stderr_text = stderr.decode(encoding)
    except (UnicodeError, LookupError): stderr_text = None
    return ExecResultValue(process.returncode, stdout_text, stderr_text, BytesValue(stdout), BytesValue(stderr), timed_out, DurationValue(elapsed), command)


def _exec(checked):
    def implementation(arguments, named, position, runtime):
        command, argv = arguments; _string_list(argv, position, runtime)
        resolved = runtime.capabilities.command(command, position)
        if resolved is None: raise error("E802", "Command not found or denied", "Command is unavailable under the host capability.", position, actual=command)
        result = _run(resolved, argv, named, position, runtime)
        if checked and result.timed_out: raise error("E809", "command_timeout_error", "Command exceeded its timeout.", position, actual=resolved)
        if checked and result.exit_code != 0: raise error("E808", "command_error", f"Command exited with code {result.exit_code}.", position, actual=str(result.exit_code))
        return result
    return implementation


def _shell_exec(arguments, named, position, runtime):
    runtime.capabilities.require(runtime.capabilities.run_shell, "run shell", position)
    command = arguments[0]
    if type(command) is not str or not command or "\0" in command: runtime.type_error(position, "non-empty string", runtime.type_name(command), "shell_exec() requires a command string.")
    return _run(command, [], named, position, runtime, True)


def _command_exists(arguments, named, position, runtime):
    return runtime.capabilities.command(arguments[0], position) is not None


PROCESS_BUILTINS = (
    UtilityFunction("exec", 2, 2, _exec(False), OPTIONS), UtilityFunction("exec_checked", 2, 2, _exec(True), OPTIONS),
    UtilityFunction("shell_exec", 1, 1, _shell_exec, OPTIONS), UtilityFunction("command_exists", 1, 1, _command_exists),
)
