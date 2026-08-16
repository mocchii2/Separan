from dataclasses import dataclass
from datetime import datetime as PyDateTime, timezone as py_timezone, timedelta
from io import StringIO
import math
from pathlib import Path

from .ast_nodes import *
from .builtins import BUILTINS
from .errors import ErrorValue, SeparanError, error
from .temporal import (
    DatetimeValue, DurationValue, LocalDatetimeValue, TimezoneValue,
    duration_scaled, format_datetime, format_duration, format_local, public_type,
)
from .randomness import BytesValue, SeparanRandom
from .system_utilities import RegexMatchValue
from .objects import ObjectValue
from .capabilities import RuntimeCapabilities
from .processes import ExecResultValue
from .http_client import HttpProfileValue, HttpResponseValue, urllib_transport
from .auth import HttpAuthValue, OAuthTokenValue, SecretValue
from .cookies import CookieJarValue
from .http_server import HttpReturned, ServerRequest, ServerResponse, compile_path, match_path, static_response
from .database import DbConnectionValue, begin as db_begin, commit as db_commit, rollback as db_rollback
from .system_context import SystemContextValue, build_system_context
from .mail import MailAddressValue, MailMessageValue, MailSendResultValue, MailSenderValue, send_transport as mail_send_transport
from .structured_data import XmlDocumentValue, XmlElementValue
from .embedded import BoardValue, BusValue, EmbeddedContext, PinNamespaceValue, PinValue, fixed_member, pin_member
from .network import IpAddressValue, NativeNetworkAdapter, NetworkInterfaceValue, TcpConnectionValue, UdpSocketValue
from .network_services import DhcpServerValue, DnsServerValue
from .token import SourcePosition


@dataclass(frozen=True)
class NamespaceValue:
    runtime: object
    exports: frozenset


@dataclass(frozen=True)
class FunctionValue:
    runtime: object
    name: str


def type_name(value):
    if isinstance(value, SystemContextValue): return "system"
    if isinstance(value, BoardValue): return "board"
    if isinstance(value, PinNamespaceValue): return "pin_namespace"
    if isinstance(value, PinValue): return "pin"
    if isinstance(value, BusValue): return "embedded_bus"
    if isinstance(value, IpAddressValue): return "ip_address"
    if isinstance(value, NetworkInterfaceValue): return "network_interface"
    if isinstance(value, TcpConnectionValue): return "tcp_connection"
    if isinstance(value, UdpSocketValue): return "udp_socket"
    if isinstance(value, DhcpServerValue): return "dhcp_server"
    if isinstance(value, DnsServerValue): return "dns_server"
    if isinstance(value, BytesValue): return "bytes"
    if isinstance(value, RegexMatchValue): return "regex_match_result"
    if isinstance(value, ObjectValue): return "object"
    if isinstance(value, NamespaceValue): return "namespace"
    if isinstance(value, FunctionValue): return "function"
    if isinstance(value, ErrorValue): return "error"
    if isinstance(value, ExecResultValue): return "exec_result"
    if isinstance(value, HttpProfileValue): return "http_profile"
    if isinstance(value, HttpResponseValue): return "http_response"
    if isinstance(value, SecretValue): return "secret"
    if isinstance(value, HttpAuthValue): return "http_auth"
    if isinstance(value, OAuthTokenValue): return "oauth_token"
    if isinstance(value, CookieJarValue): return "cookie_jar"
    if isinstance(value, MailAddressValue): return "mail_address"
    if isinstance(value, MailMessageValue): return "mail_message"
    if isinstance(value, MailSenderValue): return "mail_sender"
    if isinstance(value, MailSendResultValue): return "mail_send_result"
    if isinstance(value, XmlDocumentValue): return "xml_document"
    if isinstance(value, XmlElementValue): return "xml_element"
    if isinstance(value, DbConnectionValue): return "db_connection"
    temporal = public_type(value)
    if temporal != "unknown": return temporal
    return "unknown"


@dataclass
class Binding:
    value: object
    declared_type: str
    element_type: str | None = None
    constant: bool = False
    declaration_position: object = None


class Environment:
    def __init__(self, parent=None): self.parent, self.values = parent, {}
    def assign(self, name, value, position):
        value_type = type_name(value)
        element_type = list_element_type(value, position) if value_type == "list" else None
        if name in self.values:
            old = self.values[name]
            if old.constant:
                raise error("E211", "Constant reassignment", f"Constant '{name}' cannot be assigned again.", position, expected="no reassignment", actual=name, related=old.declaration_position)
            if old.declared_type != value_type:
                raise error("E201", "Type error", f"Variable '{name}' has fixed type {old.declared_type} and cannot receive {value_type}.", position, expected=old.declared_type, actual=value_type)
            if value_type == "list" and old.element_type and element_type and old.element_type != element_type:
                raise error("E201", "Type error", f"List variable '{name}' has fixed element type {old.element_type}.", position, expected=old.element_type, actual=element_type)
            old.value = value
            if old.element_type is None: old.element_type = element_type
        else: self.values[name] = Binding(value, value_type, element_type, False, position)
    def define_const(self, name, value, position):
        if name in self.values:
            previous = self.values[name]
            raise error("E210", "Duplicate binding", f"Name '{name}' is already defined in this scope.", position, expected="a unique constant name", actual=name, related=previous.declaration_position)
        value_type = type_name(value)
        element_type = list_element_type(value, position) if value_type == "list" else None
        self.values[name] = Binding(value, value_type, element_type, True, position)
    def get(self, name, position):
        if name in self.values: return self.values[name].value
        if self.parent: return self.parent.get(name, position)
        raise error("E202", "Undefined variable", f"Variable '{name}' is not defined.", position, actual=name)
    def contains(self, name):
        return name in self.values or bool(self.parent and self.parent.contains(name))


def list_element_type(value, position):
    if not value: return None
    first = type_name(value[0])
    for item in value[1:]:
        if type_name(item) != first:
            raise error("E203", "Heterogeneous list", "All list elements must have the same type in v0.1.", position, expected=first, actual=type_name(item))
    return first


class Returned(Exception):
    def __init__(self, value): self.value = value


class Interpreter:
    def __init__(self, output=None, clock=None, command_arguments=None, script_path=None, project_root=None, environment_variables=None, module_cache=None, import_stack=None, capabilities=None, input_stream=None, error_output=None, http_transport=None, secret_provider=None, cookie_key_provider=None, mail_transport=None, embedded_context=None, board_id=None, embedded_adapter=None, network_adapter=None):
        self.output = output or StringIO()
        self.input_stream = input_stream or StringIO()
        self.error_output = error_output or StringIO()
        self.globals = Environment()
        self.environment = self.globals
        self.functions = {}
        self.error_categories = set()
        self.http_routes = []
        self.http_static_mounts = []
        self.function_parameter_types = {}
        self.clock = clock or (lambda: PyDateTime.now(py_timezone.utc))
        self.random = SeparanRandom()
        self.command_arguments = list(command_arguments or [])
        self.script_path = script_path
        self.project_root = project_root
        system_position = SourcePosition("<runtime>", 1, 1, "system")
        self.globals.define_const("system", build_system_context(script_path, self.command_arguments), system_position)
        self.embedded_context = embedded_context or EmbeddedContext(board_id, locked=board_id is not None, adapter=embedded_adapter)
        self.globals.define_const("pin", PinNamespaceValue(self.embedded_context), system_position)
        import os
        self.environment_variables = dict(os.environ if environment_variables is None else environment_variables)
        self.module_cache = {} if module_cache is None else module_cache
        self.import_stack = [] if import_stack is None else import_stack
        default_root = project_root or (Path(script_path).parent if script_path else Path.cwd())
        self.capabilities = capabilities or RuntimeCapabilities.local(default_root)
        self.http_transport = http_transport or urllib_transport
        self.secret_provider = secret_provider
        self.cookie_key_provider = cookie_key_provider
        self.mail_transport = mail_transport or mail_send_transport
        self.network_adapter = network_adapter or NativeNetworkAdapter()
        self.network_preferred_interfaces = []
        self.network_resources = []
        self.http_request_context = None
        self.database_connections = []

    def run(self, program: Program, invoke_main=True):
        for stmt in program.statements:
            if isinstance(stmt, FunctionDecl):
                if stmt.name in BUILTINS:
                    raise error("E209", "Reserved function name", f"Function '{stmt.name}' is a built-in and cannot be redefined.", stmt.position, actual=stmt.name)
                if stmt.name in self.functions:
                    raise error("E204", "Duplicate function", f"Function '{stmt.name}' is already defined.", stmt.position, actual=stmt.name)
                self.functions[stmt.name] = stmt
            elif isinstance(stmt, ErrorDecl):
                if stmt.name in BUILTINS or stmt.name in self.error_categories or any(item.name == stmt.name for item in program.statements if isinstance(item, FunctionDecl)):
                    raise error("E122", "Duplicate error name", f"Custom error name '{stmt.name}' conflicts with an existing declaration or built-in.", stmt.position, actual=stmt.name)
                self.error_categories.add(stmt.name)
            elif isinstance(stmt, HttpRouteDecl):
                try: compiled = compile_path(stmt.path)
                except ValueError as exc: raise error("E892", "Invalid route path", str(exc), stmt.position, actual=stmt.path)
                if any(route.method == stmt.method and route.path == stmt.path for route, _ in self.http_routes): raise error("E896", "Duplicate HTTP route", "HTTP method and path must be unique.", stmt.position, actual=f"{stmt.method} {stmt.path}")
                self.http_routes.append((stmt, compiled))
        main = self.functions.get("main")
        if main and main.parameters:
            raise error("E205", "Invalid main function", "main must have zero parameters in v0.1.", main.position, expected="main()", actual=f"main({', '.join(main.parameters)})")
        for stmt in program.statements:
            if not isinstance(stmt, (FunctionDecl, HttpRouteDecl, ErrorDecl)): self._execute(stmt)
        if invoke_main and main: self._call("main", [], main.position)
        return self.output.getvalue() if hasattr(self.output, "getvalue") else None

    def dispatch_http(self, request: ServerRequest):
        for route, compiled in self.http_routes:
            if route.method != request.method and not (request.method == "HEAD" and route.method == "GET"): continue
            params = match_path(compiled, request.path)
            if params is None: continue
            previous_env, previous_context = self.environment, self.http_request_context
            self.environment = Environment(self.globals); self.http_request_context = {"request": request, "params": params, "response_cookies": []}
            try:
                try: self._execute_all(route.body)
                except HttpReturned as returned: return returned.response
                return ServerResponse(204, {}, b"")
            finally: self.environment, self.http_request_context = previous_env, previous_context
        response = static_response(request, self.http_static_mounts)
        return response or ServerResponse(404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found")

    def _execute_all(self, statements):
        for stmt in statements: self._execute(stmt)

    def _execute(self, stmt):
        if isinstance(stmt, ImportStmt): self._import(stmt)
        elif isinstance(stmt, Assignment): self.environment.assign(stmt.name, self._eval(stmt.value), stmt.position)
        elif isinstance(stmt, ConstDeclaration): self.environment.define_const(stmt.name, self._eval(stmt.value), stmt.position)
        elif isinstance(stmt, PrintStmt): self.output.write(self._display(self._eval(stmt.value)) + "\n")
        elif isinstance(stmt, PrintErrorStmt): self.error_output.write(self._display(self._eval(stmt.value)) + "\n")
        elif isinstance(stmt, ExpressionStmt): self._eval(stmt.expression)
        elif isinstance(stmt, ReturnStmt): raise Returned(None if stmt.value is None else self._eval(stmt.value))
        elif isinstance(stmt, IfStmt):
            for branch in stmt.branches:
                if self._boolean(self._eval(branch.condition), branch.condition.position): self._execute_all(branch.body); return
            if stmt.else_body is not None: self._execute_all(stmt.else_body)
        elif isinstance(stmt, WhileStmt):
            while self._boolean(self._eval(stmt.condition), stmt.condition.position): self._execute_all(stmt.body)
        elif isinstance(stmt, ForStmt):
            iterable = self._eval(stmt.iterable)
            if type(iterable) is not list: self._type_error(stmt.iterable.position, "list", type_name(iterable), "for can iterate only over a list.")
            for item in iterable: self.environment.assign(stmt.variable, item, stmt.position); self._execute_all(stmt.body)
        elif isinstance(stmt, (ObjectBlock, ListBlock)):
            self.environment.assign(stmt.name, self._build_data_block(stmt), stmt.position)
        elif isinstance(stmt, ThrowStmt):
            value = self._eval(stmt.value)
            if not isinstance(value, ErrorValue): self._type_error(stmt.position, "error", type_name(value), "throw requires an error value.")
            raise error("E760", value.category, value.message, stmt.position)
        elif isinstance(stmt, TransactionStmt):
            connection = self._eval(stmt.connection); db_begin(connection, stmt.position, self)
            try: self._execute_all(stmt.body)
            except SeparanError:
                db_rollback(connection, stmt.position, self); raise
            except (Returned, HttpReturned):
                db_commit(connection, stmt.position, self); raise
            except BaseException:
                db_rollback(connection, stmt.position, self); raise
            else: db_commit(connection, stmt.position, self)
        elif isinstance(stmt, TryStmt): self._execute_try(stmt)

    def _execute_try(self, stmt):
        active = None
        try:
            try: self._execute_all(stmt.body)
            except SeparanError as caught:
                active = caught; category = self._error_category(caught)
                branch = next((item for item in stmt.catches if self._error_matches(item.category, category)), None)
                if branch is None: raise
                active = None; self._execute_all(branch.body)
        finally:
            if stmt.finally_body is not None: self._execute_all(stmt.finally_body)

    @staticmethod
    def _error_category(value):
        if value.code == "E760": return value.category
        prefix = int(value.code[1:]) if value.code[1:].isdigit() else 0
        if value.code in ("E201", "E203", "E208"): return "type_error"
        if value.code in ("E301",): return "value_error"
        if value.code in ("E302",): return "index_error"
        if 830 <= prefix <= 839: return "regex_error"
        if 840 <= prefix <= 849: return "glob_error"
        if 860 <= prefix <= 869: return "argument_error"
        if 701 <= prefix <= 709: return "import_error"
        if prefix == 720 or prefix == 721: return "permission_error"
        if 722 <= prefix <= 729: return "io_error"
        if 740 <= prefix <= 749: return "parse_error"
        if 800 <= prefix <= 819: return value.category if value.code in ("E808", "E809") else "process_error"
        if 780 <= prefix <= 799: return value.category if value.category.endswith("_error") else "http_error"
        if prefix == 870: return "permission_error"
        if prefix == 871: return "secret_error"
        if 872 <= prefix <= 879: return value.category if value.category.endswith("_error") else "auth_error"
        if 880 <= prefix <= 889: return "cookie_error"
        if 900 <= prefix <= 919: return value.category
        if 920 <= prefix <= 929: return value.category if value.category.endswith("_error") else "crypto_error"
        if 930 <= prefix <= 939: return value.category if value.category.endswith("_error") else "mail_error"
        if 940 <= prefix <= 949: return value.category if value.category.endswith("_error") else "yaml_error"
        if 950 <= prefix <= 959: return value.category if value.category.endswith("_error") else "xml_error"
        if 970 <= prefix <= 978 or 980 <= prefix <= 984: return value.category if value.category.endswith("_error") else "network_error"
        if prefix == 979: return "permission_error"
        return "runtime_error"

    @staticmethod
    def _error_matches(requested, actual):
        if requested in (actual, "any", "runtime_error"): return True
        parents = {
            "command_timeout_error": "command_error", "command_error": "process_error",
            "http_timeout_error": "http_error", "http_dns_error": "http_error", "http_tls_error": "http_error",
            "http_redirect_error": "http_error", "http_status_error": "http_error", "http_decode_error": "http_error",
            "http_limit_error": "http_error",
            "oauth_error": "auth_error", "secret_error": "auth_error",
            "crypto_authentication_error": "crypto_error",
            "mail_address_error": "mail_error", "mail_attachment_error": "mail_error", "mail_provider_error": "mail_error",
            "mail_connection_error": "mail_error", "mail_authentication_error": "mail_error", "mail_send_error": "mail_error",
            "yaml_parse_error": "yaml_error", "yaml_encode_error": "yaml_error", "yaml_type_error": "yaml_error", "yaml_limit_error": "yaml_error",
            "xml_parse_error": "xml_error", "xml_model_error": "xml_error", "xml_security_error": "xml_error",
            "xml_limit_error": "xml_error", "xml_path_error": "xml_error", "xml_escape_error": "xml_error",
            "network_dns_error": "network_error", "network_interface_error": "network_error",
            "network_connection_error": "network_error", "network_timeout_error": "network_error",
            "network_limit_error": "network_error", "network_closed_error": "network_error",
            "network_protocol_error": "network_error", "network_operation_unavailable": "network_error",
            "network_address_error": "network_error",
            "network_service_error": "network_error", "dhcp_server_error": "network_service_error",
            "dns_server_error": "network_service_error", "wifi_access_point_error": "network_service_error",
        }
        current = actual
        while current in parents:
            current = parents[current]
            if requested == current: return True
        return False

    def _build_data_block(self, stmt):
        if isinstance(stmt, ListBlock):
            values = [self._eval(value) for value in stmt.elements]; list_element_type(values, stmt.position); return values
        fields = {}
        for entry in stmt.entries:
            fields[entry.name] = self._eval(entry.value) if isinstance(entry, ObjectField) else self._build_data_block(entry)
        return ObjectValue.create(fields)

    def _import(self, stmt):
        self.capabilities.require(self.capabilities.import_modules, "import modules", stmt.position)
        if not stmt.path.endswith(".sep") or Path(stmt.path).is_absolute() or ".." in Path(stmt.path).parts:
            raise error("E704", "Invalid import path", "Import paths must be relative .sep paths without '..'.", stmt.position, actual=stmt.path)
        base = Path(self.script_path).parent if self.script_path else Path(self.project_root or ".")
        root = Path(self.project_root or base).resolve(); path = (base / stmt.path).resolve()
        if path != root and root not in path.parents:
            raise error("E704", "Import root escape", "Imported module escapes the project root.", stmt.position, actual=stmt.path)
        key = str(path)
        if key in self.import_stack:
            chain = " -> ".join([*self.import_stack, key])
            raise error("E701", "Circular import", chain, stmt.position, actual=stmt.path)
        namespace = self.module_cache.get(key)
        if namespace is None:
            try: source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc: raise error("E705", "Import error", str(exc), stmt.position, actual=stmt.path)
            from .lexer import Lexer
            from .parser import Parser
            program = Parser(Lexer(source, key).scan_tokens()).parse()
            self.import_stack.append(key)
            module = Interpreter(self.output, self.clock, self.command_arguments, key, root,
                                 self.environment_variables, self.module_cache, self.import_stack, self.capabilities,
                                 self.input_stream, self.error_output, self.http_transport, self.secret_provider, self.cookie_key_provider, self.mail_transport,
                                 self.embedded_context, network_adapter=self.network_adapter)
            try: module.run(program, invoke_main=False)
            finally: self.import_stack.pop()
            exports = frozenset([item.name for item in program.statements if isinstance(item, (FunctionDecl, ConstDeclaration, ErrorDecl))])
            namespace = NamespaceValue(module, exports); self.module_cache[key] = namespace
        self.environment.define_const(stmt.alias, namespace, stmt.position)

    def _eval(self, expr):
        if isinstance(expr, LiteralExpr): return expr.value
        if isinstance(expr, GroupExpr): return self._eval(expr.expression)
        if isinstance(expr, VariableExpr):
            if self.environment.contains(expr.name): return self.environment.get(expr.name, expr.position)
            if expr.name in self.functions or expr.name in BUILTINS: return FunctionValue(self, expr.name)
            return self.environment.get(expr.name, expr.position)
        if isinstance(expr, ListExpr):
            values = [self._eval(e) for e in expr.elements]; list_element_type(values, expr.position); return values
        if isinstance(expr, CallExpr):
            positional = [self._eval(a) for a in expr.arguments]
            named = {name: self._eval(value) for name, value in expr.named_arguments.items()}
            return self._call(expr.callee, positional, expr.position, named)
        if isinstance(expr, IndexExpr):
            target, index = self._eval(expr.target), self._eval(expr.index)
            if type(target) is not list: self._type_error(expr.position, "list", type_name(target), "Only lists support indexing in v0.1.")
            if type(index) is not int or index < 0: self._type_error(expr.index.position, "non-negative integer", self._display(index), "List indexes must be non-negative integers.")
            if index >= len(target): raise error("E302", "Index out of range", f"Index {index} is outside a list of length {len(target)}.", expr.index.position, expected=f"0..{len(target)-1}", actual=str(index))
            return target[index]
        if isinstance(expr, MemberExpr):
            target = self._eval(expr.target)
            if isinstance(target, PinNamespaceValue): return pin_member(target, expr.name, expr.position)
            member, supported = fixed_member(target, expr.name, expr.position)
            if supported: return member
            if isinstance(target, ObjectValue):
                if expr.name not in target.fields: raise error("E212", "Missing object field", f"Object field '{expr.name}' does not exist.", expr.position, actual=expr.name)
                return target.fields[expr.name]
            if isinstance(target, RegexMatchValue) and expr.name in ("text", "start", "end"):
                return getattr(target, expr.name)
            if isinstance(target, ExecResultValue) and expr.name in ("exit_code", "stdout", "stderr", "stdout_bytes", "stderr_bytes", "timed_out", "duration", "command"):
                return getattr(target, expr.name)
            if isinstance(target, HttpResponseValue) and expr.name in ("status", "url", "headers", "bytes", "text", "encoding", "redirects", "cookies"):
                return getattr(target, expr.name)
            if isinstance(target, OAuthTokenValue) and expr.name in ("access_token", "token_type", "expires_in", "scope"):
                return getattr(target, expr.name)
            if isinstance(target, MailAddressValue) and expr.name in ("address", "display_name"):
                return getattr(target, expr.name)
            if isinstance(target, MailSendResultValue) and expr.name in ("provider", "message_id", "accepted_recipients"):
                return getattr(target, expr.name)
            if isinstance(target, NamespaceValue):
                if expr.name not in target.exports: raise error("E706", "Private or missing export", f"Module does not export '{expr.name}'.", expr.position, actual=expr.name)
                if expr.name in target.runtime.functions: return FunctionValue(target.runtime, expr.name)
                return target.runtime.globals.get(expr.name, expr.position)
            self._type_error(expr.position, "object or fixed-shape value", type_name(target), "Member access requires an object or fixed-shape value.")
        if isinstance(expr, MemberCallExpr):
            target = self._eval(expr.target)
            args = [self._eval(item) for item in expr.arguments]; named = {key: self._eval(value) for key, value in expr.named_arguments.items()}
            if isinstance(target, RegexMatchValue):
                if expr.name != "group": raise error("E213", "Unknown member method", f"regex_match_result has no method '{expr.name}'.", expr.position, actual=expr.name)
                if named or len(args) != 1: raise error("E207", "Argument count mismatch", "regex match group() requires exactly one positional index.", expr.position, expected="1", actual=str(len(args) + len(named)))
                index = args[0]
                if type(index) is not int or index < 0: self._type_error(expr.position, "non-negative integer", type_name(index), "regex match group index must be a non-negative integer.")
                if index == 0: return target.text
                if index > len(target.groups): raise error("E834", "Regex group out of range", "The requested capture group does not exist.", expr.position, expected=f"0..{len(target.groups)}", actual=str(index))
                return target.groups[index - 1]
            if not isinstance(target, NamespaceValue): self._type_error(expr.position, "namespace or fixed-shape value", type_name(target), "Member calls require an imported namespace or supported fixed-shape value.")
            if expr.name not in target.exports or (expr.name not in target.runtime.functions and expr.name not in target.runtime.error_categories): raise error("E706", "Private or missing export", f"Module does not export function or error '{expr.name}'.", expr.position, actual=expr.name)
            return target.runtime._call(expr.name, args, expr.position, named)
        if isinstance(expr, UnaryExpr):
            value = self._eval(expr.operand)
            if expr.operator in ("!", "not"): return not self._boolean(value, expr.position)
            if type(value) not in (int, float) or type(value) is bool: self._type_error(expr.position, "number", type_name(value), "Unary '-' requires a number.")
            return -value
        if isinstance(expr, BinaryExpr):
            left = self._eval(expr.left)
            if expr.operator == "&&": return self._boolean(left, expr.left.position) and self._boolean(self._eval(expr.right), expr.right.position)
            if expr.operator == "||": return self._boolean(left, expr.left.position) or self._boolean(self._eval(expr.right), expr.right.position)
            if expr.operator == "??": return left if left is not None else self._eval(expr.right)
            right = self._eval(expr.right); op = expr.operator
            if op in ("in", "not in"):
                contained = self._contains_operator(left, right, expr.position)
                return not contained if op == "not in" else contained
            if op in ("==", "!="):
                if left is not None and right is not None and type_name(left) != type_name(right):
                    if self._is_temporal(left) or self._is_temporal(right):
                        raise error("E408", "Invalid temporal operation", "Temporal equality requires matching temporal types.", expr.position, expected=type_name(left), actual=type_name(right))
                    self._type_error(expr.position, type_name(left), type_name(right), "Equality does not convert between types.")
                return (left == right) if op == "==" else (left != right)
            if self._is_temporal(left) or self._is_temporal(right):
                return self._temporal_binary(left, op, right, expr.position)
            if op == "+" and type(left) is str and type(right) is str: return left + right
            if op == "+" and isinstance(left, BytesValue) and isinstance(right, BytesValue):
                from .bytes_ops import MAX_BYTES_LENGTH
                if len(left.value) + len(right.value) > MAX_BYTES_LENGTH: raise error("E624", "Bytes size limit", f"bytes result cannot exceed {MAX_BYTES_LENGTH} bytes.", expr.position)
                return BytesValue(left.value + right.value)
            if op == "+" and type(left) is list and type(right) is list:
                left_type = list_element_type(left, expr.position); right_type = list_element_type(right, expr.position)
                if left_type and right_type and left_type != right_type:
                    self._type_error(expr.position, f"list[{left_type}]", f"list[{right_type}]", "List concatenation requires matching element types.")
                return left + right
            if op in ("+", "-", "*", "/", "//", "%", "**", ">", "<", ">=", "<="):
                if not self._numbers(left, right): self._type_error(expr.position, "number + number" if op == "+" else "number operands", f"{type_name(left)}, {type_name(right)}", f"Operator '{op}' received incompatible values.")
                if op in ("/", "//", "%") and right == 0: raise error("E301", "Division by zero", f"Operator '{op}' cannot use zero as its right operand.", expr.position, actual="0")
                if op == "//" and (type(left) is not int or type(right) is not int):
                    self._type_error(expr.position, "integer number operands", f"{left!r}, {right!r}", "Operator '//' requires integer-valued numbers.")
                if op == "**": return self._power(left, right, expr.position)
                return {"+": lambda: left+right, "-": lambda: left-right, "*": lambda: left*right, "/": lambda: left/right, "//": lambda: left//right, "%": lambda: left%right, ">": lambda: left>right, "<": lambda: left<right, ">=": lambda: left>=right, "<=": lambda: left<=right}[op]()
        raise RuntimeError(f"Unknown AST node: {expr!r}")

    def _call(self, name, args, position, named=None):
        named = named or {}
        if name in self.error_categories:
            if named or len(args) != 1: raise error("E207", "Argument count mismatch", f"Custom error '{name}' requires one positional message.", position, expected="1", actual=str(len(args) + len(named)))
            if type(args[0]) is not str: self._type_error(position, "string message", type_name(args[0]), f"Custom error '{name}' requires a string message.")
            return ErrorValue(name, args[0])
        builtin = BUILTINS.get(name)
        if builtin is not None:
            return builtin.call(args, position, self, named)
        function = self.functions.get(name)
        if function is None: raise error("E206", "Undefined function", f"Function '{name}' is not defined.", position, actual=name)
        if named: raise error("E207", "Unsupported named argument", f"Function '{name}' does not declare named arguments.", position, actual=next(iter(named)))
        if len(args) != len(function.parameters): raise error("E207", "Argument count mismatch", f"Function '{name}' requires {len(function.parameters)} argument(s).", position, expected=str(len(function.parameters)), actual=str(len(args)))
        signature = tuple((type_name(value), list_element_type(value, position) if type(value) is list else None) for value in args)
        inferred = self.function_parameter_types.get(name)
        if inferred is None:
            self.function_parameter_types[name] = signature
        else:
            updated = list(inferred)
            for index, (parameter, expected_type, actual_type) in enumerate(zip(function.parameters, inferred, signature)):
                if expected_type[0] != actual_type[0] or (expected_type[1] and actual_type[1] and expected_type[1] != actual_type[1]):
                    expected = expected_type[0] + (f"[{expected_type[1]}]" if expected_type[1] else "")
                    actual = actual_type[0] + (f"[{actual_type[1]}]" if actual_type[1] else "")
                    raise error("E208", "Function parameter type mismatch", f"Parameter '{parameter}' of function '{name}' was inferred as {expected} by its first call.", position, expected=expected, actual=actual)
                if expected_type[0] == "list" and expected_type[1] is None and actual_type[1] is not None:
                    updated[index] = actual_type
            self.function_parameter_types[name] = tuple(updated)
        previous = self.environment; self.environment = Environment(self.globals)
        try:
            for param, value in zip(function.parameters, args): self.environment.assign(param, value, position)
            try: self._execute_all(function.body)
            except Returned as result: return result.value
            return None
        finally: self.environment = previous

    def call_function_value(self, value, arguments, position):
        self.validate_function_value(value, position)
        return value.runtime._call(value.name, arguments, position)

    @staticmethod
    def validate_function_value(value, position):
        if not isinstance(value, FunctionValue):
            Interpreter._type_error(position, "function", type_name(value), "A higher-order list operation requires a function reference.")

    @staticmethod
    def validate_list(value, position):
        return list_element_type(value, position)

    @staticmethod
    def _numbers(left, right): return type(left) in (int, float) and type(left) is not bool and type(right) in (int, float) and type(right) is not bool

    def _contains_operator(self, needle, container, position):
        if type(container) is str:
            if type(needle) is not str: self._type_error(position, "string in string", f"{type_name(needle)} in string", "String containment requires a string search value.")
            return needle in container
        if type(container) is list:
            element_type = list_element_type(container, position)
            if element_type is not None and type_name(needle) != element_type:
                self._type_error(position, element_type, type_name(needle), "List containment does not convert the search value.")
            return needle in container
        if isinstance(container, ObjectValue):
            if type(needle) is not str: self._type_error(position, "string object key", type_name(needle), "Object containment tests field names.")
            return needle in container.fields
        if isinstance(container, BytesValue):
            if isinstance(needle, BytesValue): return needle.value in container.value
            if type(needle) is int and 0 <= needle <= 255: return needle in container.value
            self._type_error(position, "bytes or integer byte 0..255", type_name(needle), "Bytes containment requires bytes or one integer byte.")
        self._type_error(position, "string, list, object, or bytes container", type_name(container), "Operator 'in' requires a supported container on the right.")

    @staticmethod
    def _power(base, exponent, position):
        try: result = base ** exponent
        except (ValueError, OverflowError, ZeroDivisionError):
            raise error("E308", "Math domain error", "Operator '**' operands are outside the supported real, finite domain.", position, actual=f"{base}, {exponent}")
        if type(result) is complex or (type(result) is float and not math.isfinite(result)):
            raise error("E308", "Math domain error", "Operator '**' result must be real and finite.", position, actual=repr(result))
        return result
    @staticmethod
    def is_number(value): return type(value) in (int, float) and type(value) is not bool
    @staticmethod
    def type_name(value): return type_name(value)
    @staticmethod
    def type_error(position, expected, actual, description): Interpreter._type_error(position, expected, actual, description)
    @staticmethod
    def display(value): return Interpreter._display(value)
    def current_time(self):
        value = self.clock()
        if not isinstance(value, PyDateTime) or value.tzinfo is None:
            raise RuntimeError("Injected Separan clock must return a timezone-aware datetime")
        return value.astimezone(py_timezone.utc).replace(microsecond=(value.microsecond // 1000) * 1000)

    @staticmethod
    def _is_temporal(value):
        return isinstance(value, (DatetimeValue, LocalDatetimeValue, TimezoneValue, DurationValue))

    def _temporal_binary(self, left, operator, right, position):
        if operator in (">", "<", ">=", "<="):
            if type(left) is type(right) and isinstance(left, (DatetimeValue, LocalDatetimeValue, DurationValue)):
                return {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[operator]
            raise error("E408", "Invalid temporal operation", f"Operator '{operator}' requires matching orderable temporal types.", position, actual=f"{type_name(left)} {operator} {type_name(right)}")
        if operator == "+":
            if isinstance(left, DatetimeValue) and isinstance(right, DurationValue): return self._shift_datetime(left, right.milliseconds, position)
            if isinstance(left, DurationValue) and isinstance(right, DatetimeValue): return self._shift_datetime(right, left.milliseconds, position)
            if isinstance(left, DurationValue) and isinstance(right, DurationValue): return self._duration_result(left.milliseconds + right.milliseconds, position)
        if operator == "-":
            if isinstance(left, DatetimeValue) and isinstance(right, DurationValue): return self._shift_datetime(left, -right.milliseconds, position)
            if isinstance(left, DatetimeValue) and isinstance(right, DatetimeValue):
                delta = left.instant_utc - right.instant_utc
                return DurationValue(delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000)
            if isinstance(left, DurationValue) and isinstance(right, DurationValue): return self._duration_result(left.milliseconds - right.milliseconds, position)
        if operator == "*":
            if isinstance(left, DurationValue): return duration_scaled(left, right, False, position)
            if isinstance(right, DurationValue): return duration_scaled(right, left, False, position)
        if operator == "/" and isinstance(left, DurationValue):
            if isinstance(right, DurationValue):
                if right.milliseconds == 0: raise error("E301", "Division by zero", "A duration cannot be divided by a zero duration.", position)
                return left.milliseconds / right.milliseconds
            return duration_scaled(left, right, True, position)
        raise error("E408", "Invalid temporal operation", f"Operator '{operator}' is not defined for these temporal types.", position, actual=f"{type_name(left)} {operator} {type_name(right)}")

    @staticmethod
    def _duration_result(milliseconds, position):
        if not -(2**63) <= milliseconds <= 2**63 - 1:
            raise error("E407", "Duration overflow", "Duration result exceeds the signed 64-bit millisecond range.", position, actual=str(milliseconds))
        return DurationValue(milliseconds)

    @staticmethod
    def _shift_datetime(value, milliseconds, position):
        try:
            return DatetimeValue(value.instant_utc + timedelta(milliseconds=milliseconds), value.zone)
        except OverflowError:
            raise error("E401", "Datetime overflow", "Datetime arithmetic exceeded years 0001 through 9999.", position)
    def _boolean(self, value, position):
        if type(value) is not bool: self._type_error(position, "boolean", type_name(value), "Conditions must evaluate to boolean.")
        return value
    @staticmethod
    def _type_error(position, expected, actual, description): raise error("E201", "Type error", description, position, expected=expected, actual=actual)
    @staticmethod
    def _display(value):
        if isinstance(value, SystemContextValue): return "system:[READONLY]"
        if isinstance(value, BoardValue): return f"board:{value.profile.id}"
        if isinstance(value, PinNamespaceValue): return "pin:[READONLY]"
        if isinstance(value, PinValue): return f"pin:{value.definition.name}"
        if isinstance(value, BusValue): return f"{value.kind}_bus:{value.index}"
        if isinstance(value, IpAddressValue): return str(value.value)
        if isinstance(value, NetworkInterfaceValue): return f"network_interface:{value.fields['name']}"
        if isinstance(value, TcpConnectionValue): return f"tcp_connection:{value.host}:{value.port}{' [CLOSED]' if value.closed else ''}"
        if isinstance(value, UdpSocketValue): return f"udp_socket:{value.local_address or 'unbound'}:{value.local_port or 0}{' [CLOSED]' if value.closed else ''}"
        if isinstance(value, RegexMatchValue): return value.text
        if isinstance(value, ObjectValue): return "object:" + ", ".join(f"{key}={Interpreter._display(field)}" for key, field in value.fields.items())
        if isinstance(value, NamespaceValue): return "namespace"
        if isinstance(value, FunctionValue): return f"<function:{value.name}>"
        if isinstance(value, ErrorValue): return f"{value.category}: {value.message}"
        if isinstance(value, ExecResultValue): return f"exec_result(exit_code={value.exit_code})"
        if isinstance(value, HttpProfileValue): return f"http_profile:{value.name}"
        if isinstance(value, HttpResponseValue): return f"http_response(status={value.status})"
        if isinstance(value, SecretValue): return "[REDACTED]"
        if isinstance(value, HttpAuthValue): return "http_auth:[REDACTED]"
        if isinstance(value, OAuthTokenValue): return "oauth_token:[REDACTED]"
        if isinstance(value, CookieJarValue): return "cookie_jar:[REDACTED]"
        if isinstance(value, MailAddressValue): return f"mail_address:{value.address}"
        if isinstance(value, MailMessageValue): return f"mail_message(recipients={len(value.to) + len(value.cc) + len(value.bcc)}, attachments={len(value.attachments)})"
        if isinstance(value, MailSenderValue): return f"mail_sender(provider={value.provider}, credentials=[REDACTED])"
        if isinstance(value, MailSendResultValue): return f"mail_send_result(provider={value.provider}, accepted={value.accepted_recipients})"
        if isinstance(value, XmlDocumentValue): return f"xml_document(root={value.root.tag})"
        if isinstance(value, XmlElementValue): return f"xml_element(name={value.element.tag})"
        if isinstance(value, DbConnectionValue): return f"db_connection(driver={value.driver}, database=[REDACTED])"
        if isinstance(value, DhcpServerValue): return f"dhcp_server(interface={value.interface_name}, state={'stopped' if value.closed else 'running'})"
        if isinstance(value, DnsServerValue): return f"dns_server(interface={value.interface_name}, state={'stopped' if value.closed else 'running'})"
        if isinstance(value, BytesValue): return "0x" + value.value.hex()
        if isinstance(value, DatetimeValue): return format_datetime(value)
        if isinstance(value, LocalDatetimeValue): return format_local(value)
        if isinstance(value, TimezoneValue): return value.name
        if isinstance(value, DurationValue): return format_duration(value)
        if value is None: return "null"
        if type(value) is bool: return "true" if value else "false"
        if type(value) is list: return "[" + ", ".join(Interpreter._display(v) for v in value) + "]"
        return str(value)

    def close_resources(self):
        for resource in reversed(self.network_resources):
            if not resource.closed:
                try:
                    closer = getattr(resource, "close", None)
                    if closer is not None: closer()
                    else: resource.native.close()
                except Exception: pass
                resource.closed = True
        for connection in reversed(self.database_connections):
            if not connection.closed:
                try: connection.native.close()
                except Exception: pass
                connection.closed = True; connection.transaction_active = False
