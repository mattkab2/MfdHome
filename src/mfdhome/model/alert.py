"""Alert definitions. Runtime state (latching, acknowledgement) lives in ``mfd``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
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
    def needs_ack(self) -> bool:
        """Cautions and warnings latch until acknowledged and ask for attention;
        advisories clear on their own and never do."""
        return self is not Severity.ADVISORY


@dataclass(frozen=True)
class System:
    """A house system that alerts are grouped under (one annunciator tile each)."""

    id: str
    label: str


@dataclass(frozen=True)
class AlertDef:
    """An alert: raised while ``condition`` holds.

    ``page`` optionally names the page the alert relates to (for a future
    "jump to page" control; alerts never switch pages on their own).
    ``hold`` is how long the condition must hold before the alert is raised,
    and stop holding before it clears (zero: immediately).
    """

    id: str
    severity: Severity
    system: str
    message: str
    condition: AnyOf
    page: str | None = None
    hold: timedelta = timedelta(0)
