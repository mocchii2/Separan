"""Static, non-executing summaries for named Separan structures."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from .ast_nodes import (
    Assignment, CallExpr, ConstDeclaration, ForStmt, FunctionDecl, IndexExpr,
    ListBlock, MemberCallExpr, MemberExpr, ObjectBlock, Program, VariableExpr,
)
from .lexer import Lexer
from .lsp_analysis import analyze_blocks
from .parser import Parser
from .structural import NAMED_NODES, _direct_named_children, inspect_source
from .token import SourcePosition


class _OrderedNames:
    def __init__(self):
        self.items: list[str] = []
        self.seen: set[str] = set()

    def add(self, value: str) -> None:
        if value not in self.seen:
            self.seen.add(value)
            self.items.append(value)


@dataclass(frozen=True)
class BlockInsights:
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    calls: tuple[str, ...]
    parameters: tuple[str, ...]


def _qualified_name(expression: Any) -> str | None:
    if isinstance(expression, VariableExpr):
        return expression.name
    if isinstance(expression, MemberExpr):
        target = _qualified_name(expression.target)
        return f"{target}.{expression.name}" if target else None
    return None


def summarize_block(node: Any) -> BlockInsights:
    """Summarize direct work in a block, excluding nested named blocks."""
    reads, writes, calls = _OrderedNames(), _OrderedNames(), _OrderedNames()

    def visit(value: Any, *, root: bool = False) -> None:
        if isinstance(value, SourcePosition):
            return
        if isinstance(value, NAMED_NODES) and not root:
            return
        if isinstance(value, Assignment):
            writes.add(value.name); visit(value.value); return
        if isinstance(value, ConstDeclaration):
            writes.add(value.name); visit(value.value); return
        if isinstance(value, VariableExpr):
            reads.add(value.name); return
        if isinstance(value, MemberExpr):
            qualified = _qualified_name(value)
            if qualified: reads.add(qualified)
            else: visit(value.target)
            return
        if isinstance(value, CallExpr):
            calls.add(value.callee)
            visit(value.arguments); visit(value.named_arguments)
            return
        if isinstance(value, MemberCallExpr):
            target = _qualified_name(value.target)
            calls.add(f"{target}.{value.name}" if target else value.name)
            visit(value.target); visit(value.arguments); visit(value.named_arguments)
            return
        if isinstance(value, IndexExpr):
            visit(value.target); visit(value.index); return
        if isinstance(value, (list, tuple)):
            for item in value: visit(item)
            return
        if isinstance(value, dict):
            for item in value.values(): visit(item)
            return
        if is_dataclass(value):
            for item in fields(value): visit(getattr(value, item.name))

    if isinstance(node, ForStmt):
        writes.add(node.variable)
    if isinstance(node, (ObjectBlock, ListBlock)):
        writes.add(node.name)
    visit(node, root=True)
    parameters = tuple(node.parameters) if isinstance(node, FunctionDecl) else ()
    return BlockInsights(tuple(reads.items), tuple(writes.items), tuple(calls.items), parameters)


def _named_preorder(container: Any) -> list[Any]:
    result = []
    for child in _direct_named_children(container):
        result.append(child)
        result.extend(_named_preorder(child))
    return result


def document_structure(source: str, source_name: str = "<source>") -> dict[str, Any]:
    """Return a versioned hierarchy for editor structure explorers."""
    program: Program = Parser(Lexer(source, source_name).scan_tokens()).parse()
    snapshot = inspect_source(source, source_name)
    records = list(snapshot.blocks[1:])
    nodes = _named_preorder(program)
    if len(records) != len(nodes):
        raise RuntimeError("Separan structure identity and AST traversal disagree.")

    _, parsed_blocks = analyze_blocks(source)
    ranges = {(item.kind, item.label, item.line + 1): item for item in parsed_blocks}
    items: list[dict[str, Any]] = []
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for record, node in zip(records, nodes):
        insights = summarize_block(node)
        parsed = ranges.get((record.kind, record.label, record.start_line))
        end_line = (parsed.end_line + 1) if parsed and parsed.end_line is not None else record.start_line
        item = {
            "id": record.id, "path": record.path, "parent_id": record.parent_id,
            "kind": record.kind, "label": record.label,
            "start_line": record.start_line, "start_column": record.start_column,
            "end_line": end_line,
            "reads": list(insights.reads), "writes": list(insights.writes),
            "calls": list(insights.calls), "parameters": list(insights.parameters),
            "tags": list(node.tags) if isinstance(node, FunctionDecl) else [],
            "children": [],
        }
        items.append(item)
        by_parent.setdefault(record.parent_id or "root", []).append(item)
    for item in items:
        item["children"] = by_parent.get(item["id"], [])
    return {
        "schema": "separan.document-structure.v2",
        "source": source_name,
        "roots": by_parent.get("root", []),
        "block_count": len(items),
    }
