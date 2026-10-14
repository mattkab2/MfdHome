"""Symbol-level rendering tests."""

import re

from mfdhome.model import Orientation, Status
from mfdhome.symbols import Flow, battery, breaker, line
from mfdhome.symbols.line import LineParts
from mfdhome.symbols.svg import element, fmt, text
from mfdhome.themes import EINK_MONO, LCD

GRAY = LCD.color(Status.UNAVAILABLE)


def test_fmt_is_stable() -> None:
    assert [fmt(v) for v in (1.0, 1.5, 1.234, -0.001, 0)] == ["1", "1.5", "1.23", "0", "0"]


def test_element_escapes_and_drops_none() -> None:
    assert element("text", {"x": 1, "id": None}, [text("a<b")]) == '<text x="1">a&lt;b</text>'


def test_unavailable_symbols_are_gray_and_dotted() -> None:
    fragments = [
        line(((0, 0), (100, 0)), Status.UNAVAILABLE, None, LCD).body,
        battery(0, 0, None, Status.UNAVAILABLE, LCD),
        breaker(0, 0, None, Status.UNAVAILABLE, Orientation.HORIZONTAL, LCD),
    ]
    for fragment in fragments:
        assert f'stroke-dasharray="{LCD.unavailable_dots}" stroke-linecap="round"' in fragment
        assert set(re.findall(r"#[0-9a-f]{6}", fragment)) == {GRAY}


def test_line_flow_chevron_points_in_flow_direction() -> None:
    forward = line(((0, 0), (100, 0)), Status.ACTIVE, Flow.FORWARD, LCD).body
    reverse = line(((0, 0), (100, 0)), Status.ACTIVE, Flow.REVERSE, LCD).body
    assert 'points="60,0 40,10 40,-10"' in forward
    assert 'points="40,0 60,-10 60,10"' in reverse
    assert "polygon" not in line(((0, 0), (100, 0)), Status.NORMAL, None, LCD).body


def test_degenerate_line_renders_nothing() -> None:
    assert line(((0, 0),), Status.NORMAL, None, LCD) == LineParts("", "", 0.0)


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


class TestCasing:
    def test_cased_line_has_shell_and_hollow(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.NORMAL, None, LCD, casing=True)
        assert f'stroke="{LCD.color(Status.NORMAL)}" stroke-width="10"' in parts.casing
        assert f'stroke="{LCD.background}" stroke-width="6"' in parts.body
        assert parts.half_width == 5

    def test_weight_scales_casing_and_arrow(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.ACTIVE, Flow.FORWARD, LCD, weight=2, casing=True)
        assert 'stroke-width="20"' in parts.casing
        assert 'stroke-width="16"' in parts.body  # walls stay 2 thick
        assert 'points="75,0 25,25 25,-25"' in parts.body  # arrow 1.25 x outer width

    def test_uncased_line_is_solid_and_weighted(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.NORMAL, None, LCD, weight=0.5)
        assert parts.casing == ""
        assert 'stroke-width="1.5"' in parts.body

    def test_cased_unavailable_dots_scale_with_width(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.UNAVAILABLE, None, LCD, casing=True)
        assert 'stroke-dasharray="0 20" stroke-linecap="round"' in parts.casing


class TestSeverityPatterns:
    def test_caution_dashes_the_core_not_the_walls(self) -> None:
        for flow in (None, Flow.FORWARD):  # shown whether or not power flows
            parts = line(((0, 0), (100, 0)), Status.CAUTION, flow, LCD, casing=True)
            assert "stroke-dasharray" not in parts.casing  # solid walls
            assert 'stroke-width="4" stroke-dasharray="15 10"' in parts.body

    def test_caution_dashes_an_uncased_line(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.CAUTION, None, LCD)
        assert 'stroke-dasharray="4.5 3"' in parts.body

    def test_warning_hatches_the_hollow_and_forces_casing(self) -> None:
        parts = line(((0, 0), (100, 0)), Status.WARNING, None, LCD, line_id="g")
        assert parts.casing  # casing forced on so the stripes have room
        assert '<pattern id="hatch-g-0"' in parts.body
        assert 'stroke="url(#hatch-g-0)" stroke-width="6"' in parts.body

    def test_hatch_rotates_per_segment(self) -> None:
        pts = ((0, 0), (100, 0), (100, 100), (200, 200))
        body = line(pts, Status.WARNING, None, LCD, casing=True, line_id="g").body
        rotations = re.findall(r'patternTransform="rotate\(([-0-9.]+)\)"', body)
        assert rotations == ["45", "135", "90"]  # always 45 degrees off each segment

    def test_patterns_distinct_on_eink(self) -> None:
        bodies = {
            s: "".join((p.casing, p.body))
            for s in Status
            for p in [line(((0, 0), (100, 0)), s, None, EINK_MONO, casing=True)]
        }
        assert (
            len(
                {
                    bodies[s]
                    for s in (Status.NORMAL, Status.CAUTION, Status.WARNING, Status.UNAVAILABLE)
                }
            )
            == 4
        )

    def test_lines_ignore_status_weight(self) -> None:
        normal = line(((0, 0), (100, 0)), Status.NORMAL, None, EINK_MONO, casing=True)
        warning = line(((0, 0), (100, 0)), Status.WARNING, None, EINK_MONO, casing=True)
        assert 'stroke-width="10"' in normal.casing and 'stroke-width="10"' in warning.casing


class TestCore:
    PTS = ((0.0, 0.0), (100.0, 0.0))

    def test_flowing_pipe_has_solid_core(self) -> None:
        body = line(self.PTS, Status.ACTIVE, Flow.FORWARD, LCD, casing=True).body
        blue = LCD.color(Status.ACTIVE)
        # walls 2, hollow 6, core inset 1 on each side -> 4
        assert f'stroke="{blue}" stroke-width="4"' in body

    def test_idle_pipe_is_blank(self) -> None:
        body = line(self.PTS, Status.NORMAL, None, LCD, casing=True).body
        assert body.count("<polyline") == 1  # hollow only, no core

    def test_caution_keeps_core_warning_keeps_hatch(self) -> None:
        caution = line(self.PTS, Status.CAUTION, Flow.FORWARD, LCD, casing=True).body
        yellow = LCD.color(Status.CAUTION)
        assert f'stroke="{yellow}" stroke-width="4" stroke-dasharray="15 10"' in caution
        warning = line(self.PTS, Status.WARNING, Flow.FORWARD, LCD, casing=True).body
        assert "url(#hatch" in warning and 'stroke-width="4"' not in warning

    def test_uncased_line_has_no_core(self) -> None:
        body = line(self.PTS, Status.ACTIVE, Flow.FORWARD, LCD).body
        assert body.count("<polyline") == 1
