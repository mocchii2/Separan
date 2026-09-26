"""Dependency-free Language Server Protocol preview for Separan."""

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import fields, is_dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from .ast_nodes import (
    BinaryExpr, CallExpr, EmptyTestExpr, EmptysTestExpr, LogicDecl, GroupExpr,
    ImportStmt, ListExpr, LiteralExpr, MemberCallExpr, MemberExpr, UnaryExpr, VariableExpr,
)
from .errors import SeparanError
from .builtins import BUILTINS
from .interpreter import Interpreter
from .lexer import Lexer
from .parser import Parser
from .token import TokenType
from .embedded import BOARD_PROFILES
from .structural import ScopeResolutionError, inspect_source, structural_diff, verify_scopes, verify_tag_scope
from .structure_insights import document_structure
from .lsp_analysis import (
    BLOCK_KINDS, BUILTIN_SIGNATURES, analyze_blocks, block_at, format_source,
    _literal_type, lsp_range, resolve_variable, scope_at, static_type_diagnostics,
    variable_at, variables, word_at,
)

for _builtin_name in BUILTINS:
    BUILTIN_SIGNATURES.setdefault(_builtin_name, f"{_builtin_name}(...)")


def _range(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


def _uri_to_path(uri):
    if not uri.startswith("file:"):
        return Path(uri)
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if os.name == "nt" or sys.platform.startswith("win"):
        if path.startswith("/") and len(path) >= 3 and path[1].isalpha() and path[2] == ":":
            path = path[1:]
        elif path.startswith("//"):
            path = "\\\\" + path.lstrip("/")
        path = path.replace("/", "\\")
    return Path(path)


def _source_key(uri):
    return _uri_to_path(uri).resolve() if uri.startswith("file:") else uri


def _workspace_sources(server, current_uri):
    sources = {}
    roots = server.workspace_roots
    if not roots and current_uri.startswith("file:"):
        roots = [_uri_to_path(current_uri).resolve().parent]
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist"}
    for root in roots:
        if not root.is_dir():
            continue
        for directory, children, filenames in os.walk(root):
            children[:] = [name for name in children if name not in excluded]
            for filename in filenames:
                if not filename.endswith(".sep"):
                    continue
                path = Path(directory) / filename
                try:
                    sources[path.resolve()] = (path.resolve().as_uri(), path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
    for uri, source in server.documents.items():
        sources[_source_key(uri)] = (uri, source)
    current_key = _source_key(current_uri)
    if current_key not in sources:
        try:
            sources[current_key] = (current_uri, server.source(current_uri))
        except (OSError, UnicodeDecodeError):
            pass
    return sources


def _logic_index(source, uri, source_key):
    try:
        tokens = Lexer(source, uri).scan_tokens()
    except SeparanError:
        return None
    declarations, imports = {}, {}
    for index, token in enumerate(tokens):
        if token.type == TokenType.SEP and index + 2 < len(tokens):
            if tokens[index + 1].type == TokenType.COLON and tokens[index + 2].type == TokenType.IDENTIFIER:
                declarations.setdefault(tokens[index + 2].lexeme, []).append(index + 2)
        if token.type == TokenType.IMPORT and index + 3 < len(tokens):
            path_token, as_token, alias_token = tokens[index + 1:index + 4]
            if (isinstance(source_key, Path) and path_token.type == TokenType.STRING
                    and as_token.type == TokenType.AS and alias_token.type == TokenType.IDENTIFIER):
                imports[alias_token.lexeme] = (source_key.parent / path_token.literal).resolve()
    return tokens, declarations, imports


def _token_location(uri, token):
    line = token.position.line - 1
    start = token.position.column - 1
    return {"uri": uri, "range": lsp_range(line, start, start + len(token.lexeme))}


def _valid_semantic_tag(tag):
    return bool(tag) and all(
        segment.isidentifier() and unicodedata.is_normalized("NFC", segment)
        for segment in tag.split(":")
    )


def semantic_tag_workspace_edits(server, uri, old_name, new_name):
    if not _valid_semantic_tag(new_name):
        return None
    changes = {}
    for source_uri, source in _workspace_sources(server, uri).values():
        try:
            tokens = Lexer(source, source_uri).scan_tokens()
        except SeparanError:
            continue
        try:
            program = Parser(tokens).parse()
        except SeparanError:
            program = None
        if program and new_name != old_name:
            if any(old_name in item.tags and new_name in item.tags
                   for item in program.statements if isinstance(item, LogicDecl)):
                return None
        edits = []
        for token in tokens:
            if token.type == TokenType.TAG and token.lexeme == old_name:
                line = token.position.line - 1
                start = token.position.column
                edits.append({"range": lsp_range(line, start, start + len(old_name)), "newText": new_name})
        if edits:
            changes[source_uri] = edits
    return {"changes": changes} if changes else None


def logic_references(server, uri, line, character, include_declaration=False):
    sources = _workspace_sources(server, uri)
    current_key = _source_key(uri)
    current = sources.get(current_key)
    if current is None:
        return []
    current_uri, current_source = current
    current_index = _logic_index(current_source, current_uri, current_key)
    if current_index is None:
        return []
    tokens, declarations, imports = current_index
    selected_index = next((index for index, token in enumerate(tokens)
                           if token.type == TokenType.IDENTIFIER and token.position.line - 1 == line
                           and token.position.column - 1 <= character <= token.position.column - 1 + len(token.lexeme)), None)
    if selected_index is None:
        return []
    selected = tokens[selected_index]
    target_key = current_key
    name = selected.lexeme
    if selected_index >= 2 and tokens[selected_index - 1].type == TokenType.DOT:
        alias = tokens[selected_index - 2]
        if alias.type != TokenType.IDENTIFIER or alias.lexeme not in imports:
            return []
        target_key = imports[alias.lexeme]
    elif selected_index + 1 >= len(tokens) or tokens[selected_index + 1].type != TokenType.LPAREN:
        if selected_index not in declarations.get(name, ()):
            return []

    target = sources.get(target_key)
    if target is None:
        return []
    target_uri, target_source = target
    target_index = _logic_index(target_source, target_uri, target_key)
    if target_index is None:
        return []
    target_tokens, target_declarations, _ = target_index
    declaration_indices = target_declarations.get(name, ())
    if not declaration_indices:
        return []

    results = []
    if include_declaration:
        results.extend(_token_location(target_uri, target_tokens[index]) for index in declaration_indices)
    for source_key, (source_uri, source_text) in sources.items():
        indexed = _logic_index(source_text, source_uri, source_key)
        if indexed is None:
            continue
        source_tokens, source_declarations, source_imports = indexed
        if source_key == target_key:
            declaration_set = set(source_declarations.get(name, ()))
            for index, token in enumerate(source_tokens):
                if (token.type == TokenType.IDENTIFIER and token.lexeme == name and index not in declaration_set
                        and index + 1 < len(source_tokens) and source_tokens[index + 1].type == TokenType.LPAREN
                        and not (index and source_tokens[index - 1].type == TokenType.DOT)):
                    results.append(_token_location(source_uri, token))
        for alias, imported_key in source_imports.items():
            if imported_key != target_key:
                continue
            for index in range(len(source_tokens) - 3):
                if (source_tokens[index].type == TokenType.IDENTIFIER and source_tokens[index].lexeme == alias
                        and source_tokens[index + 1].type == TokenType.DOT
                        and source_tokens[index + 2].type == TokenType.IDENTIFIER
                        and source_tokens[index + 2].lexeme == name
                        and source_tokens[index + 3].type == TokenType.LPAREN):
                    results.append(_token_location(source_uri, source_tokens[index + 2]))
    return results


def _diagnostic_from_error(exc, uri):
    line = max(0, exc.position.line - 1)
    start = max(0, exc.position.column - 1)
    width = max(1, len(exc.actual or ""))
    replacement = None
    if exc.code == "E104" and exc.expected and ":" in exc.expected:
        replacement = exc.expected.split(":", 1)[1]
        width = max(1, len((exc.actual or "").split(":", 1)[-1]))
    elif exc.code == "E105" and exc.expected:
        replacement = exc.expected
    item = {"range": _range(line, start, start + width), "severity": 1,
            "code": exc.code, "source": "separan", "message": f"{exc.category}: {exc.description}"}
    if exc.expected and exc.actual:
        item["message"] += f"\nExpected: {exc.expected}\nActual: {exc.actual}"
        if replacement is not None:
            item["data"] = {"replacement": replacement, "title": exc.expected, "actual": exc.actual}
    if exc.related is not None:
        item["relatedInformation"] = [{"location": {"uri": uri, "range": _range(exc.related.line - 1, exc.related.column - 1, exc.related.column)}, "message": "Opened here"}]
    return item


def diagnostic(source, uri):
    try:
        tokens = Lexer(source, uri).scan_tokens()
    except SeparanError as exc:
        return [_diagnostic_from_error(exc, uri)]
    _, parse_errors = Parser(tokens).parse_with_diagnostics()
    if parse_errors:
        return [_diagnostic_from_error(exc, uri) for exc in parse_errors]
    return static_type_diagnostics(source)


def blocks(source):
    return analyze_blocks(source)[0]


def document_symbols(source):
    def convert(item):
        end = item.end_line if item.end_line is not None else item.line
        result = {"name": item.label, "detail": item.kind, "kind": item.symbol_kind,
                  "range": _range(item.line, 0, len(source.splitlines()[end]) if source.splitlines() else 0),
                  "selectionRange": _range(item.line, item.start, item.start + len(item.kind)),
                  "children": [convert(child) for child in item.children]}
        result["range"]["end"]["line"] = end
        return result
    return [convert(item) for item in blocks(source)]


def folding_ranges(source):
    result = []
    def visit(item):
        if item.end_line is not None and item.end_line > item.line:
            result.append({"startLine": item.line, "endLine": item.end_line, "kind": "region"})
        for child in item.children: visit(child)
    for item in blocks(source): visit(item)
    return result


TOKEN_TYPES = ["namespace", "type", "function", "parameter", "variable", "property", "label", "decorator", "number", "string", "keyword", "comment", "operator"]
TOKEN_MODIFIERS = ["declaration", "readonly", "number", "string", "boolean", "list", "object", "bytes", "datetime", "duration", "secret", "constant", "parameter"]
TYPE_MODIFIER = {name: TOKEN_MODIFIERS.index(name) for name in ("number", "string", "boolean", "list", "object", "bytes", "datetime", "duration", "secret")}
KEYWORDS = {"SEP", "END_SEP", "if", "elseif", "else", "endif", "while", "endwhile", "for", "endfor", "return", "const", "object", "end_object", "list", "end_list", "try", "catch", "finally", "endtry", "throw", "transaction", "end_transaction", "http_route", "end_http_route", "import", "as", "in", "not", "is"}
RENAMABLE_LABEL_KINDS = {"if", "while", "for", "try", "transaction", "http_route"}


def _comment_start(text):
    quoted, escaped = False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char == "#": return index
    return None


def _tag_at(source, line, character):
    lines = source.splitlines()
    if line >= len(lines): return None
    found = re.match(r"^\s*@([^\s#]+)", lines[line])
    if not found: return None
    start, end = found.start(1), found.end(1)
    return (found.group(1), start, end) if start <= character <= end else None


def semantic_tokens(source):
    entries, occupied = [], set(); lines = source.splitlines(); known = variables(source)
    variables_by_name = {}
    for item in known: variables_by_name.setdefault(item.name, []).append(item)
    scopes, scope = [], "global"
    for text in lines:
        opened = re.match(r"^\s*SEP:([A-Za-z_][A-Za-z0-9_]*)", text)
        if opened: scope = "logic " + opened.group(1)
        scopes.append(scope)
        if re.match(r"^\s*END_SEP:", text): scope = "global"
    def add(line, start, length, token_type, modifiers=0):
        cells = {(line, index) for index in range(start, start + length)}
        if length <= 0 or cells & occupied: return
        occupied.update(cells); entries.append((line, start, length, TOKEN_TYPES.index(token_type), modifiers))
    comment_label = None
    for line_no, text in enumerate(lines):
        stripped = text.lstrip(); offset = len(text) - len(stripped); candidate = stripped.rstrip()
        delimiter = "" if candidate == "##" else candidate[2:] if candidate.startswith("##") and candidate[2:].isidentifier() else None
        if delimiter is not None:
            add(line_no, offset, len(text) - offset, "comment")
            comment_label = None if comment_label == delimiter else delimiter if comment_label is None else comment_label
            continue
        if comment_label is not None:
            add(line_no, offset, len(text) - offset, "comment"); continue
        comment = _comment_start(text)
        code = text if comment is None else text[:comment]
        if comment is not None: add(line_no, comment, len(text) - comment, "comment")
        for found in re.finditer(r'r?"(?:\\.|[^"\\])*"', code): add(line_no, found.start(), len(found.group()), "string")
        tag = re.match(r"^\s*@([^\s#]+)", code)
        if tag: add(line_no, tag.start(), len(tag.group()), "decorator", 1)
    for block in analyze_blocks(source)[1]:
        for occurrence in block.occurrences: add(occurrence.line, occurrence.start, occurrence.end - occurrence.start, "label", 1 if occurrence.role == "open" else 0)
    namespaces = set(re.findall(r'^\s*import\s+"[^"]+"\s+as\s+([A-Za-z_][A-Za-z0-9_]*)', source, re.MULTILINE))
    for line_no, text in enumerate(lines):
        for name in namespaces:
            for found in re.finditer(r"\b" + re.escape(name) + r"\b", text): add(line_no, found.start(), len(name), "namespace")
    for line_no, text in enumerate(lines):
        for found in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            item = resolve_variable(variables_by_name.get(found.group(), ()), found.group(), line_no, scopes[line_no])
            if item is None or item.name != found.group(): continue
            modifier = 1 << TYPE_MODIFIER[item.type] if item.type in TYPE_MODIFIER else 0
            if item.constant: modifier |= (1 << TOKEN_MODIFIERS.index("constant")) | (1 << TOKEN_MODIFIERS.index("readonly"))
            if item.parameter: modifier |= 1 << TOKEN_MODIFIERS.index("parameter")
            declaration = 1 if line_no == item.line and found.start() == item.start else 0
            add(line_no, found.start(), len(item.name), "parameter" if item.parameter else "variable", modifier | declaration)
    for line_no, text in enumerate(lines):
        for found in re.finditer(r"\b\d+(?:\.\d+)?\b", text): add(line_no, found.start(), len(found.group()), "number")
        for found in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            word = found.group()
            if word in KEYWORDS: add(line_no, found.start(), len(word), "keyword")
            elif word in ("print", "print_error"): add(line_no, found.start(), len(word), "function")
            elif word in ("true", "false", "EMPTY", "EMPTYS", "front", "back"): add(line_no, found.start(), len(word), "type")
            elif word in BUILTIN_SIGNATURES or re.match(r"\s*\(", text[found.end():]): add(line_no, found.start(), len(word), "function")
            elif found.start() > 0 and text[found.start() - 1] == ".": add(line_no, found.start(), len(word), "property")
        for found in re.finditer(r"\*\*|//|==|!=|>=|<=|&&|\|\||\?\?|[+\-*/%><!=]", text): add(line_no, found.start(), len(found.group()), "operator")
    entries.sort(); data, previous_line, previous_start = [], 0, 0
    for line, start, length, token_type, modifiers in entries:
        delta_line = line - previous_line; delta_start = start - previous_start if delta_line == 0 else start
        data.extend([delta_line, delta_start, length, token_type, modifiers]); previous_line, previous_start = line, start
    return {"data": data}


def hover(source, line, character):
    block = block_at(source, line, character)
    if block:
        closed = block.end_line + 1 if block.end_line is not None else "unclosed"
        parent = f"\nParent: `{block.parent.label}` ({block.parent.kind})" if block.parent else ""
        count = block.end_line - block.line + 1 if block.end_line is not None else "?"
        return {"contents": {"kind": "markdown", "value": f"**Label:** `{block.label}`\n\nBlock: `{block.kind}`  \nOpened: line {block.line + 1}  \nClosed: line {closed}  \nLines: {count}{parent}"}}
    pin = _pin_at(source, line, character)
    if pin is not None:
        profile, value = pin
        capabilities = ", ".join(value.definition.capabilities)
        return {"contents": {"kind": "markdown", "value":
            f"**pin.{value.definition.name}** on `{profile.id}`\n\n"
            f"Backend: `{value.definition.backend_pin}`  \nPhysical pin: `{value.definition.physical_pin}`  \n"
            f"Voltage: `{value.definition.voltage} V`  \nCapabilities: {capabilities}"}}
    variable = variable_at(source, line, character)
    if variable:
        mutable = "no (readonly)" if variable.constant else "yes"; members = ""
        if variable.members: members = "\n\nMembers:\n" + "\n".join(f"- `{name}`: {kind}" for name, kind in variable.members.items())
        value = "\n\nValue: `<redacted>`" if variable.type == "secret" else ""
        return {"contents": {"kind": "markdown", "value": f"**{variable.name}**\n\nType: `{variable.type}`  \nScope: `{variable.scope}`  \nMutable: {mutable}  \nDefined: line {variable.line + 1}{value}{members}"}}
    word = word_at(source, line, character)
    if word and word[0] in BUILTIN_SIGNATURES: return {"contents": {"kind": "markdown", "value": "```separan\n" + BUILTIN_SIGNATURES[word[0]] + "\n```"}}
    if word:
        function = re.search(r"^\s*SEP:" + re.escape(word[0]) + r"(?:\(([^)]*)\))?", source, re.MULTILINE)
        if function:
            params = function.group(1) or ""
            return {"contents": {"kind": "markdown", "value": f"```separan\n{word[0]}({params}) -> inferred\n```"}}
    return None


def _source_board_profile(source):
    found = re.search(r'\bboard_select\(\s*"([a-z0-9_]+)"\s*\)', source)
    return BOARD_PROFILES.get(found.group(1)) if found else None


def _pin_at(source, line, character):
    lines = source.splitlines()
    if line >= len(lines): return None
    for found in re.finditer(r"\bpin\.([A-Za-z0-9_]+)", lines[line]):
        if found.start(1) <= character <= found.end(1):
            profile = _source_board_profile(source)
            if profile is None: return None
            try: return profile, profile.resolve(found.group(1), None)
            except SeparanError: return None
    return None


def label_edits(source, line, character, new_name, uri):
    block = block_at(source, line, character)
    if not block or block.kind not in RENAMABLE_LABEL_KINDS: return None
    return {"changes": {uri: [{"range": lsp_range(item.line, item.start, item.end), "newText": new_name} for item in block.occurrences]}}


def definition(source, line, character, uri):
    block = block_at(source, line, character)
    if block: return {"uri": uri, "range": lsp_range(block.line, block.start, block.start + len(block.label))}
    variable = variable_at(source, line, character)
    if variable: return {"uri": uri, "range": lsp_range(variable.line, variable.start, variable.start + len(variable.name))}
    word = word_at(source, line, character)
    if word:
        pattern = re.compile(r"^\s*SEP:" + re.escape(word[0]) + r"\b")
        for number, text in enumerate(source.splitlines()):
            found = pattern.match(text)
            if found:
                start = text.index(word[0]); return {"uri": uri, "range": lsp_range(number, start, start + len(word[0]))}
    return None


def highlights(source, line, character):
    block = block_at(source, line, character)
    if not block: return []
    return [{"range": lsp_range(item.line, item.start, item.end), "kind": 1 if item.role == "open" else 2} for item in block.occurrences]


def completions(source, line, character):
    lines = source.splitlines(); prefix = lines[line][:character] if line < len(lines) else ""
    items = []
    roots, all_blocks = analyze_blocks("\n".join(lines[:line + 1]))
    open_blocks = [item for item in all_blocks if item.end_line is None]
    structural_trigger = re.search(r":end$", prefix)
    for priority, block in enumerate(reversed(open_blocks)):
        closer = BLOCK_KINDS[block.kind][0] + ":" + block.label
        item = {"label": closer, "kind": 14, "sortText": f"0{priority:03}", "insertText": closer,
                "detail": f"Close {block.kind} :{block.label}; opened at line {block.line + 1}"}
        if structural_trigger:
            item["textEdit"] = {"range": _range(line, character - 4, character), "newText": closer}
        items.append(item)
    if structural_trigger:
        return {"isIncomplete": False, "items": items}
    pin_prefix = re.search(r"\bpin\.([A-Za-z0-9_]*)$", prefix)
    if pin_prefix:
        selected = _source_board_profile(source)
        if selected is None:
            names = set.intersection(*(set(profile.aliases) for profile in BOARD_PROFILES.values()))
            detail = "Logical pin available on every bundled Tier 1 board"
        else:
            names = set(selected.aliases)
            detail = f"Logical pin for {selected.id}"
        typed = pin_prefix.group(1); start = character - len(typed)
        return {"isIncomplete": False, "items": [
            {"label": name, "kind": 5, "sortText": "0" + name,
             "textEdit": {"range": _range(line, start, character), "newText": name}, "detail": detail}
            for name in sorted(names) if name.startswith(typed)
        ]}
    tag_prefix = re.match(r"^\s*@([^\s#]*)$", prefix)
    if tag_prefix:
        typed = tag_prefix.group(1)
        known_tags = sorted(tag for tag in set(re.findall(r"^\s*@([^\s#]+)\s*(?:#.*)?$", source, re.MULTILINE))
                            if tag.startswith(typed) and tag != typed)
        start = prefix.index("@")
        return {"isIncomplete": False, "items": [
            {"label": "@" + tag, "kind": 14, "sortText": "0" + tag,
             "textEdit": {"range": _range(line, start, character), "newText": "@" + tag},
             "detail": "Separan SEP semantic tag"} for tag in known_tags
        ]}
    for name, signature in BUILTIN_SIGNATURES.items():
        items.append({"label": name, "kind": 3, "sortText": "1" + name, "insertText": name + "($0)", "insertTextFormat": 2, "detail": signature})
    for function in re.finditer(r"^\s*SEP:([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?", source, re.MULTILINE):
        name, params = function.group(1), function.group(2) or ""
        items.append({"label": name, "kind": 3, "sortText": "1" + name, "insertText": name + "($0)", "insertTextFormat": 2, "detail": f"{name}({params}) -> inferred"})
    if re.search(r"\bif\b.*\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$", prefix):
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$", prefix)
        obj, prop = match.groups()
        for suggestion in (f"{prop}_{obj}", f"{obj}_{prop}", f"check_{obj}_{prop}"):
            items.append({"label": suggestion, "kind": 18, "sortText": "00" + suggestion})
    return {"isIncomplete": False, "items": items}


def signature_help(source, line, character):
    lines = source.splitlines(); prefix = lines[line][:character] if line < len(lines) else ""
    match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\(([^()]*)$", prefix)
    if not match: return None
    label = BUILTIN_SIGNATURES.get(match.group(1))
    if label is None:
        function = re.search(r"^\s*SEP:" + re.escape(match.group(1)) + r"(?:\(([^)]*)\))?", source, re.MULTILINE)
        if not function: return None
        label = f"{match.group(1)}({function.group(1) or ''}) -> inferred"
    active = match.group(2).count(",")
    return {"signatures": [{"label": label}], "activeSignature": 0, "activeParameter": active}


def _call_expressions(value):
    if isinstance(value, (CallExpr, MemberCallExpr)):
        yield value
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _call_expressions(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _call_expressions(item)
    elif is_dataclass(value):
        for item in fields(value):
            if item.name != "position":
                yield from _call_expressions(getattr(value, item.name))


def _argument_type(expression, source, known_variables):
    if isinstance(expression, LiteralExpr):
        value = expression.value
        if type(value) is bool: return "boolean"
        if type(value) in (int, float): return "number"
        if isinstance(value, str): return "string"
        return "unknown"
    if isinstance(expression, ListExpr): return "list"
    if isinstance(expression, GroupExpr): return _argument_type(expression.expression, source, known_variables)
    if isinstance(expression, UnaryExpr):
        return "boolean" if expression.operator == "not" else _argument_type(expression.operand, source, known_variables)
    if isinstance(expression, (EmptyTestExpr, EmptysTestExpr)): return "boolean"
    if isinstance(expression, VariableExpr):
        line = expression.position.line - 1
        item = resolve_variable(known_variables, expression.name, line, scope_at(source, line))
        return item.type if item and item.type != "unknown" else "unknown"
    if isinstance(expression, MemberExpr) and isinstance(expression.target, VariableExpr):
        line = expression.position.line - 1
        item = resolve_variable(known_variables, expression.target.name, line, scope_at(source, line))
        if item:
            return item.members.get(expression.name, "unknown")
    if isinstance(expression, CallExpr):
        return _literal_type(expression.callee + "()")
    if isinstance(expression, MemberCallExpr):
        return _literal_type(expression.name + "()")
    if isinstance(expression, BinaryExpr):
        if expression.operator in ("==", "!=", ">", ">=", "<", "<=", "in", "not in", "&&", "||"):
            return "boolean"
        left = _argument_type(expression.left, source, known_variables)
        right = _argument_type(expression.right, source, known_variables)
        if expression.operator == "+" and left == right == "string": return "string"
        if left == right == "number": return "number"
    return "unknown"


def _workspace_programs(sources):
    programs = {}
    for source_key, (source_uri, source_text) in sources.items():
        try:
            program = Parser(Lexer(source_text, source_uri).scan_tokens()).parse()
        except SeparanError:
            continue
        functions = {item.name: item for item in program.statements if isinstance(item, LogicDecl)}
        imports = {
            item.alias: (source_key.parent / item.path).resolve()
            for item in program.statements
            if isinstance(item, ImportStmt) and isinstance(source_key, Path)
        }
        programs[source_key] = {
            "uri": source_uri, "source": source_text, "program": program,
            "functions": functions, "imports": imports,
        }
    return programs


def _called_logic(expression, source_key, imports):
    if isinstance(expression, CallExpr):
        return source_key, expression.callee
    if isinstance(expression, MemberCallExpr) and isinstance(expression.target, VariableExpr):
        target_key = imports.get(expression.target.name)
        if target_key is not None:
            return target_key, expression.name
    return None


def _call_range(expression):
    if isinstance(expression, CallExpr):
        line = expression.position.line - 1
        start = expression.position.column - 1
        return lsp_range(line, start, start + len(expression.callee))
    line = expression.position.line - 1
    start = expression.target.position.column - 1
    end = expression.position.column + len(expression.name)
    return lsp_range(line, start, end)


def _call_hierarchy_item(info, function):
    source = info["source"]
    lines = source.splitlines()
    start_line = function.position.line - 1
    matching = [block for block in analyze_blocks(source)[1]
                if block.kind == "SEP" and block.label == function.name and block.line == start_line]
    end_line = matching[0].end_line if matching and matching[0].end_line is not None else start_line
    end_character = len(lines[end_line]) if end_line < len(lines) else 0
    selection_line = function.label_position.line - 1
    selection_start = function.label_position.column - 1
    selection = lsp_range(selection_line, selection_start, selection_start + len(function.name))
    return {
        "name": function.name, "kind": 12, "detail": "SEP logic", "uri": info["uri"],
        "range": lsp_range(start_line, 0, end_character) | {
            "end": {"line": end_line, "character": end_character},
        },
        "selectionRange": selection,
        "data": {"uri": info["uri"], "name": function.name},
    }


def _call_hierarchy_target(programs, item):
    data = item.get("data") or {}
    uri, name = data.get("uri"), data.get("name")
    if not uri or not name:
        return None
    key = _source_key(uri)
    info = programs.get(key)
    function = info["functions"].get(name) if info else None
    return (key, info, function) if function is not None else None


def prepare_call_hierarchy(server, uri, source, line, character):
    references = logic_references(server, uri, line, character, include_declaration=True)
    if not references:
        return []
    name = word_at(source, line, character)
    if not name:
        return []
    declaration = references[0]
    sources = _workspace_sources(server, uri)
    programs = _workspace_programs(sources)
    info = programs.get(_source_key(declaration["uri"]))
    function = info["functions"].get(name[0]) if info else None
    return [_call_hierarchy_item(info, function)] if function is not None else []


def reference_code_lenses(server, uri):
    source = server.source(uri)
    try:
        program = Parser(Lexer(source, uri).scan_tokens()).parse()
    except SeparanError:
        return []
    lenses = []
    for function in program.statements:
        if not isinstance(function, LogicDecl):
            continue
        line = function.label_position.line - 1
        character = function.label_position.column - 1
        references = logic_references(server, uri, line, character, include_declaration=False)
        count = len(references)
        title = f"{count} reference" if count == 1 else f"{count} references"
        position = {"line": line, "character": character}
        lenses.append({
            "range": lsp_range(line, character, character + len(function.name)),
            "command": {
                "title": title, "command": "editor.action.showReferences",
                "arguments": [uri, position, references],
            },
        })
        if not function.parameters:
            run_title = "Run Test" if function.name.startswith("test_") else "Run SEP"
            lenses.append({
                "range": lsp_range(line, character, character + len(function.name)),
                "command": {
                    "title": run_title, "command": "separan.runFunction",
                    "arguments": [uri, function.name, []],
                },
            })
    return lenses


def run_logic(server, uri, function_name, arguments):
    if not uri.startswith("file:") or not isinstance(arguments, list):
        return {"error": "Run SEP requires a file-backed document and a JSON argument array."}
    path = _uri_to_path(uri).resolve()
    output = StringIO()
    runtime = None
    try:
        source = server.source(uri)
        program = Parser(Lexer(source, str(path)).scan_tokens()).parse()
        runtime = Interpreter(output=output, script_path=str(path), project_root=str(path.parent))
        runtime.run(program, invoke_main=False)
        if function_name not in runtime.logics:
            return {"error": f"Unknown Separan SEP '{function_name}'.", "output": output.getvalue()}
        result = runtime.invoke(function_name, arguments)
        if type(result) in (bool, int, float, str):
            rendered_result = str(result)
        else:
            rendered_result = f"<{type(result).__name__}>"
        return {"output": output.getvalue(), "result": rendered_result}
    except (SeparanError, OSError, UnicodeDecodeError) as exc:
        return {"error": str(exc), "output": output.getvalue()}
    finally:
        if runtime is not None:
            runtime.close_resources()


def incoming_call_hierarchy(server, item):
    programs = _workspace_programs(_workspace_sources(server, item.get("uri", "")))
    target = _call_hierarchy_target(programs, item)
    if target is None:
        return []
    target_key, _, target_function = target
    incoming = []
    for source_key, info in programs.items():
        for function in info["program"].statements:
            if not isinstance(function, LogicDecl):
                continue
            ranges = []
            for expression in _call_expressions(function.body):
                callee = _called_logic(expression, source_key, info["imports"])
                if callee == (target_key, target_function.name):
                    ranges.append(_call_range(expression))
            if ranges:
                incoming.append({"from": _call_hierarchy_item(info, function), "fromRanges": ranges})
    return incoming


def outgoing_call_hierarchy(server, item):
    programs = _workspace_programs(_workspace_sources(server, item.get("uri", "")))
    target = _call_hierarchy_target(programs, item)
    if target is None:
        return []
    source_key, info, function = target
    grouped = {}
    for expression in _call_expressions(function.body):
        callee = _called_logic(expression, source_key, info["imports"])
        if callee is None:
            continue
        callee_key, callee_name = callee
        callee_info = programs.get(callee_key)
        callee_function = callee_info["functions"].get(callee_name) if callee_info else None
        if callee_function is None:
            continue
        key = (callee_key, callee_name)
        if key not in grouped:
            grouped[key] = {"to": _call_hierarchy_item(callee_info, callee_function), "fromRanges": []}
        grouped[key]["fromRanges"].append(_call_range(expression))
    return list(grouped.values())


def workspace_signature_help(server, uri, source, line, character):
    lines = source.splitlines()
    prefix = lines[line][:character] if line < len(lines) else ""
    call = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\(([^()]*)$", prefix)
    if not call:
        return None
    name = call.group(1)
    current_key = _source_key(uri)
    sources = _workspace_sources(server, uri)
    current_source = sources.get(current_key)
    if current_source is None:
        return signature_help(source, line, character)
    current_uri, current_text = current_source
    current_index = _logic_index(current_text, current_uri, current_key)
    if current_index is None:
        return signature_help(source, line, character)
    _, _, import_paths = current_index
    target_key = current_key
    qualified = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.$", prefix[:call.start(1)])
    if qualified:
        target_key = import_paths.get(qualified.group(1))
        if target_key is None:
            return signature_help(source, line, character)

    programs = _workspace_programs(sources)

    target = programs.get(target_key)
    function = target["functions"].get(name) if target else None
    if function is None:
        return signature_help(source, line, character)

    observed = {parameter: set() for parameter in function.parameters}
    for source_key, info in programs.items():
        source_text = info["source"]
        known_variables = variables(source_text)
        for expression in _call_expressions(info["program"]):
            arguments = expression.arguments
            matches = (source_key == target_key and isinstance(expression, CallExpr)
                       and expression.callee == name)
            if isinstance(expression, MemberCallExpr) and isinstance(expression.target, VariableExpr):
                matches = expression.name == name and info["imports"].get(expression.target.name) == target_key
            if not matches:
                continue
            for parameter, argument in zip(function.parameters, arguments):
                inferred = _argument_type(argument, source_text, known_variables)
                if inferred not in ("unknown", "EMPTY"):
                    observed[parameter].add(inferred)

    target_source = target["source"]
    declaration_line = target_source.splitlines()[function.position.line - 1]
    header = re.search(r"^\s*SEP:" + re.escape(name) + r"\(([^)]*)\)", declaration_line)
    original_parameters = {}
    if header:
        for parameter in header.group(1).split(","):
            parameter = parameter.strip()
            if parameter:
                original_parameters[parameter.split(":", 1)[0].strip()] = parameter
    rendered_parameters = []
    for parameter in function.parameters:
        if parameter in function.parameter_types:
            rendered_parameters.append(original_parameters.get(parameter, parameter))
            continue
        types = sorted(observed[parameter])
        annotation = " | ".join(types)
        rendered_parameters.append(f"{parameter}: {annotation}" if annotation else parameter)
    active = call.group(2).count(",")
    return {"signatures": [{"label": f"{name}({', '.join(rendered_parameters)}) -> inferred"}],
            "activeSignature": 0, "activeParameter": active}


def inlay_hints(source, requested_range):
    result = []
    for item in variables(source):
        if item.type == "unknown" or item.parameter: continue
        if requested_range["start"]["line"] <= item.line <= requested_range["end"]["line"]:
            result.append({"position": {"line": item.line, "character": item.start + len(item.name)}, "label": f": {item.type}", "kind": 1, "paddingRight": True})
    return result


def structural_scope_at(source, line, character, uri="<document>"):
    block = block_at(source, line, character)
    if block is None:
        return None
    snapshot = inspect_source(source, uri)
    matches = [item for item in snapshot.blocks
               if item.kind == block.kind and item.label == block.label and item.start_line == block.line + 1]
    if len(matches) != 1:
        return None
    item = matches[0]
    return {"id": item.id, "path": item.path, "kind": item.kind, "label": item.label}


class Server:
    def __init__(self, reader=None, writer=None):
        self.reader = reader or sys.stdin.buffer
        self.writer = writer or sys.stdout.buffer
        self.documents = {}
        self.workspace_roots = []
        self.shutdown_requested = False
        self.initialization_options = {}

    def source(self, uri):
        source = self.documents.get(uri)
        if source is None and uri.startswith("file:"):
            source = _uri_to_path(uri).read_text(encoding="utf-8")
        return source or ""

    def send(self, payload):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.writer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
        self.writer.flush()

    def publish(self, uri):
        self.send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                   "params": {"uri": uri, "diagnostics": diagnostic(self.documents.get(uri, ""), uri)}})

    def dispatch(self, message):
        method, params = message.get("method"), message.get("params", {})
        if method == "initialize":
            self.initialization_options = params.get("initializationOptions") or {}
            folders = params.get("workspaceFolders") or []
            self.workspace_roots = [
                _uri_to_path(folder["uri"]).resolve() for folder in folders
                if folder.get("uri", "").startswith("file:")
            ]
            if not self.workspace_roots:
                root_uri = params.get("rootUri")
                root_path = params.get("rootPath")
                if root_uri and root_uri.startswith("file:"):
                    self.workspace_roots = [_uri_to_path(root_uri).resolve()]
                elif root_path:
                    self.workspace_roots = [Path(root_path).resolve()]
            return {"capabilities": {"textDocumentSync": 1, "documentSymbolProvider": True, "foldingRangeProvider": True,
                    "hoverProvider": True, "definitionProvider": True, "renameProvider": {"prepareProvider": True},
                    "referencesProvider": True,
                    "callHierarchyProvider": True,
                    "codeLensProvider": {"resolveProvider": False},
                    "executeCommandProvider": {"commands": ["separan.runFunction"]},
                    "documentHighlightProvider": True, "completionProvider": {"triggerCharacters": [":", "_", "@"]},
                    "signatureHelpProvider": {"triggerCharacters": ["(", ","]}, "codeActionProvider": True,
                    "documentFormattingProvider": True, "inlayHintProvider": True,
                    "semanticTokensProvider": {"legend": {"tokenTypes": TOKEN_TYPES, "tokenModifiers": TOKEN_MODIFIERS}, "full": True}},
                    "serverInfo": {"name": "separan-lsp", "version": "0.6.0"}}
        if method == "shutdown": self.shutdown_requested = True; return None
        if method == "exit": raise SystemExit(0 if self.shutdown_requested else 1)
        if method in ("textDocument/didOpen", "textDocument/didChange"):
            document = params.get("textDocument", {})
            uri = document.get("uri")
            changes = params.get("contentChanges", [])
            text = document.get("text") if method.endswith("didOpen") else (changes[-1].get("text") if changes else None)
            if uri is not None and text is not None: self.documents[uri] = text; self.publish(uri)
        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]; self.documents.pop(uri, None)
            self.send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": uri, "diagnostics": []}})
        elif method in ("textDocument/documentSymbol", "textDocument/foldingRange"):
            uri = params["textDocument"]["uri"]
            source = self.source(uri)
            return document_symbols(source) if method.endswith("documentSymbol") else folding_ranges(source)
        elif method in ("textDocument/hover", "textDocument/definition", "textDocument/documentHighlight",
                        "textDocument/completion", "textDocument/signatureHelp", "textDocument/prepareRename",
                        "textDocument/references", "textDocument/prepareCallHierarchy"):
            uri = params["textDocument"]["uri"]; source = self.source(uri); position = params["position"]
            line, character = position["line"], position["character"]
            if method.endswith("references"):
                include_declaration = params.get("context", {}).get("includeDeclaration", False)
                return logic_references(self, uri, line, character, include_declaration)
            if method.endswith("prepareCallHierarchy"):
                return prepare_call_hierarchy(self, uri, source, line, character)
            if method.endswith("hover"): return hover(source, line, character)
            if method.endswith("definition"): return definition(source, line, character, uri)
            if method.endswith("documentHighlight"): return highlights(source, line, character)
            if method.endswith("completion"): return completions(source, line, character)
            if method.endswith("signatureHelp"):
                return workspace_signature_help(self, uri, source, line, character)
            tag = _tag_at(source, line, character)
            if tag:
                return {"range": lsp_range(line, tag[1], tag[2]), "placeholder": tag[0]}
            block = block_at(source, line, character)
            return {"range": lsp_range(line, next((o.start for o in block.occurrences if o.line == line), 0), next((o.end for o in block.occurrences if o.line == line), 0)), "placeholder": block.label} if block and block.kind in RENAMABLE_LABEL_KINDS else None
        elif method == "textDocument/rename":
            uri = params["textDocument"]["uri"]; position = params["position"]
            new_name = params["newName"]
            tag = _tag_at(self.source(uri), position["line"], position["character"])
            if tag:
                return semantic_tag_workspace_edits(self, uri, tag[0], new_name)
            if not new_name.isidentifier() or not unicodedata.is_normalized("NFC", new_name): return None
            return label_edits(self.source(uri), position["line"], position["character"], new_name, uri)
        elif method == "textDocument/semanticTokens/full":
            return semantic_tokens(self.source(params["textDocument"]["uri"]))
        elif method == "textDocument/codeLens":
            return reference_code_lenses(self, params["textDocument"]["uri"])
        elif method == "codeLens/resolve":
            return params["item"]
        elif method == "workspace/executeCommand":
            if params.get("command") != "separan.runFunction":
                return None
            arguments = params.get("arguments") or []
            if len(arguments) < 2:
                return {"error": "Run SEP requires a document URI and SEP name."}
            call_arguments = arguments[2] if len(arguments) > 2 else []
            return run_logic(self, arguments[0], arguments[1], call_arguments)
        elif method == "callHierarchy/incomingCalls":
            return incoming_call_hierarchy(self, params.get("item", {}))
        elif method == "callHierarchy/outgoingCalls":
            return outgoing_call_hierarchy(self, params.get("item", {}))
        elif method == "textDocument/inlayHint":
            if self.initialization_options.get("inlayHints", True) is False: return []
            return inlay_hints(self.source(params["textDocument"]["uri"]), params["range"])
        elif method == "textDocument/formatting":
            source = self.source(params["textDocument"]["uri"]); formatted = format_source(source)
            if formatted == source: return []
            lines = source.splitlines()
            if source.endswith(("\n", "\r")): end_line, end_character = len(lines), 0
            else: end_line, end_character = max(0, len(lines) - 1), len(lines[-1]) if lines else 0
            return [{"range": lsp_range(0, 0, 0) | {"end": {"line": end_line, "character": end_character}}, "newText": formatted}]
        elif method == "textDocument/codeAction":
            uri = params["textDocument"]["uri"]; actions = []
            for item in params["context"].get("diagnostics", []):
                data = item.get("data") or {}; replacement = data.get("replacement"); actual = data.get("actual")
                if replacement and actual:
                    actions.append({"title": f"Replace with {data.get('title', replacement)}", "kind": "quickfix", "diagnostics": [item],
                        "edit": {"changes": {uri: [{"range": item["range"], "newText": replacement}]}}})
            return actions
        elif method in ("separan/structuralDiff", "separan/verifyScope", "separan/verifyTagScope"):
            before_source = params.get("before", ""); after_source = params.get("after", "")
            uri = params.get("uri", "<document>")
            try:
                before = inspect_source(before_source, uri + "@before")
                after = inspect_source(after_source, uri + "@after")
                if method == "separan/structuralDiff":
                    return structural_diff(before, after)
                if method == "separan/verifyTagScope":
                    return verify_tag_scope(before, after, params.get("tag", ""))
                return verify_scopes(before, after, params.get("scopes") or [])
            except (SeparanError, ScopeResolutionError) as exc:
                return {"error": str(exc)}
        elif method == "separan/scopeAt":
            uri = params["textDocument"]["uri"]; position = params["position"]
            try:
                return structural_scope_at(self.source(uri), position["line"], position["character"], uri)
            except SeparanError:
                return None
        elif method == "separan/documentStructure":
            uri = params["textDocument"]["uri"]
            try:
                return document_structure(self.source(uri), uri)
            except SeparanError as exc:
                return {"error": str(exc)}
        return None

    def run(self):
        while True:
            headers = {}
            while True:
                line = self.reader.readline()
                if not line: return 0
                if line in (b"\r\n", b"\n"): break
                name, value = line.decode("ascii").split(":", 1); headers[name.lower()] = value.strip()
            body = self.reader.read(int(headers.get("content-length", "0")))
            message = json.loads(body.decode("utf-8"))
            try: result = self.dispatch(message)
            except SystemExit as exc: return exc.code
            if "id" in message:
                self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})


def main(argv=None):
    argparse.ArgumentParser(prog="separan-lsp").parse_args(argv)
    return Server().run()


if __name__ == "__main__": raise SystemExit(main())
