"""AWS Lambda execution boundary for Separan applications.

The Lambda bootstrap remains a small Python host adapter; application decisions
live in a .sep file and are evaluated by the regular Separan interpreter.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .cli import create_application


def value_from_host(value):
    """Convert JSON-shaped host data to immutable Separan values."""
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, bytes):
        return BytesValue(value)
    if isinstance(value, (list, tuple)):
        return [value_from_host(item) for item in value]
    if isinstance(value, dict):
        return ObjectValue.create({str(key): value_from_host(item) for key, item in value.items()})
    raise TypeError(f"Unsupported host value: {type(value).__name__}")


def value_to_host(value):
    """Convert a Separan value to a JSON-compatible host value."""
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, BytesValue):
        return value.value
    if type(value) is list:
        return [value_to_host(item) for item in value]
    if isinstance(value, ObjectValue):
        return {key: value_to_host(item) for key, item in value.fields.items()}
    raise TypeError(f"Separan value '{type(value).__name__}' cannot cross the Lambda boundary")


@dataclass(frozen=True)
class HostFunction:
    """A named, arity-checked function supplied by the Lambda host."""

    name: str
    minimum_arguments: int
    maximum_arguments: int
    implementation: Callable
    allow_named_arguments: bool = False

    def call(self, arguments, position, runtime, named=None):
        named = dict(named or {})
        if named and not self.allow_named_arguments:
            raise error(
                "E207", "Unsupported named argument",
                f"Host function '{self.name}' does not accept named arguments.",
                position, actual=next(iter(named)),
            )
        count = len(arguments)
        if not self.minimum_arguments <= count <= self.maximum_arguments:
            expected = (
                str(self.minimum_arguments)
                if self.minimum_arguments == self.maximum_arguments
                else f"{self.minimum_arguments}..{self.maximum_arguments}"
            )
            raise error(
                "E207", "Argument count mismatch",
                f"Host function '{self.name}' requires {expected} positional argument(s).",
                position, expected=expected, actual=str(count),
            )
        host_arguments = [value_to_host(value) for value in arguments]
        host_named = {key: value_to_host(value) for key, value in named.items()}
        try:
            result = self.implementation(host_arguments, host_named)
        except Exception as exc:
            raise error(
                "E980", "Lambda host error",
                f"Host function '{self.name}' failed: {exc}", position,
                actual=type(exc).__name__,
            ) from exc
        return value_from_host(result)


def _context_value(context):
    if context is None:
        return ObjectValue.create({})
    fields = {}
    for name in (
        "aws_request_id", "function_name", "function_version",
        "invoked_function_arn", "log_group_name", "log_stream_name",
        "memory_limit_in_mb",
    ):
        value = getattr(context, name, None)
        if value is not None:
            fields[name] = value_from_host(value)
    deadline = getattr(context, "get_remaining_time_in_millis", None)
    if callable(deadline):
        fields["remaining_time_milliseconds"] = int(deadline())
    return ObjectValue.create(fields)


class LambdaApplication:
    """A parsed Separan application reused for the lifetime of a Lambda worker."""

    def __init__(self, source, filename="application.sep", handler="handler", host_functions=None):
        self.handler_name = handler
        self.runtime = create_application(
            source,
            filename,
            script_path=filename,
            host_functions=host_functions,
        )

    def handle(self, event, context=None):
        result = self.runtime.invoke(
            self.handler_name,
            [value_from_host(event), _context_value(context)],
        )
        return value_to_host(result)


_APPLICATIONS = {}


def load_application(source_path=None, handler=None, host_functions=None):
    path = Path(source_path or os.environ.get("SEPARAN_SOURCE_PATH", "application.sep"))
    selected_handler = handler or os.environ.get("SEPARAN_HANDLER", "handler")
    cache_key = (str(path.resolve()), selected_handler, id(host_functions))
    application = _APPLICATIONS.get(cache_key)
    if application is None:
        application = LambdaApplication(
            path.read_text(encoding="utf-8"),
            str(path),
            selected_handler,
            host_functions,
        )
        _APPLICATIONS[cache_key] = application
    return application


def create_lambda_handler(source_path=None, handler=None, host_functions=None):
    """Return an AWS-compatible handler with cold-start application caching."""
    def lambda_handler(event, context):
        application = load_application(source_path, handler, host_functions)
        return application.handle(event, context)
    return lambda_handler


def json_result(value):
    """Stable JSON rendering used by runtime tests and non-AWS adapters."""
    return json.dumps(value_to_host(value), ensure_ascii=False, separators=(",", ":"))
