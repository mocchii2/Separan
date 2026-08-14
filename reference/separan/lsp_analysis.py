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
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text): return "number"
    if text.startswith('"') and text.endswith('"'): return "string"
    if text in ("true", "false"): return "boolean"
    if text == "null": return "null"
    if text.startswith("["): return "list"
    call = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
    if call:
        name = call.group(1)
        if name in ("number", "length", "len", "sum", "average", "count", "sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "abs", "ceil", "floor", "round", "min", "max", "pow"): return "number"
        if name in ("string", "trim", "upper", "lower", "substring", "char_at", "reverse", "read_text", "http_get"): return "string"
        if name.startswith("is_") or name in ("boolean", "contains", "starts_with", "ends_with", "regex_match", "regex_search"): return "boolean"
        if name in ("map", "filter", "flatten", "sort", "find_all", "split", "read_lines"): return "list"
        if name in ("datetime", "datetime_now", "datetime_parse"): return "datetime"
        if name == "duration": return "duration"
        if name in ("read_bytes", "bytes_from_string", "bytes_from_hex", "hex_decode", "base64_decode"): return "bytes"
        if name == "secret_get": return "secret"
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
