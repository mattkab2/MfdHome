"""Symbol type registry: channels, geometry and drawing for each symbol type.

The config loader validates element bindings and params against this registry,
and the renderer dispatches through it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from mfdhome.conditions.values import Value
from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols.battery import battery, battery_box
from mfdhome.symbols.breaker import breaker, breaker_box
from mfdhome.symbols.panel import panel_box, solar_panel
from mfdhome.symbols.transfer import ats_box, load_panel, transfer_switch
from mfdhome.symbols.transfer import panel_box as load_panel_box
from mfdhome.themes.theme import Theme

#: Channels accepted by line elements; ``power`` is primary and numeric.
LINE_CHANNELS = ("power",)
LINE_PRIMARY = "power"
LINE_NUMERIC = frozenset({"power"})

type PortFn = Callable[[Point, Orientation], Port]


@dataclass(frozen=True)
class SymbolInput:
    """Everything a symbol needs to draw itself, already resolved."""

    at: Point
    orientation: Orientation
    status: Status
    values: Mapping[str, Value]
    params: Mapping[str, object]


def _no_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    if raw:
        raise ValueError(f"unknown parameter {next(iter(raw))!r}")
    return {}


@dataclass(frozen=True)
class SymbolSpec:
    """A symbol type.

    ``channels`` lists every accepted channel; ``required`` must be bound;
    ``primary`` decides the no-data state; ``numeric`` channels count as no
    data when their value is not a number. ``ports`` adds named connection
    points beyond the box edges and corners every symbol has; ``ports_for``
    replaces it for types whose ports depend on their (normalized) params.
    ``params`` validates and normalizes type-specific settings, raising
    ``ValueError`` for bad input.
    """

    type: str
    channels: tuple[str, ...]
    required: frozenset[str]
    primary: str
    numeric: frozenset[str]
    box: Callable[[Point, Orientation], Box]
    draw: Callable[[SymbolInput, Theme], str]
    ports: Mapping[str, PortFn] = field(default_factory=lambda: {})
    params: Callable[[Mapping[str, object]], Mapping[str, object]] = field(default=_no_params)
    ports_for: Callable[[Mapping[str, object]], Mapping[str, PortFn]] | None = None

    def named_ports(self, params: Mapping[str, object]) -> Mapping[str, PortFn]:
        """The type's named ports for an element with ``params``."""
        return self.ports if self.ports_for is None else self.ports_for(params)


def _draw_battery(inp: SymbolInput, theme: Theme) -> str:
    level = inp.values["level"].number
    fill = None if level is None else level / 100
    return battery(inp.at[0], inp.at[1], fill, inp.status, theme)


DEFAULT_CLOSED_STATES = frozenset({"on", "closed"})
DEFAULT_CONNECTED_STATES = frozenset({"on", "connected", "grid", "closed"})

type ParamsValidator = Callable[[Mapping[str, object]], Mapping[str, object]]


def _state_list_params(name: str, default: frozenset[str]) -> ParamsValidator:
    """Params with one optional entry: ``name``, a list of state strings (lowercased)."""

    def validate(raw: Mapping[str, object]) -> Mapping[str, object]:
        unknown = set(raw) - {name}
        if unknown:
            raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
        states = raw.get(name, default)
        if isinstance(states, str) or not isinstance(states, (list, tuple, frozenset, set)):
            raise ValueError(f"{name!r} must be a list of state strings")
        return {name: frozenset(str(s).strip().lower() for s in states)}

    return validate


def _in_states(inp: SymbolInput, param: str, default: frozenset[str]) -> bool | None:
    """Whether the ``state`` channel is one of the ``param`` states; ``None`` without data."""
    raw = inp.values["state"].raw
    states = inp.params.get(param, default)
    assert isinstance(states, frozenset)
    return None if raw is None else str(raw).strip().lower() in states


def _terminal(box: Callable[[Point, Orientation], Box], side: float) -> PortFn:
    """A port at the start (side -1: left, or top when vertical) or end (+1) of ``box``."""

    def port(at: Point, orientation: Orientation) -> Port:
        b = box(at, orientation)
        if orientation is Orientation.VERTICAL:
            return Port((at[0], b.top if side < 0 else b.bottom), (0.0, side))
        return Port((b.left if side < 0 else b.right, at[1]), (side, 0.0))

    return port


def _draw_breaker(inp: SymbolInput, theme: Theme) -> str:
    closed = _in_states(inp, "closed", DEFAULT_CLOSED_STATES)
    return breaker(*inp.at, closed, inp.status, inp.orientation, theme)


def _draw_ats(inp: SymbolInput, theme: Theme) -> str:
    connected = _in_states(inp, "connected", DEFAULT_CONNECTED_STATES)
    return transfer_switch(*inp.at, connected, inp.status, inp.orientation, theme)


def _breaker_box(at: Point, _orientation: Orientation) -> Box:
    return breaker_box(*at)


def _ats_box(at: Point, orientation: Orientation) -> Box:
    return ats_box(*at, orientation)


REGISTRY: Mapping[str, SymbolSpec] = {
    "transfer_switch": SymbolSpec(
        type="transfer_switch",
        channels=("state",),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset(),
        box=_ats_box,
        draw=_draw_ats,
        params=_state_list_params("connected", DEFAULT_CONNECTED_STATES),
        ports={"grid": _terminal(_ats_box, -1.0), "load": _terminal(_ats_box, 1.0)},
    ),
    "load_panel": SymbolSpec(
        type="load_panel",
        channels=("power",),
        required=frozenset(),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, _orientation: load_panel_box(*at),
        draw=lambda inp, theme: load_panel(*inp.at, inp.status, theme),
    ),
    "solar_panel": SymbolSpec(
        type="solar_panel",
        channels=("power",),
        required=frozenset({"power"}),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, _orientation: panel_box(*at),
        draw=lambda inp, theme: solar_panel(*inp.at, inp.status, theme),
    ),
    "battery": SymbolSpec(
        type="battery",
        channels=("level", "power"),
        required=frozenset({"level"}),
        primary="level",
        numeric=frozenset({"level", "power"}),
        box=lambda at, _orientation: battery_box(*at),
        draw=_draw_battery,
    ),
    "breaker": SymbolSpec(
        type="breaker",
        channels=("state",),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset(),
        box=_breaker_box,
        draw=_draw_breaker,
        params=_state_list_params("closed", DEFAULT_CLOSED_STATES),
        ports={"in": _terminal(_breaker_box, -1.0), "out": _terminal(_breaker_box, 1.0)},
    ),
}


def get_symbol(type_name: str) -> SymbolSpec:
    """Look up a symbol type; raises ``KeyError`` for unknown types."""
    return REGISTRY[type_name]
