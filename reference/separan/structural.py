"""AST-aware structure inspection, diffing, and AI edit-scope verification."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, fields, is_dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from .ast_nodes import (
    ErrorDecl, ForStmt, FunctionDecl, HttpRouteDecl, IfStmt, ListBlock,
    ObjectBlock, Program, TransactionStmt, TryStmt, WhileStmt,
)
from .errors import SeparanError
from .lexer import Lexer
from .parser import Parser
from .token import SourcePosition


NAMED_NODES = (
    FunctionDecl, IfStmt, WhileStmt, ForStmt, ObjectBlock, ListBlock,
    TryStmt, ErrorDecl, HttpRouteDecl, TransactionStmt,
)


@dataclass(frozen=True)
class BlockRecord:
    id: str
    path: str
    kind: str
    label: str
    parent_id: str | None
    start_line: int
    start_column: int
    tags: tuple[str, ...]
    own_fingerprint: str
    tree_fingerprint: str


@dataclass(frozen=True)
class StructureSnapshot:
    source_name: str
    source_fingerprint: str
    blocks: tuple[BlockRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "separan.structure.v2",
            "source": self.source_name,
            "source_fingerprint": self.source_fingerprint,
            "blocks": [asdict(item) for item in self.blocks],
        }


class ScopeResolutionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"SEPARAN {code}: {message}")


def _kind_and_label(node: Any) -> tuple[str, str]:
    if isinstance(node, FunctionDecl): return "function", node.name
    if isinstance(node, IfStmt): return "if", node.label
    if isinstance(node, WhileStmt): return "while", node.label
    if isinstance(node, ForStmt): return "for", node.label
    if isinstance(node, ObjectBlock): return "object", node.name
    if isinstance(node, ListBlock): return "list", node.name
    if isinstance(node, TryStmt): return "try", node.label
    if isinstance(node, ErrorDecl): return "error", node.name
    if isinstance(node, HttpRouteDecl): return "http_route", node.label
    if isinstance(node, TransactionStmt): return "transaction", node.label
    raise TypeError(f"Not a named Separan node: {type(node).__name__}")


def _canonical(value: Any, *, boundary_root: Any = None, replace_blocks: bool = False) -> Any:
    if isinstance(value, SourcePosition):
        return None
    if replace_blocks and isinstance(value, NAMED_NODES) and value is not boundary_root:
        kind, label = _kind_and_label(value)
        return {"$block": kind, "label": label}
    if isinstance(value, list):
        return [_canonical(item, boundary_root=boundary_root, replace_blocks=replace_blocks) for item in value]
    if isinstance(value, tuple):
        return [_canonical(item, boundary_root=boundary_root, replace_blocks=replace_blocks) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item, boundary_root=boundary_root, replace_blocks=replace_blocks)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if is_dataclass(value):
        members = {}
        for item in fields(value):
            member = getattr(value, item.name)
            if isinstance(member, SourcePosition):
                continue
            members[item.name] = _canonical(member, boundary_root=boundary_root, replace_blocks=replace_blocks)
        return {"node": type(value).__name__, "fields": members}
    return value


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _direct_named_children(container: Any) -> list[Any]:
    result = []

    def visit(value: Any, root: bool = False) -> None:
        if isinstance(value, SourcePosition):
            return
        if isinstance(value, NAMED_NODES) and not root:
            result.append(value)
            return
        if isinstance(value, (list, tuple)):
            for item in value: visit(item)
        elif isinstance(value, dict):
            for item in value.values(): visit(item)
        elif is_dataclass(value):
            for item in fields(value): visit(getattr(value, item.name))

    visit(container, root=True)
    return result


def inspect_source(source: str, source_name: str = "<source>") -> StructureSnapshot:
    program = Parser(Lexer(source, source_name).scan_tokens()).parse()
    records: list[BlockRecord] = []

    root_own = _canonical(program, boundary_root=program, replace_blocks=True)
    records.append(BlockRecord(
        id="root", path="root", kind="program", label="root", parent_id=None,
        start_line=1, start_column=1, tags=(), own_fingerprint=_fingerprint(root_own),
        tree_fingerprint=_fingerprint(_canonical(program)),
    ))

    def add_children(container: Any, parent_id: str, parent_path: str) -> None:
        counts: dict[tuple[str, str], int] = {}
        for node in _direct_named_children(container):
            kind, label = _kind_and_label(node)
            key = kind, label
            counts[key] = counts.get(key, 0) + 1
            segment = f"{kind}:{label}#{counts[key]}"
            identity = f"{parent_id}/{segment}"
            path = segment if parent_path == "root" else f"{parent_path}/{segment}"
            position = node.position
            own = _canonical(node, boundary_root=node, replace_blocks=True)
            records.append(BlockRecord(
                id=identity, path=path, kind=kind, label=label, parent_id=parent_id,
                start_line=position.line, start_column=position.column,
                tags=tuple(node.tags) if isinstance(node, FunctionDecl) else (),
                own_fingerprint=_fingerprint(own),
                tree_fingerprint=_fingerprint(_canonical(node)),
            ))
            add_children(node, identity, path)

    add_children(program, "root", "root")
    return StructureSnapshot(
        source_name=source_name,
        source_fingerprint=_fingerprint(_canonical(program)),
        blocks=tuple(records),
    )


def inspect_file(path: Path) -> StructureSnapshot:
    return inspect_source(path.read_text(encoding="utf-8"), str(path))


def structural_diff(before: StructureSnapshot, after: StructureSnapshot, *, include_unchanged: bool = False) -> dict[str, Any]:
    old = {item.id: item for item in before.blocks}
    new = {item.id: item for item in after.blocks}
    changes = []
    counts = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for identity in sorted(set(old) | set(new)):
        left, right = old.get(identity), new.get(identity)
        if left is None: status = "added"
        elif right is None: status = "removed"
        elif left.own_fingerprint != right.own_fingerprint: status = "modified"
        else: status = "unchanged"
        counts[status] += 1
        if status == "unchanged" and not include_unchanged:
            continue
        representative = right or left
        changes.append({
            "status": status, "id": identity, "path": representative.path,
            "kind": representative.kind, "label": representative.label,
            "before": asdict(left) if left else None,
            "after": asdict(right) if right else None,
        })
    return {
        "schema": "separan.structural-diff.v1",
        "before": before.source_name, "after": after.source_name,
        "summary": counts, "changes": changes,
    }


def _scope_matches(snapshot: StructureSnapshot, requested: str) -> list[BlockRecord]:
    query = requested.strip()
    if query.startswith(":"): query = query[1:]
    blocks = [item for item in snapshot.blocks if item.id != "root"]
    exact = [item for item in blocks if item.id == query or item.path == query]
    if exact: return exact
    without_ordinals = lambda path: "/".join(part.rsplit("#", 1)[0] for part in path.split("/"))
    path_matches = [item for item in blocks if without_ordinals(item.path) == query]
    if path_matches: return path_matches
    return [item for item in blocks if item.label == query]


def resolve_scopes(snapshot: StructureSnapshot, requested: Iterable[str]) -> tuple[BlockRecord, ...]:
    resolved = []
    for query in requested:
        matches = _scope_matches(snapshot, query)
        if not matches:
            raise ScopeResolutionError("S401", f"Unknown AI edit scope '{query}'.")
        if len(matches) > 1:
            choices = ", ".join(item.path for item in matches)
            raise ScopeResolutionError("S402", f"Ambiguous AI edit scope '{query}'. Use one of: {choices}")
        resolved.append(matches[0])
    if not resolved:
        raise ScopeResolutionError("S403", "At least one AI edit scope is required.")
    return tuple(resolved)


def verify_scopes(before: StructureSnapshot, after: StructureSnapshot, requested: Iterable[str]) -> dict[str, Any]:
    scopes = resolve_scopes(before, requested)
    diff = structural_diff(before, after)
    after_ids = {item.id for item in after.blocks}
    allowed, violations = [], []

    def inside(identity: str) -> bool:
        return any(identity == scope.id or identity.startswith(scope.id + "/") for scope in scopes)

    for scope in scopes:
        if scope.id not in after_ids:
            violations.append({"status": "boundary_removed", "id": scope.id, "path": scope.path,
                               "reason": "The named edit-scope boundary was removed, renamed, or moved."})
    for change in diff["changes"]:
        if inside(change["id"]):
            allowed.append(change)
        else:
            violations.append(change | {"reason": "Structural change is outside the allowed scope."})
    return {
        "schema": "separan.scope-verification.v1",
        "passed": not violations,
        "scopes": [{"id": item.id, "path": item.path, "kind": item.kind, "label": item.label} for item in scopes],
        "summary": {"allowed_changes": len(allowed), "violations": len(violations)},
        "allowed_changes": allowed, "violations": violations, "diff": diff,
    }


def _tag_path_matches(tags: tuple[str, ...], query: str) -> bool:
    return any(tag == query or tag.startswith(query + ":") for tag in tags)


def resolve_tag(snapshot: StructureSnapshot, tag: str) -> tuple[BlockRecord, ...]:
    query = tag[1:] if tag.startswith("@") else tag
    matches = tuple(
        item for item in snapshot.blocks
        if item.kind == "function" and _tag_path_matches(item.tags, query)
    )
    if not matches:
        raise ScopeResolutionError("S404", f"Unknown semantic tag '@{query}'.")
    return matches


def verify_tag_scope(before: StructureSnapshot, after: StructureSnapshot, tag: str) -> dict[str, Any]:
    query = tag[1:] if tag.startswith("@") else tag
    scopes = resolve_tag(before, query)
    diff = structural_diff(before, after)
    after_by_id = {item.id: item for item in after.blocks}
    allowed, violations = [], []

    def inside(identity: str) -> bool:
        return any(identity == scope.id or identity.startswith(scope.id + "/") for scope in scopes)

    for scope in scopes:
        current = after_by_id.get(scope.id)
        if current is None or not _tag_path_matches(current.tags, query):
            violations.append({"status": "boundary_removed", "id": scope.id, "path": scope.path,
                               "reason": f"The function was removed, moved, renamed, or detached from '@{query}'."})
    for change in diff["changes"]:
        if inside(change["id"]):
            allowed.append(change)
        else:
            violations.append(change | {"reason": f"Structural change is outside semantic scope '@{query}'."})
    return {
        "schema": "separan.semantic-scope-verification.v1",
        "passed": not violations,
        "tag": query,
        "functions": [{"id": item.id, "path": item.path, "name": item.label} for item in scopes],
        "summary": {"resolved_functions": len(scopes), "allowed_changes": len(allowed), "violations": len(violations)},
        "allowed_changes": allowed, "violations": violations, "diff": diff,
    }


def inspect_tag_path(path: Path, tag: str) -> dict[str, Any]:
    query = tag[1:] if tag.startswith("@") else tag
    paths = [path] if path.is_file() else sorted(path.rglob("*.sep"))
    functions = []
    for source_path in paths:
        snapshot = inspect_file(source_path)
        for item in snapshot.blocks:
            if item.kind == "function" and _tag_path_matches(item.tags, query):
                functions.append({"source": str(source_path), "path": item.path, "function": item.label,
                                  "line": item.start_line, "tags": list(item.tags)})
    if not functions:
        raise ScopeResolutionError("S404", f"Unknown semantic tag '@{query}'.")
    return {"schema": "separan.semantic-tag-index.v1", "tag": query,
            "function_count": len(functions), "functions": functions}


def verify_tag_paths(before_path: Path, after_path: Path, tag: str) -> dict[str, Any]:
    """Verify a semantic tag-path scope across either two files or two workspaces."""
    if before_path.is_file() and after_path.is_file():
        return verify_tag_scope(inspect_file(before_path), inspect_file(after_path), tag)
    if not before_path.is_dir() or not after_path.is_dir():
        raise ScopeResolutionError("S405", "Semantic workspace verification requires two files or two directories.")
    query = tag[1:] if tag.startswith("@") else tag
    before_files = {path.relative_to(before_path): path for path in before_path.rglob("*.sep")}
    after_files = {path.relative_to(after_path): path for path in after_path.rglob("*.sep")}
    snapshots_before = {relative: inspect_file(path) for relative, path in before_files.items()}
    snapshots_after = {relative: inspect_file(path) for relative, path in after_files.items()}
    scopes = [(relative, item) for relative, snapshot in snapshots_before.items()
              for item in snapshot.blocks if item.kind == "function" and _tag_path_matches(item.tags, query)]
    if not scopes:
        raise ScopeResolutionError("S404", f"Unknown semantic tag '@{query}'.")
    allowed, violations, all_changes = [], [], []
    empty = lambda name: inspect_source("", name)
    for relative in sorted(set(before_files) | set(after_files), key=str):
        before = snapshots_before[relative] if relative in snapshots_before else empty(str(relative) + "@before")
        after = snapshots_after[relative] if relative in snapshots_after else empty(str(relative) + "@after")
        diff = structural_diff(before, after)
        file_scopes = [item for file_name, item in scopes if file_name == relative]
        for change in diff["changes"]:
            contextual = change | {"source": str(relative), "path": f"{relative}:{change['path']}"}
            all_changes.append(contextual)
            if any(change["id"] == scope.id or change["id"].startswith(scope.id + "/") for scope in file_scopes):
                allowed.append(contextual)
            else:
                violations.append(contextual | {"reason": f"Structural change is outside semantic scope '@{query}'."})
    for relative, scope in scopes:
        after_snapshot = snapshots_after[relative] if relative in snapshots_after else empty(str(relative))
        current = next((item for item in after_snapshot.blocks
                        if item.id == scope.id), None)
        if current is None or not _tag_path_matches(current.tags, query):
            violations.append({"status": "boundary_removed", "id": scope.id,
                               "path": f"{relative}:{scope.path}", "source": str(relative),
                               "reason": f"The function was removed, moved, renamed, or detached from '@{query}'."})
    return {
        "schema": "separan.semantic-workspace-verification.v1", "passed": not violations, "tag": query,
        "functions": [{"source": str(relative), "id": item.id, "path": f"{relative}:{item.path}", "name": item.label}
                      for relative, item in scopes],
        "summary": {"resolved_functions": len(scopes), "allowed_changes": len(allowed), "violations": len(violations)},
        "allowed_changes": allowed, "violations": violations,
        "diff": {"schema": "separan.workspace-structural-diff.v1", "changes": all_changes},
    }


def _human_diff(report: dict[str, Any]) -> str:
    symbols = {"added": "+", "removed": "-", "modified": "~", "unchanged": "="}
    lines = ["Separan structural diff"]
    changes = report["changes"]
    if not changes: lines.append("No structural changes.")
    else:
        for item in changes: lines.append(f"{symbols[item['status']]} {item['path']} ({item['status']})")
    summary = report["summary"]
    lines.append(f"Added {summary['added']}, removed {summary['removed']}, modified {summary['modified']}, unchanged {summary['unchanged']}")
    return "\n".join(lines)


def _human_verification(report: dict[str, Any]) -> str:
    semantic = "tag" in report
    lines = [("PASS: semantic edit scope verified." if semantic else "PASS: AI edit scope verified.") if report["passed"] else
             ("FAIL: semantic edit scope violation." if semantic else "FAIL: AI edit scope violation.")]
    if semantic:
        lines.append("Allowed tag: @" + report["tag"])
        lines.append("Resolved functions: " + ", ".join(item["path"] for item in report["functions"]))
    else:
        lines.append("Allowed: " + ", ".join(item["path"] for item in report["scopes"]))
    for item in report["violations"]:
        lines.append(f"! {item['path']}: {item['reason']}")
    lines.append(f"Allowed changes {report['summary']['allowed_changes']}, violations {report['summary']['violations']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="separan-structure", description="AST-aware Separan review tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="emit machine-readable block identities")
    inspect_parser.add_argument("source", type=Path, nargs="?", default=Path(".")); inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.add_argument("--tag", metavar="TAG", help="list functions carrying a semantic tag path or one of its descendants")
    diff_parser = subparsers.add_parser("diff", help="compare two Separan programs structurally")
    diff_parser.add_argument("before", type=Path); diff_parser.add_argument("after", type=Path)
    diff_parser.add_argument("--json", action="store_true"); diff_parser.add_argument("--include-unchanged", action="store_true")
    verify_parser = subparsers.add_parser("verify", help="reject changes outside named AI edit scopes")
    verify_parser.add_argument("before", type=Path); verify_parser.add_argument("after", type=Path)
    scope_group = verify_parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--allow", action="append", metavar="SCOPE")
    scope_group.add_argument("--allow-tag", metavar="TAG")
    verify_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            if args.tag:
                report = inspect_tag_path(args.source, args.tag)
                if args.json: print(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    print("Tag: @" + report["tag"])
                    for item in report["functions"]: print(f"{item['source']}\n  function:{item['function']}")
                return 0
            report = inspect_file(args.source).to_dict()
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else "\n".join(item["path"] for item in report["blocks"]))
            return 0
        if args.command == "diff":
            before, after = inspect_file(args.before), inspect_file(args.after)
            report = structural_diff(before, after, include_unchanged=args.include_unchanged)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _human_diff(report))
            return 0
        if args.allow_tag:
            report = verify_tag_paths(args.before, args.after, args.allow_tag)
        else:
            report = verify_scopes(inspect_file(args.before), inspect_file(args.after), args.allow)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _human_verification(report))
        return 0 if report["passed"] else 1
    except (SeparanError, ScopeResolutionError, UnicodeDecodeError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
