"""Alert definitions. Runtime state (latching, acknowledgement) lives in ``mfd``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Annotation-only: conditions imports model.binding, so a runtime import would cycle.
    from mfdhome.conditions.model import AnyOf


class Severity(StrEnum):
    """Alert severity, in increasing order of urgency."""

    ADVISORY = "advisory"
    CAUTION = "caution"
    WARNING = "warning"

    @property
    def rank(self) -> int:
        """0 for advisory up to 2 for warning."""
        return list(Severity).index(self)

    @property
    def preempts(self) -> bool:
        """Cautions and warnings preempt page rotation; advisories never do."""
        return self is not Severity.ADVISORY

    @property
    def latches(self) -> bool:
        """Cautions and warnings stay until acknowledged; advisories clear on their own."""
        return self is not Severity.ADVISORY


@dataclass(frozen=True)
class System:
    """A house system that alerts are grouped under (one annunciator tile each)."""

    id: str
    label: str


@dataclass(frozen=True)
class AlertDef:
    """An alert: raised while ``condition`` holds.

    ``page`` is shown when the alert preempts rotation (required for cautions
    and warnings, optional for advisories).
    """

    id: str
    severity: Severity
    system: str
    message: str
    condition: AnyOf
    page: str | None = None
