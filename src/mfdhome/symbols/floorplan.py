"""Floorplan drawing: rooms, walls, stairs, openings (doors, windows and overhead
doors) and the alarm panel.

Structure (rooms, walls, stairs) is drawn in the theme's structure color, so it
recedes; only things that report (openings, sensors, the panel) and rooms
with a status worth showing take status colors.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from enum import StrEnum

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke, text_at
from mfdhome.themes.theme import Theme

#: Exterior walls relative to the theme's symbol stroke width.
EXTERIOR_WEIGHT = 2.5
ROOM_LABEL_SCALE = 0.75


def _middle(points: Sequence[Point]) -> Point:
    """The average of the vertices: the middle of a convex or near-convex room."""
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def room(
    points: Sequence[Point],
    name: str | None,
    label_at: Point | None,
    status: Status,
    theme: Theme,
) -> str:
    """Render a room: its outline (in a status color only when not normal) and name."""
    quiet = status is Status.NORMAL
    outline: dict[str, svg.AttrValue] = (
        {"stroke": theme.structure_color, "stroke-width": theme.symbol_stroke_width}
        if quiet
        else stroke(status, theme, theme.symbol_stroke_width)
    )
    parts = [svg.polygon(points, {"fill": "none", "stroke-linejoin": "miter", **outline})]
    if name:
        x, y = label_at or _middle(points)
        color = theme.structure_color if quiet else theme.text_in(status)
        parts.append(text_at(x, y, name, theme, theme.font_size * ROOM_LABEL_SCALE, color))
    return "".join(parts)


def wall(points: Sequence[Point], exterior: bool, theme: Theme) -> str:
    """Render a wall: a static polyline in the structure color."""
    width = theme.symbol_stroke_width * (EXTERIOR_WEIGHT if exterior else 1.0)
    return svg.polyline(
        points,
        {
            "fill": "none",
            "stroke": theme.structure_color,
            "stroke-width": width,
            "stroke-linejoin": "miter",
            "stroke-linecap": "square",
        },
    )


#: Depth of one stair tread, for a flight's default tread count.
TREAD = 10.0
#: An arrowhead on a flight of stairs: half its width and its length.
STAIR_ARROW = 4.0


def stairs_box(x: float, y: float, vertical: bool, length: float, width: float) -> Box:
    """Bounding box of a flight ``length`` long (along its run) centered at (x, y)."""
    along, across = length / 2, width / 2
    if vertical:
        return Box(x - across, y - along, x + across, y + along)
    return Box(x - along, y - across, x + along, y + across)


def stairs(
    x: float,
    y: float,
    vertical: bool,
    length: float,
    width: float,
    treads: int,
    up_at_start: bool,
    theme: Theme,
) -> str:
    """Render a flight of stairs centered at (x, y): its outline, a line across at each
    tread and an arrow up the middle, pointing up the flight (toward its start,
    the top or left end, when ``up_at_start``). Stairs are structure: always in
    the structure color, whatever happens around them."""
    at = _placer(x, y, vertical, None)
    half, across = length / 2, width / 2
    line: dict[str, svg.AttrValue] = {
        "stroke": theme.structure_color,
        "stroke-width": theme.symbol_stroke_width,
    }
    fine = {**line, "stroke-width": theme.symbol_stroke_width * 0.5}
    box = stairs_box(x, y, vertical, length, width)
    parts = [
        svg.rect(
            box.left, box.top, box.right - box.left, box.bottom - box.top, {"fill": "none", **line}
        )
    ]
    step = length / treads
    for i in range(1, treads):
        u = -half + i * step
        parts.append(svg.line(*at(u, -across), *at(u, across), fine))
    sign = -1.0 if up_at_start else 1.0
    tip, tail = sign * (half - step / 2), -sign * (half - step / 2)
    back = tip - sign * STAIR_ARROW * 2
    parts.append(svg.line(*at(tail, 0), *at(tip, 0), line))
    parts.append(
        svg.polyline(
            [at(back, -STAIR_ARROW), at(tip, 0), at(back, STAIR_ARROW)],
            {"fill": "none", "stroke-linejoin": "miter", **line},
        )
    )
    return "".join(parts)


class OpeningKind(StrEnum):
    """A door (a leaf that swings), a window (a double line) or an overhead door (a
    panel that lifts into the room, such as a garage door)."""

    DOOR = "door"
    WINDOW = "window"
    OVERHEAD = "overhead"


#: Half the length of the jamb marks at each end of an opening.
JAMB = 5.0
#: Half the spacing of a window's double line.
WINDOW_GAP = 2.5
#: How far an open window's brackets return along the wall into the gap.
BRACKET = 3.0
#: An opening's leaf, relative to the theme's symbol stroke width.
LEAF_WEIGHT = 1.5
#: How far an open overhead door's lifted panel reaches into the room, seen from above.
OVERHEAD_DEPTH = 20.0


def _placer(
    x: float, y: float, vertical: bool, angle: float | None
) -> Callable[[float, float], Point]:
    """Local (``u`` along the wall, ``v`` across it) to canvas coordinates.

    Horizontal openings run right with ``v`` down; vertical ones run down with
    ``v`` right. ``angle`` (degrees, clockwise from pointing right) turns the
    wall for a diagonal one, ``v`` turning with it (down at 0).
    """
    if angle is None:
        return (lambda u, v: (x + v, y + u)) if vertical else (lambda u, v: (x + u, y + v))
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return lambda u, v: (x + u * c - v * s, y + u * s + v * c)


def _across(kind: OpeningKind, length: float, swing: float) -> tuple[float, float]:
    """How far an opening reaches across its wall (``v``), both ways."""
    if kind is OpeningKind.WINDOW:
        return -JAMB, JAMB
    reach = swing * (length if kind is OpeningKind.DOOR else OVERHEAD_DEPTH)
    return min(-JAMB, reach), max(JAMB, reach)


def _cut_width(theme: Theme) -> float:
    """Wide enough to erase an exterior wall under an opening."""
    return theme.symbol_stroke_width * EXTERIOR_WEIGHT + 2.0


def opening_box(
    x: float,
    y: float,
    vertical: bool,
    kind: OpeningKind,
    length: float,
    swing: float,
    angle: float | None = None,
) -> Box:
    """Bounding box of an opening centered at (x, y), including a door's swing.

    ``swing`` is -1 (up, or left when vertical) or +1 (down, or right); on a
    wall turned by ``angle``, the sides turn with it.
    """
    half = length / 2
    low, high = _across(kind, length, swing)
    if angle is None and vertical:
        return Box(x + low, y - half, x + high, y + half)
    if angle is None:
        return Box(x - half, y + low, x + half, y + high)
    at = _placer(x, y, vertical, angle)
    corners = [at(u, v) for u in (-half, half) for v in (low, high)]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    return Box(min(xs), min(ys), max(xs), max(ys))


def opening(
    x: float,
    y: float,
    vertical: bool,
    kind: OpeningKind,
    length: float,
    swing: float,
    hinge_at_start: bool,
    is_open: bool,
    status: Status,
    theme: Theme,
    angle: float | None = None,
) -> str:
    """Render a door or window centered at (x, y) in a wall (a diagonal one when
    ``angle`` is given).

    The wall is erased under the opening and its ends marked with jambs (in
    the structure color). A closed door is a leaf across the gap; an open one
    swings 90 degrees toward ``swing`` around its hinge, with the swing arc.
    A closed window is a double line; an open one leaves the gap bare between
    brackets at its jambs. A closed overhead door is a panel across the gap; an open
    one leaves the gap clear and shows its panel lifted overhead on the
    ``swing`` side, seen from above as a box reaching into the room.
    """
    at = _placer(x, y, vertical, angle)

    def seg(a: Point, b: Point, attrs: dict[str, svg.AttrValue]) -> str:
        return svg.line(*a, *b, attrs)

    half = length / 2
    leaf = stroke(status, theme, theme.symbol_stroke_width * LEAF_WEIGHT)
    jamb: dict[str, svg.AttrValue] = {
        "stroke": theme.structure_color,
        "stroke-width": theme.symbol_stroke_width,
    }
    parts = [
        seg(
            at(-half, 0),
            at(half, 0),
            {"stroke": theme.background, "stroke-width": _cut_width(theme)},
        ),
        seg(at(-half, -JAMB), at(-half, JAMB), jamb),
        seg(at(half, -JAMB), at(half, JAMB), jamb),
    ]
    if kind is OpeningKind.WINDOW:
        if is_open:  # a bare gap; the brackets carry the status
            for end, inward in ((-half, BRACKET), (half, -BRACKET)):
                bracket = [
                    at(end + inward, -JAMB),
                    at(end, -JAMB),
                    at(end, JAMB),
                    at(end + inward, JAMB),
                ]
                parts.append(
                    svg.polyline(bracket, {"fill": "none", "stroke-linejoin": "miter", **leaf})
                )
        else:
            parts += [seg(at(-half, -WINDOW_GAP), at(half, -WINDOW_GAP), leaf)]
            parts += [seg(at(-half, WINDOW_GAP), at(half, WINDOW_GAP), leaf)]
        return "".join(parts)
    if kind is OpeningKind.OVERHEAD:
        if not is_open:
            return "".join([*parts, seg(at(-half, 0), at(half, 0), leaf)])
        depth = swing * OVERHEAD_DEPTH
        lifted = [
            at(-half, JAMB * swing),
            at(half, JAMB * swing),
            at(half, depth),
            at(-half, depth),
        ]
        panel = {**stroke(status, theme, 1.0), "fill": "none"}
        return "".join([*parts, svg.polygon(lifted, panel)])
    hinge_u, free_u = (-half, half) if hinge_at_start else (half, -half)
    hinge = at(hinge_u, 0)
    if not is_open:
        return "".join([*parts, seg(hinge, at(free_u, 0), leaf)])
    tip, frame = at(hinge_u, swing * length), at(free_u, 0)
    cross = (tip[0] - hinge[0]) * (frame[1] - hinge[1]) - (tip[1] - hinge[1]) * (
        frame[0] - hinge[0]
    )
    f = svg.fmt
    arc = (
        f"M{f(tip[0])} {f(tip[1])} A{f(length)} {f(length)} 0 0 {1 if cross > 0 else 0} "
        f"{f(frame[0])} {f(frame[1])}"
    )
    swing_line = {**stroke(status, theme, 1.0), "fill": "none"}
    return "".join([*parts, seg(hinge, tip, leaf), svg.element("path", {"d": arc, **swing_line})])


#: What the alarm panel badge says for each Home Assistant state.
PANEL_LABELS = {
    "disarmed": "DISARMED",
    "arming": "ARMING",
    "armed_home": "ARMED HOME",
    "armed_away": "ARMED AWAY",
    "armed_night": "ARMED NIGHT",
    "armed_vacation": "ARMED VACATION",
    "armed_custom_bypass": "ARMED BYPASS",
    "pending": "ENTRY DELAY",
    "disarming": "DISARMING",
    "triggered": "TRIGGERED",
}
PANEL_WIDTH = 200.0
PANEL_HEIGHT = 36.0


def panel_box(x: float, y: float) -> Box:
    """Bounding box of an alarm panel badge centered at (x, y)."""
    return Box(x - PANEL_WIDTH / 2, y - PANEL_HEIGHT / 2, x + PANEL_WIDTH / 2, y + PANEL_HEIGHT / 2)


def alarm_panel(x: float, y: float, state: str | None, status: Status, theme: Theme) -> str:
    """Render the alarm panel badge: its state in words.

    Armed (with nothing wrong) is drawn in the active color; caution and
    warning (from status rules, e.g. ``triggered: warning``) win over it.
    """
    armed = state is not None and state.startswith("armed")
    look = Status.ACTIVE if status is Status.NORMAL and armed else status
    box = panel_box(x, y)
    label = "---" if state is None else PANEL_LABELS.get(state, state.upper().replace("_", " "))
    return svg.rect(
        box.left,
        box.top,
        PANEL_WIDTH,
        PANEL_HEIGHT,
        {"rx": 4, "fill": "none", **stroke(look, theme, theme.symbol_stroke_width)},
    ) + text_at(x, y, label, theme, theme.label_font_size, theme.text_in(look))
