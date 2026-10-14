"""The alert information render needs, derived from definitions and the board."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from mfdhome.conditions.values import read
from mfdhome.mfd.alerts import INACTIVE, Board, Phase, attention_order
from mfdhome.model.alert import AlertDef, Severity, System
from mfdhome.model.binding import EntityRef, Status
from mfdhome.model.state import StateSnapshot

#: How each severity is colored.
SEVERITY_STATUS: Mapping[Severity, Status] = {
    Severity.ADVISORY: Status.ACTIVE,
    Severity.CAUTION: Status.CAUTION,
    Severity.WARNING: Status.WARNING,
}


@dataclass(frozen=True)
class SystemView:
    """What one annunciator tile shows.

    ``severity`` is the worst lit alert (active or latched), ``None`` if dark.
    ``cleared`` means every lit alert at that severity is latched, not active.
    ``unacknowledged`` counts cautions and warnings only: advisories never
    demand attention. ``unavailable`` means every entity the system's alerts
    read has no data, so a dark tile would be misleading.
    """

    severity: Severity | None
    cleared: bool = False
    unacknowledged: bool = False
    unavailable: bool = False


@dataclass(frozen=True)
class Banner:
    """The annunciator banner: the most urgent alert, plus how many others need attention."""

    alert: AlertDef
    others: int = 0


@dataclass(frozen=True)
class AlertView:
    """Alert definitions, systems and the shared board, as one render input."""

    alerts: tuple[AlertDef, ...] = ()
    systems: Mapping[str, System] = field(default_factory=dict)
    board: Board = field(default_factory=dict)
    show_banner: bool = False

    def phase(self, alert_id: str) -> Phase:
        """Current phase of an alert."""
        return self.board.get(alert_id, INACTIVE).phase

    def in_system(self, system: str) -> Iterator[AlertDef]:
        """Alerts grouped under ``system``."""
        return (a for a in self.alerts if a.system == system)

    def system(self, system: str, state: StateSnapshot) -> SystemView:
        """Combine a system's alerts into what its tile shows."""
        members = list(self.in_system(system))
        lit = [a for a in members if self.phase(a.id).lit]
        if lit:
            worst = max((a.severity for a in lit), key=lambda s: s.rank)
            top = [a for a in lit if a.severity is worst]
            cleared = all(self.phase(a.id) is Phase.CLEARED_UNACKED for a in top)
        else:
            worst, cleared = None, False
        unacked = any(self.phase(a.id).unacknowledged and a.severity.needs_ack for a in members)
        refs = {ref for a in members for ref in _entity_refs(a)}
        unavailable = bool(refs) and all(not read(r, state).available for r in refs)
        return SystemView(worst, cleared, unacked, unavailable)

    def active_status(self, systems: tuple[str, ...], alerts: tuple[str, ...]) -> Status | None:
        """Worst *active* caution/warning among the given systems and alert ids."""
        relevant = [
            a
            for a in self.alerts
            if (a.system in systems or a.id in alerts)
            and a.severity.needs_ack
            and self.phase(a.id) in (Phase.ACTIVE_UNACKED, Phase.ACTIVE_ACKED)
        ]
        if not relevant:
            return None
        return SEVERITY_STATUS[max((a.severity for a in relevant), key=lambda s: s.rank)]

    def banner(self) -> Banner | None:
        """The banner to show, if enabled and a caution/warning is unacknowledged."""
        if not self.show_banner:
            return None
        pending = [a for a in attention_order(self.board, self.alerts) if a.severity.needs_ack]
        return Banner(pending[0], len(pending) - 1) if pending else None


def _entity_refs(alert: AlertDef) -> Iterator[EntityRef]:
    for term in alert.condition.terms:
        for cond in term.conditions:
            if isinstance(cond.ref, EntityRef):
                yield cond.ref


NO_ALERTS = AlertView()
