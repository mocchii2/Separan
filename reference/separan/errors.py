from dataclasses import dataclass

from .token import SourcePosition


@dataclass
class SeparanError(Exception):
    code: str
    category: str
    description: str
    position: SourcePosition
    expected: str | None = None
    actual: str | None = None
    related: SourcePosition | None = None

    def __str__(self) -> str:
        p = self.position
        width = max(1, len(self.actual or ""))
        parts = [
            f"SEPARAN {self.code}: {self.category}", "",
            f"File: {p.file}", f"Line: {p.line}", f"Column: {p.column}", "",
            p.source_line, " " * (p.column - 1) + "^" * width, "", self.description,
        ]
        if self.expected is not None:
            parts += ["", "Expected:", self.expected]
        if self.actual is not None:
            parts += ["", "Actual:", self.actual]
        if self.related is not None:
            parts += ["", "Opened here:", f"Line {self.related.line}", self.related.source_line]
        return "\n".join(parts)


def error(code, category, description, position, **details):
    return SeparanError(code, category, description, position, **details)


@dataclass(frozen=True)
class ErrorValue:
    category: str
    message: str
