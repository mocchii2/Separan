"""Stable, read-only execution context exposed as the reserved `system` value."""

import os
from pathlib import Path
import platform
import socket
from dataclasses import dataclass

from .objects import ObjectValue


VERSION = "0.2.0-alpha.10"
ENGINE = "python-reference"


@dataclass(frozen=True)
class SystemContextValue(ObjectValue):
    pass


def _os_name():
    name = platform.system().casefold()
    if name == "windows": return "windows"
    if name == "darwin": return "macos"
    if name == "linux": return "linux"
    return "unknown"


def _architecture():
    value = platform.machine().casefold().replace("-", "_")
    if value in ("amd64", "x86_64", "x64"): return "x86_64"
    if value in ("arm64", "aarch64"): return "arm64"
    if value in ("x86", "i386", "i486", "i586", "i686"): return "x86"
    return value or "unknown"


def build_system_context(script_path, arguments):
    script = None if script_path is None else Path(script_path).resolve()
    return SystemContextValue.create({
        "version": VERSION,
        "engine": ENGINE,
        "script_path": None if script is None else str(script),
        "script_name": None if script is None else script.name,
        "script_dir": None if script is None else str(script.parent),
        "working_dir": str(Path.cwd().resolve()),
        "os": _os_name(),
        "arch": _architecture(),
        "hostname": socket.gethostname(),
        "args": list(arguments),
        "arg_count": len(arguments),
        "pid": os.getpid(),
        "runtime": "python",
        "cpu_count": os.cpu_count() or 1,
    })
