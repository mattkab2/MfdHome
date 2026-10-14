"""Tests for anchors and polyline geometry."""

import pytest

from mfdhome.layout import (
    LINE_GAP,
    Anchor,
    Box,
    Placement,
    default_line_anchor,
    parse_anchor,
    place_stack,
    point_along,
)

BOX = Box(0, 0, 100, 50)  # cx=50, cy=25
GAP = 4.0


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (Anchor.TOP_LEFT, Placement(0, -4, "end", None)),
        (Anchor.TOP_CENTER, Placement(50, -4, "middle", None)),
        (Anchor.TOP_RIGHT, Placement(100, -4, "start", None)),
        (Anchor.CENTER_LEFT, Placement(-4, 25, "end", "middle")),
        (Anchor.CENTER, Placement(50, 25, "middle", "middle")),
        (Anchor.CENTER_RIGHT, Placement(104, 25, "start", "middle")),
        (Anchor.BOTTOM_LEFT, Placement(0, 66, "end", None)),
        (Anchor.BOTTOM_CENTER, Placement(50, 66, "middle", None)),
        (Anchor.BOTTOM_RIGHT, Placement(100, 66, "start", None)),
    ],
)
def test_single_label_placement(anchor: Anchor, expected: Placement) -> None:
    # bottom row: 50 + gap 4 + 0.75 * 16 = 66
    assert place_stack(BOX, anchor, [16], GAP) == [expected]


def test_aliases_and_names() -> None:
    assert parse_anchor("top") is Anchor.TOP_CENTER
    assert parse_anchor("Bottom") is Anchor.BOTTOM_CENTER
    assert parse_anchor("left") is Anchor.CENTER_LEFT
    assert parse_anchor("right") is Anchor.CENTER_RIGHT
    assert parse_anchor("center-right") is Anchor.CENTER_RIGHT
    with pytest.raises(ValueError):
        parse_anchor("upper-left")


def test_bottom_stack_grows_downward() -> None:
    ys = [p.y for p in place_stack(BOX, Anchor.BOTTOM_CENTER, [16, 16], GAP)]
    assert ys == pytest.approx([66, 86.8])


def test_top_stack_grows_upward_in_reading_order() -> None:
    ys = [p.y for p in place_stack(BOX, Anchor.TOP_CENTER, [20, 16], GAP)]
    # last label sits just above the box; first is one line above it
    assert ys == pytest.approx([-4 - 20.8, -4])


def test_center_stack_is_centered() -> None:
    ys = [p.y for p in place_stack(BOX, Anchor.CENTER_RIGHT, [10, 10, 10], GAP)]
    assert ys == pytest.approx([12, 25, 38])


def test_offset_and_empty_stack() -> None:
    [p] = place_stack(BOX, Anchor.CENTER, [16], GAP, offset=(5, -3))
    assert (p.x, p.y) == (55, 22)
    assert place_stack(BOX, Anchor.CENTER, [], GAP) == []


def test_point_box_matches_line_label_positions() -> None:
    point = Box.point(10, 20)
    [above] = place_stack(point, Anchor.TOP_CENTER, [16], LINE_GAP)
    [right] = place_stack(point, Anchor.CENTER_RIGHT, [16], LINE_GAP)
    assert above == Placement(10, 6, "middle", None)
    assert right == Placement(24, 20, "start", "middle")


def test_default_line_anchor() -> None:
    assert default_line_anchor((1, 0)) is Anchor.TOP_CENTER
    assert default_line_anchor((-1, 0)) is Anchor.TOP_CENTER
    assert default_line_anchor((0, 1)) is Anchor.CENTER_RIGHT


def test_point_along() -> None:
    pts = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0))
    assert point_along(pts, 0.5) == ((100, 0), (1, 0))
    assert point_along(pts, 0.75) == ((100, 50), (0, 1))
    assert point_along(pts, 0) == ((0, 0), (1, 0))
    assert point_along(pts, 1) == ((100, 100), (0, 1))
    assert point_along(((5.0, 5.0), (5.0, 5.0)), 0.5) == ((5, 5), (1, 0))


def test_grid_centers() -> None:
    from mfdhome.layout import grid_centers

    centers = grid_centers((10, 20), 5, 2, (100, 50), (10, 5))
    assert centers == [(60, 45), (170, 45), (60, 100), (170, 100), (60, 155)]
    with pytest.raises(ValueError):
        grid_centers((0, 0), 1, 0, (1, 1))
