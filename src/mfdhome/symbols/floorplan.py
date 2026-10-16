"""Floorplan drawing: rooms, walls, openings (doors and windows) and the alarm panel.

Structure (rooms, walls) is drawn in the theme's structure color, so it
recedes; only things that report (openings, sensors, the panel) and rooms
with a status worth showing take status colors.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
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
    parts = [
        svg.element(
            "polygon",
            {
                "points": svg.points(points),
                "fill": "none",
                "stroke-linejoin": "miter",
                **outline,
            },
        )
    ]
    if name:
        x, y = label_at or _middle(points)
        color = theme.structure_color if quiet else theme.text_in(status)
        parts.append(
            svg.element(
                "text",
                {
                    "x": x,
                    "y": y,
                    "text-anchor": "middle",
                    "dominant-baseline": "middle",
                    **font(theme, theme.font_size * ROOM_LABEL_SCALE, color),
                },
                [svg.text(name)],
            )
        )
    return "".join(parts)


def wall(points: Sequence[Point], exterior: bool, theme: Theme) -> str:
    """Render a wall: a static polyline in the structure color."""
    width = theme.symbol_stroke_width * (EXTERIOR_WEIGHT if exterior else 1.0)
    return svg.element(
        "polyline",
        {
            "points": svg.points(points),
            "fill": "none",
            "stroke": theme.structure_color,
            "stroke-width": width,
            "stroke-linejoin": "miter",
            "stroke-linecap": "square",
        },
    )


class OpeningKind(StrEnum):
    """A door (a leaf that swings) or a window (a double line)."""

    DOOR = "door"
    WINDOW = "window"


#: Half the length of the jamb marks at each end of an opening.
JAMB = 5.0
#: Half the spacing of a window's double line.
WINDOW_GAP = 2.5
#: An opening's leaf, relative to the theme's symbol stroke width.
LEAF_WEIGHT = 1.5


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
) -> Box:
    """Bounding box of an opening centered at (x, y), including a door's swing.

    ``swing`` is -1 (up, or left when vertical) or +1 (down, or right).
    """
    half = length / 2
    if kind is OpeningKind.DOOR:
        low, high = min(-JAMB, swing * length), max(JAMB, swing * length)
    else:
        low, high = -JAMB, JAMB
    if vertical:
        return Box(x + low, y - half, x + high, y + half)
    return Box(x - half, y + low, x + half, y + high)


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
) -> str:
    """Render a door or window centered at (x, y) in a wall.

    The wall is erased under the opening and its ends marked with jambs (in
    the structure color). A closed door is a leaf across the gap; an open one
    swings 90 degrees toward ``swing`` around its hinge, with the swing arc.
    A closed window is a double line; an open one shows the gap with one
    sash slid aside.
    """

    def at(u: float, v: float) -> Point:
        return (x + v, y + u) if vertical else (x + u, y + v)

    def seg(a: Point, b: Point, attrs: dict[str, svg.AttrValue]) -> str:
        return svg.element("line", {"x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], **attrs})

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
        if is_open:  # one sash, slid aside: the gap shows, and so does the status
            parts += [seg(at(-half, -WINDOW_GAP), at(0, -WINDOW_GAP), leaf)]
        else:
            parts += [seg(at(-half, -WINDOW_GAP), at(half, -WINDOW_GAP), leaf)]
            parts += [seg(at(-half, WINDOW_GAP), at(half, WINDOW_GAP), leaf)]
        return "".join(parts)
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
    return svg.element(
        "rect",
        {
            "x": box.left,
            "y": box.top,
            "width": PANEL_WIDTH,
            "height": PANEL_HEIGHT,
            "rx": 4,
            "fill": "none",
            **stroke(look, theme, theme.symbol_stroke_width),
        },
    ) + svg.element(
        "text",
        {
            "x": x,
            "y": y,
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            **font(theme, theme.label_font_size, theme.text_in(look)),
        },
        [svg.text(label)],
    )
