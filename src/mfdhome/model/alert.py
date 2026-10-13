"""Alert data types. Behavior (preemption, acknowledgement) lives in ``mfd``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Alert severity, in increasing order of urgency."""

    ADVISORY = "advisory"
    CAUTION = "caution"
    WARNING = "warning"


@dataclass(frozen=True)
class Alert:
    """An alert raised against a page."""

    id: str
    severity: Severity
    message: str
    page_id: str
