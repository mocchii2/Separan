"""Static editor analysis for the dependency-free Separan language server."""

from dataclasses import dataclass, field
import re


BLOCK_KINDS = {
    "function": ("end_function", 12), "if": ("endif", 5), "while": ("endwhile", 5),
    "for": ("endfor", 5), "object": ("end_object", 23), "list": ("end_list", 18),
    "try": ("endtry", 5), "error": ("end_error", 5), "http_route": ("end_http_route", 12),
    "transaction": ("end_transaction", 5),
}
CLOSER_KIND = {closer: kind for kind, (closer, _) in BLOCK_KINDS.items()}
LABEL = r"[^\s:()]+"
OPEN_RE = re.compile(r"^\s*(function|if|while|for|object|list|try|error|http_route|transaction)\b.*?:(" + LABEL + r")\s*(?:\([^\n]*\))?\s*$")
CLOSE_RE = re.compile(r"^\s*(end_function|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):(" + LABEL + r")\s*$")
BRANCH_RE = re.compile(r"^\s*(elseif\b.*?|else|catch\b.*?|finally):(" + LABEL + r")\s*$")
ASSIGN_RE = re.compile(r"^\s*(const\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
FUNCTION_RE = re.compile(r"^\s*function:([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?\s*$")
FOR_RE = re.compile(r"^\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b")
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

BUILTIN_SIGNATURES = {
    "substring": "substring(value: string, start: number, end?: number) -> string",
    "char_at": "char_at(value: string, index: number) -> string",
    "find_all": "find_all(value: string, search: string) -> list<number>",
    "map": "map(items: list, function: function) -> list",
    "filter": "filter(items: list, predicate: function) -> list",
    "reduce": "reduce(items: list, function: function, initial: value) -> value",
    "flatten": "flatten(items: list<list>) -> list",
    "sum": "sum(items: list<number>) -> number",
    "average": "average(items: list<number>) -> number",
    "count": "count(items: list, value: value) -> number",
    "length": "length(value: string | list | bytes) -> number",
    "string": "string(value: number | string | boolean | null) -> string",
    "number": "number(value: number | string) -> number",
    "boolean": "boolean(value: boolean | string) -> boolean",
    "sort": "sort(items: list) -> list",
    "sort_by": "sort_by(items: list<object>, field: string) -> list<object>",
    "datetime": "datetime(value: string) -> datetime",
    "duration": "duration(value: string) -> duration",
    "read_text": "read_text(path: string) -> string",
    "write_text": "write_text(path: string, text: string) -> null",
    "http_get": "http_get(url: string, options...) -> string",
    "db_query": "db_query(connection: db_connection, sql: string, parameters: list) -> list<object>",
    "yaml_to_object": "yaml_to_object(text: string) -> value",
    "object_to_yaml": "object_to_yaml(value: value, indent?: number, sort_keys?: boolean) -> string",
    "yaml_file_to_object": "yaml_file_to_object(path: string) -> value",
    "object_to_yaml_file": "object_to_yaml_file(path: string, value: value, indent?: number, sort_keys?: boolean) -> null",
    "yaml_to_objects": "yaml_to_objects(text: string) -> list",
    "yaml_validate": "yaml_validate(text: string) -> boolean",
    "xml_document_parse": "xml_document_parse(text: string) -> xml_document",
    "xml_document_read": "xml_document_read(path: string) -> xml_document",
    "xml_document_to_text": "xml_document_to_text(document: xml_document, indent?: number, declaration?: boolean) -> string",
    "xml_root": "xml_root(document: xml_document) -> xml_element",
    "xml_find": "xml_find(document_or_element: value, path: string) -> xml_element | null",
    "xml_find_all": "xml_find_all(document_or_element: value, path: string) -> list<xml_element>",
    "xml_element_name": "xml_element_name(element: xml_element) -> string",
    "xml_element_text": "xml_element_text(element: xml_element) -> string",
    "xml_get_attribute": "xml_get_attribute(element: xml_element, name: string, namespace_uri?: string) -> string | null",
    "xml_set_attribute": "xml_set_attribute(element: xml_element, name: string, value: string, namespace_uri?: string) -> null",
    "absolute": "absolute(value: number) -> number",
    "minimum": "minimum(values: list<number>) -> number",
    "maximum": "maximum(values: list<number>) -> number",
    "round": "round(value: number, digits?: number) -> number",
    "truncate": "truncate(value: number) -> number",
    "clamp": "clamp(value: number, minimum: number, maximum: number) -> number",
    "sign": "sign(value: number) -> number",
    "square_root": "square_root(value: number) -> number",
    "cube_root": "cube_root(value: number) -> number",
    "power": "power(base: number, exponent: number) -> number",
    "hypotenuse": "hypotenuse(a: number, b: number) -> number",
    "exponential": "exponential(value: number) -> number",
    "exponential_base2": "exponential_base2(value: number) -> number",
    "natural_log": "natural_log(value: number) -> number",
    "log_base2": "log_base2(value: number) -> number",
    "log_base10": "log_base10(value: number) -> number",
    "log_one_plus": "log_one_plus(value: number) -> number",
    "arc_sin": "arc_sin(value: number) -> number",
    "arc_cos": "arc_cos(value: number) -> number",
    "arc_tan": "arc_tan(value: number) -> number",
    "arc_tan2": "arc_tan2(y: number, x: number) -> number",
    "sinh": "sinh(value: number) -> number",
    "cosh": "cosh(value: number) -> number",
    "tanh": "tanh(value: number) -> number",
    "arc_sinh": "arc_sinh(value: number) -> number",
    "arc_cosh": "arc_cosh(value: number) -> number",
    "arc_tanh": "arc_tanh(value: number) -> number",
    "to_radians": "to_radians(degrees: number) -> number",
    "to_degrees": "to_degrees(radians: number) -> number",
    "greatest_common_divisor": "greatest_common_divisor(a: number, b: number) -> number",
    "least_common_multiple": "least_common_multiple(a: number, b: number) -> number",
    "factorial": "factorial(value: number) -> number",
    "is_finite": "is_finite(value: number) -> boolean",
    "is_infinite": "is_infinite(value: number) -> boolean",
    "is_nan": "is_nan(value: number) -> boolean",
    "is_close": "is_close(a: number, b: number) -> boolean",
    "is_integer_value": "is_integer_value(value: number) -> boolean",
    "median": "median(values: list<number>) -> number",
    "variance": "variance(values: list<number>) -> number",
    "sample_variance": "sample_variance(values: list<number>) -> number",
    "standard_deviation": "standard_deviation(values: list<number>) -> number",
    "sample_standard_deviation": "sample_standard_deviation(values: list<number>) -> number",
    "percentile": "percentile(values: list<number>, percent: number) -> number",
    "moving_average": "moving_average(values: list<number>, window: number) -> list<number>",
    "number_to_binary": "number_to_binary(value: number) -> string",
    "number_to_octal": "number_to_octal(value: number) -> string",
    "number_to_hexadecimal": "number_to_hexadecimal(value: number) -> string",
    "binary_to_number": "binary_to_number(text: string) -> number",
    "octal_to_number": "octal_to_number(text: string) -> number",
    "hexadecimal_to_number": "hexadecimal_to_number(text: string) -> number",
    "number_to_base": "number_to_base(value: number, base: number) -> string",
    "base_to_number": "base_to_number(text: string, base: number) -> number",
}


def _code_text(text):
    """Remove a # comment while retaining # characters inside quoted strings."""
    quoted, escaped = False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char == "#": return text[:index].rstrip()
    return text


def _multiline_delimiter(text):
    candidate = text.strip()
    if candidate == "##": return ""
    if candidate.startswith("##") and candidate[2:].isidentifier(): return candidate[2:]
    return None


def lsp_range(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


@dataclass
class LabelOccurrence:
    line: int
    start: int
    end: int
    role: str


@dataclass
class Block:
    kind: str
    label: str
    line: int
    start: int
    symbol_kind: int
    parent: object = None
    end_line: int | None = None
    children: list = field(default_factory=list)
    occurrences: list = field(default_factory=list)


@dataclass
class Variable:
    name: str
    type: str
    line: int
    start: int
    constant: bool
    scope: str
    parameter: bool = False
    members: dict = field(default_factory=dict)


def analyze_blocks(source):
    roots, stack, all_blocks = [], [], []; comment_label = None
    for number, text in enumerate(source.splitlines()):
        delimiter = _multiline_delimiter(text)
        if delimiter is not None:
            comment_label = None if comment_label == delimiter else delimiter if comment_label is None else comment_label
            continue
        if comment_label is not None: continue
        code = _code_text(text)
        opened = OPEN_RE.match(code)
        if opened:
            kind, label = opened.groups(); label_start = text.rfind(":" + label) + 1
            item = Block(kind, label, number, label_start, BLOCK_KINDS[kind][1], stack[-1] if stack else None)
            item.occurrences.append(LabelOccurrence(number, label_start, label_start + len(label), "open"))
            (stack[-1].children if stack else roots).append(item); stack.append(item); all_blocks.append(item)
            continue
        branch = BRANCH_RE.match(code)
        if branch and stack:
            label = branch.group(2); start = text.rfind(":" + label) + 1
            if stack[-1].label == label: stack[-1].occurrences.append(LabelOccurrence(number, start, start + len(label), "branch"))
            continue
        closed = CLOSE_RE.match(code)
        if closed:
            closer, label = closed.groups(); start = text.rfind(":" + label) + 1
            if stack and stack[-1].kind == CLOSER_KIND[closer] and stack[-1].label == label:
                item = stack.pop(); item.end_line = number
                item.occurrences.append(LabelOccurrence(number, start, start + len(label), "close"))
    return roots, all_blocks


def block_at(source, line, character):
    _, items = analyze_blocks(source)
    for item in items:
        for occurrence in item.occurrences:
            if occurrence.line == line and occurrence.start <= character <= occurrence.end: return item
    return None


def _literal_type(expression):
    text = expression.strip()
    digits = r"[0-9]+(?:_[0-9]+)*"
    based = r"(?:0[bB][01]+(?:_[01]+)*|0[oO][0-7]+(?:_[0-7]+)*|0[xX][0-9A-Fa-f]+(?:_[0-9A-Fa-f]+)*)"
    if re.fullmatch(rf"-?(?:{based}|{digits}(?:\.{digits})?)", text): return "number"
    if text.startswith('"') and text.endswith('"'): return "string"
    if text in ("true", "false"): return "boolean"
    if text == "null": return "null"
    if text.startswith("["): return "list"
    call = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
    if call:
        name = call.group(1)
        if name in ("number", "length", "len", "sum", "average", "count", "sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "abs", "ceil", "floor", "round", "min", "max", "pow", "absolute", "minimum", "maximum", "truncate", "clamp", "sign", "square_root", "cube_root", "power", "hypotenuse", "exponential", "exponential_base2", "natural_log", "log_base2", "log_base10", "log_one_plus", "arc_sin", "arc_cos", "arc_tan", "arc_tan2", "sinh", "cosh", "tanh", "arc_sinh", "arc_cosh", "arc_tanh", "to_radians", "to_degrees", "greatest_common_divisor", "least_common_multiple", "factorial", "median", "variance", "sample_variance", "standard_deviation", "sample_standard_deviation", "percentile", "binary_to_number", "octal_to_number", "hexadecimal_to_number", "base_to_number"): return "number"
        if name in ("string", "trim", "upper", "lower", "substring", "char_at", "reverse", "read_text", "http_get", "number_to_binary", "number_to_octal", "number_to_hexadecimal", "number_to_base", "object_to_yaml", "objects_to_yaml", "object_to_xml", "xml_document_to_text", "xml_element_name", "xml_element_text", "xml_namespace_uri", "xml_namespace_prefix", "xml_escape_text", "xml_escape_attribute", "xml_unescape"): return "string"
        if name.startswith("is_") or name in ("boolean", "contains", "starts_with", "ends_with", "regex_match", "regex_search", "yaml_validate", "yaml_validate_file"): return "boolean"
        if name in ("map", "filter", "flatten", "sort", "find_all", "split", "read_lines", "moving_average", "yaml_to_objects", "yaml_file_to_objects", "xml_children", "xml_find_all"): return "list"
        if name in ("datetime", "datetime_now", "datetime_parse"): return "datetime"
        if name == "duration": return "duration"
        if name in ("read_bytes", "bytes_from_string", "bytes_from_hex", "hex_decode", "base64_decode"): return "bytes"
        if name == "secret_get": return "secret"
        if name in ("xml_document_parse", "xml_document_read"): return "xml_document"
        if name in ("xml_root", "xml_create_element", "xml_find", "xml_child"): return "xml_element"
        if name in ("xml_to_object", "xml_file_to_object"): return "object"
    return "unknown"


def variables(source):
    result, scope_stack, object_stack = [], ["global"], []; comment_label = None
    for number, text in enumerate(source.splitlines()):
        delimiter = _multiline_delimiter(text)
        if delimiter is not None:
            comment_label = None if comment_label == delimiter else delimiter if comment_label is None else comment_label
            continue
        if comment_label is not None: continue
        code = _code_text(text)
        function = FUNCTION_RE.match(code)
        if function:
            scope_stack.append("function " + function.group(1))
            search_start = text.find("(") + 1
            for parameter in [item.strip() for item in (function.group(2) or "").split(",") if item.strip()]:
                start = text.find(parameter, search_start); search_start = start + len(parameter)
                result.append(Variable(parameter, "unknown", number, start, False, scope_stack[-1], True))
            continue
        if re.match(r"^\s*end_function:", code):
            if len(scope_stack) > 1: scope_stack.pop()
            continue
        opened_object = re.match(r"^\s*object:([A-Za-z_][A-Za-z0-9_]*)", code)
        if opened_object:
            name = opened_object.group(1); start = text.index(name)
            value = Variable(name, "object", number, start, False, scope_stack[-1]); result.append(value); object_stack.append(value); continue
        if re.match(r"^\s*end_object:", code):
            if object_stack: object_stack.pop()
            continue
        match = ASSIGN_RE.match(code)
        if match:
            const, name, expression = match.groups(); start = text.index(name)
            inferred = _literal_type(expression)
            if object_stack:
                object_stack[-1].members[name] = inferred
            else: result.append(Variable(name, inferred, number, start, bool(const), scope_stack[-1]))
        loop = FOR_RE.match(code)
        if loop:
            name = loop.group(1); result.append(Variable(name, "unknown", number, text.index(name), False, scope_stack[-1]))
    return result


def word_at(source, line, character):
    lines = source.splitlines()
    if line >= len(lines): return None
    for match in WORD_RE.finditer(lines[line]):
        if match.start() <= character <= match.end(): return match.group(), match.start(), match.end()
    return None


def scope_at(source, line):
    scope = "global"; comment_label = None
    for text in source.splitlines()[:line + 1]:
        delimiter = _multiline_delimiter(text)
        if delimiter is not None:
            comment_label = None if comment_label == delimiter else delimiter if comment_label is None else comment_label
            continue
        if comment_label is not None: continue
        code = _code_text(text); opened = FUNCTION_RE.match(code)
        if opened: scope = "function " + opened.group(1)
        elif re.match(r"^\s*end_function:", code): scope = "global"
    return scope


def resolve_variable(items, name, line, scope):
    candidates = [item for item in items if item.name == name and item.line <= line and item.scope in (scope, "global")]
    local = [item for item in candidates if item.scope == scope]
    return (local or candidates)[0] if candidates else None


def variable_at(source, line, character):
    word = word_at(source, line, character)
    if not word: return None
    return resolve_variable(variables(source), word[0], line, scope_at(source, line))


def static_type_diagnostics(source):
    seen, diagnostics = {}, []
    for item in variables(source):
        key = (item.scope, item.name)
        previous = seen.get(key)
        if previous and previous.type != "unknown" and item.type != "unknown" and previous.type != item.type:
            diagnostics.append({"range": lsp_range(item.line, item.start, item.start + len(item.name)), "severity": 1,
                "code": "E201", "source": "separan", "message": f"Type error: Variable '{item.name}' has fixed type {previous.type}; found {item.type}."})
        else: seen.setdefault(key, item)
    return diagnostics


def format_source(source, indent="    "):
    result, depth, comment_label = [], 0, None
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped: result.append(""); continue
        delimiter = _multiline_delimiter(stripped)
        if delimiter is not None:
            result.append(indent * depth + stripped)
            comment_label = None if comment_label == delimiter else delimiter if comment_label is None else comment_label
            continue
        if comment_label is not None:
            result.append(indent * depth + stripped); continue
        code = _code_text(stripped)
        if CLOSE_RE.match(code) or re.match(r"^(elseif\b|else:|catch\b|finally:)", code): depth = max(0, depth - 1)
        result.append(indent * depth + stripped)
        if OPEN_RE.match(code) or re.match(r"^(elseif\b|else:|catch\b|finally:)", code): depth += 1
    return "\n".join(result) + ("\n" if source.endswith(("\n", "\r")) else "")
