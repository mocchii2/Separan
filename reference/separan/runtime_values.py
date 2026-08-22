"""Internal sentinels for absence and non-value function completion.

These values are deliberately distinct from Python ``None``. Host adapters may
use ``None`` internally, but it is converted at every Separan value boundary.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmptyValue:
    """A value slot whose declared type is retained but whose value is absent."""

    declared_type: str | None = None
    element_type: str | None = None
    external: bool = False


@dataclass(frozen=True)
class VoidResult:
    """Function completion that produced no value."""


@dataclass(frozen=True)
class EmptysValue:
    """Operation marker requesting that a container retain only empty slots."""


EMPTY = EmptyValue()
EMPTYS = EmptysValue()
VOID = VoidResult()


def empty_of(declared_type=None, element_type=None, *, external=False):
    """Create an EMPTY value that retains the API's documented result type."""

    return EmptyValue(declared_type, element_type, external)
