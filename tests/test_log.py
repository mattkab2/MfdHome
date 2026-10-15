"""The alert log: rows from history, flapping merges, paging, rendering and keys."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.mfd.history import AlertEvent, EventKind
from mfdhome.mfd.keys import Action
from mfdhome.model import LogElement
from mfdhome.render import render_page
from mfdhome.render.alerts import AlertView
from mfdhome.render.controls import Controls
from mfdhome.render.log import event_text, log_rows, page_count, rows_per_page
from mfdhome.server.runtime import Runtime
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import config_page, load_test_config

CONFIG = load_test_config()
ALERTS = CONFIG.alerts.by_id()
T0 = datetime(2026, 10, 14, 13, 58, tzinfo=UTC)
TABLET = Target("tablet", 1280, 768)
RAISED, CLEARED, ACKED = EventKind.RAISED, EventKind.CLEARED, EventKind.ACKED


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def ev(
    minutes: float, kind: EventKind, alert: str | None = None, by: str | None = None
) -> AlertEvent:
    return AlertEvent(at(minutes), kind, alert, by)


def summary(
    events: list[AlertEvent], systems: tuple[str, ...] = ()
) -> list[tuple[float, str, str]]:
    """(minute, alert or kind, event text) per row, newest first."""
    return [
        (
            (r.at - T0).total_seconds() / 60,
            r.alert.id if r.alert else r.kind.value,
            event_text(r),
        )
        for r in log_rows(events, ALERTS, systems)
    ]


#: A morning: a batch (grid lost, battery low), an acknowledgement, a flapping
#: caution, an advisory and a Home Assistant outage.
HISTORY = [
    ev(-1500, RAISED, "wan_down"),
    ev(-1473, CLEARED, "wan_down"),
    ev(0, EventKind.CONNECTION_LOST),
    ev(2, EventKind.CONNECTION_RESTORED),
    ev(4.1, RAISED, "grid_lost"),
    ev(4.15, RAISED, "battery_low"),
    ev(4.2, RAISED, "grid_exporting"),
    ev(7.5, ACKED, "grid_lost", "workshop"),
    *[ev(20 + 2 * i + d, k, "high_wind") for i in range(6) for d, k in ((0, RAISED), (1, CLEARED))],
    ev(40, CLEARED, "grid_exporting"),
    ev(90, CLEARED, "grid_lost"),
]


class TestRows:
    def test_every_change_is_a_row_newest_first(self) -> None:
        assert summary(
            [
                ev(0, RAISED, "grid_lost"),
                ev(3, ACKED, "grid_lost", "tab"),
                ev(9, CLEARED, "grid_lost"),
            ]
        ) == [
            (9, "grid_lost", "CLEARED"),
            (3, "grid_lost", "ACK TAB"),
            (0, "grid_lost", "RAISED"),
        ]

    def test_advisories_read_start_and_end(self) -> None:
        rows = summary([ev(0, RAISED, "grid_exporting"), ev(5, CLEARED, "grid_exporting")])
        assert rows == [(5, "grid_exporting", "END"), (0, "grid_exporting", "START")]

    def test_flapping_collapses_to_one_row(self) -> None:
        rows = summary([e for e in HISTORY if e.alert_id == "high_wind"])
        assert rows == [(31, "high_wind", "CLEARED"), (20, "high_wind", "FLAPPING x6")]

    def test_a_long_gap_is_not_flapping(self) -> None:
        events = [
            ev(0, RAISED, "high_wind"),
            ev(1, CLEARED, "high_wind"),
            ev(7, RAISED, "high_wind"),
        ]
        assert [r[2] for r in summary(events)] == ["RAISED", "CLEARED", "RAISED"]

    def test_acknowledgement_ends_a_run(self) -> None:
        events = [
            ev(0, RAISED, "high_wind"),
            ev(1, CLEARED, "high_wind"),
            ev(2, ACKED, "high_wind", "tab"),
            ev(3, RAISED, "high_wind"),
        ]
        assert [r[2] for r in summary(events)] == ["RAISED", "ACK TAB", "CLEARED", "RAISED"]

    def test_runs_are_per_alert(self) -> None:
        events = []
        for i in range(3):  # two alerts flapping together, interleaved
            events += [
                ev(4 * i, RAISED, "high_wind"),
                ev(4 * i + 1, RAISED, "battery_low"),
                ev(4 * i + 2, CLEARED, "high_wind"),
                ev(4 * i + 3, CLEARED, "battery_low"),
            ]
        assert [r[1:] for r in summary(events)] == [
            ("battery_low", "CLEARED"),
            ("high_wind", "CLEARED"),
            ("battery_low", "FLAPPING x3"),
            ("high_wind", "FLAPPING x3"),
        ]

    def test_system_filter(self) -> None:
        rows = summary(HISTORY, ("GRID",))
        assert {r[1] for r in rows} == {"grid_lost", "grid_exporting"}  # no connection rows
        assert "connection_lost" in {r[1] for r in summary(HISTORY)}

    def test_unknown_alerts_are_skipped(self) -> None:
        assert summary([ev(0, RAISED, "retired_alert")]) == []


class TestPaging:
    LOG = LogElement("log", (40, 56), (920, 480))

    def test_rows_per_page(self) -> None:
        assert rows_per_page(self.LOG) == 19
        assert [page_count(self.LOG, n) for n in (0, 19, 20, 38, 39)] == [1, 1, 2, 2, 3]

    def test_keys_page_the_log_and_reset_on_leaving(self) -> None:
        rt = Runtime(CONFIG)
        rt.history = [ev(10 * i, RAISED if i % 2 == 0 else CLEARED, "grid_lost") for i in range(45)]
        rt.press("workshop", "1", T0)  # PREV from status: the log
        assert rt.selected["workshop"] == "log"
        assert rt.actions("workshop") == (
            Action.PREV,
            Action.PAGE_UP,
            Action.PAGE_DOWN,
            Action.NEXT,
        )
        assert rt.press("workshop", "3", T0) is None  # already newest
        assert rt.press("workshop", "2", T0) is Action.PAGE_UP and rt.log_page["workshop"] == 1
        assert rt.press("workshop", "2", T0) is Action.PAGE_UP and rt.log_page["workshop"] == 2
        assert rt.press("workshop", "2", T0) is None  # 45 rows: three pages
        assert "39-45 OF 45" in rt.render("workshop")
        assert rt.press("workshop", "3", T0) is Action.PAGE_DOWN and rt.log_page["workshop"] == 1
        rt.press("workshop", "4", T0)  # away and back: newest again
        rt.press("workshop", "1", T0)
        assert rt.log_page["workshop"] == 0 and "1-19 OF 45" in rt.render("workshop")


def render(theme: Theme = LCD, page: int = 0, history: list[AlertEvent] = HISTORY) -> str:
    view = AlertView(
        CONFIG.alerts.alerts, CONFIG.alerts.systems, {}, history=history, log_page=page
    )
    keys = Controls(actions=(Action.PREV, Action.PAGE_UP, Action.PAGE_DOWN, Action.NEXT))
    return render_page(config_page("log"), {}, theme, TABLET, view, keys)


class TestRender:
    def test_header_and_rows(self) -> None:
        svg = render()
        assert ">ALL SYSTEMS<" in svg and ">1-12 OF 12<" in svg
        assert ">FLAPPING x6<" in svg and ">ACK WORKSHOP<" in svg and ">CONNECTION LOST<" in svg
        # Dates only where the day changes: today's first row and yesterday's.
        assert re.findall(r">(\d\d-\d\d)<", svg) == ["10-14", "10-13"]

    def test_batches_are_not_split(self) -> None:
        svg = render(
            history=[
                ev(0, RAISED, "grid_lost"),
                ev(0.05, RAISED, "battery_low"),
                ev(9, CLEARED, "grid_lost"),
            ]
        )
        assert svg.count('stroke-width="1"/>') == 2  # the header line, one rule before the batch

    def test_empty_log(self) -> None:
        assert ">NO EVENTS<" in render(history=[])

    def test_page_past_the_end_shows_the_last(self) -> None:
        many = [ev(10 * i, RAISED if i % 2 == 0 else CLEARED, "grid_lost") for i in range(30)]
        assert ">20-30 OF 30<" in render(page=1, history=many)
        assert ">20-30 OF 30<" in render(page=9, history=many)

    def test_caution_text_is_never_pale_yellow(self) -> None:
        svg = render(EINK_COLOR)
        assert re.search(r'<text[^>]*fill="#ffff00"', svg) is None

    @pytest.mark.parametrize("theme", [LCD, MIRROR, EINK_MONO, EINK_COLOR], ids=lambda t: t.name)
    def test_snapshot(self, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
        svg = render(theme)
        assert svg == svg_snapshot
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()
