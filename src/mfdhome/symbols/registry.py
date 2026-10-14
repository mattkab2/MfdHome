"""Symbol type registry: channels, geometry and drawing for each symbol type.

The config loader validates element bindings and params against this registry,
and the renderer dispatches through it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from mfdhome.conditions.values import Value
from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols.battery import battery, battery_box
from mfdhome.symbols.breaker import breaker, breaker_box
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
    return MappingProxyType({})


@dataclass(frozen=True)
class SymbolSpec:
    """A symbol type.

    ``channels`` lists every accepted channel; ``required`` must be bound;
    ``primary`` decides the no-data state; ``numeric`` channels count as no
    data when their value is not a number. ``params`` validates and normalizes
    type-specific settings, raising ``ValueError`` for bad input.
    """

    type: str
    channels: tuple[str, ...]
    required: frozenset[str]
    primary: str
    numeric: frozenset[str]
    box: Callable[[Point, Orientation], Box]
    draw: Callable[[SymbolInput, Theme], str]
    params: Callable[[Mapping[str, object]], Mapping[str, object]] = field(default=_no_params)


def _draw_battery(inp: SymbolInput, theme: Theme) -> str:
    level = inp.values["level"].number
    fill = None if level is None else level / 100
    return battery(inp.at[0], inp.at[1], fill, inp.status, theme)


DEFAULT_CLOSED_STATES = frozenset({"on", "closed"})


def _breaker_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"closed"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    closed = raw.get("closed", DEFAULT_CLOSED_STATES)
    if isinstance(closed, str) or not isinstance(closed, (list, tuple, frozenset, set)):
        raise ValueError("'closed' must be a list of state strings")
    return MappingProxyType({"closed": frozenset(str(s).strip().lower() for s in closed)})


def _draw_breaker(inp: SymbolInput, theme: Theme) -> str:
    state = inp.values["state"]
    closed_states = inp.params.get("closed", DEFAULT_CLOSED_STATES)
    assert isinstance(closed_states, frozenset)
    closed = None if state.raw is None else str(state.raw).strip().lower() in closed_states
    return breaker(inp.at[0], inp.at[1], closed, inp.status, inp.orientation, theme)


REGISTRY: Mapping[str, SymbolSpec] = MappingProxyType(
    {
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
            params=_breaker_params,
        ),
    }
)


def get_symbol(type_name: str) -> SymbolSpec:
    """Look up a symbol type; raises ``KeyError`` for unknown types."""
    return REGISTRY[type_name]
