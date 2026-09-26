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
from .runtime_values import EmptyValue, EmptysValue, VoidResult, EMPTY, EMPTYS, VOID
from .token import SourcePosition


@dataclass(frozen=True)
class NamespaceValue:
    runtime: object
    exports: frozenset


@dataclass(frozen=True)
class LogicValue:
    runtime: object
    name: str


def type_name(value):
    if isinstance(value, EmptyValue): return value.declared_type or "EMPTY"
    if isinstance(value, EmptysValue): return "EMPTYS"
    if isinstance(value, VoidResult): return "VOID"
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
    if isinstance(value, LogicValue): return "logic"
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
    element_type: object = None
    constant: bool = False
    declaration_position: object = None


class Environment:
    def __init__(self, parent=None): self.parent, self.values = parent, {}
    def assign(self, name, value, position):
        if isinstance(value, VoidResult):
            raise error("E126", "VOID assignment", "VOID does not represent a value and cannot be assigned.", position,
                        expected="a value", actual="VOID")
        if name in self.values:
            old = self.values[name]
            if old.constant:
                raise error("E211", "Constant reassignment", f"Constant '{name}' cannot be assigned again.", position, expected="no reassignment", actual=name, related=old.declaration_position)
            if isinstance(value, EmptysValue):
                old.value = clear_container_value(old.value, old.declared_type, old.element_type, position)
                return
            if isinstance(value, EmptyValue):
                old.value = EmptyValue(old.declared_type, old.element_type)
                return
            value_type = type_name(value)
            element_type = list_element_type(value, position) if value_type == "list" else None
            if old.declared_type != value_type:
                raise error("E201", "Type error", f"Variable '{name}' has fixed type {old.declared_type} and cannot receive {value_type}.", position, expected=old.declared_type, actual=value_type)
            if value_type == "list" and not type_specs_compatible(old.element_type, element_type):
                raise error("E201", "Type error", f"List variable '{name}' has fixed element type {type_spec_text(old.element_type)}.", position,
                            expected=type_spec_text(old.element_type), actual=type_spec_text(element_type))
            if value_type == "list":
                element_type = merge_type_specs(old.element_type, element_type)
                value = normalize_list_values(value, element_type, position)
            old.value = value
            old.element_type = merge_type_specs(old.element_type, element_type)
        else:
            if isinstance(value, EmptysValue):
                raise error("E133", "EMPTYS container required", f"Variable '{name}' has no declared container to clear.", position,
                            expected="an existing list or object binding", actual="EMPTYS")
            if isinstance(value, EmptyValue):
                if value.declared_type is None:
                    raise error("E129", "EMPTY type required", f"Variable '{name}' cannot infer a type from EMPTY.", position,
                                expected=f"type {name} = EMPTY", actual=f"{name} = EMPTY")
                self.values[name] = Binding(value, value.declared_type, value.element_type, False, position)
                return
            value_type = type_name(value)
            element_type = list_element_type(value, position) if value_type == "list" else None
            if value_type == "list": value = normalize_list_values(value, element_type, position)
            self.values[name] = Binding(value, value_type, element_type, False, position)
    def define_const(self, name, value, position):
        if isinstance(value, VoidResult):
            raise error("E126", "VOID assignment", "VOID does not represent a value and cannot be assigned.", position,
                        expected="a value", actual="VOID")
        if name in self.values:
            previous = self.values[name]
            raise error("E210", "Duplicate binding", f"Name '{name}' is already defined in this scope.", position, expected="a unique constant name", actual=name, related=previous.declaration_position)
        if isinstance(value, (EmptyValue, EmptysValue)):
            raise error("E130", "EMPTY constant", "A constant must contain a value and cannot be initialized with EMPTY.", position,
                        expected="a concrete constant value", actual=type_name(value))
        value_type = type_name(value)
        element_type = list_element_type(value, position) if value_type == "list" else None
        self.values[name] = Binding(value, value_type, element_type, True, position)
    def define_typed(self, name, declared_type, declared_element_type, value, constant, position):
        if isinstance(value, VoidResult):
            raise error("E126", "VOID assignment", "VOID does not represent a value and cannot be assigned.", position,
                        expected=declared_type, actual="VOID")
        if name in self.values:
            previous = self.values[name]
            raise error("E210", "Duplicate binding", f"Name '{name}' is already defined in this scope.", position,
                        expected="a unique variable name", actual=name, related=previous.declaration_position)
        if constant and isinstance(value, (EmptyValue, EmptysValue)):
            raise error("E130", "EMPTY constant", "A constant must contain a value and cannot be initialized with EMPTY.", position,
                        expected="a concrete constant value", actual=type_name(value))
        value = prepare_typed_value(name, declared_type, declared_element_type, value, position)
        self.values[name] = Binding(value, declared_type, declared_element_type, constant, position)
    def get(self, name, position):
        if name in self.values: return self.values[name].value
        if self.parent: return self.parent.get(name, position)
        raise error("E202", "Undefined variable", f"Variable '{name}' is not defined.", position, actual=name)
    def contains(self, name):
        return name in self.values or bool(self.parent and self.parent.contains(name))
    def binding(self, name, position):
        if name in self.values: return self.values[name]
        if self.parent: return self.parent.binding(name, position)
        raise error("E202", "Undefined variable", f"Variable '{name}' is not defined.", position, actual=name)
    def assign_indexes(self, name, indexes, value, position):
        binding = self.binding(name, position)
        if binding.constant:
            raise error("E211", "Constant reassignment", f"Constant '{name}' cannot be changed through an index.", position,
                        expected="no reassignment", actual=name, related=binding.declaration_position)
        if binding.declared_type != "list" or type(binding.value) is not list:
            raise error("E201", "Type error", f"Indexed assignment requires a present list variable, but '{name}' is {binding.declared_type}.", position,
                        expected="list", actual=binding.declared_type)
        if not indexes:
            raise error("E302", "Index required", "Indexed assignment requires at least one list index.", position)

        def update(container, depth, expected):
            index = indexes[depth]
            if type(index) is not int or index < 0:
                raise error("E201", "Type error", "List indexes must be non-negative integers.", position,
                            expected="non-negative integer", actual=repr(index))
            if index >= len(container):
                raise error("E302", "Index out of range", f"Index {index} is outside a list of length {len(container)}.", position,
                            expected=f"0..{len(container)-1}", actual=str(index))
            current = container[index]
            if depth + 1 < len(indexes):
                if isinstance(current, EmptyValue):
                    raise error("E131", "EMPTY value use", "An EMPTY list slot has no nested shape to index.", position,
                                expected="a present nested list", actual="EMPTY")
                if type(current) is not list:
                    raise error("E201", "Type error", "Nested indexed assignment requires a list at every level.", position,
                                expected="list", actual=type_name(current))
                child_expected = expected[1] if is_list_type_spec(expected) else list_element_type(current, position)
                replacement, adopted_child = update(current, depth + 1, child_expected)
                adopted = ("list", adopted_child)
            else:
                if isinstance(value, EmptysValue):
                    if not isinstance(current, (list, ObjectValue)):
                        raise error("E133", "EMPTYS container required", "EMPTYS can clear only a container-valued list slot.", position,
                                    expected="list or object slot", actual=type_name(current))
                    current_element = expected[1] if is_list_type_spec(expected) else None
                    replacement = clear_container_value(current, type_name(current), current_element, position)
                    adopted = expected
                elif isinstance(value, EmptyValue):
                    slot_type = expected or value_type_spec(current, position)
                    replacement = empty_for_type_spec(slot_type)
                    adopted = slot_type
                else:
                    actual = value_type_spec(value, position)
                    if expected is not None and not type_specs_compatible(expected, actual):
                        raise error("E201", "Type error", f"List variable '{name}' requires elements of type {type_spec_text(expected)}.", position,
                                    expected=type_spec_text(expected), actual=type_spec_text(actual))
                    adopted = merge_type_specs(expected, actual)
                    replacement = normalize_value_for_type_spec(value, adopted, position)
            updated = list(container); updated[index] = replacement; return updated, merge_type_specs(expected, adopted)

        binding.value, binding.element_type = update(binding.value, 0, binding.element_type)
        binding.value = normalize_list_values(binding.value, binding.element_type, position)


def is_list_type_spec(value):
    return isinstance(value, tuple) and len(value) == 2 and value[0] == "list"


def type_spec_text(value):
    if is_list_type_spec(value): return f"list<{type_spec_text(value[1])}>"
    return value or "unknown"


def retained_empty_type(value):
    if value.declared_type is None: return None
    return ("list", value.element_type) if value.declared_type == "list" else value.declared_type


def value_type_spec(value, position):
    if isinstance(value, EmptyValue): return retained_empty_type(value)
    if type(value) is list: return ("list", list_element_type(value, position))
    return type_name(value)


def type_specs_compatible(expected, actual):
    if expected is None or actual is None: return True
    if is_list_type_spec(expected) and is_list_type_spec(actual):
        return type_specs_compatible(expected[1], actual[1])
    return expected == actual


def merge_type_specs(left, right):
    if left is None: return right
    if right is None: return left
    if is_list_type_spec(left) and is_list_type_spec(right):
        return ("list", merge_type_specs(left[1], right[1]))
    return left


def empty_for_type_spec(spec, *, external=False):
    if is_list_type_spec(spec): return EmptyValue("list", spec[1], external)
    return EmptyValue(spec, external=external)


def normalize_value_for_type_spec(value, spec, position):
    if isinstance(value, EmptyValue): return empty_for_type_spec(spec, external=value.external)
    if is_list_type_spec(spec):
        if type(value) is not list:
            raise error("E201", "Type error", "Nested list element has an incompatible type.", position,
                        expected=type_spec_text(spec), actual=type_name(value))
        return normalize_list_values(value, spec[1], position)
    if type_name(value) != spec:
        raise error("E203", "Heterogeneous list", "All list elements must have the same type.", position,
                    expected=type_spec_text(spec), actual=type_name(value))
    return value


def list_element_type(value, position):
    if not value: return None
    if any(isinstance(item, VoidResult) for item in value):
        raise error("E127", "VOID value use", "VOID cannot be stored in a list because it does not represent a value.", position,
                    expected="list elements", actual="VOID")
    if any(isinstance(item, EmptysValue) for item in value):
        raise error("E133", "EMPTYS list element", "EMPTYS applies to a whole container and cannot be stored as an element.", position,
                    expected="EMPTY or a concrete element", actual="EMPTYS")
    found = None
    for item in value:
        actual = value_type_spec(item, position)
        if actual is None: continue
        if found is not None and not type_specs_compatible(found, actual):
            raise error("E203", "Heterogeneous list", "All list elements must have the same type, including retained EMPTY types.", position,
                        expected=type_spec_text(found), actual=type_spec_text(actual))
        found = merge_type_specs(found, actual)
    return found


def normalize_list_values(values, element_type, position):
    if values and element_type is None:
        if all(isinstance(item, EmptyValue) and item.external for item in values): return list(values)
        raise error("E134", "List element type required", "A source list containing only EMPTY elements requires an explicit element type.", position,
                    expected="list<type>", actual="list[EMPTY]")
    result = []
    for item in values:
        result.append(normalize_value_for_type_spec(item, element_type, position))
    return result


def container_is_emptys(value):
    if type(value) is list:
        return not value or all(isinstance(item, EmptyValue) or isinstance(item, (list, ObjectValue)) and container_is_emptys(item) for item in value)
    if isinstance(value, ObjectValue):
        return not value.fields or all(isinstance(item, EmptyValue) or isinstance(item, (list, ObjectValue)) and container_is_emptys(item) for item in value.fields.values())
    return False


def clear_container_value(value, declared_type, element_type, position):
    if declared_type == "list":
        if isinstance(value, EmptyValue): return []
        if type(value) is not list:
            raise error("E133", "EMPTYS container required", "EMPTYS requires a present list structure.", position,
                        expected="list", actual=type_name(value))
        result = []
        for item in value:
            if isinstance(item, (list, ObjectValue)):
                nested_element = element_type[1] if is_list_type_spec(element_type) and type(item) is list else None
                result.append(clear_container_value(item, type_name(item), nested_element, position))
            else:
                result.append(empty_for_type_spec(element_type or value_type_spec(item, position)))
        return result
    if declared_type == "object":
        if not isinstance(value, ObjectValue):
            raise error("E133", "EMPTYS container required", "An EMPTY object has no field structure for EMPTYS to preserve.", position,
                        expected="a present object", actual=type_name(value))
        fields, field_types = {}, dict(value.field_types)
        for key, item in value.fields.items():
            expected = field_types.get(key, (type_name(item), None))
            field_types[key] = expected
            if isinstance(item, (list, ObjectValue)): fields[key] = clear_container_value(item, type_name(item), expected[1], position)
            else:
                field_spec = ("list", expected[1]) if expected[0] == "list" else expected[0]
                fields[key] = empty_for_type_spec(field_spec)
        return ObjectValue.create(fields, field_types)
    raise error("E133", "EMPTYS scalar", "EMPTYS can only be assigned to a list or object.", position,
                expected="list or object", actual=declared_type)


def prepare_typed_value(name, declared_type, declared_element_type, value, position):
    if isinstance(value, EmptysValue):
        if declared_type == "list": return []
        raise error("E133", "EMPTYS container required", f"'{name}' has no existing container structure to clear.", position,
                    expected="list<type> or an existing object", actual=declared_type)
    if isinstance(value, EmptyValue):
        if value.declared_type not in (None, declared_type):
            raise error("E201", "Type error", f"'{name}' requires {declared_type}, but the EMPTY value retains {value.declared_type}.", position,
                        expected=declared_type, actual=value.declared_type)
        return EmptyValue(declared_type, declared_element_type)
    value_type = type_name(value)
    if value_type != declared_type:
        raise error("E201", "Type error", f"'{name}' is declared as {declared_type} and cannot receive {value_type}.", position,
                    expected=declared_type, actual=value_type)
    element_type = list_element_type(value, position) if value_type == "list" else None
    if declared_type == "list" and not type_specs_compatible(declared_element_type, element_type):
        raise error("E201", "Type error", f"List '{name}' requires elements of type {type_spec_text(declared_element_type)}.", position,
                    expected=type_spec_text(declared_element_type), actual=type_spec_text(element_type))
    if declared_type == "list": return normalize_list_values(value, declared_element_type, position)
    return value


class Returned(Exception):
    def __init__(self, value): self.value = value


class Interpreter:
    def __init__(self, output=None, clock=None, command_arguments=None, script_path=None, project_root=None, environment_variables=None, module_cache=None, import_stack=None, capabilities=None, input_stream=None, error_output=None, http_transport=None, secret_provider=None, cookie_key_provider=None, mail_transport=None, embedded_context=None, board_id=None, embedded_adapter=None, network_adapter=None, host_functions=None):
        self.output = output or StringIO()
        self.input_stream = input_stream or StringIO()
        self.error_output = error_output or StringIO()
        self.globals = Environment()
        self.environment = self.globals
        self.logics = {}
        self.host_functions = dict(host_functions or {})
        conflicts = sorted(set(self.host_functions) & set(BUILTINS))
        if conflicts:
            raise ValueError(f"Host functions cannot replace Separan built-ins: {', '.join(conflicts)}")
        self.error_categories = set()
        self.http_routes = []
        self.http_static_mounts = []
        self.logic_parameter_types = {}
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
            if isinstance(stmt, LogicDecl):
                if stmt.name in BUILTINS or stmt.name in self.host_functions:
                    raise error("E209", "Reserved function name", f"Function '{stmt.name}' is a built-in and cannot be redefined.", stmt.position, actual=stmt.name)
                if stmt.name in self.logics:
                    raise error("E204", "Duplicate function", f"Function '{stmt.name}' is already defined.", stmt.position, actual=stmt.name)
                self.logics[stmt.name] = stmt
            elif isinstance(stmt, ErrorDecl):
                if stmt.name in BUILTINS or stmt.name in self.host_functions or stmt.name in self.error_categories or any(item.name == stmt.name for item in program.statements if isinstance(item, LogicDecl)):
                    raise error("E122", "Duplicate error name", f"Custom error name '{stmt.name}' conflicts with an existing declaration or built-in.", stmt.position, actual=stmt.name)
                self.error_categories.add(stmt.name)
            elif isinstance(stmt, HttpRouteDecl):
                try: compiled = compile_path(stmt.path)
                except ValueError as exc: raise error("E892", "Invalid route path", str(exc), stmt.position, actual=stmt.path)
                if any(route.method == stmt.method and route.path == stmt.path for route, _ in self.http_routes): raise error("E896", "Duplicate HTTP route", "HTTP method and path must be unique.", stmt.position, actual=f"{stmt.method} {stmt.path}")
                self.http_routes.append((stmt, compiled))
        main = self.logics.get("main")
        if main and main.parameters:
            raise error("E205", "Invalid main function", "main must have zero parameters in v0.1.", main.position, expected="main()", actual=f"main({', '.join(main.parameters)})")
        for stmt in program.statements:
            if not isinstance(stmt, (LogicDecl, HttpRouteDecl, ErrorDecl)): self._execute(stmt)
        if invoke_main and main: self._call("main", [], main.position)
        return self.output.getvalue() if hasattr(self.output, "getvalue") else None

    def invoke(self, name, arguments=None, named_arguments=None):
        """Invoke a loaded Separan function from an explicit host boundary."""
        position = SourcePosition(self.script_path or "<host>", 1, 1, f"host invoke {name}")
        return self._call(name, list(arguments or []), position, dict(named_arguments or {}))

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
        elif isinstance(stmt, IndexAssignment): self.environment.assign_indexes(stmt.name, [self._eval(index) for index in stmt.indexes], self._eval(stmt.value), stmt.position)
        elif isinstance(stmt, ConstDeclaration): self.environment.define_const(stmt.name, self._eval(stmt.value), stmt.position)
        elif isinstance(stmt, TypedDeclaration): self.environment.define_typed(stmt.name, stmt.declared_type, stmt.element_type, self._eval(stmt.value), stmt.constant, stmt.position)
        elif isinstance(stmt, PrintStmt): self.output.write(self._display_value(self._eval(stmt.value), stmt.position) + "\n")
        elif isinstance(stmt, PrintErrorStmt): self.error_output.write(self._display_value(self._eval(stmt.value), stmt.position) + "\n")
        elif isinstance(stmt, ExpressionStmt): self._eval(stmt.expression)
        elif isinstance(stmt, ReturnStmt): raise Returned(VOID if stmt.value is None else self._eval(stmt.value))
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
        fields, field_types = {}, {}
        for entry in stmt.entries:
            if isinstance(entry, ObjectField):
                value = self._eval(entry.value)
                if entry.declared_type is not None:
                    value = prepare_typed_value(entry.name, entry.declared_type, entry.element_type, value, entry.position)
                    field_types[entry.name] = (entry.declared_type, entry.element_type)
                elif isinstance(value, EmptyValue):
                    raise error("E129", "EMPTY type required", f"Object field '{entry.name}' cannot infer a type from EMPTY.", entry.position,
                                expected=f"type {entry.name} = EMPTY", actual=f"{entry.name} = EMPTY")
                fields[entry.name] = value
            else:
                fields[entry.name] = self._build_data_block(entry)
                field_types[entry.name] = (type_name(fields[entry.name]), None)
        return ObjectValue.create(fields, field_types)

    @staticmethod
    def prepare_object_field(name, expected, value, position, current=None, current_exists=False):
        if isinstance(value, EmptysValue):
            if not current_exists:
                raise error("E133", "EMPTYS container required", f"New object field '{name}' has no container structure to clear.", position,
                            expected="an existing list or object field", actual="EMPTYS")
            return clear_container_value(current, expected[0] if expected else type_name(current), expected[1] if expected else None, position)
        if expected is None:
            if isinstance(value, EmptyValue):
                raise error("E129", "EMPTY type required", f"New object field '{name}' cannot infer a type from EMPTY.", position,
                            expected="a concrete value", actual="EMPTY")
            return value
        return prepare_typed_value(name, expected[0], expected[1], value, position)

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
            exports = frozenset([item.name for item in program.statements if isinstance(item, (LogicDecl, ConstDeclaration, TypedDeclaration, ErrorDecl))])
            namespace = NamespaceValue(module, exports); self.module_cache[key] = namespace
        self.environment.define_const(stmt.alias, namespace, stmt.position)

    def _eval(self, expr):
        if isinstance(expr, LiteralExpr): return expr.value
        if isinstance(expr, GroupExpr): return self._eval(expr.expression)
        if isinstance(expr, EmptyTestExpr):
            result = isinstance(self._eval(expr.operand), EmptyValue)
            return not result if expr.negated else result
        if isinstance(expr, EmptysTestExpr):
            result = container_is_emptys(self._eval(expr.operand))
            return not result if expr.negated else result
        if isinstance(expr, PositionSelectorExpr):
            raise error("E136", "Position selector context", f"'{expr.name}' is valid only as a list shape position.", expr.position,
                        expected="list_insert/list_remove position", actual=expr.name)
        if isinstance(expr, VariableExpr):
            if self.environment.contains(expr.name): return self.environment.get(expr.name, expr.position)
            if expr.name in self.logics or expr.name in BUILTINS or expr.name in self.host_functions: return LogicValue(self, expr.name)
            return self.environment.get(expr.name, expr.position)
        if isinstance(expr, ListExpr):
            values = [self._eval(e) for e in expr.elements]; list_element_type(values, expr.position); return values
        if isinstance(expr, CallExpr):
            if expr.callee in ("list_insert", "list_remove_horizontal", "list_remove_vertical") or expr.callee == "list_remove" and len(expr.arguments) == 3:
                return self._list_shape_call(expr)
            positional = [self._eval(a) for a in expr.arguments]
            named = {name: self._eval(value) for name, value in expr.named_arguments.items()}
            return self._call(expr.callee, positional, expr.position, named)
        if isinstance(expr, IndexExpr):
            target, index = self._eval(expr.target), self._eval(expr.index)
            if isinstance(target, EmptyValue) or isinstance(index, EmptyValue):
                raise error("E131", "EMPTY value use", "EMPTY cannot be used for list indexing.", expr.position,
                            expected="a present list and index", actual="EMPTY")
            if type(target) is not list: self._type_error(expr.position, "list", type_name(target), "Only lists support indexing in v0.1.")
            if type(index) is not int or index < 0: self._type_error(expr.index.position, "non-negative integer", self._display(index), "List indexes must be non-negative integers.")
            if index >= len(target): raise error("E302", "Index out of range", f"Index {index} is outside a list of length {len(target)}.", expr.index.position, expected=f"0..{len(target)-1}", actual=str(index))
            return target[index]
        if isinstance(expr, MemberExpr):
            target = self._eval(expr.target)
            if isinstance(target, EmptyValue):
                raise error("E131", "EMPTY value use", "EMPTY has no members because it has no current value.", expr.position,
                            expected="a present object", actual="EMPTY")
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
                if expr.name in target.runtime.logics: return LogicValue(target.runtime, expr.name)
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
            if expr.name not in target.exports or (expr.name not in target.runtime.logics and expr.name not in target.runtime.error_categories): raise error("E706", "Private or missing export", f"Module does not export SEP or error '{expr.name}'.", expr.position, actual=expr.name)
            return target.runtime._call(expr.name, args, expr.position, named)
        if isinstance(expr, UnaryExpr):
            value = self._eval(expr.operand)
            if isinstance(value, EmptysValue):
                raise error("E133", "EMPTYS value use", "EMPTYS is a container-clear operation and cannot participate in an operator.", expr.position,
                            expected="a present value", actual="EMPTYS")
            if isinstance(value, EmptyValue):
                raise error("E131", "EMPTY value use", "EMPTY cannot participate in an operator.", expr.position,
                            expected="a present value", actual="EMPTY")
            if isinstance(value, VoidResult):
                raise error("E127", "VOID value use", "VOID cannot participate in an operator.", expr.position,
                            expected="a value", actual="VOID")
            if expr.operator in ("!", "not"): return not self._boolean(value, expr.position)
            if type(value) not in (int, float) or type(value) is bool: self._type_error(expr.position, "number", type_name(value), "Unary '-' requires a number.")
            return -value
        if isinstance(expr, BinaryExpr):
            left = self._eval(expr.left)
            if isinstance(left, EmptysValue):
                raise error("E133", "EMPTYS value use", "EMPTYS is a container-clear operation and cannot participate in an operator.", expr.left.position,
                            expected="a present value", actual="EMPTYS")
            if expr.operator == "??":
                return self._eval(expr.right) if isinstance(left, EmptyValue) else left
            if isinstance(left, EmptyValue):
                raise error("E131", "EMPTY value use", "EMPTY cannot participate in an operator; use 'is EMPTY'.", expr.left.position,
                            expected="a present value", actual="EMPTY")
            if isinstance(left, VoidResult):
                raise error("E127", "VOID value use", "VOID cannot participate in an operator.", expr.left.position,
                            expected="a value", actual="VOID")
            if expr.operator == "&&": return self._boolean(left, expr.left.position) and self._boolean(self._eval(expr.right), expr.right.position)
            if expr.operator == "||": return self._boolean(left, expr.left.position) or self._boolean(self._eval(expr.right), expr.right.position)
            right = self._eval(expr.right); op = expr.operator
            if isinstance(right, EmptysValue):
                raise error("E133", "EMPTYS value use", "EMPTYS is a container-clear operation and cannot participate in an operator.", expr.right.position,
                            expected="a present value", actual="EMPTYS")
            if isinstance(right, EmptyValue):
                raise error("E131", "EMPTY value use", "EMPTY cannot participate in an operator; use 'is EMPTY'.", expr.right.position,
                            expected="a present value", actual="EMPTY")
            if isinstance(right, VoidResult):
                raise error("E127", "VOID value use", "VOID cannot participate in an operator.", expr.right.position,
                            expected="a value", actual="VOID")
            if op in ("in", "not in"):
                contained = self._contains_operator(left, right, expr.position)
                return not contained if op == "not in" else contained
            if op in ("==", "!="):
                if type_name(left) != type_name(right):
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
                if not type_specs_compatible(left_type, right_type):
                    self._type_error(expr.position, f"list[{type_spec_text(left_type)}]", f"list[{type_spec_text(right_type)}]", "List concatenation requires matching element types.")
                return left + right
            if op in ("+", "-", "*", "/", "//", "%", "**", ">", "<", ">=", "<="):
                if not self._numbers(left, right): self._type_error(expr.position, "number + number" if op == "+" else "number operands", f"{type_name(left)}, {type_name(right)}", f"Operator '{op}' received incompatible values.")
                if op in ("/", "//", "%") and right == 0: raise error("E301", "Division by zero", f"Operator '{op}' cannot use zero as its right operand.", expr.position, actual="0")
                if op == "//" and (type(left) is not int or type(right) is not int):
                    self._type_error(expr.position, "integer number operands", f"{left!r}, {right!r}", "Operator '//' requires integer-valued numbers.")
                if op == "**": return self._power(left, right, expr.position)
                return {"+": lambda: left+right, "-": lambda: left-right, "*": lambda: left*right, "/": lambda: left/right, "//": lambda: left//right, "%": lambda: left%right, ">": lambda: left>right, "<": lambda: left<right, ">=": lambda: left>=right, "<=": lambda: left<=right}[op]()
        raise RuntimeError(f"Unknown AST node: {expr!r}")

    @staticmethod
    def _shape_argument_count(name, actual, expected, position):
        if actual != expected:
            raise error("E207", "Argument count mismatch", f"Built-in function '{name}' requires {expected} argument(s).", position,
                        expected=str(expected), actual=str(actual))

    def _shape_integer(self, expression, name, position, *, positive=False):
        value = self._eval(expression)
        valid = type(value) is int and value >= (1 if positive else 0)
        if not valid:
            expectation = "positive integer" if positive else "non-negative integer"
            self._type_error(position, expectation, self._display(value), f"{name} must be a {expectation}.")
        return value

    def _resolve_shape_target(self, expression, position):
        if isinstance(expression, GroupExpr):
            return self._resolve_shape_target(expression.expression, position)
        if isinstance(expression, VariableExpr):
            binding = self.environment.binding(expression.name, expression.position)
            if binding.constant:
                raise error("E211", "Constant reassignment", f"Constant '{expression.name}' cannot be changed by a list shape operation.", position,
                            expected="mutable list", actual=expression.name, related=binding.declaration_position)
            value = binding.value
            if isinstance(value, EmptyValue):
                raise error("E131", "EMPTY value use", "An EMPTY list has no slot shape to modify.", position,
                            expected="a present list", actual="EMPTY")
            if type(value) is not list:
                self._type_error(position, "mutable list", type_name(value), "List shape operations require a list target.")
            return value, binding.element_type
        if isinstance(expression, IndexExpr):
            parent, parent_element = self._resolve_shape_target(expression.target, position)
            index = self._shape_integer(expression.index, "List target index", expression.index.position)
            if index >= len(parent):
                raise error("E603", "Invalid list shape range", "Indexed list shape target is outside the parent list.", expression.index.position,
                            expected=f"0..{len(parent)-1}", actual=str(index))
            value = parent[index]
            if isinstance(value, EmptyValue):
                raise error("E131", "EMPTY value use", "An EMPTY nested-list slot has no row shape to modify.", position,
                            expected="a present nested list", actual="EMPTY")
            if type(value) is not list:
                self._type_error(position, "nested list", type_name(value), "Indexed list shape targets must identify a nested list.")
            element_type = parent_element[1] if is_list_type_spec(parent_element) else list_element_type(value, position)
            return value, element_type
        raise error("E605", "List shape target required", "The first argument must directly name a mutable list variable or indexed row.", position,
                    expected="list variable or values[index]", actual=type(expression).__name__)

    def _shape_position(self, expression, values, count, name, position, *, insert):
        candidate = expression.expression if isinstance(expression, GroupExpr) else expression
        if isinstance(candidate, PositionSelectorExpr):
            if candidate.name == "front": return 0
            return len(values) if insert else len(values) - count
        index = self._shape_integer(expression, f"{name} position", position)
        maximum = len(values) if insert else len(values) - count
        if index > maximum:
            raise error("E603", "Invalid list shape range", f"{name} position and count exceed the target list shape.", position,
                        expected=f"0..{maximum}", actual=str(index))
        return index

    def _list_shape_call(self, expression):
        name = expression.callee
        if expression.named_arguments:
            raise error("E207", "Unsupported named argument", f"Built-in function '{name}' does not accept named arguments.", expression.position,
                        actual=next(iter(expression.named_arguments)))
        expected_count = 3 if name in ("list_insert", "list_remove") else 4
        self._shape_argument_count(name, len(expression.arguments), expected_count, expression.position)
        values, element_type = self._resolve_shape_target(expression.arguments[0], expression.position)

        if name in ("list_insert", "list_remove"):
            count = self._shape_integer(expression.arguments[2], f"{name} count", expression.arguments[2].position, positive=True)
            if name == "list_insert":
                if element_type is None:
                    element_type = list_element_type(values, expression.position)
                if element_type is None:
                    raise error("E134", "List element type required", "list_insert() creates typed EMPTY slots and requires a known element type.", expression.position,
                                expected="list<type>", actual="untyped empty list")
                index = self._shape_position(expression.arguments[1], values, count, name, expression.arguments[1].position, insert=True)
                values[index:index] = [empty_for_type_spec(element_type) for _ in range(count)]
            else:
                if count > len(values):
                    raise error("E603", "Invalid list shape range", "list_remove() count exceeds the target list length.", expression.arguments[2].position,
                                expected=f"1..{len(values)}", actual=str(count))
                index = self._shape_position(expression.arguments[1], values, count, name, expression.arguments[1].position, insert=False)
                del values[index:index + count]
            return VOID

        count = self._shape_integer(expression.arguments[3], f"{name} count", expression.arguments[3].position, positive=True)

        if name == "list_remove_horizontal":
            row_index = self._shape_integer(expression.arguments[1], f"{name} fixed row", expression.arguments[1].position)
            if row_index >= len(values):
                raise error("E603", "Invalid list shape range", f"{name} fixed row is outside the outer list.", expression.arguments[1].position,
                            expected=f"0..{len(values)-1}", actual=str(row_index))
            row = values[row_index]
            if isinstance(row, EmptyValue) or type(row) is not list:
                self._type_error(expression.position, "present nested list row", type_name(row), "Horizontal removal requires a present list row.")
            if count > len(row):
                raise error("E603", "Invalid list shape range", "Horizontal removal count exceeds the selected row shape.", expression.arguments[3].position,
                            expected=f"1..{len(row)}", actual=str(count))
            position = self._shape_position(expression.arguments[2], row, count, name, expression.arguments[2].position, insert=False)
            del row[position:position + count]
            return VOID

        column = self._shape_integer(expression.arguments[1], f"{name} fixed column", expression.arguments[1].position)
        if count > len(values):
            raise error("E603", "Invalid list shape range", "Vertical removal count exceeds the outer list shape.", expression.arguments[3].position,
                        expected=f"1..{len(values)}", actual=str(count))
        row_index = self._shape_position(expression.arguments[2], values, count, name, expression.arguments[2].position, insert=False)
        affected = values[row_index:]
        for offset, row in enumerate(affected, row_index):
            if isinstance(row, EmptyValue) or type(row) is not list or column >= len(row):
                raise error("E605", "Jagged list shape mismatch", "Vertical removal requires the target column in every affected row and changes nothing on failure.", expression.position,
                            expected=f"column {column} in rows {row_index}..{len(values)-1}", actual=f"row {offset} length {0 if not isinstance(row, list) else len(row)}")
        cell_type = element_type[1] if is_list_type_spec(element_type) else None
        column_values = [row[column] for row in affected]
        if cell_type is None:
            for value in column_values:
                actual = value_type_spec(value, expression.position)
                if not type_specs_compatible(cell_type, actual):
                    raise error("E203", "Heterogeneous list", "Vertical column values must retain one element type.", expression.position)
                cell_type = merge_type_specs(cell_type, actual)
        if cell_type is None:
            raise error("E134", "List element type required", "Vertical removal requires a known cell type for the new EMPTY tail slots.", expression.position)
        shifted = column_values[count:] + [empty_for_type_spec(cell_type) for _ in range(count)]
        for row, value in zip(affected, shifted):
            row[column] = value
        return VOID

    def _call(self, name, args, position, named=None):
        named = named or {}
        if any(isinstance(value, VoidResult) for value in args) or any(isinstance(value, VoidResult) for value in named.values()):
            raise error("E127", "VOID value use", "VOID cannot be passed as a function argument.", position,
                        expected="a value", actual="VOID")
        if name != "object_set" and (any(isinstance(value, EmptysValue) for value in args) or any(isinstance(value, EmptysValue) for value in named.values())):
            raise error("E133", "EMPTYS value use", "EMPTYS is an assignment operation and cannot be passed as an argument.", position,
                        expected="a value", actual="EMPTYS")
        if name in self.error_categories:
            if named or len(args) != 1: raise error("E207", "Argument count mismatch", f"Custom error '{name}' requires one positional message.", position, expected="1", actual=str(len(args) + len(named)))
            if type(args[0]) is not str: self._type_error(position, "string message", type_name(args[0]), f"Custom error '{name}' requires a string message.")
            return ErrorValue(name, args[0])
        builtin = BUILTINS.get(name)
        if builtin is not None:
            empty_safe = {"type", "type_of", "is_number", "is_string", "is_boolean", "is_list", "is_object", "is_bytes", "is_datetime", "is_duration", "is_secret", "object_set", "json_encode", "object_to_yaml", "network_set_static_address"}
            if name not in empty_safe and any(isinstance(value, EmptyValue) for value in (*args, *named.values())):
                raise error("E131", "EMPTY value use", f"{name}() cannot use EMPTY as a concrete value.", position,
                            expected="a present value", actual="EMPTY")
            return builtin.call(args, position, self, named)
        host_function = self.host_functions.get(name)
        if host_function is not None:
            if any(isinstance(value, EmptyValue) for value in (*args, *named.values())):
                raise error("E131", "EMPTY value use", "EMPTY cannot cross a host-function boundary as a concrete value.", position,
                            expected="a present value", actual="EMPTY")
            return host_function.call(args, position, self, named)
        logic = self.logics.get(name)
        if logic is None: raise error("E206", "Undefined SEP", f"SEP '{name}' is not defined.", position, actual=name)
        if named: raise error("E207", "Unsupported named argument", f"SEP '{name}' does not declare named arguments.", position, actual=next(iter(named)))
        if len(args) != len(logic.parameters): raise error("E207", "Argument count mismatch", f"SEP '{name}' requires {len(logic.parameters)} argument(s).", position, expected=str(len(logic.parameters)), actual=str(len(args)))
        normalized_args = []
        for parameter, value in zip(logic.parameters, args):
            declared = logic.parameter_types.get(parameter)
            if declared is not None:
                value = prepare_typed_value(parameter, declared[0], declared[1], value, position)
            elif isinstance(value, EmptyValue) and value.declared_type is None:
                raise error("E129", "EMPTY type required", f"Untyped parameter '{parameter}' cannot infer a type from EMPTY.", position,
                            expected=f"{parameter}: type", actual="EMPTY")
            normalized_args.append(value)
        args = normalized_args
        signature = tuple((type_name(value), list_element_type(value, position) if type(value) is list else None) for value in args)
        inferred = self.logic_parameter_types.get(name)
        if inferred is None:
            self.logic_parameter_types[name] = signature
        else:
            updated = list(inferred)
            for index, (parameter, expected_type, actual_type) in enumerate(zip(logic.parameters, inferred, signature)):
                if expected_type[0] != actual_type[0] or not type_specs_compatible(expected_type[1], actual_type[1]):
                    expected = expected_type[0] + (f"[{type_spec_text(expected_type[1])}]" if expected_type[1] else "")
                    actual = actual_type[0] + (f"[{type_spec_text(actual_type[1])}]" if actual_type[1] else "")
                    raise error("E208", "SEP parameter type mismatch", f"Parameter '{parameter}' of SEP '{name}' was inferred as {expected} by its first call.", position, expected=expected, actual=actual)
                if expected_type[0] == "list" and expected_type[1] is None and actual_type[1] is not None:
                    updated[index] = actual_type
            self.logic_parameter_types[name] = tuple(updated)
        previous = self.environment; self.environment = Environment(self.globals)
        try:
            for param, value in zip(logic.parameters, args):
                declared = logic.parameter_types.get(param)
                if declared is None: self.environment.assign(param, value, position)
                else: self.environment.define_typed(param, declared[0], declared[1], value, False, position)
            try: self._execute_all(logic.body)
            except Returned as result: return result.value
            return VOID
        finally: self.environment = previous

    def call_logic_value(self, value, arguments, position):
        self.validate_logic_value(value, position)
        return value.runtime._call(value.name, arguments, position)

    @staticmethod
    def validate_logic_value(value, position):
        if not isinstance(value, LogicValue):
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
    def is_empty_state(value): return isinstance(value, EmptyValue)
    @staticmethod
    def value_type_spec(value, position):
        value_type = type_name(value)
        return value_type, list_element_type(value, position) if value_type == "list" else None
    @staticmethod
    def type_name(value): return type_name(value)
    @staticmethod
    def type_error(position, expected, actual, description): Interpreter._type_error(position, expected, actual, description)
    @staticmethod
    def display(value): return Interpreter._display(value)
    @staticmethod
    def _display_value(value, position):
        if isinstance(value, EmptysValue):
            raise error("E133", "EMPTYS value use", "EMPTYS is a container-clear operation and cannot be printed.", position,
                        expected="a value", actual="EMPTYS")
        if isinstance(value, EmptyValue):
            raise error("E131", "EMPTY value use", "EMPTY cannot be printed because it has no current value.", position,
                        expected="a present value", actual="EMPTY")
        if isinstance(value, VoidResult):
            raise error("E127", "VOID value use", "VOID cannot be printed because it does not represent a value.", position,
                        expected="a value", actual="VOID")
        return Interpreter._display(value)
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
        if isinstance(value, EmptyValue):
            raise error("E131", "EMPTY value use", "EMPTY cannot be used as a condition; test it with 'is EMPTY'.", position,
                        expected="boolean", actual="EMPTY")
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
        if isinstance(value, LogicValue): return f"<logic:{value.name}>"
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
        if isinstance(value, EmptyValue): return "EMPTY"
        if isinstance(value, EmptysValue): return "EMPTYS"
        if isinstance(value, VoidResult): return "VOID"
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
