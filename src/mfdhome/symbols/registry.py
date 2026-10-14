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
    points beyond the box edges and corners every symbol has. ``params`` validates and normalizes
    type-specific settings, raising ``ValueError`` for bad input.
    """

    type: str
    channels: tuple[str, ...]
    required: frozenset[str]
    primary: str
    numeric: frozenset[str]
    box: Callable[[Point, Orientation], Box]
    draw: Callable[[SymbolInput, Theme], str]
    ports: Mapping[str, Callable[[Point, Orientation], Port]] = field(default_factory=lambda: {})
    params: Callable[[Mapping[str, object]], Mapping[str, object]] = field(default=_no_params)


def _draw_battery(inp: SymbolInput, theme: Theme) -> str:
    level = inp.values["level"].number
    fill = None if level is None else level / 100
    return battery(inp.at[0], inp.at[1], fill, inp.status, theme)


DEFAULT_CLOSED_STATES = frozenset({"on", "closed"})


def _breaker_in(at: Point, orientation: Orientation) -> Port:
    half = breaker_box(*at).right - at[0]
    if orientation is Orientation.VERTICAL:
        return Port((at[0], at[1] - half), (0.0, -1.0))
    return Port((at[0] - half, at[1]), (-1.0, 0.0))


def _breaker_out(at: Point, orientation: Orientation) -> Port:
    half = breaker_box(*at).right - at[0]
    if orientation is Orientation.VERTICAL:
        return Port((at[0], at[1] + half), (0.0, 1.0))
    return Port((at[0] + half, at[1]), (1.0, 0.0))


def _draw_breaker(inp: SymbolInput, theme: Theme) -> str:
    state = inp.values["state"]
    closed_states = inp.params.get("closed", DEFAULT_CLOSED_STATES)
    assert isinstance(closed_states, frozenset)
    closed = None if state.raw is None else str(state.raw).strip().lower() in closed_states
    return breaker(inp.at[0], inp.at[1], closed, inp.status, inp.orientation, theme)


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


def _draw_ats(inp: SymbolInput, theme: Theme) -> str:
    state = inp.values["state"]
    connected_states = inp.params.get("connected", DEFAULT_CONNECTED_STATES)
    assert isinstance(connected_states, frozenset)
    connected = None if state.raw is None else str(state.raw).strip().lower() in connected_states
    return transfer_switch(inp.at[0], inp.at[1], connected, inp.status, inp.orientation, theme)


def _ats_port(side: float) -> Callable[[Point, Orientation], Port]:
    """The grid (side -1) or load (side +1) port; it follows orientation."""

    def port(at: Point, orientation: Orientation) -> Port:
        box = ats_box(*at, orientation)
        if orientation is Orientation.VERTICAL:
            y = box.top if side < 0 else box.bottom
            return Port((at[0], y), (0.0, side))
        x = box.left if side < 0 else box.right
        return Port((x, at[1]), (side, 0.0))

    return port


def _draw_load_panel(inp: SymbolInput, theme: Theme) -> str:
    return load_panel(inp.at[0], inp.at[1], inp.status, theme)


def _draw_panel(inp: SymbolInput, theme: Theme) -> str:
    return solar_panel(inp.at[0], inp.at[1], inp.status, theme)


REGISTRY: Mapping[str, SymbolSpec] = {
    "transfer_switch": SymbolSpec(
        type="transfer_switch",
        channels=("state",),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset(),
        box=lambda at, orientation: ats_box(*at, orientation),
        draw=_draw_ats,
        params=_state_list_params("connected", DEFAULT_CONNECTED_STATES),
        ports={"grid": _ats_port(-1.0), "load": _ats_port(1.0)},
    ),
    "load_panel": SymbolSpec(
        type="load_panel",
        channels=("power",),
        required=frozenset(),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, _orientation: load_panel_box(*at),
        draw=_draw_load_panel,
    ),
    "solar_panel": SymbolSpec(
        type="solar_panel",
        channels=("power",),
        required=frozenset({"power"}),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, _orientation: panel_box(*at),
        draw=_draw_panel,
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
        box=lambda at, _orientation: breaker_box(*at),
        draw=_draw_breaker,
        params=_state_list_params("closed", DEFAULT_CLOSED_STATES),
        ports={"in": _breaker_in, "out": _breaker_out},
    ),
}


def get_symbol(type_name: str) -> SymbolSpec:
    """Look up a symbol type; raises ``KeyError`` for unknown types."""
    return REGISTRY[type_name]
