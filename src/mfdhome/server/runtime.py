"""The live runtime: state in, alert board kept current, displays rendered.

The clock is always passed in, so this is testable without real time; the
server supplies ``datetime.now(UTC)``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from mfdhome.config.load import Config
from mfdhome.mfd.alerts import Board, acknowledge, evaluate_alerts, step
from mfdhome.mfd.display import Display
from mfdhome.model.state import StateSnapshot
from mfdhome.render.alerts import AlertView
from mfdhome.render.page import render_page
from mfdhome.server.store import BoardStore
from mfdhome.sources.staleness import mark_stale
from mfdhome.themes.builtin import THEMES
from mfdhome.themes.target import Target

logger = logging.getLogger(__name__)


class Runtime:
    """Holds the current state, the shared alert board and each display's page."""

    def __init__(self, config: Config, store: BoardStore | None = None) -> None:
        self.config = config
        self.store = store
        self.board: Board = store.load() if store else {}
        self.state: StateSnapshot = {}
        self.selected = {d.id: d.home for d in config.displays.values()}

    @property
    def displays(self) -> dict[str, Display]:
        """Configured displays by id."""
        return dict(self.config.displays)

    def update(self, raw: StateSnapshot, now: datetime) -> bool:
        """Take a new snapshot: mark stale entities, step alerts, save the board if it changed.

        Returns whether the board changed. Call it on every HA change and on a
        periodic tick (entities go stale without any event).
        """
        self.state = mark_stale(raw, self.config.defs.stale_after, now)
        alerts = self.config.alerts.alerts
        return self._set_board(step(self.board, alerts, evaluate_alerts(alerts, self.state), now))

    def acknowledge(
        self, by: str, now: datetime, ids: Iterable[str] | None = None, system: str | None = None
    ) -> bool:
        """Acknowledge ``ids``, a ``system``'s alerts, or (neither given) everything."""
        if system is not None:
            ids = [a.id for a in self.config.alerts.alerts if a.system == system]
        return self._set_board(acknowledge(self.board, by, now, ids))

    def select(self, display_id: str, page_id: str) -> bool:
        """Show ``page_id`` on a display, if the display offers it."""
        display = self.config.displays.get(display_id)
        if display is None or not display.can_show(page_id):
            return False
        self.selected[display_id] = page_id
        return True

    def render(self, display_id: str) -> str:
        """The SVG a display should show now."""
        display = self.config.displays[display_id]
        page = self.config.pages[self.selected[display_id]]
        view = AlertView(
            self.config.alerts.alerts, self.config.alerts.systems, self.board, show_banner=True
        )
        target = Target(display.id, display.width, display.height)
        return render_page(page, self.state, THEMES[display.theme], target, view)

    def _set_board(self, board: Board) -> bool:
        if board == self.board:
            return False
        self.board = board
        if self.store is not None:
            self.store.save(board)
        return True
