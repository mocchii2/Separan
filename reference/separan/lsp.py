"""Dependency-free Language Server Protocol preview for Separan."""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import SeparanError
from .lexer import Lexer
from .parser import Parser


BLOCKS = {
    "function": ("end_function", 12), "if": ("endif", 5),
    "while": ("endwhile", 5), "for": ("endfor", 5),
    "object": ("end_object", 23), "list": ("end_list", 18),
    "try": ("endtry", 5), "error": ("end_error", 5),
    "http_route": ("end_http_route", 12), "transaction": ("end_transaction", 5),
}
LABEL_PATTERN = r"([^\s:()]+)"
OPEN_RE = re.compile(r"^\s*(function|if|while|for|object|list|try|error|http_route|transaction)\b.*?:" + LABEL_PATTERN + r"\s*(?:\([^\n]*\))?\s*$")
CLOSE_RE = re.compile(r"^\s*(end_function|endif|endwhile|endfor|end_object|end_list|endtry|end_error|end_http_route|end_transaction):" + LABEL_PATTERN + r"\s*$")


def _range(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


def diagnostic(source, uri):
    try:
        Parser(Lexer(source, uri).scan_tokens()).parse()
        return []
    except SeparanError as exc:
        line = max(0, exc.position.line - 1)
        start = max(0, exc.position.column - 1)
        width = max(1, len(exc.actual or ""))
        item = {"range": _range(line, start, start + width), "severity": 1,
                "code": exc.code, "source": "separan", "message": f"{exc.category}: {exc.description}"}
        if exc.related is not None:
            item["relatedInformation"] = [{"location": {"uri": uri, "range": _range(exc.related.line - 1, exc.related.column - 1, exc.related.column)}, "message": "Opened here"}]
        return [item]


@dataclass
class Block:
    kind: str
    label: str
    line: int
    start: int
    symbol_kind: int
    end_line: int | None = None
    children: list = field(default_factory=list)


def blocks(source):
    roots, stack = [], []
    closer_to_kind = {closer: kind for kind, (closer, _) in BLOCKS.items()}
    for number, text in enumerate(source.splitlines()):
        opened = OPEN_RE.match(text)
        if opened:
            kind, label = opened.groups()
            item = Block(kind, label, number, text.index(kind), BLOCKS[kind][1])
            (stack[-1].children if stack else roots).append(item)
            stack.append(item)
            continue
        closed = CLOSE_RE.match(text)
        if closed:
            closer, label = closed.groups()
            if stack and stack[-1].kind == closer_to_kind[closer] and stack[-1].label == label:
                stack.pop().end_line = number
    return roots


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


class Server:
    def __init__(self, reader=None, writer=None):
        self.reader = reader or sys.stdin.buffer
        self.writer = writer or sys.stdout.buffer
        self.documents = {}
        self.shutdown_requested = False

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
            return {"capabilities": {"textDocumentSync": 1, "documentSymbolProvider": True, "foldingRangeProvider": True},
                    "serverInfo": {"name": "separan-lsp", "version": "0.1.0-alpha.1"}}
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
            source = self.documents.get(uri)
            if source is None and uri.startswith("file:"):
                source = Path(unquote(urlparse(uri).path.lstrip("/") if sys.platform == "win32" else urlparse(uri).path)).read_text(encoding="utf-8")
            return document_symbols(source or "") if method.endswith("documentSymbol") else folding_ranges(source or "")
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
