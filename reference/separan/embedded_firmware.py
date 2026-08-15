"""Pico SDK firmware generation, compilation, and explicit UF2 flashing."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .ast_nodes import (
    Assignment,
    BinaryExpr,
    CallExpr,
    ConstDeclaration,
    ExpressionStmt,
    ForStmt,
    FunctionDecl,
    GroupExpr,
    IfStmt,
    IndexExpr,
    ListExpr,
    LiteralExpr,
    MemberCallExpr,
    MemberExpr,
    PrintErrorStmt,
    PrintStmt,
    Program,
    ReturnStmt,
    UnaryExpr,
    VariableExpr,
    WhileStmt,
)
from .embedded import BOARD_PROFILES, validate_embedded_program
from .errors import error


PICO_SDK_BOARDS = {
    "raspberry_pi_pico": "pico",
    "raspberry_pi_pico_2": "pico2",
}


@dataclass(frozen=True)
class FirmwareProject:
    board_id: str
    sdk_board: str
    target_name: str
    directory: Path
    source_file: Path
    cmake_file: Path
    manifest_file: Path
    position: object


@dataclass(frozen=True)
class FirmwareArtifacts:
    elf: Path
    uf2: Path
    hex: Path
    binary: Path | None


def generate_pico_project(program: Program, source: str, source_path: Path, board_id: str,
                          output_directory: Path) -> FirmwareProject:
    """Validate and emit a self-contained Pico SDK CMake source project."""
    profile = validate_embedded_program(program, board_id)
    position = next(
        (statement.position for statement in program.statements
         if isinstance(statement, FunctionDecl) and statement.name == "main"),
        program.statements[0].position if program.statements else program.position,
    )
    sdk_board = PICO_SDK_BOARDS.get(board_id)
    if sdk_board is None:
        raise error(
            "E966",
            "Firmware backend unavailable",
            "The first firmware backend supports Raspberry Pi Pico and Pico 2 targets only.",
            position,
            expected="raspberry_pi_pico or raspberry_pi_pico_2",
            actual=board_id,
        )

    target_name = _target_name(source_path.stem)
    emitter = _PicoCppEmitter(program, profile, target_name)
    cpp_source = emitter.generate()
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    source_file = output_directory / "separan_firmware.cpp"
    cmake_file = output_directory / "CMakeLists.txt"
    manifest_file = output_directory / "separan-firmware.json"
    source_file.write_text(cpp_source, encoding="utf-8", newline="\n")
    cmake_file.write_text(_cmake_project(target_name, sdk_board), encoding="utf-8", newline="\n")
    manifest = {
        "format": "separan-pico-firmware",
        "version": 1,
        "source": str(Path(source_path).resolve()),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "board": board_id,
        "pico_sdk_board": sdk_board,
        "mcu": profile.mcu,
        "target": target_name,
        "generated_files": [source_file.name, cmake_file.name],
        "expected_artifacts": [
            f"build/{target_name}.elf",
            f"build/{target_name}.uf2",
            f"build/{target_name}.hex",
        ],
    }
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return FirmwareProject(board_id, sdk_board, target_name, output_directory, source_file,
                           cmake_file, manifest_file, position)


def build_pico_project(project: FirmwareProject, *, sdk_path=None, toolchain_path=None,
                       cmake=None, ninja=None, build_type="Release") -> FirmwareArtifacts:
    """Configure and compile a generated project with the official Pico SDK."""
    sdk = _resolve_sdk_path(sdk_path, project.position)
    cmake_executable = _resolve_tool(cmake, "cmake", project.position)
    ninja_executable = _resolve_tool(ninja, "ninja", project.position)
    toolchain = _resolve_toolchain_path(toolchain_path, project.position)
    build_directory = project.directory / "build"
    configure = [
        str(cmake_executable),
        "-S", str(project.directory),
        "-B", str(build_directory),
        "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja_executable}",
        f"-DPICO_SDK_PATH={sdk}",
        f"-DPICO_BOARD={project.sdk_board}",
        f"-DCMAKE_BUILD_TYPE={build_type}",
    ]
    if toolchain is not None:
        configure.append(f"-DPICO_TOOLCHAIN_PATH={toolchain}")
    _run_firmware_tool(configure, project.directory, project.position, "Pico SDK configuration")
    _run_firmware_tool(
        [str(cmake_executable), "--build", str(build_directory), "--target", project.target_name],
        project.directory,
        project.position,
        "Pico SDK compilation",
    )
    artifacts = FirmwareArtifacts(
        build_directory / f"{project.target_name}.elf",
        build_directory / f"{project.target_name}.uf2",
        build_directory / f"{project.target_name}.hex",
        _optional_artifact(build_directory / f"{project.target_name}.bin"),
    )
    missing = [str(path) for path in (artifacts.elf, artifacts.uf2, artifacts.hex) if not path.is_file()]
    if missing:
        raise error(
            "E968",
            "Firmware artifacts missing",
            "The Pico SDK command completed but did not produce every required artifact.",
            project.position,
            expected="ELF, UF2, and HEX",
            actual=", ".join(missing),
        )
    return artifacts


def flash_uf2(uf2_file: Path, device_directory: Path, position=None) -> Path:
    """Copy one UF2 to an explicitly selected BOOTSEL mass-storage device."""
    position = position or _synthetic_position(str(uf2_file))
    uf2_file = Path(uf2_file).resolve()
    device_directory = Path(device_directory).resolve()
    if uf2_file.suffix.lower() != ".uf2" or not uf2_file.is_file():
        raise error("E969", "Invalid UF2 image", "flash requires an existing .uf2 firmware image.", position,
                    expected="existing .uf2 file", actual=str(uf2_file))
    if not device_directory.is_dir():
        raise error("E969", "Flash device unavailable", "The explicitly selected BOOTSEL device directory does not exist.", position,
                    expected="mounted Pico BOOTSEL directory", actual=str(device_directory))
    marker = device_directory / "INFO_UF2.TXT"
    try:
        marker_text = marker.read_text(encoding="utf-8", errors="replace") if marker.is_file() else ""
    except OSError:
        marker_text = ""
    if "UF2 Bootloader" not in marker_text and "Board-ID:" not in marker_text:
        raise error(
            "E969",
            "Flash device not recognized",
            "Separan will not copy firmware to a directory that does not identify itself as a UF2 BOOTSEL device.",
            position,
            expected="INFO_UF2.TXT containing UF2 Bootloader or Board-ID metadata",
            actual=str(device_directory),
        )
    destination = device_directory / uf2_file.name
    try:
        shutil.copyfile(uf2_file, destination)
    except OSError as exc:
        raise error("E969", "UF2 write failed", str(exc), position, actual=str(device_directory)) from exc
    return destination


def _optional_artifact(path):
    return path if path.is_file() else None


def _resolve_sdk_path(value, position):
    candidates = []
    if value:
        candidates.append(Path(value))
        environment = None
    else:
        environment = os.environ.get("PICO_SDK_PATH")
        if environment:
            candidates.append(Path(environment))
        sdk_root = Path.home() / ".pico-sdk" / "sdk"
        if sdk_root.is_dir():
            candidates.extend(sorted((path for path in sdk_root.iterdir() if path.is_dir()), reverse=True))
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (candidate / "pico_sdk_init.cmake").is_file() and (candidate / "external" / "pico_sdk_import.cmake").is_file():
            return candidate
    raise error(
        "E967",
        "Pico SDK is not installed",
        "Install the official Raspberry Pi Pico VS Code extension or pass --sdk-path.",
        position,
        expected="Pico SDK 2.0 or newer containing pico_sdk_init.cmake",
        actual=str(value or environment or "not found"),
    )


def _resolve_tool(value, name, position):
    if value:
        explicit = Path(value).expanduser()
        if explicit.is_file():
            return explicit.resolve()
        located = shutil.which(str(value))
        if located:
            return Path(located).resolve()
    else:
        located = shutil.which(name)
        if located:
            return Path(located).resolve()
        pico_root = Path.home() / ".pico-sdk"
        executable_names = (f"{name}.exe", name)
        if pico_root.is_dir():
            for executable_name in executable_names:
                matches = sorted(pico_root.rglob(executable_name), reverse=True)
                if matches:
                    return matches[0].resolve()
    raise error(
        "E967",
        "Firmware build tool is not installed",
        f"The '{name}' executable is required to compile Pico firmware.",
        position,
        expected=f"{name} on PATH or an explicit --{name} path",
        actual=str(value or "not found"),
    )


def _resolve_toolchain_path(value, position):
    if value:
        candidate = Path(value).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        raise error("E967", "Pico toolchain is not installed", "The explicit --toolchain-path directory does not exist.",
                    position, expected="existing Pico GCC toolchain root", actual=str(candidate))
    environment = os.environ.get("PICO_TOOLCHAIN_PATH")
    if environment:
        return Path(environment).expanduser().resolve()
    root = Path.home() / ".pico-sdk" / "toolchain"
    if root.is_dir():
        candidates = sorted((path for path in root.iterdir() if path.is_dir()), reverse=True)
        if candidates:
            return candidates[0].resolve()
    return None


def _run_firmware_tool(command, cwd, position, operation):
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise error("E968", f"{operation} failed", str(exc), position, actual=str(command[0])) from exc
    if result.returncode == 0:
        return
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    lines = output.splitlines()
    concise = "\n".join(lines[-40:]) if lines else f"Process exited with code {result.returncode}."
    raise error(
        "E968",
        f"{operation} failed",
        concise,
        position,
        expected="exit code 0",
        actual=str(result.returncode),
    )


def _target_name(stem):
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_").lower()
    if not normalized:
        normalized = "firmware"
    if normalized[0].isdigit():
        normalized = "app_" + normalized
    return "separan_" + normalized


def _cmake_project(target_name, sdk_board):
    return f"""cmake_minimum_required(VERSION 3.13...3.27)

set(PICO_BOARD {sdk_board} CACHE STRING "Separan firmware target board")

if(NOT PICO_SDK_PATH AND DEFINED ENV{{PICO_SDK_PATH}})
    set(PICO_SDK_PATH $ENV{{PICO_SDK_PATH}})
endif()
if(NOT PICO_SDK_PATH)
    message(FATAL_ERROR "PICO_SDK_PATH is required. Pass -DPICO_SDK_PATH=<path>.")
endif()

include(${{PICO_SDK_PATH}}/external/pico_sdk_import.cmake)

project({target_name} C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()
if(PICO_SDK_VERSION_STRING VERSION_LESS "2.0.0")
    message(FATAL_ERROR "Separan Pico firmware requires Pico SDK 2.0.0 or newer.")
endif()

add_executable({target_name} separan_firmware.cpp)
target_link_libraries({target_name}
    pico_stdlib
    hardware_adc
    hardware_i2c
    hardware_pwm
    hardware_uart
)
pico_enable_stdio_usb({target_name} 1)
pico_enable_stdio_uart({target_name} 0)
pico_add_extra_outputs({target_name})
"""


class _PicoCppEmitter:
    def __init__(self, program, profile, target_name):
        self.program = program
        self.profile = profile
        self.target_name = target_name
        self.lines = []
        self.indent = 0
        self.scopes = []
        self.functions = {statement.name: statement for statement in program.statements if isinstance(statement, FunctionDecl)}

    def generate(self):
        main = self.functions.get("main")
        if main is None:
            self._unsupported(self.program, "Embedded firmware requires function:main.")
        if main.parameters:
            self._unsupported(main, "Embedded function:main cannot accept parameters.")
        self.lines.extend(_PICO_RUNTIME.rstrip().splitlines())
        self.lines.append("")
        global_statements = [statement for statement in self.program.statements if not isinstance(statement, FunctionDecl)]
        self.scopes = [{}]
        for statement in global_statements:
            if self._is_board_selection(statement):
                continue
            if isinstance(statement, (Assignment, ConstDeclaration)):
                value = self._expression(statement.value)
                name = self._declare(statement.name)
                qualifier = "const " if isinstance(statement, ConstDeclaration) else ""
                self._line(f"{qualifier}auto {name} = {value};")
            else:
                self._unsupported(statement, "Only constant global values and board_select() are supported in Pico firmware.")
        if global_statements:
            self.lines.append("")
        for function in self._ordered_functions():
            self._function(function)
            self.lines.append("")
        return "\n".join(self.lines).rstrip() + "\n"

    def _ordered_functions(self):
        ordered = []
        visiting = set()
        visited = set()

        def visit(name):
            if name in visited:
                return
            if name in visiting:
                self._unsupported(self.functions[name], "Recursive functions are not supported by the Pico firmware preview.")
            visiting.add(name)
            for dependency in sorted(self._called_functions(self.functions[name])):
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(self.functions[name])

        for name in sorted(self.functions, key=lambda item: item == "main"):
            visit(name)
        return ordered

    def _called_functions(self, function):
        result = set()

        def walk(value):
            if isinstance(value, CallExpr) and value.callee in self.functions:
                result.add(value.callee)
            if is_dataclass(value):
                for item in fields(value):
                    if item.name != "position":
                        walk(getattr(value, item.name))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)

        walk(function.body)
        return result

    def _function(self, function):
        self.scopes.append({})
        parameters = []
        if function.parameters:
            template = ", ".join(f"typename SepT{index}" for index in range(len(function.parameters)))
            self._line(f"template <{template}>")
            for index, parameter in enumerate(function.parameters):
                name = self._declare(parameter)
                parameters.append(f"SepT{index} {name}")
        returns = self._contains_return(function.body)
        if function.name == "main":
            signature = "int main()"
        else:
            signature = f"{'auto' if returns else 'void'} sep_fn_{_identifier(function.name)}({', '.join(parameters)})"
        self._line(signature + " {")
        self.indent += 1
        if function.name == "main":
            self._line("stdio_init_all();")
        for statement in function.body:
            self._statement(statement, in_main=function.name == "main")
        if function.name == "main":
            self._line("return 0;")
        self.indent -= 1
        self._line("}")
        self.scopes.pop()

    def _statement(self, statement, *, in_main=False):
        if isinstance(statement, (Assignment, ConstDeclaration)):
            value = self._expression(statement.value)
            existing = self._lookup(statement.name)
            if existing is None:
                name = self._declare(statement.name)
                qualifier = "const " if isinstance(statement, ConstDeclaration) else ""
                self._line(f"{qualifier}auto {name} = {value};")
            elif isinstance(statement, ConstDeclaration):
                self._unsupported(statement, "A generated constant cannot shadow another local value.")
            else:
                self._line(f"{existing} = {value};")
            return
        if isinstance(statement, ExpressionStmt):
            self._line(self._expression(statement.expression) + ";")
            return
        if isinstance(statement, (PrintStmt, PrintErrorStmt)):
            self._line(f"sep_print({self._expression(statement.value)});")
            return
        if isinstance(statement, ReturnStmt):
            if in_main:
                if statement.value is None:
                    self._line("return 0;")
                else:
                    self._line(f"return static_cast<int>({self._expression(statement.value)});")
            else:
                suffix = "" if statement.value is None else " " + self._expression(statement.value)
                self._line(f"return{suffix};")
            return
        if isinstance(statement, WhileStmt):
            self._line(f"while ({self._expression(statement.condition)}) {{")
            self._block(statement.body, in_main)
            self._line("}")
            return
        if isinstance(statement, IfStmt):
            for index, branch in enumerate(statement.branches):
                prefix = "if" if index == 0 else "else if"
                self._line(f"{prefix} ({self._expression(branch.condition)}) {{")
                self._block(branch.body, in_main)
                self._line("}")
            if statement.else_body is not None:
                self._line("else {")
                self._block(statement.else_body, in_main)
                self._line("}")
            return
        if isinstance(statement, ForStmt):
            self._for(statement, in_main)
            return
        self._unsupported(statement, f"{type(statement).__name__} is not supported by the Pico firmware preview.")

    def _block(self, body, in_main):
        self.indent += 1
        self.scopes.append({})
        for statement in body:
            self._statement(statement, in_main=in_main)
        self.scopes.pop()
        self.indent -= 1

    def _for(self, statement, in_main):
        iterable = statement.iterable
        self.scopes.append({})
        name = self._declare(statement.variable)
        if isinstance(iterable, CallExpr) and iterable.callee == "number_range":
            if iterable.named_arguments or not 1 <= len(iterable.arguments) <= 3:
                self._unsupported(iterable, "number_range() in firmware accepts one to three positional arguments.")
            values = [self._expression(value) for value in iterable.arguments]
            if len(values) == 1:
                start, stop, step = "0", values[0], "1"
            elif len(values) == 2:
                start, stop, step = values[0], values[1], "1"
            else:
                step_expression = iterable.arguments[2]
                if not isinstance(step_expression, LiteralExpr) or type(step_expression.value) is not int or step_expression.value == 0:
                    self._unsupported(step_expression, "Firmware number_range() requires a non-zero integer literal step.")
                start, stop, step = values
            self._line(f"for (std::int64_t {name} = {start}; (({step}) > 0 ? {name} < ({stop}) : {name} > ({stop})); {name} += ({step})) {{")
        elif isinstance(iterable, ListExpr):
            kind = self._list_kind(iterable)
            elements = ", ".join(self._expression(value) for value in iterable.elements)
            self._line(f"for (const auto &{name} : std::initializer_list<{kind}>{{{elements}}}) {{")
        else:
            self._unsupported(iterable, "Firmware for loops currently require number_range() or a literal homogeneous list.")
        self.indent += 1
        for child in statement.body:
            self._statement(child, in_main=in_main)
        self.indent -= 1
        self._line("}")
        self.scopes.pop()

    def _list_kind(self, expression):
        if not expression.elements:
            self._unsupported(expression, "An empty firmware list has no inferable C++ element type.")
        values = [item.value for item in expression.elements if isinstance(item, LiteralExpr)]
        if len(values) != len(expression.elements):
            self._unsupported(expression, "Firmware list iteration currently requires literal elements.")
        if all(type(value) is bool for value in values):
            return "bool"
        if all(type(value) in (int, float) and type(value) is not bool for value in values):
            return "double"
        if all(type(value) is str for value in values):
            return "std::string"
        self._unsupported(expression, "Firmware list elements must have one homogeneous type.")

    def _expression(self, expression):
        if isinstance(expression, LiteralExpr):
            if expression.value is None:
                self._unsupported(expression, "null values are not yet supported in generated firmware.")
            if type(expression.value) is bool:
                return "true" if expression.value else "false"
            if type(expression.value) is str:
                return f"std::string({_cpp_string(expression.value)})"
            if type(expression.value) in (int, float):
                return repr(expression.value)
        if isinstance(expression, VariableExpr):
            name = self._lookup(expression.name)
            if name is None:
                self._unsupported(expression, f"Variable '{expression.name}' is not available in this generated C++ scope.")
            return name
        if isinstance(expression, GroupExpr):
            return f"({self._expression(expression.expression)})"
        if isinstance(expression, UnaryExpr):
            operator = {"!": "!", "-": "-", "+": "+"}.get(expression.operator)
            if operator is None:
                self._unsupported(expression, f"Unary operator '{expression.operator}' is not supported in firmware.")
            return f"({operator}{self._expression(expression.operand)})"
        if isinstance(expression, BinaryExpr):
            left = self._expression(expression.left)
            right = self._expression(expression.right)
            if expression.operator == "**":
                return f"std::pow({left}, {right})"
            if expression.operator == "//":
                return f"std::floor(({left}) / ({right}))"
            if expression.operator == "%":
                return f"std::fmod({left}, {right})"
            operator = {"&&": "&&", "||": "||", "+": "+", "-": "-", "*": "*", "/": "/",
                        "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}.get(expression.operator)
            if operator is None:
                self._unsupported(expression, f"Binary operator '{expression.operator}' is not supported in firmware.")
            return f"({left} {operator} {right})"
        if isinstance(expression, MemberExpr):
            if isinstance(expression.target, VariableExpr) and expression.target.name == "pin":
                return str(self._pin_number(expression))
            self._unsupported(expression, "Only pin.<logical_name> member access is supported in generated firmware.")
        if isinstance(expression, CallExpr):
            return self._call(expression)
        if isinstance(expression, (ListExpr, IndexExpr, MemberCallExpr)):
            self._unsupported(expression, f"{type(expression).__name__} is not supported in this firmware expression.")
        self._unsupported(expression, f"{type(expression).__name__} is not supported in generated firmware.")

    def _call(self, call):
        if call.named_arguments and call.callee not in {"i2c_open", "uart_open"}:
            self._unsupported(call, f"Named arguments are not supported for firmware call '{call.callee}'.")
        arguments = [self._expression(value) for value in call.arguments]
        if call.callee in self.functions:
            return f"sep_fn_{_identifier(call.callee)}({', '.join(arguments)})"
        if call.callee == "gpio_set_mode":
            self._arity(call, 2)
            mode = self._literal_string(call.arguments[1], "GPIO mode")
            modes = {"input": "SEP_GPIO_INPUT", "input_pull_up": "SEP_GPIO_INPUT_PULL_UP",
                     "input_pull_down": "SEP_GPIO_INPUT_PULL_DOWN", "output": "SEP_GPIO_OUTPUT"}
            if mode not in modes:
                self._unsupported(call.arguments[1], "GPIO mode must be input, input_pull_up, input_pull_down, or output.")
            return f"sep_gpio_set_mode({arguments[0]}, {modes[mode]})"
        direct = {
            "gpio_write": (2, "sep_gpio_write"),
            "gpio_read": (1, "sep_gpio_read"),
            "analog_read": (1, "sep_analog_read"),
            "pwm_write": (2, "sep_pwm_write"),
            "delay_milliseconds": (1, "sep_delay_milliseconds"),
            "i2c_probe": (2, "sep_i2c_probe"),
            "uart_write": (2, "sep_uart_write"),
            "uart_read_line": (1, "sep_uart_read_line"),
            "number_to_hexadecimal": (1, "sep_number_to_hexadecimal"),
        }
        if call.callee in direct:
            arity, name = direct[call.callee]
            self._arity(call, arity)
            return f"{name}({', '.join(arguments)})"
        if call.callee == "i2c_open":
            return self._bus_open(call, "i2c", ("sda", "scl"), "sep_i2c_open")
        if call.callee == "uart_open":
            return self._bus_open(call, "uart", ("tx", "rx"), "sep_uart_open")
        if call.callee == "board_name":
            self._arity(call, 0)
            return f"std::string({_cpp_string(self.profile.id)})"
        if call.callee == "board_cpu":
            self._arity(call, 0)
            return f"std::string({_cpp_string(self.profile.mcu)})"
        if call.callee == "board_voltage":
            self._arity(call, 0)
            return repr(self.profile.logic_voltage)
        if call.callee == "board_has":
            self._arity(call, 1)
            feature = self._literal_string(call.arguments[0], "board feature")
            return "true" if feature in self.profile.features else "false"
        if call.callee == "board_select":
            self._unsupported(call, "board_select() is a build-time declaration and cannot be used as a firmware value.")
        if call.callee == "number_range":
            self._unsupported(call, "number_range() is supported only as the iterable of a for loop.")
        self._unsupported(call, f"Function '{call.callee}' has no Pico firmware implementation.")

    def _bus_open(self, call, kind, roles, runtime_name):
        if len(call.arguments) > 1:
            self._unsupported(call, f"{kind}_open() accepts at most one positional bus index.")
        index = 0
        if call.arguments:
            value = call.arguments[0]
            if not isinstance(value, LiteralExpr) or type(value.value) is not int:
                self._unsupported(value, f"{kind}_open() requires a literal bus index in generated firmware.")
            index = value.value
        mapping = dict(self.profile.default_buses.get((kind, index), {}))
        for role, value in call.named_arguments.items():
            if role not in roles:
                self._unsupported(value, f"Unknown {kind}_open() pin role '{role}'.")
            mapping[role] = self.profile.resolve(self._pin_name(value), value.position).definition.name
        missing = [role for role in roles if role not in mapping]
        if missing:
            self._unsupported(call, f"{kind.upper()} bus {index} is missing {', '.join(missing)}.")
        pins = [str(self._backend_pin_number(self.profile.resolve(mapping[role], call.position))) for role in roles]
        return f"{runtime_name}({index}, {', '.join(pins)})"

    def _pin_name(self, expression):
        if isinstance(expression, MemberExpr) and isinstance(expression.target, VariableExpr) and expression.target.name == "pin":
            return expression.name
        self._unsupported(expression, "A literal pin.<logical_name> is required for generated bus mappings.")

    def _pin_number(self, expression):
        pin = self.profile.resolve(expression.name, expression.position)
        return self._backend_pin_number(pin)

    def _backend_pin_number(self, pin):
        match = re.fullmatch(r"GPIO(\d+)", pin.definition.backend_pin)
        if not match:
            self._unsupported_at(self.program.position, f"Pin '{pin.definition.name}' is not a direct RP GPIO and cannot use this backend.")
        return int(match.group(1))

    def _arity(self, call, count):
        if call.named_arguments or len(call.arguments) != count:
            self._unsupported(call, f"{call.callee}() requires exactly {count} positional argument(s) in firmware.")

    def _literal_string(self, expression, description):
        if not isinstance(expression, LiteralExpr) or type(expression.value) is not str:
            self._unsupported(expression, f"{description} must be a literal string in generated firmware.")
        return expression.value

    def _is_board_selection(self, statement):
        return isinstance(statement, (Assignment, ConstDeclaration)) and isinstance(statement.value, CallExpr) and statement.value.callee == "board_select"

    def _contains_return(self, value):
        if isinstance(value, ReturnStmt):
            return True
        if is_dataclass(value):
            return any(self._contains_return(getattr(value, item.name)) for item in fields(value) if item.name != "position")
        if isinstance(value, (list, tuple)):
            return any(self._contains_return(item) for item in value)
        return False

    def _declare(self, source_name):
        name = "sep_var_" + _identifier(source_name)
        self.scopes[-1][source_name] = name
        return name

    def _lookup(self, source_name):
        for scope in reversed(self.scopes):
            if source_name in scope:
                return scope[source_name]
        return None

    def _line(self, value):
        self.lines.append("    " * self.indent + value)

    def _unsupported(self, node, description):
        self._unsupported_at(node.position, description)

    def _unsupported_at(self, position, description):
        raise error("E966", "Unsupported firmware construct", description, position)


def _identifier(value):
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not normalized or normalized[0].isdigit():
        normalized = "value_" + normalized
    return normalized


def _cpp_string(value):
    return json.dumps(value, ensure_ascii=False)


def _synthetic_position(filename):
    from .token import SourcePosition
    return SourcePosition(filename, 1, 1, "")


_PICO_RUNTIME = r'''// Generated by Separan. Edit the .sep source, not this file.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <sstream>
#include <string>
#include <type_traits>

#include "pico/stdlib.h"
#include "hardware/adc.h"
#include "hardware/i2c.h"
#include "hardware/pwm.h"
#include "hardware/uart.h"

enum SepGpioMode {
    SEP_GPIO_INPUT,
    SEP_GPIO_INPUT_PULL_UP,
    SEP_GPIO_INPUT_PULL_DOWN,
    SEP_GPIO_OUTPUT,
};

struct SepI2cBus {
    i2c_inst_t *instance;
    unsigned int sda;
    unsigned int scl;
};

struct SepUartBus {
    uart_inst_t *instance;
    unsigned int tx;
    unsigned int rx;
};

static void sep_gpio_set_mode(unsigned int pin, SepGpioMode mode) {
    gpio_init(pin);
    gpio_disable_pulls(pin);
    if (mode == SEP_GPIO_OUTPUT) {
        gpio_set_dir(pin, GPIO_OUT);
        return;
    }
    gpio_set_dir(pin, GPIO_IN);
    if (mode == SEP_GPIO_INPUT_PULL_UP) gpio_pull_up(pin);
    if (mode == SEP_GPIO_INPUT_PULL_DOWN) gpio_pull_down(pin);
}

template <typename T>
static void sep_gpio_write(unsigned int pin, T value) {
    static_assert(std::is_same<T, bool>::value, "gpio_write value must be boolean");
    gpio_put(pin, value);
}
static bool sep_gpio_read(unsigned int pin) { return gpio_get(pin); }

static double sep_analog_read(unsigned int pin) {
    adc_init();
    adc_gpio_init(pin);
    adc_select_input(pin - 26u);
    return static_cast<double>(adc_read()) / 4095.0;
}

template <typename T>
static void sep_pwm_write(unsigned int pin, T duty) {
    static_assert(std::is_arithmetic<T>::value && !std::is_same<T, bool>::value, "pwm_write duty must be number");
    if (duty < 0 || duty > 1) panic("Separan pwm_write duty must be between 0 and 1");
    gpio_set_function(pin, GPIO_FUNC_PWM);
    const unsigned int slice = pwm_gpio_to_slice_num(pin);
    pwm_config config = pwm_get_default_config();
    pwm_config_set_wrap(&config, 65535u);
    pwm_init(slice, &config, true);
    pwm_set_gpio_level(pin, static_cast<unsigned int>(duty * 65535.0));
}

static SepI2cBus sep_i2c_open(int index, unsigned int sda, unsigned int scl) {
    i2c_inst_t *instance = index == 0 ? i2c0 : i2c1;
    i2c_init(instance, 100000u);
    gpio_set_function(sda, GPIO_FUNC_I2C);
    gpio_set_function(scl, GPIO_FUNC_I2C);
    gpio_pull_up(sda);
    gpio_pull_up(scl);
    return {instance, sda, scl};
}

template <typename T>
static bool sep_i2c_probe(const SepI2cBus &bus, T address) {
    static_assert(std::is_integral<T>::value && !std::is_same<T, bool>::value, "i2c_probe address must be integer");
    if (address < 0 || address > 127) panic("Separan i2c_probe address must be between 0 and 127");
    unsigned char byte = 0;
    return i2c_read_timeout_us(bus.instance, static_cast<unsigned char>(address), &byte, 1, false, 1000u) >= 0;
}

static SepUartBus sep_uart_open(int index, unsigned int tx, unsigned int rx) {
    uart_inst_t *instance = index == 0 ? uart0 : uart1;
    uart_init(instance, 115200u);
    gpio_set_function(tx, GPIO_FUNC_UART);
    gpio_set_function(rx, GPIO_FUNC_UART);
    return {instance, tx, rx};
}

static void sep_uart_write(const SepUartBus &bus, const std::string &value) {
    uart_write_blocking(bus.instance, reinterpret_cast<const unsigned char *>(value.data()), value.size());
}

static std::string sep_uart_read_line(const SepUartBus &bus) {
    std::string value;
    while (true) {
        const char character = static_cast<char>(uart_getc(bus.instance));
        if (character == '\n') return value;
        if (character != '\r') value.push_back(character);
    }
}

static std::string sep_number_to_hexadecimal(std::int64_t value) {
    std::ostringstream stream;
    stream << std::hex << value;
    return stream.str();
}

template <typename T>
static void sep_delay_milliseconds(T milliseconds) {
    static_assert(std::is_integral<T>::value && !std::is_same<T, bool>::value, "delay_milliseconds value must be integer");
    if (milliseconds < 0 || milliseconds > 86400000) panic("Separan delay_milliseconds value is out of range");
    sleep_ms(static_cast<std::uint32_t>(milliseconds));
}

static void sep_print(const std::string &value) { std::printf("%s\n", value.c_str()); }
static void sep_print(bool value) { std::printf("%s\n", value ? "true" : "false"); }

template <typename T, typename std::enable_if<std::is_integral<T>::value && !std::is_same<T, bool>::value, int>::type = 0>
static void sep_print(T value) { std::printf("%lld\n", static_cast<long long>(value)); }

template <typename T, typename std::enable_if<std::is_floating_point<T>::value, int>::type = 0>
static void sep_print(T value) { std::printf("%.15g\n", static_cast<double>(value)); }
'''
