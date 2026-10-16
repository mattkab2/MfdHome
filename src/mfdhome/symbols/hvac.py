"""HVAC symbols: furnace, damper and thermostat.

A furnace is a cabinet with the blower (a fan) above the burner (a flame):
the flame is solid while heating, the fan filled while the blower runs. A
damper is a blade on a pivot in a duct: along the flow when open, across it
when closed, diagonal while moving. A thermostat shows the room temperature,
its setpoint and what it's doing.
"""

from __future__ import annotations

import math
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

FURNACE_WIDTH = 64.0
FURNACE_HEIGHT = 96.0
FAN_RADIUS = 14.0
FAN_RISE = 20.0  # fan center above the cabinet's center
FLAME_BASE = 12.0  # above the cabinet's bottom
RETURN_DROP = 20.0  # return connection below the center, on the left
GAS_DROP = 34.0  # gas connection below the center, on the right

DAMPER_LENGTH = 36.0
DAMPER_HEIGHT = 24.0
BLADE_HALF = 10.0
PIVOT_RADIUS = 2.5

THERMOSTAT_WIDTH = 128.0
THERMOSTAT_HEIGHT = 60.0


def furnace_box(x: float, y: float) -> Box:
    """Bounding box of a furnace centered at (x, y)."""
    return Box(
        x - FURNACE_WIDTH / 2, y - FURNACE_HEIGHT / 2, x + FURNACE_WIDTH / 2, y + FURNACE_HEIGHT / 2
    )


def furnace_ports(x: float, y: float) -> dict[str, Port]:
    """Supply air out of the top, return air in on the left, gas in on the right."""
    return {
        "supply": Port((x, y - FURNACE_HEIGHT / 2), (0.0, -1.0)),
        "return": Port((x - FURNACE_WIDTH / 2, y + RETURN_DROP), (-1.0, 0.0)),
        "gas": Port((x + FURNACE_WIDTH / 2, y + GAS_DROP), (1.0, 0.0)),
    }


def _fan(cx: float, cy: float, running: bool, status: Status, theme: Theme) -> str:
    """A fan: a circle with three blades; filled (blades in the background color) when running."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    blade_color = theme.background if running else theme.color(status)
    parts = [
        svg.element(
            "circle",
            {
                "cx": cx,
                "cy": cy,
                "r": FAN_RADIUS,
                "fill": theme.color(status) if running else "none",
                **outline,
            },
        )
    ]
    for degrees in (90.0, 210.0, 330.0):
        a = math.radians(degrees)
        tip = (cx + math.cos(a) * FAN_RADIUS * 0.7, cy - math.sin(a) * FAN_RADIUS * 0.7)
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


def furnace(x: float, y: float, heating: bool, blowing: bool, status: Status, theme: Theme) -> str:
    """Render a furnace centered at (x, y): the blower above the burner."""
    box = furnace_box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    base = box.bottom - FLAME_BASE
    return "".join(
        [
            svg.element(
                "rect",
                {
                    "x": box.left,
                    "y": box.top,
                    "width": FURNACE_WIDTH,
                    "height": FURNACE_HEIGHT,
                    "rx": 4,
                    "fill": "none",
                    **outline,
                },
            ),
            _fan(x, y - FAN_RISE, blowing, status, theme),
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
                "line",
                {"x1": x - 10, "y1": base + 2, "x2": x + 10, "y2": base + 2, **outline},
            ),
        ]
    )


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
