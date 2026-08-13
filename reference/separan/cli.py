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


def execute(source, filename="<source>", output=None, command_arguments=None, script_path=None, project_root=None, environment_variables=None, capabilities=None, input_stream=None, error_output=None, http_transport=None, secret_provider=None, cookie_key_provider=None):
    program = Parser(Lexer(source, filename).scan_tokens()).parse()
    runtime = Interpreter(output, command_arguments=command_arguments, script_path=script_path,
                          project_root=project_root, environment_variables=environment_variables, capabilities=capabilities,
                          input_stream=input_stream, error_output=error_output, http_transport=http_transport, secret_provider=secret_provider, cookie_key_provider=cookie_key_provider)
    try: result = runtime.run(program)
    finally: runtime.close_resources()
    return program, result


def create_application(source, filename="<source>", **runtime_options):
    program = Parser(Lexer(source, filename).scan_tokens()).parse()
    runtime = Interpreter(**runtime_options); runtime.run(program, invoke_main=False)
    return runtime


def main(argv=None):
    parser = argparse.ArgumentParser(prog="separan", description="Separan v0.1 interpreter")
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--ast", action="store_true", help="print the parsed AST instead of executing")
    parser.add_argument("--timezone-version", action="store_true", help="print the timezone database version")
    parser.add_argument("--allow-database-driver", action="append", choices=("postgresql", "mysql", "oracle", "sqlserver"), default=[], help="allow an optional database driver for this run")
    args, script_arguments = parser.parse_known_args(argv)
    if args.timezone_version:
        print(timezone_database_version())
        return 0
    if args.source is None:
        parser.error("the following arguments are required: source")
    try:
        source = args.source.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(args.source)).scan_tokens()).parse()
        if args.ast: print(format_ast(program))
        else:
            resolved = args.source.resolve()
            capabilities = replace(RuntimeCapabilities.local(resolved.parent), database_drivers=frozenset({"sqlite", *args.allow_database_driver}))
            Interpreter(sys.stdout, command_arguments=script_arguments,
                        script_path=str(resolved), project_root=str(resolved.parent),
                        capabilities=capabilities, input_stream=sys.stdin, error_output=sys.stderr).run(program)
        return 0
    except (SeparanError, UnicodeDecodeError, OSError) as exc:
        print(exc, file=sys.stderr); return 1
