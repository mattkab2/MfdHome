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
from mfdhome.symbols.combiner import (
    MAX_INPUTS,
    combiner,
    combiner_box,
    input_port,
    output_port,
)
from mfdhome.symbols.meter import meter, meter_box
from mfdhome.symbols.panel import panel_box, solar_panel
from mfdhome.symbols.tap import faucet, faucet_inlet, hose_bib, hose_bib_inlet, tap_box
from mfdhome.symbols.transfer import ats_box, load_panel, transfer_switch
from mfdhome.symbols.transfer import panel_box as load_panel_box
from mfdhome.symbols.valve import Body, ValveState, valve, valve_box
from mfdhome.symbols.water_heater import (
    cold_port,
    gas_port,
    heater_box,
    hot_port,
    water_heater,
)
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


def _state_lists(**defaults: frozenset[str]) -> ParamsValidator:
    """Params whose entries are optional lists of state strings (lowercased)."""

    def validate(raw: Mapping[str, object]) -> Mapping[str, object]:
        unknown = set(raw) - set(defaults)
        if unknown:
            raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
        out = {}
        for name, default in defaults.items():
            states = raw.get(name, default)
            if isinstance(states, str) or not isinstance(states, (list, tuple, frozenset, set)):
                raise ValueError(f"{name!r} must be a list of state strings")
            out[name] = frozenset(str(s).strip().lower() for s in states)
        return out

    return validate


def _state_list_params(name: str, default: frozenset[str]) -> ParamsValidator:
    """Params with one optional entry: ``name``, a list of state strings (lowercased)."""
    return _state_lists(**{name: default})


def _in_states(
    inp: SymbolInput, param: str, default: frozenset[str], channel: str = "state"
) -> bool | None:
    """Whether ``channel`` is one of the ``param`` states; ``None`` without data."""
    raw = inp.values[channel].raw
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


def _draw_smart_breaker(inp: SymbolInput, theme: Theme) -> str:
    closed = _in_states(inp, "closed", DEFAULT_CLOSED_STATES)
    return breaker(*inp.at, closed, inp.status, inp.orientation, theme, actuator=True)


def _draw_ats(inp: SymbolInput, theme: Theme) -> str:
    connected = _in_states(inp, "connected", DEFAULT_CONNECTED_STATES)
    return transfer_switch(*inp.at, connected, inp.status, inp.orientation, theme)


#: Longest meter label that fits inside the circle.
MAX_METER_LABEL = 5


def _label_params(default: str) -> ParamsValidator:
    """Params with one optional entry: ``label``, a short text drawn inside the symbol."""

    def validate(raw: Mapping[str, object]) -> Mapping[str, object]:
        unknown = set(raw) - {"label"}
        if unknown:
            raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
        label = raw.get("label", default)
        if not isinstance(label, str) or not 0 < len(label) <= MAX_METER_LABEL:
            raise ValueError(f"'label' must be text of 1 to {MAX_METER_LABEL} characters")
        return {"label": label}

    return validate


def _draw_meter(inp: SymbolInput, theme: Theme) -> str:
    label = inp.params["label"]
    assert isinstance(label, str)
    return meter(*inp.at, label, inp.status, theme)


def _meter_box(at: Point, _orientation: Orientation) -> Box:
    return meter_box(*at)


_METER_PORTS = {"in": _terminal(_meter_box, -1.0), "out": _terminal(_meter_box, 1.0)}


def _combiner_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"inputs"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    inputs = raw.get("inputs", 2)
    if isinstance(inputs, bool) or not isinstance(inputs, int) or not 1 <= inputs <= MAX_INPUTS:
        raise ValueError(f"'inputs' must be a whole number from 1 to {MAX_INPUTS}")
    return {"inputs": inputs}


def _inputs(params: Mapping[str, object]) -> int:
    inputs = params.get("inputs", 2)
    assert isinstance(inputs, int)
    return inputs


def _combiner_ports(params: Mapping[str, object]) -> Mapping[str, PortFn]:
    inputs = _inputs(params)

    def port_in(index: int) -> PortFn:
        return lambda at, orientation: input_port(*at, orientation, inputs, index)

    ports = {f"in{i + 1}": port_in(i) for i in range(inputs)}
    return {**ports, "out": lambda at, orientation: output_port(*at, orientation)}


def _draw_combiner(inp: SymbolInput, theme: Theme) -> str:
    return combiner(*inp.at, _inputs(inp.params), inp.status, inp.orientation, theme)


DEFAULT_OPEN_STATES = frozenset({"open", "on"})
DEFAULT_MOVING_STATES = frozenset({"opening", "closing"})


def _valve_state(inp: SymbolInput) -> ValveState:
    raw = inp.values["state"].raw
    if raw is None:
        return ValveState.UNKNOWN
    state = str(raw).strip().lower()
    for param, result in (("open", ValveState.OPEN), ("moving", ValveState.MOVING)):
        states = inp.params[param]
        assert isinstance(states, frozenset)
        if state in states:
            return result
    return ValveState.CLOSED


def _draw_valve(body: Body) -> Callable[[SymbolInput, Theme], str]:
    def draw(inp: SymbolInput, theme: Theme) -> str:
        return valve(*inp.at, body, _valve_state(inp), inp.status, inp.orientation, theme)

    return draw


def _valve_box(at: Point, orientation: Orientation) -> Box:
    return valve_box(*at, orientation)


def _valve_spec(type_name: str, body: Body) -> SymbolSpec:
    return SymbolSpec(
        type=type_name,
        channels=("state", "position"),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset({"position"}),
        box=_valve_box,
        draw=_draw_valve(body),
        params=_state_lists(open=DEFAULT_OPEN_STATES, moving=DEFAULT_MOVING_STATES),
        ports={"in": _terminal(_valve_box, -1.0), "out": _terminal(_valve_box, 1.0)},
    )


DEFAULT_HEATING_STATES = frozenset({"on", "heating"})


def _draw_water_heater(inp: SymbolInput, theme: Theme) -> str:
    heating = _in_states(inp, "heating", DEFAULT_HEATING_STATES, channel="heating")
    return water_heater(*inp.at, heating, inp.status, theme)


def _tap_spec(
    type_name: str,
    draw: Callable[[float, float, bool, Status, Theme], str],
    inlet: Callable[[Point], Port],
) -> SymbolSpec:
    def draw_tap(inp: SymbolInput, theme: Theme) -> str:
        running = _in_states(inp, "open", DEFAULT_OPEN_STATES) is True
        return draw(*inp.at, running, inp.status, theme)

    return SymbolSpec(
        type=type_name,
        channels=("state",),
        required=frozenset(),
        primary="state",
        numeric=frozenset(),
        box=lambda at, _orientation: tap_box(*at),
        draw=draw_tap,
        params=_state_list_params("open", DEFAULT_OPEN_STATES),
        ports={"in": lambda at, _orientation: inlet(at)},
    )


def _breaker_box(at: Point, _orientation: Orientation) -> Box:
    return breaker_box(*at)


def _ats_box(at: Point, orientation: Orientation) -> Box:
    return ats_box(*at, orientation)


REGISTRY: Mapping[str, SymbolSpec] = {
    "electric_meter": SymbolSpec(
        type="electric_meter",
        channels=("power", "energy"),
        required=frozenset(),
        primary="power",
        numeric=frozenset({"power", "energy"}),
        box=_meter_box,
        draw=_draw_meter,
        params=_label_params("kWh"),
        ports=_METER_PORTS,
    ),
    "water_meter": SymbolSpec(
        type="water_meter",
        channels=("flow", "total"),
        required=frozenset(),
        primary="flow",
        numeric=frozenset({"flow", "total"}),
        box=_meter_box,
        draw=_draw_meter,
        params=_label_params("GAL"),
        ports=_METER_PORTS,
    ),
    "combiner": SymbolSpec(
        type="combiner",
        channels=("power",),
        required=frozenset(),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, orientation: combiner_box(*at, orientation),
        draw=_draw_combiner,
        params=_combiner_params,
        ports_for=_combiner_ports,
    ),
    "smart_breaker": SymbolSpec(
        type="smart_breaker",
        channels=("state", "power"),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset({"power"}),
        box=_breaker_box,
        draw=_draw_smart_breaker,
        params=_state_list_params("closed", DEFAULT_CLOSED_STATES),
        ports={"in": _terminal(_breaker_box, -1.0), "out": _terminal(_breaker_box, 1.0)},
    ),
    "ball_valve": _valve_spec("ball_valve", Body.BALL),
    "globe_valve": _valve_spec("globe_valve", Body.GLOBE),
    "water_heater": SymbolSpec(
        type="water_heater",
        channels=("temperature", "heating"),
        required=frozenset(),
        primary="temperature",
        numeric=frozenset({"temperature"}),
        box=lambda at, _orientation: heater_box(*at),
        draw=_draw_water_heater,
        params=_state_list_params("heating", DEFAULT_HEATING_STATES),
        ports={
            "cold": lambda at, _orientation: cold_port(at),
            "hot": lambda at, _orientation: hot_port(at),
            "gas": lambda at, _orientation: gas_port(at),
        },
    ),
    "hose_bib": _tap_spec("hose_bib", hose_bib, hose_bib_inlet),
    "faucet": _tap_spec("faucet", faucet, faucet_inlet),
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
