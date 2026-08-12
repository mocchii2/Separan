from dataclasses import fields, is_dataclass
from .ast_nodes import Node
from .token import SourcePosition


def format_ast(node, indent=0):
    pad = "  " * indent
    if isinstance(node, list): return "\n".join(format_ast(x, indent) for x in node)
    if not is_dataclass(node): return pad + repr(node)
    title = type(node).__name__
    extras = []
    for name in ("name", "label", "variable", "operator"):
        if hasattr(node, name): extras.append(f"{name}={getattr(node, name)}")
    lines = [pad + title + ((" " + " ".join(extras)) if extras else "")]
    for f in fields(node):
        if f.name in {"position", "label_position", "name", "label", "variable", "operator"}: continue
        value = getattr(node, f.name)
        if isinstance(value, Node) or (isinstance(value, list) and value):
            lines.append(pad + f"  {f.name}:")
            lines.append(format_ast(value, indent + 2))
    return "\n".join(lines)

