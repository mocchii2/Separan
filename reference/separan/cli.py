import argparse
from dataclasses import replace
import sys
from pathlib import Path

from .ast_printer import format_ast
from .capabilities import RuntimeCapabilities
from .errors import SeparanError
from .interpreter import Interpreter
from .lexer import Lexer
from .parser import Parser
from .temporal import timezone_database_version
from .embedded import BOARD_PROFILES, validate_embedded_program
from .embedded_firmware import build_pico_project, flash_uf2, generate_pico_project


def execute(source, filename="<source>", output=None, command_arguments=None, script_path=None, project_root=None, environment_variables=None, capabilities=None, input_stream=None, error_output=None, http_transport=None, secret_provider=None, cookie_key_provider=None, mail_transport=None, board_id=None, embedded_adapter=None, network_adapter=None):
    program = Parser(Lexer(source, filename).scan_tokens()).parse()
    runtime = Interpreter(output, command_arguments=command_arguments, script_path=script_path,
                          project_root=project_root, environment_variables=environment_variables, capabilities=capabilities,
                          input_stream=input_stream, error_output=error_output, http_transport=http_transport, secret_provider=secret_provider, cookie_key_provider=cookie_key_provider, mail_transport=mail_transport,
                          board_id=board_id, embedded_adapter=embedded_adapter, network_adapter=network_adapter)
    try: result = runtime.run(program)
    finally: runtime.close_resources()
    return program, result


def create_application(source, filename="<source>", **runtime_options):
    program = Parser(Lexer(source, filename).scan_tokens()).parse()
    runtime = Interpreter(**runtime_options); runtime.run(program, invoke_main=False)
    return runtime


def main(argv=None):
    command_line = list(sys.argv[1:] if argv is None else argv)
    if command_line and command_line[0] == "build":
        return _build(command_line[1:])
    if command_line and command_line[0] == "flash":
        return _flash(command_line[1:])
    parser = argparse.ArgumentParser(prog="separan", description="Separan v0.2 alpha interpreter")
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--ast", action="store_true", help="print the parsed AST instead of executing")
    parser.add_argument("--timezone-version", action="store_true", help="print the timezone database version")
    parser.add_argument("--board", choices=tuple(sorted(BOARD_PROFILES)), help="select an embedded board profile")
    parser.add_argument("--allow-database-driver", action="append", choices=("postgresql", "mysql", "oracle", "sqlserver"), default=[], help="allow an optional database driver for this run")
    parser.add_argument("--allow-mail-host", action="append", default=[], help="allow mail delivery through this SMTP/SES host")
    parser.add_argument("--allow-mail-port", action="append", type=int, default=[], help="limit mail delivery to this network port")
    parser.add_argument("--allow-mail-sender", action="append", default=[], help="allow this envelope sender address")
    parser.add_argument("--allow-mail-recipient", action="append", default=[], help="allow this mail recipient address")
    parser.add_argument("--allow-private-mail-network", action="store_true", help="allow mail delivery to private network addresses")
    parser.add_argument("--allow-network-inspection", action="store_true", help="allow reading host network interface state")
    parser.add_argument("--allow-network-configuration", action="store_true", help="allow an explicit adapter to change interface IP configuration")
    parser.add_argument("--allow-network-service-hosting", action="store_true", help="allow an explicit adapter to host local AP, DHCP, and DNS services")
    parser.add_argument("--allow-network-host", action="append", default=[], help="allow DNS/TCP/UDP/HTTP access to this host")
    parser.add_argument("--allow-network-port", action="append", type=int, default=[], help="limit DNS/TCP/UDP/HTTP access to this destination port")
    parser.add_argument("--allow-private-network", action="store_true", help="allow access to loopback and private destination addresses")
    parser.add_argument("--allow-network-bind-host", action="append", default=[], help="allow UDP sockets to bind this local address")
    parser.add_argument("--allow-network-bind-port", action="append", type=int, default=[], help="allow UDP sockets to bind this local port; use 0 for an ephemeral port")
    args, script_arguments = parser.parse_known_args(command_line)
    if args.timezone_version:
        print(timezone_database_version())
        return 0
    if args.source is None:
        parser.error("the following arguments are required: source")
    if not args.allow_mail_host and (args.allow_mail_port or args.allow_mail_sender or args.allow_mail_recipient or args.allow_private_mail_network):
        parser.error("mail capability options require at least one --allow-mail-host")
    try:
        source = args.source.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(args.source)).scan_tokens()).parse()
        if args.ast: print(format_ast(program))
        else:
            resolved = args.source.resolve()
            mail_enabled = bool(args.allow_mail_host)
            network_hosts = frozenset({*args.allow_network_host, *args.allow_mail_host})
            network_ports = frozenset({*args.allow_network_port, *args.allow_mail_port})
            bind_enabled = bool(args.allow_network_bind_host or args.allow_network_bind_port)
            network_enabled = bool(network_hosts or bind_enabled)
            capabilities = replace(
                RuntimeCapabilities.local(resolved.parent),
                database_drivers=frozenset({"sqlite", *args.allow_database_driver}),
                network=network_enabled,
                inspect_network=args.allow_network_inspection or args.allow_network_configuration or args.allow_network_service_hosting,
                configure_network=args.allow_network_configuration,
                host_network_services=args.allow_network_service_hosting,
                bind_network=bind_enabled,
                network_hosts=network_hosts if network_enabled else None,
                network_ports=network_ports if network_ports else None,
                network_bind_hosts=frozenset(args.allow_network_bind_host) if args.allow_network_bind_host else frozenset({"127.0.0.1", "::1"}),
                network_bind_ports=frozenset(args.allow_network_bind_port) if args.allow_network_bind_port else frozenset({0}),
                allow_private_network=args.allow_private_network or args.allow_private_mail_network,
                send_mail=mail_enabled,
                allowed_mail_senders=frozenset(args.allow_mail_sender) if args.allow_mail_sender else None,
                allowed_mail_recipients=frozenset(args.allow_mail_recipient) if args.allow_mail_recipient else None,
            )
            Interpreter(sys.stdout, command_arguments=script_arguments,
                        script_path=str(resolved), project_root=str(resolved.parent),
                        capabilities=capabilities, input_stream=sys.stdin, error_output=sys.stderr,
                        board_id=args.board).run(program)
        return 0
    except (SeparanError, UnicodeDecodeError, OSError) as exc:
        print(exc, file=sys.stderr); return 1


def _build(argv):
    parser = argparse.ArgumentParser(prog="separan build", description="Generate and compile Pico SDK firmware from Separan source")
    parser.add_argument("source", type=Path)
    parser.add_argument("--board", required=True, choices=tuple(sorted(BOARD_PROFILES)))
    parser.add_argument("--output-dir", type=Path, help="generated Pico SDK project directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true", help="run board and pin validation without generating firmware")
    mode.add_argument("--emit-only", action="store_true", help="generate C++ and CMake files without invoking the SDK")
    parser.add_argument("--sdk-path", type=Path, help="path to an official Raspberry Pi Pico SDK checkout")
    parser.add_argument("--toolchain-path", type=Path, help="Pico GCC toolchain root passed to CMake")
    parser.add_argument("--cmake", help="cmake executable path or command name")
    parser.add_argument("--ninja", help="ninja executable path or command name")
    parser.add_argument("--build-type", choices=("Release", "Debug", "RelWithDebInfo", "MinSizeRel"), default="Release")
    parser.add_argument("--flash-to", type=Path, help="explicit mounted Pico BOOTSEL device root")
    args = parser.parse_args(argv)
    if (args.validate_only or args.emit_only) and args.flash_to is not None:
        parser.error("--flash-to requires a complete firmware build")
    try:
        source = args.source.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(args.source)).scan_tokens()).parse()
        profile = validate_embedded_program(program, args.board)
        print(f"Validated {args.source} for {profile.id} ({profile.mcu}).")
        if args.validate_only:
            print("Board mapping validation complete; firmware generation was skipped.")
            return 0
        output_directory = args.output_dir or (Path.cwd() / "build" / f"{args.source.stem}-{args.board}")
        project = generate_pico_project(program, source, args.source, args.board, output_directory)
        print(f"Generated Pico SDK project: {project.directory}")
        print(f"Pico SDK board: {project.sdk_board}")
        if args.emit_only:
            print("Firmware source generation complete; SDK compilation was skipped.")
            return 0
        artifacts = build_pico_project(
            project,
            sdk_path=args.sdk_path,
            toolchain_path=args.toolchain_path,
            cmake=args.cmake,
            ninja=args.ninja,
            build_type=args.build_type,
        )
        print(f"ELF: {artifacts.elf}")
        print(f"UF2: {artifacts.uf2}")
        print(f"HEX: {artifacts.hex}")
        if args.flash_to is not None:
            destination = flash_uf2(artifacts.uf2, args.flash_to, project.position)
            print(f"UF2 copied to BOOTSEL device: {destination}")
        return 0
    except (SeparanError, UnicodeDecodeError, OSError) as exc:
        print(exc, file=sys.stderr); return 1


def _flash(argv):
    parser = argparse.ArgumentParser(prog="separan flash", description="Copy a UF2 image to one explicitly selected Pico BOOTSEL device")
    parser.add_argument("uf2", type=Path)
    parser.add_argument("--device", required=True, type=Path, help="mounted BOOTSEL device root containing INFO_UF2.TXT")
    args = parser.parse_args(argv)
    try:
        destination = flash_uf2(args.uf2, args.device)
        print(f"UF2 copied to BOOTSEL device: {destination}")
        return 0
    except (SeparanError, OSError) as exc:
        print(exc, file=sys.stderr); return 1
