"""Status/annunciator page and the alert banner, end to end through mfd.alerts."""

from datetime import UTC, datetime, timedelta

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.mfd import EMPTY_BOARD, Board, Phase, acknowledge, evaluate_alerts, most_urgent, step
from mfdhome.model import Status
from mfdhome.render import render_page
from mfdhome.render.alerts import AlertView
from mfdhome.render.controls import Controls
from mfdhome.themes import EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import config_page, fixture_state, load_test_config

T0 = datetime(2026, 1, 1, tzinfo=UTC)
TABLET = Target("tablet", 1280, 768)
THEMES = [LCD, MIRROR, EINK_MONO]
CONFIG = load_test_config()
ALERTS = CONFIG.alerts.alerts


def board_from(*fixtures: str, acks: tuple[str, ...] = ()) -> Board:
    """Step through ``fixtures`` in order, acknowledging ``acks`` after the first."""
    board = EMPTY_BOARD
    for i, name in enumerate(fixtures):
        board = step(
            board, ALERTS, evaluate_alerts(ALERTS, fixture_state(name)), T0 + timedelta(minutes=i)
        )
        if i == 0 and acks:
            board = acknowledge(board, "workshop", T0 + timedelta(seconds=30), ids=acks)
    return board


MIXED = board_from("status_raised", "status_mixed", acks=("wan_down", "high_wind"))


def view(board: Board, banner: bool = True) -> AlertView:
    return AlertView(ALERTS, CONFIG.alerts.systems, board, show_banner=banner)


def test_mixed_board_covers_every_phase() -> None:
    assert {k: v.phase for k, v in MIXED.items()} == {
        "battery_low": Phase.ACTIVE_UNACKED,
        "leak_detected": Phase.CLEARED_UNACKED,
        "wan_down": Phase.ACTIVE_ACKED,
        "high_wind": Phase.ACTIVE_ACKED,
        "front_door_open": Phase.ACTIVE_UNACKED,
    }
    # The cleared warning outranks the active caution.
    assert most_urgent(MIXED, ALERTS) == CONFIG.alerts.by_id()["leak_detected"]


SCENARIOS = {
    "clear": ("status_clear", EMPTY_BOARD),
    "mixed": ("status_mixed", MIXED),
    "unavailable": (None, EMPTY_BOARD),
}


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_status_page_snapshot(scenario: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    fixture, board = SCENARIOS[scenario]
    state = fixture_state(fixture) if fixture else {}
    svg = render_page(config_page("status"), state, theme, TABLET, view(board))
    assert svg == svg_snapshot


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_electrical_banner_snapshot(theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    board = board_from("electrical_islanded")
    assert most_urgent(board, ALERTS) == CONFIG.alerts.by_id()["grid_lost"]
    svg = render_page(
        config_page("electrical"), fixture_state("electrical_islanded"), theme, TABLET, view(board)
    )
    assert svg == svg_snapshot
    assert "GRID POWER LOST" in svg and ">+1<" in svg  # battery_low is also pending


def test_status_clear_has_no_banner_or_animation() -> None:
    svg = render_page(
        config_page("status"), fixture_state("status_clear"), LCD, TABLET, view(EMPTY_BOARD)
    )
    assert 'id="banner"' not in svg and "<style>" not in svg


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_status_pages_use_only_theme_palette(theme: Theme) -> None:
    import re

    for fixture, board in SCENARIOS.values():
        state = fixture_state(fixture) if fixture else {}
        svg = render_page(config_page("status"), state, theme, TABLET, view(board))
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_soft_keys_snapshot(theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    """Status page with the soft keys: ALERTS lit, banner between the keys."""
    svg = render_page(
        config_page("status"),
        fixture_state("status_mixed"),
        theme,
        TABLET,
        view(MIXED),
        Controls(Status.WARNING, locked=False),
    )
    assert svg == svg_snapshot
