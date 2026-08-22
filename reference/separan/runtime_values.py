"""Internal sentinels for absence and non-value function completion.

These values are deliberately distinct from Python ``None``, which continues
to represent legacy Separan ``null`` until the staged EMPTY migration reaches
the external API boundary.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmptyValue:
    """A value slot whose declared type is retained but whose value is absent."""

    declared_type: str | None = None
    element_type: str | None = None


@dataclass(frozen=True)
class VoidResult:
    """Function completion that produced no value."""


EMPTY = EmptyValue()
VOID = VoidResult()

