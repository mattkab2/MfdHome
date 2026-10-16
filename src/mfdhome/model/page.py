"""Page and element definitions, positioned on a logical canvas.

There are seven element kinds:

- ``SymbolElement``: a registered symbol type (battery, breaker, ...) at a point;
- ``LineElement``: a connection along a polyline, carrying a ``rate``;
- ``TextElement``: a static label;
- ``TileElement``: an annunciator tile showing one system's alerts;
- ``NodeElement``: a connection point lines can attach to;
- ``GroupElement``: a container laying out items that connect only through it;
- ``LogElement``: the alert log (history), paged by the display's keys.

Symbols and lines bind HA entities to named *channels* declared by their type.
Status rules, flow and readouts refer to channel names, not entity ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from mfdhome.layout.anchors import Anchor
from mfdhome.layout.path import Point
from mfdhome.model.binding import Binding

if TYPE_CHECKING:
    # Annotation-only: conditions imports model.binding, so a runtime import would cycle.
    from mfdhome.conditions.model import Rule


class Orientation(StrEnum):
    """Direction of the conductor through a two-terminal symbol."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass(frozen=True)
class Name:
    """The element's name label.

    ``anchor=None`` uses the default: top for symbols, beside the line for lines.
    ``along`` (0..1) positions the label along a line and is ignored for symbols.
    """

    text: str
    anchor: Anchor | None = None
    along: float = 0.5
    offset: Point = (0.0, 0.0)


@dataclass(frozen=True)
class Readout:
    """A displayed value from one of the element's channels.

    ``format`` is a named formatter (``power``, ``percent``, ``number``, ``raw``)
    or a Python format string applied to the numeric value. ``unit`` overrides
    the entity's ``unit_of_measurement``. ``absolute`` shows the magnitude only
    (useful when direction is shown by a flow arrow). ``anchor=None`` uses the
    default: bottom for symbols, beside the line for lines.
    """

    channel: str
    format: str = "number"
    unit: str | None = None
    absolute: bool = False
    anchor: Anchor | None = None
    along: float = 0.5
    offset: Point = (0.0, 0.0)


@dataclass(frozen=True)
class StatusSpec:
    """How an element's status is derived; the most severe source wins.

    Sources are ``rules``, plus any *active* alerts listed in ``alerts`` or
    belonging to ``systems``. Latched (cleared but unacknowledged) alerts do not
    affect elements: the element shows the equipment's current state, and the
    latch is shown on the annunciator.
    """

    rules: tuple[Rule, ...] = ()
    systems: tuple[str, ...] = ()
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlowSpec:
    """Draw a flow arrow when ``|channel| > threshold``; the sign sets direction.

    The default threshold of 0 shows any nonzero rate; noisy sensors (power
    hovering around zero) should set their own.
    """

    channel: str = "rate"
    threshold: float = 0.0


@dataclass(frozen=True)
class SymbolElement:
    """A registered symbol type centered at ``at``."""

    id: str
    type: str
    at: Point
    bind: Mapping[str, Binding] = field(default_factory=dict)
    name: Name | None = None
    status: StatusSpec = StatusSpec()
    readouts: tuple[Readout, ...] = ()
    orientation: Orientation = Orientation.HORIZONTAL
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LineTag:
    """A line's service tag (``HW``, ``GAS``, ``SA``), drawn at fraction ``along``."""

    text: str
    along: float = 0.25


@dataclass(frozen=True)
class LineElement:
    """A line along ``points`` (set by routing when the page loads).

    Positive flow runs from the first point toward the last; negative flows
    backward (e.g. grid export). ``casing`` draws the line as a hollow pipe
    (the default); plain lines are for sensing and minor connections. ``tag``
    names what the line carries, the P&ID way, since color can't.
    """

    id: str
    points: tuple[Point, ...] = ()
    bind: Mapping[str, Binding] = field(default_factory=dict)
    name: Name | None = None
    status: StatusSpec = StatusSpec()
    readouts: tuple[Readout, ...] = ()
    flow: FlowSpec | None = None
    casing: bool = True
    tag: LineTag | None = None


@dataclass(frozen=True)
class TextElement:
    """A static text label at ``at``; ``align`` is ``start``, ``middle`` or ``end``."""

    id: str
    at: Point
    text: str
    align: str = "middle"


@dataclass(frozen=True)
class TileElement:
    """An annunciator tile for one system, centered at ``at``.

    ``label`` overrides the system's label.
    """

    id: str
    at: Point
    system: str
    label: str | None = None


@dataclass(frozen=True)
class NodeElement:
    """A connection point that isn't equipment (e.g. a bus junction).

    ``junction`` draws a dot; the config loader sets it when three or more
    lines attach to the node.
    """

    id: str
    at: Point
    junction: bool = False


@dataclass(frozen=True)
class LogElement:
    """The alert log: history events newest first, in a box at ``at`` (top-left) of ``size``.

    ``systems`` limits it to those systems' alerts (empty: every system, plus
    Home Assistant connection events).
    """

    id: str
    at: Point
    size: tuple[float, float]
    systems: tuple[str, ...] = ()


class Frame(StrEnum):
    """How a group's boundary is drawn. Never dashed or dotted: patterns carry status."""

    OUTLINE = "outline"
    NONE = "none"


class Aggregate(StrEnum):
    """How a group derives a channel from its items."""

    SUM = "sum"
    MIN = "min"
    MAX = "max"
    COUNT = "count"  # items whose status equals ``source``


@dataclass(frozen=True)
class DerivedChannel:
    """A group channel computed from its items.

    For ``sum``/``min``/``max``, ``source`` is an item channel name; items
    without usable data are skipped (no data at all gives no data). For
    ``count``, ``source`` is a status name (e.g. ``unavailable``).
    """

    aggregate: Aggregate
    source: str


@dataclass(frozen=True)
class GridLayout:
    """Items in rows of ``columns`` fixed-size cells (the largest item's box)."""

    columns: int
    gap: Point = (16.0, 16.0)
    padding: float = 12.0


@dataclass(frozen=True)
class GroupElement:
    """A container: its ``items`` are laid out inside it and connect only through it.

    ``at`` is the top-left of the group's box and ``size`` its extent; both,
    and the items' positions, are resolved at load time. Item ids are paths
    (``array.p3``). Without status rules, a group takes its items' worst
    caution/warning, and is unavailable only when every item is.
    """

    id: str
    at: Point
    size: Point
    layout: GridLayout
    items: tuple[Element, ...] = ()
    frame: Frame = Frame.OUTLINE
    name: Name | None = None
    channels: Mapping[str, DerivedChannel] = field(default_factory=dict)
    status: StatusSpec = StatusSpec()
    readouts: tuple[Readout, ...] = ()


type Element = (
    SymbolElement
    | LineElement
    | TextElement
    | TileElement
    | NodeElement
    | GroupElement
    | LogElement
)


@dataclass(frozen=True)
class Page:
    """A page definition on a ``width`` x ``height`` logical canvas."""

    id: str
    title: str
    width: float
    height: float
    elements: tuple[Element, ...] = ()
