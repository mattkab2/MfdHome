"""Gas water heater symbol: a tall rounded tank with a burner flame at its base."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

WIDTH = 44.0
HEIGHT = 80.0
CORNER = 10.0
PIPE_INSET = 12.0  # cold and hot connections, from the center line
GAS_RISE = 14.0  # gas inlet, above the bottom edge
FLAME_BASE = 10.0  # above the bottom edge
BURNER_HALF_WIDTH = 10.0


def heater_box(x: float, y: float) -> Box:
    """Bounding box of a water heater centered at (x, y)."""
    return Box(x - WIDTH / 2, y - HEIGHT / 2, x + WIDTH / 2, y + HEIGHT / 2)


def cold_port(at: Point) -> Port:
    """Cold water in: on top, left of center."""
    return Port((at[0] - PIPE_INSET, at[1] - HEIGHT / 2), (0.0, -1.0))


def hot_port(at: Point) -> Port:
    """Hot water out: on top, right of center."""
    return Port((at[0] + PIPE_INSET, at[1] - HEIGHT / 2), (0.0, -1.0))


def gas_port(at: Point) -> Port:
    """Gas supply: low on the left side, by the burner."""
    return Port((at[0] - WIDTH / 2, at[1] + HEIGHT / 2 - GAS_RISE), (-1.0, 0.0))


def flame_path(x: float, base: float) -> str:
    """A flame standing on ``base``: a tip leaning right and a notch splitting off a second
    tongue on the left (a plain teardrop would read as a water drop)."""
    f = svg.fmt

    def p(dx: float, dy: float) -> str:
        return f"{f(x + dx)} {f(base - dy)}"

    return (
        f"M{p(1, 20)}"
        f" C{p(9, 12)} {p(9, 4)} {p(4, 1)}"
        f" Q{p(0, -1)} {p(-4, 1)}"
        f" C{p(-9, 4)} {p(-8, 11)} {p(-4, 15)}"
        f" C{p(-4, 11)} {p(-2, 9)} {p(0, 10)}"
        f" C{p(2, 13)} {p(-1, 17)} {p(1, 20)} Z"
    )


def water_heater(x: float, y: float, heating: bool | None, status: Status, theme: Theme) -> str:
    """Render a gas water heater centered at (x, y).

    The flame is filled while ``heating`` and outlined otherwise (including
    with no data).
    """
    box = heater_box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    base = box.bottom - FLAME_BASE
    burner = base + 2
    return "".join(
        [
            svg.rect(box.left, box.top, WIDTH, HEIGHT, {"rx": CORNER, "fill": "none", **outline}),
            svg.element(
                "path",
                {
                    "d": flame_path(x, base),
                    "fill": theme.color(status) if heating else "none",
                    "stroke-linejoin": "round",
                    **outline,
                },
            ),
            svg.line(x - BURNER_HALF_WIDTH, burner, x + BURNER_HALF_WIDTH, burner, outline),
        ]
    )
