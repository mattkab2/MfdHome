"""Symbol type registry: channels, geometry and drawing for each symbol type.

The config loader validates element bindings and params against this registry,
and the renderer dispatches through it.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
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
from mfdhome.symbols.fittings import (
    backflow_preventer,
    bfp_box,
    check_box,
    check_valve,
    prv,
    prv_box,
)
from mfdhome.symbols.floorplan import OpeningKind, alarm_panel, opening, opening_box
from mfdhome.symbols.floorplan import panel_box as alarm_panel_box
from mfdhome.symbols.format import format_value, is_valid_format
from mfdhome.symbols.hvac import (
    Cabinet,
    DamperState,
    air_handler,
    condenser,
    condenser_box,
    condenser_port,
    damper,
    damper_box,
    thermostat,
    thermostat_box,
)
from mfdhome.symbols.meter import meter, meter_box
from mfdhome.symbols.network import (
    access_point,
    ap_box,
    host,
    host_box,
    network_switch,
    radio,
    radio_box,
    router,
    router_box,
    switch_box,
)
from mfdhome.symbols.outlet import inlet_ports, outlet, outlet_box
from mfdhome.symbols.panel import panel_box, solar_panel
from mfdhome.symbols.sensor import gauge, gauge_box, sensor, sensor_box
from mfdhome.symbols.transfer import ats_box, load_panel, panel_breaker_ports, transfer_switch
from mfdhome.symbols.transfer import panel_box as load_panel_box
from mfdhome.symbols.valve import Body, ValveState, valve, valve_box
from mfdhome.symbols.vessels import Connections, pump, pump_box, tank, tank_box, tank_ports
from mfdhome.symbols.water_heater import (
    cold_port,
    gas_port,
    heater_box,
    hot_port,
    water_heater,
)
from mfdhome.themes.theme import Theme

#: Channels accepted by line elements: ``rate``, what the line carries (power,
#: water flow, throughput, ...), numeric; ``rate_back``, what a two-way line
#: carries the other way (upload beside download), numeric; and ``state``, a
#: link's own state (a radio link's reachability), for lines with nothing to
#: measure.
LINE_CHANNELS = ("rate", "rate_back", "state")
LINE_NUMERIC = frozenset({"rate", "rate_back"})
#: The channel that makes a line two-way.
LINE_BACK = "rate_back"


def line_primary(bound: Collection[str]) -> str:
    """A line's primary channel: ``rate``, or ``state`` when only ``state`` is bound."""
    return "state" if "state" in bound and "rate" not in bound else "rate"


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


@dataclass(frozen=True, kw_only=True)
class SymbolSpec:
    """A symbol type.

    ``channels`` lists every accepted channel; ``required`` must be bound
    (default: none); ``primary`` decides the no-data state; ``numeric``
    channels (default: none) count as no data when their value is not a
    number. ``ports`` adds named connection
    points beyond the box edges and corners every symbol has; ``ports_for``
    replaces it for types whose ports depend on their (normalized) params, as
    ``box_for`` does for the box.
    ``params`` validates and normalizes type-specific settings, raising
    ``ValueError`` for bad input.
    """

    type: str
    channels: tuple[str, ...]
    required: frozenset[str] = frozenset()
    primary: str
    numeric: frozenset[str] = frozenset()
    box: Callable[[Point, Orientation], Box]
    draw: Callable[[SymbolInput, Theme], str]
    ports: Mapping[str, PortFn] = field(default_factory=lambda: {})
    params: Callable[[Mapping[str, object]], Mapping[str, object]] = field(default=_no_params)
    ports_for: Callable[[Mapping[str, object]], Mapping[str, PortFn]] | None = None
    box_for: Callable[[Point, Orientation, Mapping[str, object]], Box] | None = None

    def bounds(self, at: Point, orientation: Orientation, params: Mapping[str, object]) -> Box:
        """The bounding box of an element with ``params`` (``box_for`` when its size
        depends on them)."""
        return (
            self.box(at, orientation)
            if self.box_for is None
            else self.box_for(at, orientation, params)
        )

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


def _panel_ports() -> dict[str, PortFn]:
    """A load panel's per-breaker ports (``l1``-``l4``, ``r1``-``r4``)."""

    def port(name: str) -> PortFn:
        return lambda at, _orientation: panel_breaker_ports(*at)[name]

    return {name: port(name) for name in panel_breaker_ports(0.0, 0.0)}


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
        state = _valve_state(inp)
        actuated = inp.params["actuated"] is True
        return valve(*inp.at, body, state, inp.status, inp.orientation, theme, actuated)

    return draw


def _valve_box(at: Point, orientation: Orientation) -> Box:
    return valve_box(*at, orientation)


def _valve_bounds(at: Point, orientation: Orientation, params: Mapping[str, object]) -> Box:
    return valve_box(*at, orientation, params.get("actuated") is True)


def _valve_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    actuated = raw.get("actuated", False)
    if not isinstance(actuated, bool):
        raise ValueError("'actuated' must be true or false")
    states = _state_lists(open=DEFAULT_OPEN_STATES, moving=DEFAULT_MOVING_STATES)(
        {k: v for k, v in raw.items() if k != "actuated"}
    )
    return {**states, "actuated": actuated}


def _valve_spec(type_name: str, body: Body) -> SymbolSpec:
    return SymbolSpec(
        type=type_name,
        channels=("state", "position"),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset({"position"}),
        box=_valve_box,
        draw=_draw_valve(body),
        params=_valve_params,
        ports={"in": _terminal(_valve_box, -1.0), "out": _terminal(_valve_box, 1.0)},
        box_for=_valve_bounds,
    )


DEFAULT_HEATING_STATES = frozenset({"on", "heating"})


def _draw_water_heater(inp: SymbolInput, theme: Theme) -> str:
    heating = _in_states(inp, "heating", DEFAULT_HEATING_STATES, channel="heating")
    return water_heater(*inp.at, heating, inp.status, theme)


def _outlet_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"label", "outdoor", "inlets", "facing"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    label = _label_params("OUT")({"label": raw["label"]} if "label" in raw else {})["label"]
    outdoor = raw.get("outdoor", False)
    if not isinstance(outdoor, bool):
        raise ValueError("'outdoor' must be true or false")
    inlets = raw.get("inlets", 1)
    if isinstance(inlets, bool) or inlets not in (1, 2):
        raise ValueError("'inlets' must be 1 or 2 (hot and cold)")
    facing = raw.get("facing", "right")
    if facing not in ("right", "left"):
        raise ValueError("'facing' must be right (fed from the left) or left")
    return {"label": label, "outdoor": outdoor, "inlets": inlets, "facing": facing}


def _outlet_ports(params: Mapping[str, object]) -> Mapping[str, PortFn]:
    inlets = params.get("inlets", 1)
    assert isinstance(inlets, int)
    left = params.get("facing") == "left"

    def port(name: str) -> PortFn:
        return lambda at, _orientation: inlet_ports(*at, inlets, left)[name]

    return {name: port(name) for name in inlet_ports(0.0, 0.0, inlets)}


def _draw_outlet(inp: SymbolInput, theme: Theme) -> str:
    label, outdoor = inp.params["label"], inp.params["outdoor"]
    assert isinstance(label, str) and isinstance(outdoor, bool)
    return outlet(*inp.at, label, outdoor, inp.status, theme, inp.params.get("facing") == "left")


#: Longest sensor code that fits inside the diamond.
MAX_SENSOR_CODE = 3
DEFAULT_ACTIVE_STATES = frozenset({"on"})


def _sensor_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"code", "active"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    code = raw.get("code", "")
    if not isinstance(code, str) or len(code) > MAX_SENSOR_CODE:
        raise ValueError(f"'code' must be text of up to {MAX_SENSOR_CODE} characters")
    active = _state_list_params("active", DEFAULT_ACTIVE_STATES)(
        {"active": raw["active"]} if "active" in raw else {}
    )
    return {"code": code, **active}


def _draw_sensor(inp: SymbolInput, theme: Theme) -> str:
    code = inp.params["code"]
    assert isinstance(code, str)
    tripped = _in_states(inp, "active", DEFAULT_ACTIVE_STATES) is True
    return sensor(*inp.at, code, tripped, inp.status, theme)


def _gauge_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"format", "unit"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    fmt, unit = raw.get("format", "number"), raw.get("unit")
    if not isinstance(fmt, str) or not is_valid_format(fmt):
        raise ValueError(f"unknown format {fmt!r}; use a named format or a format string")
    if unit is not None and not isinstance(unit, str):
        raise ValueError("'unit' must be text")
    return {"format": fmt, "unit": unit}


def _draw_gauge(inp: SymbolInput, theme: Theme) -> str:
    fmt, unit = inp.params["format"], inp.params["unit"]
    assert isinstance(fmt, str) and (unit is None or isinstance(unit, str))
    return gauge(*inp.at, format_value(inp.values["value"], fmt, unit), inp.status, theme)


def _fitting_spec(
    type_name: str,
    box: Callable[[float, float, Orientation], Box],
    draw: Callable[[float, float, Status, Orientation, Theme], str],
    channels: tuple[str, ...] = ("state",),
) -> SymbolSpec:
    """An unpowered inline fitting: optional bindings, in on the left, out on the right."""

    def spec_box(at: Point, orientation: Orientation) -> Box:
        return box(*at, orientation)

    def ends(side: float) -> PortFn:
        def port(at: Point, orientation: Orientation) -> Port:
            # The pipe axis runs through the center, even where the box reaches
            # past the body (the PRV's dome).
            b = spec_box(at, orientation)
            if orientation is Orientation.VERTICAL:
                return Port((at[0], b.top if side < 0 else b.bottom), (0.0, side))
            return Port((b.left if side < 0 else b.right, at[1]), (side, 0.0))

        return port

    return SymbolSpec(
        type=type_name,
        channels=channels,
        primary=channels[0],
        numeric=frozenset(c for c in channels if c != "state"),
        box=spec_box,
        draw=lambda inp, theme: draw(*inp.at, inp.status, inp.orientation, theme),
        ports={"in": ends(-1.0), "out": ends(1.0)},
    )


MAX_TANK_TAG = 4


def _tank_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"tag", "connections"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    tag = raw.get("tag", "")
    if not isinstance(tag, str) or len(tag) > MAX_TANK_TAG:
        raise ValueError(f"'tag' must be text of up to {MAX_TANK_TAG} characters")
    connections = raw.get("connections", Connections.TOP.value)
    if connections not in {c.value for c in Connections}:
        raise ValueError(f"'connections' must be one of: {', '.join(c.value for c in Connections)}")
    return {"tag": tag, "connections": Connections(str(connections))}


def _tank_ports(params: Mapping[str, object]) -> Mapping[str, PortFn]:
    connections = params.get("connections", Connections.TOP)
    assert isinstance(connections, Connections)

    def port(name: str) -> PortFn:
        return lambda at, _orientation: tank_ports(*at, connections)[name]

    return {name: port(name) for name in tank_ports(0.0, 0.0, connections)}


def _draw_tank(inp: SymbolInput, theme: Theme) -> str:
    tag = inp.params["tag"]
    assert isinstance(tag, str)
    return tank(*inp.at, tag, inp.status, theme)


DEFAULT_RUNNING_STATES = frozenset({"on", "running"})


def _draw_pump(inp: SymbolInput, theme: Theme) -> str:
    running = _in_states(inp, "running", DEFAULT_RUNNING_STATES) is True
    return pump(*inp.at, running, inp.status, inp.orientation, theme)


def _pump_box(at: Point, _orientation: Orientation) -> Box:
    return pump_box(*at)


SWINGS = {"up": -1.0, "left": -1.0, "down": 1.0, "right": 1.0}
DEFAULT_OPEN_CONTACT = frozenset({"on", "open"})


def _opening_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"kind", "length", "swing", "hinge", "open"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    kind = raw.get("kind", OpeningKind.DOOR.value)
    if kind not in {k.value for k in OpeningKind}:
        raise ValueError("'kind' must be door or window")
    length = raw.get("length", 36)
    if isinstance(length, bool) or not isinstance(length, int | float) or not 8 <= length <= 400:
        raise ValueError("'length' must be a number from 8 to 400")
    swing = raw.get("swing", "up")
    if swing not in SWINGS:
        raise ValueError(f"'swing' must be one of: {', '.join(SWINGS)}")
    hinge = raw.get("hinge", "start")
    if hinge not in ("start", "end"):
        raise ValueError("'hinge' must be start or end")
    states = _state_list_params("open", DEFAULT_OPEN_CONTACT)(
        {"open": raw["open"]} if "open" in raw else {}
    )
    return {
        "kind": OpeningKind(str(kind)),
        "length": float(length),
        "swing": SWINGS[str(swing)],
        "hinge_at_start": hinge == "start",
        **states,
    }


_OPENING_DEFAULTS = _opening_params({})


def _opening_bounds(at: Point, orientation: Orientation, params: Mapping[str, object]) -> Box:
    kind, length, swing = params["kind"], params["length"], params["swing"]
    assert isinstance(kind, OpeningKind) and isinstance(length, float) and isinstance(swing, float)
    return opening_box(*at, orientation is Orientation.VERTICAL, kind, length, swing)


def _draw_opening(inp: SymbolInput, theme: Theme) -> str:
    p = inp.params
    kind, length, swing, hinge = p["kind"], p["length"], p["swing"], p["hinge_at_start"]
    assert isinstance(kind, OpeningKind) and isinstance(length, float)
    assert isinstance(swing, float) and isinstance(hinge, bool)
    is_open = _in_states(inp, "open", DEFAULT_OPEN_CONTACT) is True
    vertical = inp.orientation is Orientation.VERTICAL
    return opening(*inp.at, vertical, kind, length, swing, hinge, is_open, inp.status, theme)


def _draw_alarm_panel(inp: SymbolInput, theme: Theme) -> str:
    raw = inp.values["state"].raw
    state = None if raw is None else str(raw).strip().lower()
    return alarm_panel(*inp.at, state, inp.status, theme)


DEFAULT_HEATING_ACTIONS = frozenset({"heating", "on"})
DEFAULT_COOLING_ACTIONS = frozenset({"cooling"})
DEFAULT_BLOWING_ACTIONS = frozenset({"heating", "cooling", "fan", "on"})


def _cabinet_params(burner: bool, coil: bool) -> ParamsValidator:
    """Params for an air handler (``burner`` False) or furnace: the action states for
    heating, cooling and the blower, and whether it has an AC ``coil``."""
    states = _state_lists(
        heating=DEFAULT_HEATING_ACTIONS,
        cooling=DEFAULT_COOLING_ACTIONS,
        blowing=DEFAULT_BLOWING_ACTIONS,
    )

    def validate(raw: Mapping[str, object]) -> Mapping[str, object]:
        has_coil = raw.get("coil", coil)
        if not isinstance(has_coil, bool):
            raise ValueError("'coil' must be true or false")
        return {
            **states({k: v for k, v in raw.items() if k != "coil"}),
            "cabinet": Cabinet(coil=has_coil, burner=burner),
        }

    return validate


def _cabinet(params: Mapping[str, object]) -> Cabinet:
    cabinet = params["cabinet"]
    assert isinstance(cabinet, Cabinet)
    return cabinet


def _draw_cabinet(inp: SymbolInput, theme: Theme) -> str:
    def acting(param: str, default: frozenset[str]) -> bool:
        return _in_states(inp, param, default, channel="action") is True

    return air_handler(
        *inp.at,
        _cabinet(inp.params),
        acting("heating", DEFAULT_HEATING_ACTIONS),
        acting("cooling", DEFAULT_COOLING_ACTIONS),
        acting("blowing", DEFAULT_BLOWING_ACTIONS),
        inp.status,
        theme,
    )


def _cabinet_ports(params: Mapping[str, object]) -> Mapping[str, PortFn]:
    cabinet = _cabinet(params)

    def port(name: str) -> PortFn:
        return lambda at, _orientation: cabinet.ports(*at)[name]

    return {name: port(name) for name in cabinet.ports(0.0, 0.0)}


def _cabinet_spec(type_name: str, burner: bool, coil: bool) -> SymbolSpec:
    validate = _cabinet_params(burner, coil)
    default = _cabinet(validate({}))
    return SymbolSpec(
        type=type_name,
        channels=("action",),
        primary="action",
        box=lambda at, _orientation: default.box(*at),
        draw=_draw_cabinet,
        params=validate,
        ports_for=_cabinet_ports,
        box_for=lambda at, _orientation, params: _cabinet(params).box(*at),
    )


DEFAULT_COMPRESSOR_ACTIONS = frozenset({"cooling", "on"})


def _draw_condenser(inp: SymbolInput, theme: Theme) -> str:
    running = _in_states(inp, "running", DEFAULT_COMPRESSOR_ACTIONS, channel="action") is True
    return condenser(*inp.at, running, inp.status, theme)


_DAMPER_STATES = {
    ValveState.OPEN: DamperState.OPEN,
    ValveState.CLOSED: DamperState.CLOSED,
}


def _draw_damper(inp: SymbolInput, theme: Theme) -> str:
    state = _DAMPER_STATES.get(_valve_state(inp), DamperState.MOVING)
    actuated = inp.params["actuated"] is True
    return damper(*inp.at, state, actuated, inp.status, inp.orientation, theme)


def _damper_box(at: Point, orientation: Orientation) -> Box:
    return damper_box(*at, orientation)


def _damper_bounds(at: Point, orientation: Orientation, params: Mapping[str, object]) -> Box:
    return damper_box(*at, orientation, params.get("actuated") is True)


def _thermostat_params(raw: Mapping[str, object]) -> Mapping[str, object]:
    unknown = set(raw) - {"format"}
    if unknown:
        raise ValueError(f"unknown parameter {sorted(unknown)[0]!r}")
    fmt = raw.get("format", "{:.0f}°")
    if not isinstance(fmt, str) or not is_valid_format(fmt):
        raise ValueError(f"unknown format {fmt!r}; use a named format or a format string")
    return {"format": fmt}


def _draw_thermostat(inp: SymbolInput, theme: Theme) -> str:
    fmt = inp.params["format"]
    assert isinstance(fmt, str)
    action = inp.values["action"].raw
    return thermostat(
        *inp.at,
        format_value(inp.values["temperature"], fmt),
        format_value(inp.values["setpoint"], fmt),
        None if action is None else str(action).strip().lower(),
        inp.status,
        theme,
    )


#: Readings most network devices report, beside their ``state``.
DEVICE_CHANNELS = ("state", "cpu", "memory", "temperature")
#: A radio node's link readings (``hops``: repeaters in between, 0 = heard directly).
RADIO_CHANNELS = ("state", "rssi", "snr", "noise_floor", "hops", "battery")


def _network_spec(
    type_name: str,
    box: Callable[[float, float], Box],
    draw: Callable[[float, float, Status, Theme], str],
    channels: tuple[str, ...] = DEVICE_CHANNELS,
) -> SymbolSpec:
    """A network device: ``state`` (primary, for status maps) plus numeric readings."""
    return SymbolSpec(
        type=type_name,
        channels=channels,
        primary="state",
        numeric=frozenset(channels[1:]),
        box=lambda at, _orientation: box(*at),
        draw=lambda inp, theme: draw(*inp.at, inp.status, theme),
    )


def _breaker_box(at: Point, _orientation: Orientation) -> Box:
    return breaker_box(*at)


def _ats_box(at: Point, orientation: Orientation) -> Box:
    return ats_box(*at, orientation)


REGISTRY: Mapping[str, SymbolSpec] = {
    "electric_meter": SymbolSpec(
        type="electric_meter",
        channels=("power", "energy"),
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
    "check_valve": _fitting_spec("check_valve", check_box, check_valve),
    "backflow_preventer": _fitting_spec("backflow_preventer", bfp_box, backflow_preventer),
    "prv": _fitting_spec("prv", prv_box, prv, channels=("pressure",)),
    "gas_meter": SymbolSpec(
        type="gas_meter",
        channels=("flow", "total"),
        primary="flow",
        numeric=frozenset({"flow", "total"}),
        box=_meter_box,
        draw=_draw_meter,
        params=_label_params("CCF"),
        ports=_METER_PORTS,
    ),
    "tank": SymbolSpec(
        type="tank",
        channels=("state",),
        primary="state",
        box=lambda at, _orientation: tank_box(*at),
        draw=_draw_tank,
        params=_tank_params,
        ports_for=_tank_ports,
    ),
    "pump": SymbolSpec(
        type="pump",
        channels=("state", "power"),
        primary="state",
        numeric=frozenset({"power"}),
        box=_pump_box,
        draw=_draw_pump,
        params=_state_list_params("running", DEFAULT_RUNNING_STATES),
        ports={"in": _terminal(_pump_box, -1.0), "out": _terminal(_pump_box, 1.0)},
    ),
    "water_heater": SymbolSpec(
        type="water_heater",
        channels=("temperature", "heating"),
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
    "outlet": SymbolSpec(
        type="outlet",
        channels=("state",),
        primary="state",
        box=lambda at, _orientation: outlet_box(*at),
        draw=_draw_outlet,
        params=_outlet_params,
        ports_for=_outlet_ports,
    ),
    "sensor": SymbolSpec(
        type="sensor",
        channels=("state",),
        primary="state",
        box=lambda at, _orientation: sensor_box(*at),
        draw=_draw_sensor,
        params=_sensor_params,
    ),
    "gauge": SymbolSpec(
        type="gauge",
        channels=("value",),
        required=frozenset({"value"}),
        primary="value",
        numeric=frozenset({"value"}),
        box=lambda at, _orientation: gauge_box(*at),
        draw=_draw_gauge,
        params=_gauge_params,
    ),
    "opening": SymbolSpec(
        type="opening",
        channels=("state",),
        primary="state",
        box=lambda at, orientation: _opening_bounds(at, orientation, _OPENING_DEFAULTS),
        draw=_draw_opening,
        params=_opening_params,
        box_for=_opening_bounds,
    ),
    "alarm_panel": SymbolSpec(
        type="alarm_panel",
        channels=("state",),
        required=frozenset({"state"}),
        primary="state",
        box=lambda at, _orientation: alarm_panel_box(*at),
        draw=_draw_alarm_panel,
    ),
    "furnace": _cabinet_spec("furnace", burner=True, coil=False),
    "air_handler": _cabinet_spec("air_handler", burner=False, coil=True),
    "condenser": SymbolSpec(
        type="condenser",
        channels=("action",),
        primary="action",
        box=lambda at, _orientation: condenser_box(*at),
        draw=_draw_condenser,
        params=_state_list_params("running", DEFAULT_COMPRESSOR_ACTIONS),
        ports={"refrigerant": lambda at, _orientation: condenser_port(*at)},
    ),
    "damper": SymbolSpec(
        type="damper",
        channels=("state", "position"),
        required=frozenset({"state"}),
        primary="state",
        numeric=frozenset({"position"}),
        box=_damper_box,
        draw=_draw_damper,
        params=_valve_params,
        ports={"in": _terminal(_damper_box, -1.0), "out": _terminal(_damper_box, 1.0)},
        box_for=_damper_bounds,
    ),
    "thermostat": SymbolSpec(
        type="thermostat",
        channels=("temperature", "setpoint", "action"),
        required=frozenset({"temperature"}),
        primary="temperature",
        numeric=frozenset({"temperature", "setpoint"}),
        box=lambda at, _orientation: thermostat_box(*at),
        draw=_draw_thermostat,
        params=_thermostat_params,
    ),
    "router": _network_spec("router", router_box, router),
    "network_switch": _network_spec("network_switch", switch_box, network_switch),
    "access_point": _network_spec(
        "access_point", ap_box, access_point, channels=(*DEVICE_CHANNELS, "clients")
    ),
    "host": _network_spec("host", host_box, host),
    "radio": _network_spec("radio", radio_box, radio, channels=RADIO_CHANNELS),
    "transfer_switch": SymbolSpec(
        type="transfer_switch",
        channels=("state",),
        required=frozenset({"state"}),
        primary="state",
        box=_ats_box,
        draw=_draw_ats,
        params=_state_list_params("connected", DEFAULT_CONNECTED_STATES),
        ports={"grid": _terminal(_ats_box, -1.0), "load": _terminal(_ats_box, 1.0)},
    ),
    "load_panel": SymbolSpec(
        type="load_panel",
        channels=("power",),
        primary="power",
        numeric=frozenset({"power"}),
        box=lambda at, _orientation: load_panel_box(*at),
        draw=lambda inp, theme: load_panel(*inp.at, inp.status, theme),
        ports=_panel_ports(),
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
        box=_breaker_box,
        draw=_draw_breaker,
        params=_state_list_params("closed", DEFAULT_CLOSED_STATES),
        ports={"in": _terminal(_breaker_box, -1.0), "out": _terminal(_breaker_box, 1.0)},
    ),
}


def get_symbol(type_name: str) -> SymbolSpec:
    """Look up a symbol type; raises ``KeyError`` for unknown types."""
    return REGISTRY[type_name]
