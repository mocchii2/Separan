from dataclasses import dataclass
import unicodedata

from .token import SourcePosition


def _display_width(value: str) -> int:
    width = 0
    for character in value:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
    return width


def _highlight_width(position: SourcePosition, actual: str | None) -> int:
    if not actual:
        return 1
    start = max(0, position.column - 1)
    candidates = [actual]
    if ":" in actual:
        candidates.append(actual.split(":", 1)[1])
    for candidate in candidates:
        if candidate and position.source_line.startswith(candidate, start):
            return max(1, _display_width(candidate.expandtabs(4)))
    return 1


def _source_excerpt(position: SourcePosition, marker_width: int = 1) -> list[str]:
    number = str(position.line)
    gutter = " " * len(number)
    source = position.source_line.expandtabs(4)
    prefix = position.source_line[:max(0, position.column - 1)].expandtabs(4)
    marker = " " * _display_width(prefix) + "^" * max(1, marker_width)
    return [
        f" --> {position.file}:{position.line}:{position.column}",
        f"{gutter} |",
        f"{number} | {source}",
        f"{gutter} | {marker}",
    ]


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
        parts = [
            f"SEPARAN {self.code}: {self.category}", "",
            *_source_excerpt(p, _highlight_width(p, self.actual)), "", self.description,
        ]
        if self.expected is not None:
            parts += ["", "Expected:", self.expected]
        if self.actual is not None:
            parts += ["", "Actual:", self.actual]
        if self.related is not None:
            parts += ["", "Opened here:", *_source_excerpt(self.related)]
        return "\n".join(parts)


def error(code, category, description, position, **details):
    return SeparanError(code, category, description, position, **details)


@dataclass(frozen=True)
class ErrorValue:
    category: str
    message: str
