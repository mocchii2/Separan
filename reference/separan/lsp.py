"""Dependency-free Language Server Protocol preview for Separan."""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import SeparanError
from .builtins import BUILTINS
from .lexer import Lexer
from .parser import Parser
from .structural import ScopeResolutionError, inspect_source, structural_diff, verify_scopes, verify_tag_scope
from .structure_insights import document_structure
from .lsp_analysis import (
    BLOCK_KINDS, BUILTIN_SIGNATURES, analyze_blocks, block_at, format_source,
    lsp_range, resolve_variable, static_type_diagnostics, variable_at, variables, word_at,
)

for _builtin_name in BUILTINS:
    BUILTIN_SIGNATURES.setdefault(_builtin_name, f"{_builtin_name}(...)")


def _range(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


def diagnostic(source, uri):
    try:
        Parser(Lexer(source, uri).scan_tokens()).parse()
        return static_type_diagnostics(source)
    except SeparanError as exc:
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
        return [item]


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
KEYWORDS = {"function", "end_function", "if", "elseif", "else", "endif", "while", "endwhile", "for", "endfor", "return", "const", "object", "end_object", "list", "end_list", "try", "catch", "finally", "endtry", "throw", "transaction", "end_transaction", "http_route", "end_http_route", "import", "as", "in", "not"}
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
        opened = re.match(r"^\s*function:([A-Za-z_][A-Za-z0-9_]*)", text)
        if opened: scope = "function " + opened.group(1)
        scopes.append(scope)
        if re.match(r"^\s*end_function:", text): scope = "global"
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
            elif word in ("true", "false", "null"): add(line_no, found.start(), len(word), "type")
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
    variable = variable_at(source, line, character)
    if variable:
        mutable = "no (readonly)" if variable.constant else "yes"; members = ""
        if variable.members: members = "\n\nMembers:\n" + "\n".join(f"- `{name}`: {kind}" for name, kind in variable.members.items())
        value = "\n\nValue: `<redacted>`" if variable.type == "secret" else ""
        return {"contents": {"kind": "markdown", "value": f"**{variable.name}**\n\nType: `{variable.type}`  \nScope: `{variable.scope}`  \nMutable: {mutable}  \nDefined: line {variable.line + 1}{value}{members}"}}
    word = word_at(source, line, character)
    if word and word[0] in BUILTIN_SIGNATURES: return {"contents": {"kind": "markdown", "value": "```separan\n" + BUILTIN_SIGNATURES[word[0]] + "\n```"}}
    if word:
        function = re.search(r"^\s*function:" + re.escape(word[0]) + r"(?:\(([^)]*)\))?", source, re.MULTILINE)
        if function:
            params = function.group(1) or ""
            return {"contents": {"kind": "markdown", "value": f"```separan\n{word[0]}({params}) -> inferred\n```"}}
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
        pattern = re.compile(r"^\s*function:" + re.escape(word[0]) + r"\b")
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
    tag_prefix = re.match(r"^\s*@([^\s#]*)$", prefix)
    if tag_prefix:
        typed = tag_prefix.group(1)
        known_tags = sorted(tag for tag in set(re.findall(r"^\s*@([^\s#]+)\s*(?:#.*)?$", source, re.MULTILINE))
                            if tag.startswith(typed) and tag != typed)
        start = prefix.index("@")
        return {"isIncomplete": False, "items": [
            {"label": "@" + tag, "kind": 14, "sortText": "0" + tag,
             "textEdit": {"range": _range(line, start, character), "newText": "@" + tag},
             "detail": "Separan function semantic tag"} for tag in known_tags
        ]}
    for name, signature in BUILTIN_SIGNATURES.items():
        items.append({"label": name, "kind": 3, "sortText": "1" + name, "insertText": name + "($0)", "insertTextFormat": 2, "detail": signature})
    for function in re.finditer(r"^\s*function:([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?", source, re.MULTILINE):
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
        function = re.search(r"^\s*function:" + re.escape(match.group(1)) + r"(?:\(([^)]*)\))?", source, re.MULTILINE)
        if not function: return None
        label = f"{match.group(1)}({function.group(1) or ''}) -> inferred"
    active = match.group(2).count(",")
    return {"signatures": [{"label": label}], "activeSignature": 0, "activeParameter": active}


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
        self.shutdown_requested = False
        self.initialization_options = {}

    def source(self, uri):
        source = self.documents.get(uri)
        if source is None and uri.startswith("file:"):
            path = unquote(urlparse(uri).path.lstrip("/") if sys.platform == "win32" else urlparse(uri).path)
            source = Path(path).read_text(encoding="utf-8")
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
            return {"capabilities": {"textDocumentSync": 1, "documentSymbolProvider": True, "foldingRangeProvider": True,
                    "hoverProvider": True, "definitionProvider": True, "renameProvider": {"prepareProvider": True},
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
                        "textDocument/completion", "textDocument/signatureHelp", "textDocument/prepareRename"):
            uri = params["textDocument"]["uri"]; source = self.source(uri); position = params["position"]
            line, character = position["line"], position["character"]
            if method.endswith("hover"): return hover(source, line, character)
            if method.endswith("definition"): return definition(source, line, character, uri)
            if method.endswith("documentHighlight"): return highlights(source, line, character)
            if method.endswith("completion"): return completions(source, line, character)
            if method.endswith("signatureHelp"): return signature_help(source, line, character)
            tag = _tag_at(source, line, character)
            if tag:
                return {"range": lsp_range(line, tag[1], tag[2]), "placeholder": tag[0]}
            block = block_at(source, line, character)
            return {"range": lsp_range(line, next((o.start for o in block.occurrences if o.line == line), 0), next((o.end for o in block.occurrences if o.line == line), 0)), "placeholder": block.label} if block and block.kind in RENAMABLE_LABEL_KINDS else None
        elif method == "textDocument/rename":
            uri = params["textDocument"]["uri"]; position = params["position"]
            new_name = params["newName"]
            if not new_name.isidentifier() or not unicodedata.is_normalized("NFC", new_name): return None
            tag = _tag_at(self.source(uri), position["line"], position["character"])
            if tag:
                edits = []
                for number, text in enumerate(self.source(uri).splitlines()):
                    found = re.match(r"^\s*@" + re.escape(tag[0]) + r"(?=\s|#|$)", text)
                    if found:
                        start = found.end() - len(tag[0]); edits.append({"range": lsp_range(number, start, start + len(tag[0])), "newText": new_name})
                return {"changes": {uri: edits}}
            return label_edits(self.source(uri), position["line"], position["character"], new_name, uri)
        elif method == "textDocument/semanticTokens/full":
            return semantic_tokens(self.source(params["textDocument"]["uri"]))
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
