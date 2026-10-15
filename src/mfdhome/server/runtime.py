"""The live runtime: state in, alert board kept current, displays rendered.

The clock is always passed in, so this is testable without real time; the
server supplies ``datetime.now(UTC)``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from mfdhome.config.load import Config
from mfdhome.mfd.alerts import (
    Board,
    Pending,
    acknowledge,
    apply_holds,
    evaluate_alerts,
    most_urgent,
    step,
)
from mfdhome.mfd.display import Display
from mfdhome.mfd.history import AlertEvent, EventKind, board_events, prune
from mfdhome.model.state import StateSnapshot
from mfdhome.render.alerts import SEVERITY_STATUS, AlertView
from mfdhome.render.controls import Controls
from mfdhome.render.page import render_page
from mfdhome.server.history import HistoryStore
from mfdhome.server.store import BoardStore
from mfdhome.sources.staleness import mark_stale
from mfdhome.themes.builtin import THEMES
from mfdhome.themes.target import Target

logger = logging.getLogger(__name__)

#: How long alert history is kept by default.
HISTORY_DAYS = 14


class Runtime:
    """Holds the current state, the shared alert board, its history and each display's page.

    ``history`` is every event in the last ``keep`` (oldest first), loaded from
    ``history_store`` and appended to it as the board changes.
    """

    def __init__(
        self,
        config: Config,
        store: BoardStore | None = None,
        history_store: HistoryStore | None = None,
        keep: timedelta = timedelta(days=HISTORY_DAYS),
    ) -> None:
        self.config = config
        self.store = store
        self.history_store = history_store
        self.keep = keep
        self.board: Board = store.load() if store else {}
        self.history: list[AlertEvent] = history_store.load() if history_store else []
        self._pruned_on: date | None = None
        self.connected: bool | None = None  # unknown until the first update
        self._was_connected = False
        self.pending: Pending = {}  # alerts waiting out their hold time
        self.state: StateSnapshot = {}
        self.selected = {d.id: d.home for d in config.displays.values()}
        self.locked = dict.fromkeys(config.displays, False)

    @property
    def displays(self) -> dict[str, Display]:
        """Configured displays by id."""
        return dict(self.config.displays)

    def update(self, raw: StateSnapshot, now: datetime, connected: bool = True) -> bool:
        """Take a new snapshot: mark stale entities, step alerts, save the board if it changed.

        Returns whether the board changed. Call it on every HA change and on a
        periodic tick (entities go stale without any event).

        While Home Assistant is disconnected (``connected`` false) the board is
        frozen: every entity reads as unavailable, and stepping would raise or
        clear alerts across the house for a mere network blip. Losing and
        regaining the connection are recorded in the history instead.
        """
        self.state = mark_stale(raw, self.config.defs.stale_after, now)
        # Lost only once it was up; restored only after a loss (not at startup).
        kind = None
        if self.connected and not connected:
            kind = EventKind.CONNECTION_LOST
        elif self.connected is False and connected and self._was_connected:
            kind = EventKind.CONNECTION_RESTORED
        if kind is not None:
            logger.info("Home Assistant %s", kind.value.replace("_", " "))
            self.record([AlertEvent(now, kind)])
        self.connected = connected
        self._was_connected = self._was_connected or connected
        changed = False
        if connected:
            alerts = self.config.alerts.alerts
            raised, self.pending = apply_holds(
                alerts, evaluate_alerts(alerts, self.state), self.board, self.pending, now
            )
            changed = self._set_board(step(self.board, alerts, raised, now), now)
        else:
            self.pending = {}  # after reconnecting, conditions must hold afresh
        self._prune(now)
        return changed

    def acknowledge(
        self, by: str, now: datetime, ids: Iterable[str] | None = None, system: str | None = None
    ) -> bool:
        """Acknowledge ``ids``, a ``system``'s alerts, or (neither given) everything."""
        if system is not None:
            ids = [a.id for a in self.config.alerts.alerts if a.system == system]
        return self._set_board(acknowledge(self.board, by, now, ids), now, by)

    def select(self, display_id: str, page_id: str) -> bool:
        """Show ``page_id`` on a display, if the display offers it."""
        display = self.config.displays.get(display_id)
        if display is None or not display.can_show(page_id):
            return False
        self.selected[display_id] = page_id
        return True

    def press(self, display_id: str, key: str) -> bool:
        """A soft key: ``prev``/``next`` step through pages, ``alerts`` jumps to the
        alerts page, ``lock`` toggles the lock. Returns whether anything changed.

        While locked, only ``lock`` does anything.
        """
        display = self.config.displays.get(display_id)
        if display is None or (self.locked[display_id] and key != "lock"):
            return False
        current = self.selected[display_id]
        match key:
            case "lock":
                self.locked[display_id] = not self.locked[display_id]
                return True
            case "prev" | "next":
                target = display.step(current, -1 if key == "prev" else 1)
            case "alerts":
                target = display.alerts_page
            case _:
                return False
        self.selected[display_id] = target
        return target != current

    def render(self, display_id: str, as_of: str | None = None) -> str:
        """The SVG a display should show now, with an optional "as of" stamp."""
        display = self.config.displays[display_id]
        page = self.config.pages[self.selected[display_id]]
        view = AlertView(
            self.config.alerts.alerts, self.config.alerts.systems, self.board, show_banner=True
        )
        target = Target(display.id, display.width, display.height)
        controls = None
        if display.controls:
            urgent = most_urgent(self.board, self.config.alerts.alerts)
            alert_status = None if urgent is None else SEVERITY_STATUS[urgent.severity]
            controls = Controls(alert_status, self.locked[display_id])
        theme = THEMES[display.theme]
        return render_page(page, self.state, theme, target, view, controls, as_of)

    def record(self, events: list[AlertEvent]) -> None:
        """Add events to the history (and its file)."""
        if not events:
            return
        self.history.extend(events)
        if self.history_store is not None:
            self.history_store.append(events)

    def _prune(self, now: datetime) -> None:
        """Drop history older than ``keep``, at most once a day."""
        if self._pruned_on == now.date():
            return
        self._pruned_on = now.date()
        kept = prune(self.history, now, self.keep)
        if len(kept) != len(self.history):
            self.history = kept
            if self.history_store is not None:
                self.history_store.replace(kept)

    def _set_board(self, board: Board, now: datetime, by: str | None = None) -> bool:
        if board == self.board:
            return False
        known = self.config.alerts.by_id()
        self.record(board_events(self.board, board, now, known, by))
        self.board = board
        if self.store is not None:
            self.store.save(board)
        return True
