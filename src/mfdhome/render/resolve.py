"""Resolving elements to status and channel values, bottom-up through groups."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from mfdhome.conditions.evaluate import SEVERITY_ORDER, EvalContext
from mfdhome.conditions.model import ChannelRef
from mfdhome.conditions.values import MISSING, Value
from mfdhome.model.alert import Severity
from mfdhome.model.binding import Binding, Status
from mfdhome.model.page import (
    Aggregate,
    DerivedChannel,
    Element,
    EnclosureElement,
    GroupElement,
    LineElement,
    RoomElement,
    SymbolElement,
    TileElement,
)
from mfdhome.model.state import StateSnapshot
from mfdhome.render.alerts import AlertView
from mfdhome.render.status import element_status
from mfdhome.symbols.registry import LINE_CHANNELS, LINE_NUMERIC, get_symbol, line_primary

_NO_VALUES: Mapping[str, Value] = {}


@dataclass(frozen=True)
class Resolved:
    """An element's status and channel values (bound or derived)."""

    status: Status
    values: Mapping[str, Value] = field(default_factory=dict)


class Resolver:
    """Resolves elements against one state snapshot and alert view.

    ``elements`` holds other elements' channel values, for bindings that refer
    to another element (``array.power``); ``by_id`` the page's top-level
    elements, for enclosures' members. Results are cached by element id.
    """

    def __init__(
        self,
        state: StateSnapshot,
        alerts: AlertView,
        elements: Mapping[str, Mapping[str, Value]] = {},
        by_id: Mapping[str, Element] = {},
    ) -> None:
        self.state = state
        self.alerts = alerts
        self.elements = elements
        self.by_id = by_id
        self._cache: dict[str, Resolved] = {}

    def context(
        self, bind: Mapping[str, Binding], derived: Mapping[str, Value] = _NO_VALUES
    ) -> EvalContext:
        """An evaluation context for an element with these bindings and derived channels."""
        return EvalContext(self.state, bind, derived, self.elements)

    def element(self, element: Element) -> Resolved | None:
        """Resolve a symbol, line, tile, group or enclosure; ``None`` for kinds without a
        status."""
        if element.id in self._cache:
            return self._cache[element.id]
        match element:
            case SymbolElement():
                spec = get_symbol(element.type)
                result = self._bound(
                    element, spec.channels, spec.primary, spec.primary in spec.numeric
                )
            case LineElement():
                primary = line_primary(element.bind)
                result = self._bound(element, LINE_CHANNELS, primary, primary in LINE_NUMERIC)
            case TileElement():
                result = self._tile(element)
            case GroupElement():
                result = self._group(element)
            case EnclosureElement():
                members = (self.element(self.by_id[m]) for m in element.members if m in self.by_id)
                result = Resolved(_combined([r for r in members if r is not None]))
            case RoomElement():
                alert_status = self.alerts.active_status(
                    element.status.systems, element.status.alerts
                )
                status = element_status(element.status, self.context({}), "", False, alert_status)
                result = Resolved(status)
            case _:
                return None
        self._cache[element.id] = result
        return result

    def _bound(
        self,
        element: SymbolElement | LineElement,
        channels: Iterable[str],
        primary: str,
        numeric: bool,
    ) -> Resolved:
        """Status and channel values of an element with bound channels."""
        ctx = self.context(element.bind)
        values = {channel: ctx.value(ChannelRef(channel)) for channel in channels}
        alert_status = self.alerts.active_status(element.status.systems, element.status.alerts)
        status = element_status(element.status, ctx, primary, numeric, alert_status)
        return Resolved(status, values)

    def _tile(self, element: TileElement) -> Resolved:
        view = self.alerts.system(element.system, self.state)
        if view.severity in (Severity.CAUTION, Severity.WARNING):
            status = Status(view.severity.value)
        elif view.unavailable and view.severity is None:
            status = Status.UNAVAILABLE
        else:
            status = Status.NORMAL
        return Resolved(status)

    def _group(self, element: GroupElement) -> Resolved:
        items = [r for r in (self.element(i) for i in element.items) if r is not None]
        derived = {name: derive(spec, items) for name, spec in element.channels.items()}
        ctx = self.context({}, derived)
        own = element_status(
            element.status,
            ctx,
            primary="",
            alert_status=self.alerts.active_status(element.status.systems, element.status.alerts),
        )
        return Resolved(_combined(items, own), derived)


def _combined(items: Sequence[Resolved], own: Status = Status.NORMAL) -> Status:
    """A container's status: the worst caution/warning of its own and its items',
    unavailable only when every item is, otherwise normal."""
    severe = [s for s in (own, *(r.status for r in items)) if s in SEVERITY_ORDER[1:]]
    if severe:
        return max(severe, key=SEVERITY_ORDER.index)
    if items and all(r.status is Status.UNAVAILABLE for r in items):
        return Status.UNAVAILABLE
    return Status.NORMAL


def derive(spec: DerivedChannel, items: Iterable[Resolved]) -> Value:
    """Compute a group's derived channel from its items' resolved values/statuses."""
    if spec.aggregate is Aggregate.COUNT:
        return Value(float(sum(1 for r in items if r.status.value == spec.source)))
    present = [v for r in items if (v := r.values.get(spec.source, MISSING)).number is not None]
    if not present:
        return MISSING
    numbers = [v.number for v in present if v.number is not None]
    unit = next((v.unit for v in present if v.unit), None)
    match spec.aggregate:
        case Aggregate.SUM:
            total = sum(numbers)
        case Aggregate.MIN:
            total = min(numbers)
        case _:
            total = max(numbers)
    return Value(total, unit)
