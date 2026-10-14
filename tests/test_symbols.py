"""Symbol-level rendering tests."""

import re

from mfdhome.model import Orientation, Status
from mfdhome.symbols import Flow, battery, breaker, line
from mfdhome.symbols.svg import element, fmt, text
from mfdhome.themes import LCD

GRAY = LCD.color(Status.UNAVAILABLE)


def test_fmt_is_stable() -> None:
    assert [fmt(v) for v in (1.0, 1.5, 1.234, -0.001, 0)] == ["1", "1.5", "1.23", "0", "0"]


def test_element_escapes_and_drops_none() -> None:
    assert element("text", {"x": 1, "id": None}, [text("a<b")]) == '<text x="1">a&lt;b</text>'


def test_unavailable_symbols_are_gray_and_dashed() -> None:
    fragments = [
        line(((0, 0), (100, 0)), Status.UNAVAILABLE, None, LCD),
        battery(0, 0, None, Status.UNAVAILABLE, LCD),
        breaker(0, 0, None, Status.UNAVAILABLE, Orientation.HORIZONTAL, LCD),
    ]
    for fragment in fragments:
        assert LCD.unavailable_dash in fragment
        assert set(re.findall(r"#[0-9a-f]{6}", fragment)) == {GRAY}


def test_line_flow_chevron_points_in_flow_direction() -> None:
    forward = line(((0, 0), (100, 0)), Status.ACTIVE, Flow.FORWARD, LCD)
    reverse = line(((0, 0), (100, 0)), Status.ACTIVE, Flow.REVERSE, LCD)
    assert 'points="60,0 40,10 40,-10"' in forward
    assert 'points="40,0 60,-10 60,10"' in reverse
    assert "polygon" not in line(((0, 0), (100, 0)), Status.NORMAL, None, LCD)


def test_degenerate_line_renders_nothing() -> None:
    assert line(((0, 0),), Status.NORMAL, None, LCD) == ""


def test_battery_fill_is_clamped() -> None:
    full = battery(0, 0, 1.0, Status.NORMAL, LCD)
    over = battery(0, 0, 1.4, Status.NORMAL, LCD)
    assert full == over


def test_breaker_open_vs_closed_and_vertical() -> None:
    closed = breaker(0, 0, True, Status.NORMAL, Orientation.HORIZONTAL, LCD)
    opened = breaker(0, 0, False, Status.CAUTION, Orientation.HORIZONTAL, LCD)
    assert 'x2="20" y2="0"' in closed
    assert 'y2="-24"' in opened
    vertical = breaker(5, 5, True, Status.NORMAL, Orientation.VERTICAL, LCD)
    assert 'transform="rotate(90 5 5)"' in vertical
