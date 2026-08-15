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


def execute(source, filename="<source>", output=None, command_arguments=None, script_path=None, project_root=None, environment_variables=None, capabilities=None, input_stream=None, error_output=None, http_transport=None, secret_provider=None, cookie_key_provider=None, mail_transport=None, board_id=None, embedded_adapter=None):
    program = Parser(Lexer(source, filename).scan_tokens()).parse()
    runtime = Interpreter(output, command_arguments=command_arguments, script_path=script_path,
                          project_root=project_root, environment_variables=environment_variables, capabilities=capabilities,
                          input_stream=input_stream, error_output=error_output, http_transport=http_transport, secret_provider=secret_provider, cookie_key_provider=cookie_key_provider, mail_transport=mail_transport,
                          board_id=board_id, embedded_adapter=embedded_adapter)
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
            capabilities = replace(
                RuntimeCapabilities.local(resolved.parent),
                database_drivers=frozenset({"sqlite", *args.allow_database_driver}),
                network=mail_enabled,
                network_hosts=frozenset(args.allow_mail_host) if mail_enabled else None,
                network_ports=frozenset(args.allow_mail_port) if args.allow_mail_port else None,
                allow_private_network=args.allow_private_mail_network,
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
    parser = argparse.ArgumentParser(prog="separan build", description="Validate Separan source against an embedded board profile")
    parser.add_argument("source", type=Path)
    parser.add_argument("--board", required=True, choices=tuple(sorted(BOARD_PROFILES)))
    args = parser.parse_args(argv)
    try:
        source = args.source.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(args.source)).scan_tokens()).parse()
        profile = validate_embedded_program(program, args.board)
        print(f"Validated {args.source} for {profile.id} ({profile.mcu}).")
        print("Board mapping validation only; firmware code generation is not implemented yet.")
        return 0
    except (SeparanError, UnicodeDecodeError, OSError) as exc:
        print(exc, file=sys.stderr); return 1
