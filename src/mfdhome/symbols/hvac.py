"""HVAC symbols: air handler and furnace, outdoor condenser, damper and thermostat.

An air handler is a cabinet with an optional AC coil on top and the blower
(a fan); a furnace is one with a gas burner (a flame) below. The coil is
filled while cooling, the fan while the blower runs and the flame while
heating. A condenser is the outdoor AC unit, its fan seen from above, filled
while the compressor runs. A damper is a blade on a pivot in a duct: along
the flow when open, across it when closed, diagonal while moving. A
thermostat shows the room temperature, its setpoint and what it's doing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
from mfdhome.symbols.valve import ACTUATOR_HEIGHT, ACTUATOR_REACH, ACTUATOR_WIDTH
from mfdhome.symbols.water_heater import flame_path
from mfdhome.themes.theme import Theme

CABINET_WIDTH = 64.0
CABINET_PAD = 4.0  # between the cabinet wall and its first and last section
COIL_SECTION = 24.0
FAN_SECTION = 40.0
BURNER_SECTION = 36.0
FAN_RADIUS = 14.0
COIL_WIDTH = 44.0
COIL_HEIGHT = 16.0
COIL_ZIGS = 6

CONDENSER_SIZE = 64.0
CONDENSER_FAN_RADIUS = 24.0

DAMPER_LENGTH = 36.0
DAMPER_HEIGHT = 24.0
BLADE_HALF = 10.0
PIVOT_RADIUS = 2.5

THERMOSTAT_WIDTH = 128.0
THERMOSTAT_HEIGHT = 60.0


@dataclass(frozen=True)
class Cabinet:
    """An air handler's layout: optional coil on top, the blower, optional burner below."""

    coil: bool
    burner: bool

    @property
    def height(self) -> float:
        """The cabinet's height, from its sections."""
        sections = (
            FAN_SECTION
            + (COIL_SECTION if self.coil else 0)
            + (BURNER_SECTION if self.burner else 0)
        )
        return sections + 2 * CABINET_PAD

    def top(self, y: float) -> float:
        """The cabinet's top edge, centered on ``y``."""
        return y - self.height / 2

    def coil_y(self, y: float) -> float:
        """The coil section's center."""
        return self.top(y) + CABINET_PAD + COIL_SECTION / 2

    def fan_y(self, y: float) -> float:
        """The blower's center."""
        return self.top(y) + CABINET_PAD + (COIL_SECTION if self.coil else 0) + FAN_SECTION / 2

    def burner_y(self, y: float) -> float:
        """The burner section's center."""
        return self.top(y) + self.height - CABINET_PAD - BURNER_SECTION / 2

    def box(self, x: float, y: float) -> Box:
        """Bounding box of the cabinet centered at (x, y)."""
        half = CABINET_WIDTH / 2
        return Box(x - half, self.top(y), x + half, self.top(y) + self.height)

    def ports(self, x: float, y: float) -> dict[str, Port]:
        """Supply air out of the top, return air in on the left at the blower; the
        refrigerant line on the right at the coil, gas on the right at the burner."""
        left, right = x - CABINET_WIDTH / 2, x + CABINET_WIDTH / 2
        ports = {
            "supply": Port((x, self.top(y)), (0.0, -1.0)),
            "return": Port((left, self.fan_y(y)), (-1.0, 0.0)),
        }
        if self.coil:
            ports["refrigerant"] = Port((right, self.coil_y(y)), (1.0, 0.0))
        if self.burner:
            ports["gas"] = Port((right, self.burner_y(y)), (1.0, 0.0))
        return ports


def _fan(cx: float, cy: float, radius: float, running: bool, status: Status, theme: Theme) -> str:
    """A fan: a circle with three blades; filled (blades in the background color) when running."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    blade_color = theme.background if running else theme.color(status)
    parts = [
        svg.element(
            "circle",
            {
                "cx": cx,
                "cy": cy,
                "r": radius,
                "fill": theme.color(status) if running else "none",
                **outline,
            },
        )
    ]
    for degrees in (90.0, 210.0, 330.0):
        a = math.radians(degrees)
        tip = (cx + math.cos(a) * radius * 0.7, cy - math.sin(a) * radius * 0.7)
        parts.append(
            svg.element(
                "line",
                {
                    "x1": cx,
                    "y1": cy,
                    "x2": tip[0],
                    "y2": tip[1],
                    "stroke": blade_color,
                    "stroke-width": theme.symbol_stroke_width * 1.5,
                    "stroke-linecap": "round",
                },
            )
        )
    return "".join(parts)


def _coil(cx: float, cy: float, cooling: bool, status: Status, theme: Theme) -> str:
    """An evaporator coil: a zigzag in a box; filled (zigzag in the background) while cooling."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half_w, half_h = COIL_WIDTH / 2, COIL_HEIGHT / 2
    inset = 3.0
    step = (COIL_WIDTH - 2 * inset) / COIL_ZIGS
    zigzag = [
        (cx - half_w + inset + i * step, cy + (half_h - inset) * (1 if i % 2 else -1))
        for i in range(COIL_ZIGS + 1)
    ]
    return svg.element(
        "rect",
        {
            "x": cx - half_w,
            "y": cy - half_h,
            "width": COIL_WIDTH,
            "height": COIL_HEIGHT,
            "fill": theme.color(status) if cooling else "none",
            **outline,
        },
    ) + svg.element(
        "polyline",
        {
            "points": svg.points(zigzag),
            "fill": "none",
            "stroke": theme.background if cooling else theme.color(status),
            "stroke-width": theme.symbol_stroke_width,
            "stroke-linejoin": "round",
        },
    )


def air_handler(
    x: float,
    y: float,
    cabinet: Cabinet,
    heating: bool,
    cooling: bool,
    blowing: bool,
    status: Status,
    theme: Theme,
) -> str:
    """Render an air handler (or a furnace: one with a burner) centered at (x, y).

    The coil is filled while cooling, the fan while the blower runs and the
    flame while heating.
    """
    box = cabinet.box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [
        svg.element(
            "rect",
            {
                "x": box.left,
                "y": box.top,
                "width": CABINET_WIDTH,
                "height": cabinet.height,
                "rx": 4,
                "fill": "none",
                **outline,
            },
        )
    ]
    if cabinet.coil:
        parts.append(_coil(x, cabinet.coil_y(y), cooling, status, theme))
    parts.append(_fan(x, cabinet.fan_y(y), FAN_RADIUS, blowing, status, theme))
    if cabinet.burner:
        base = cabinet.burner_y(y) + 12
        parts += [
            svg.element(
                "path",
                {
                    "d": flame_path(x, base),
                    "fill": theme.color(status) if heating else "none",
                    "stroke-linejoin": "round",
                    **outline,
                },
            ),
            svg.element(
                "line", {"x1": x - 10, "y1": base + 2, "x2": x + 10, "y2": base + 2, **outline}
            ),
        ]
    return "".join(parts)


def condenser_box(x: float, y: float) -> Box:
    """Bounding box of an outdoor condenser centered at (x, y)."""
    half = CONDENSER_SIZE / 2
    return Box(x - half, y - half, x + half, y + half)


def condenser_port(x: float, y: float) -> Port:
    """The refrigerant line set connection: the left side."""
    return Port((x - CONDENSER_SIZE / 2, y), (-1.0, 0.0))


def condenser(x: float, y: float, running: bool, status: Status, theme: Theme) -> str:
    """Render an outdoor AC condenser: a square unit with its fan seen from above,
    filled while the compressor runs."""
    box = condenser_box(x, y)
    return svg.element(
        "rect",
        {
            "x": box.left,
            "y": box.top,
            "width": CONDENSER_SIZE,
            "height": CONDENSER_SIZE,
            "rx": 4,
            "fill": "none",
            **stroke(status, theme, theme.symbol_stroke_width),
        },
    ) + _fan(x, y, CONDENSER_FAN_RADIUS, running, status, theme)


class DamperState(StrEnum):
    """What a damper's blade shows."""

    OPEN = "open"  # along the flow
    CLOSED = "closed"  # across the flow
    MOVING = "moving"  # diagonal (also: no data)


def damper_box(x: float, y: float, orientation: Orientation, actuated: bool = False) -> Box:
    """Bounding box of a damper centered at (x, y), including any actuator."""
    reach = ACTUATOR_REACH if actuated else 0.0
    if orientation is Orientation.VERTICAL:
        return Box(
            x - DAMPER_HEIGHT / 2,
            y - DAMPER_LENGTH / 2,
            x + DAMPER_HEIGHT / 2 + reach,
            y + DAMPER_LENGTH / 2,
        )
    return Box(
        x - DAMPER_LENGTH / 2,
        y - DAMPER_HEIGHT / 2 - reach,
        x + DAMPER_LENGTH / 2,
        y + DAMPER_HEIGHT / 2,
    )


def damper(
    x: float,
    y: float,
    state: DamperState,
    actuated: bool,
    status: Status,
    orientation: Orientation,
    theme: Theme,
) -> str:
    """Render a damper centered at (x, y), the duct running left to right (top to bottom)."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half_l, half_h = DAMPER_LENGTH / 2, DAMPER_HEIGHT / 2

    def line(a: Point, b: Point, attrs: dict[str, svg.AttrValue]) -> str:
        return svg.element("line", {"x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], **attrs})

    angle = {DamperState.OPEN: 0.0, DamperState.CLOSED: 90.0}.get(state, 45.0)
    dx = math.cos(math.radians(angle)) * BLADE_HALF
    dy = math.sin(math.radians(angle)) * BLADE_HALF
    blade = stroke(status, theme, theme.symbol_stroke_width * 1.5)
    parts = [
        line((x - half_l, y - half_h), (x + half_l, y - half_h), outline),  # duct walls
        line((x - half_l, y + half_h), (x + half_l, y + half_h), outline),
        line((x - dx, y + dy), (x + dx, y - dy), {**blade, "stroke-linecap": "round"}),
        svg.element(
            "circle",
            {"cx": x, "cy": y, "r": PIVOT_RADIUS, "fill": theme.color(status), "stroke": "none"},
        ),
    ]
    if actuated:
        top = y - half_h - ACTUATOR_REACH
        parts.append(line((x, y - half_h), (x, top + ACTUATOR_HEIGHT), outline))
        parts.append(
            svg.element(
                "rect",
                {
                    "x": x - ACTUATOR_WIDTH / 2,
                    "y": top,
                    "width": ACTUATOR_WIDTH,
                    "height": ACTUATOR_HEIGHT,
                    "fill": "none",
                    **outline,
                },
            )
        )
    vertical = orientation is Orientation.VERTICAL
    transform = f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if vertical else None
    return svg.element("g", {"transform": transform}, parts)


#: What a thermostat says for each ``hvac_action``.
ACTION_LABELS = {
    "heating": "HEAT",
    "cooling": "COOL",
    "fan": "FAN",
    "idle": "IDLE",
    "off": "OFF",
    "drying": "DRY",
    "preheating": "PREHEAT",
    "defrosting": "DEFROST",
}
#: Actions where equipment runs: shown in the active color.
RUNNING_ACTIONS = frozenset({"heating", "cooling", "fan", "drying", "preheating", "defrosting"})


def thermostat_box(x: float, y: float) -> Box:
    """Bounding box of a thermostat centered at (x, y)."""
    return Box(
        x - THERMOSTAT_WIDTH / 2,
        y - THERMOSTAT_HEIGHT / 2,
        x + THERMOSTAT_WIDTH / 2,
        y + THERMOSTAT_HEIGHT / 2,
    )


def thermostat(
    x: float,
    y: float,
    temperature: str,
    setpoint: str,
    action: str | None,
    status: Status,
    theme: Theme,
) -> str:
    """Render a thermostat: the temperature large, the setpoint and action beside it."""
    box = thermostat_box(x, y)
    running = status is Status.NORMAL and action in RUNNING_ACTIONS
    action_label = "---" if action is None else ACTION_LABELS.get(action, action.upper())
    action_color = theme.text_in(Status.ACTIVE) if running else theme.text_in(status)

    def text(tx: float, ty: float, value: str, size: float, color: str, anchor: str) -> str:
        return svg.element(
            "text",
            {
                "x": tx,
                "y": ty,
                "text-anchor": anchor,
                "dominant-baseline": "middle",
                **font(theme, size, color),
            },
            [svg.text(value)],
        )

    return "".join(
        [
            svg.element(
                "rect",
                {
                    "x": box.left,
                    "y": box.top,
                    "width": THERMOSTAT_WIDTH,
                    "height": THERMOSTAT_HEIGHT,
                    "rx": 6,
                    "fill": "none",
                    **stroke(status, theme, theme.symbol_stroke_width),
                },
            ),
            text(
                box.left + 12,
                y,
                temperature,
                theme.label_font_size * 1.4,
                theme.text_in(status),
                "start",
            ),
            text(box.right - 10, y - 12, action_label, theme.font_size * 0.75, action_color, "end"),
            text(
                box.right - 10,
                y + 12,
                f"SET {setpoint}",
                theme.font_size * 0.75,
                theme.text_in(status),
                "end",
            ),
        ]
    )
