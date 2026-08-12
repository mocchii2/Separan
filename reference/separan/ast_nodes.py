from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any

from .token import SourcePosition


@dataclass
class Node: position: SourcePosition
@dataclass
class Expr(Node): pass
@dataclass
class LiteralExpr(Expr): value: Any
@dataclass
class VariableExpr(Expr): name: str
@dataclass
class BinaryExpr(Expr): left: Expr; operator: str; right: Expr
@dataclass
class UnaryExpr(Expr): operator: str; operand: Expr
@dataclass
class GroupExpr(Expr): expression: Expr
@dataclass
class CallExpr(Expr):
    callee: str
    arguments: list[Expr]
    named_arguments: dict[str, Expr] = field(default_factory=dict)
@dataclass
class ListExpr(Expr): elements: list[Expr]
@dataclass
class IndexExpr(Expr): target: Expr; index: Expr
@dataclass
class MemberExpr(Expr): target: Expr; name: str
@dataclass
class MemberCallExpr(Expr): target: Expr; name: str; arguments: list[Expr]; named_arguments: dict[str, Expr] = field(default_factory=dict)

@dataclass
class Stmt(Node): pass
@dataclass
class Assignment(Stmt): name: str; value: Expr
@dataclass
class ConstDeclaration(Stmt): name: str; value: Expr
@dataclass
class PrintStmt(Stmt): value: Expr
@dataclass
class PrintErrorStmt(Stmt): value: Expr
@dataclass
class ReturnStmt(Stmt): value: Expr | None
@dataclass
class ExpressionStmt(Stmt): expression: Expr
@dataclass
class ObjectField(Node): name: str; value: Expr
@dataclass
class ObjectBlock(Stmt): name: str; entries: list[Node]; label_position: SourcePosition
@dataclass
class ListBlock(Stmt): name: str; elements: list[Expr]; label_position: SourcePosition
@dataclass
class ImportStmt(Stmt): path: str; alias: str
@dataclass
class CatchBranch(Node): category: str; body: list[Stmt]
@dataclass
class TryStmt(Stmt): label: str; body: list[Stmt]; catches: list[CatchBranch]; finally_body: list[Stmt] | None; label_position: SourcePosition
@dataclass
class ThrowStmt(Stmt): value: Expr
@dataclass
class ErrorDecl(Stmt): name: str; label_position: SourcePosition
@dataclass
class HttpRouteDecl(Stmt): method: str; path: str; label: str; body: list[Stmt]; label_position: SourcePosition
@dataclass
class TransactionStmt(Stmt): connection: Expr; label: str; body: list[Stmt]; label_position: SourcePosition
@dataclass
class IfBranch:
    condition: Expr
    body: list[Stmt]
    position: SourcePosition
@dataclass
class IfStmt(Stmt):
    label: str
    branches: list[IfBranch]
    else_body: list[Stmt] | None
    label_position: SourcePosition
@dataclass
class WhileStmt(Stmt):
    label: str
    condition: Expr
    body: list[Stmt]
    label_position: SourcePosition
@dataclass
class ForStmt(Stmt):
    label: str
    variable: str
    iterable: Expr
    body: list[Stmt]
    label_position: SourcePosition
@dataclass
class FunctionDecl(Stmt):
    name: str
    parameters: list[str]
    body: list[Stmt]
    label_position: SourcePosition
@dataclass
class Program(Node): statements: list[Stmt] = field(default_factory=list)


def ast_structural_equal(left, right):
    """Compare AST meaning while deliberately excluding source locations."""
    return _structural_value(left) == _structural_value(right)


def _structural_value(value):
    if isinstance(value, SourcePosition):
        return None
    if isinstance(value, list):
        return tuple(_structural_value(item) for item in value)
    if is_dataclass(value):
        return (
            type(value),
            tuple(
                (item.name, _structural_value(getattr(value, item.name)))
                for item in fields(value)
                if not isinstance(getattr(value, item.name), SourcePosition)
            ),
        )
    return value
