"""The live runtime: state in, alert board and history kept current, keys handled,
displays rendered.

The clock is always passed in, so this is testable without real time; the
server supplies ``datetime.now(UTC)``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from mfdhome.config.inventory import entity_uses
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
from mfdhome.mfd.history import AlertEvent, EventKind, board_events, prune, state_events
from mfdhome.mfd.keys import Action, KeyActions, key_actions, slot_index
from mfdhome.model.page import LogElement
from mfdhome.model.state import StateSnapshot
from mfdhome.render.alerts import SEVERITY_STATUS, AlertView
from mfdhome.render.controls import Controls
from mfdhome.render.log import log_rows, page_count
from mfdhome.render.page import render_page
from mfdhome.server.history import HistoryStore
from mfdhome.server.store import BoardStore
from mfdhome.sources.averaging import Samples, averaged
from mfdhome.sources.staleness import mark_stale
from mfdhome.themes.builtin import THEMES
from mfdhome.themes.target import Target

logger = logging.getLogger(__name__)

#: How long alert history is kept by default.
HISTORY_DAYS = 14


class Runtime:
    """Holds the current state, the shared alert board, its history, each display's
    page, and recent samples for displays that show averages.

    ``history`` is every event in the last ``keep`` (oldest first), loaded from
    ``history_store`` and appended to it as the board changes. Log times are
    shown in ``tz`` (``None``: the machine's local time).
    """

    def __init__(
        self,
        config: Config,
        store: BoardStore | None = None,
        history_store: HistoryStore | None = None,
        keep: timedelta = timedelta(days=HISTORY_DAYS),
        tz: tzinfo | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.history_store = history_store
        self.keep = keep
        self.tz = tz
        self.board: Board = store.load() if store else {}
        self.history: list[AlertEvent] = history_store.load() if history_store else []
        self._pruned_on: date | None = None
        self.connected: bool | None = None  # unknown until the first update
        self._was_connected = False
        self.pending: Pending = {}  # alerts waiting out their hold time
        self._logged: dict[str, str] = {}  # last states of logged entities
        self.state: StateSnapshot = {}
        self.updated_at: datetime | None = None
        windows = [d.average for d in config.displays.values() if d.average is not None]
        # Recent values, for displays that show averages (only the entities in use).
        self.samples = Samples(max(windows), entity_uses(config)) if windows else None
        self.selected = {d.id: d.home for d in config.displays.values()}
        self.locked = dict.fromkeys(config.displays, False)
        self.log_page = dict.fromkeys(config.displays, 0)  # 0: newest; reset on page change

    @property
    def displays(self) -> dict[str, Display]:
        """Configured displays by id."""
        return dict(self.config.displays)

    def update(self, raw: StateSnapshot, now: datetime, connected: bool = True) -> bool:
        """Take a new snapshot: mark stale entities, record samples for averaging, step
        alerts, and save the board if it changed.

        Returns whether the board changed. Call it on every HA change and on a
        periodic tick (entities go stale without any event).

        While Home Assistant is disconnected (``connected`` false) the board is
        frozen: every entity reads as unavailable, and stepping would raise or
        clear alerts across the house for a mere network blip. Losing and
        regaining the connection are recorded in the history instead.
        """
        self.state = mark_stale(raw, self.config.defs.stale_after, now)
        self.updated_at = now
        if self.samples is not None:
            self.samples.record(self.state, now)
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
            logged, self._logged = state_events(
                self._logged, self.state, self.config.alerts.logged, now
            )
            self.record(logged)
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

    def acknowledge_banner(self, by: str, now: datetime) -> bool:
        """Acknowledge the alert the banner names (the most urgent caution/warning)."""
        urgent = most_urgent(self.board, self.config.alerts.alerts)
        return urgent is not None and self.acknowledge(by, now, ids=[urgent.id])

    def select(self, display_id: str, page_id: str) -> bool:
        """Show ``page_id`` on a display, if the display offers it.

        Displays change pages with their keys; this is for one-off renders
        (``mfdhome render --page``).
        """
        display = self.config.displays.get(display_id)
        if display is None or not display.can_show(page_id):
            return False
        self._show(display_id, page_id)
        return True

    def _show(self, display_id: str, page_id: str) -> None:
        if page_id != self.selected[display_id]:
            self.log_page[display_id] = 0  # a log always opens on its newest entries
        self.selected[display_id] = page_id

    def _log(self, display_id: str) -> LogElement | None:
        """The alert log on the display's current page, if it has one."""
        page = self.config.pages[self.selected[display_id]]
        return next((e for e in page.elements if isinstance(e, LogElement)), None)

    def actions(self, display_id: str) -> KeyActions:
        """What each key does on the display's current page."""
        display = self.config.displays[display_id]
        paged = self._log(display_id) is not None
        return key_actions(display, self.selected[display_id], paged)

    def _turn_log(self, display_id: str, delta: int) -> bool:
        """Move the log ``delta`` pages older (positive) or newer, within its pages."""
        log = self._log(display_id)
        if log is None:
            return False
        alerts = self.config.alerts.by_id()
        logged = {e.entity_id: e for e in self.config.alerts.logged}
        pages = page_count(log, len(log_rows(self.history, alerts, log.systems, logged)))
        current = self.log_page[display_id]
        target = min(max(current + delta, 0), pages - 1)
        self.log_page[display_id] = target
        return target != current

    def press(self, display_id: str, key: str, now: datetime) -> Action | None:
        """Press key ``key`` (position ``"1"`` to ``"4"``) on a display.

        PREV/NEXT step through pages, ALERTS jumps to the alerts page, ACK
        acknowledges the alert the banner names, PG UP/PG DN page the alert
        log, LOCK toggles the lock; while locked, only LOCK does anything.
        Returns the action if it changed something.
        """
        display = self.config.displays.get(display_id)
        slot = slot_index(key)
        if display is None or slot is None:
            return None
        action = self.actions(display_id)[slot]
        if self.locked[display_id] and action is not Action.LOCK:
            return None
        current = self.selected[display_id]
        match action:
            case Action.LOCK:
                self.locked[display_id] = not self.locked[display_id]
                return action
            case Action.ACK:
                return action if self.acknowledge_banner(display_id, now) else None
            case Action.PREV | Action.NEXT:
                target = display.step(current, -1 if action is Action.PREV else 1)
            case Action.ALERTS:
                target = display.alerts_page
            case Action.PAGE_UP | Action.PAGE_DOWN:
                turned = self._turn_log(display_id, 1 if action is Action.PAGE_UP else -1)
                return action if turned else None
            case _:
                return None
        self._show(display_id, target)
        return action if target != current else None

    def view(self, display_id: str, now: datetime | None = None) -> StateSnapshot:
        """The state a display shows at ``now`` (default: the last update): live, or
        averaged over the display's window."""
        display = self.config.displays[display_id]
        now = now or self.updated_at
        if display.average is None or self.samples is None or now is None:
            return self.state
        policy = self.config.defs.averaging
        return averaged(self.state, self.samples, display.average, now, policy)

    def render(self, display_id: str, as_of: str | None = None, now: datetime | None = None) -> str:
        """The SVG a display should show at ``now`` (default: the last update), with an
        optional "as of" stamp."""
        display = self.config.displays[display_id]
        page = self.config.pages[self.selected[display_id]]
        view = AlertView(
            self.config.alerts.alerts,
            self.config.alerts.systems,
            self.board,
            history=self.history,
            logged={e.entity_id: e for e in self.config.alerts.logged},
            log_page=self.log_page[display_id],
            tz=self.tz,
        )
        target = Target(display.id, display.width, display.height)
        controls = None
        if display.controls:
            urgent = most_urgent(self.board, self.config.alerts.alerts)
            alert_status = None if urgent is None else SEVERITY_STATUS[urgent.severity]
            controls = Controls(alert_status, self.locked[display_id], self.actions(display_id))
        theme = THEMES[display.theme]
        state = self.view(display_id, now)
        return render_page(page, state, theme, target, view, controls, as_of, display.annunciator)

    def signature(self, display_id: str) -> tuple[object, ...]:
        """What a display's image depends on besides measurements: the page, its lock
        and log page, the alert board and the history (alerts, acknowledgements,
        connection events). E-paper images are redrawn as soon as it changes."""
        return (
            self.selected[display_id],
            self.locked[display_id],
            self.log_page[display_id],
            tuple(sorted(self.board.items(), key=lambda item: item[0])),
            len(self.history),
        )

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
