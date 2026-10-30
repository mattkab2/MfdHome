"""The alert log: history events as rows, newest first, one page at a time.

Rows are built from the history (pure). Each raise, clear and acknowledgement
is a row; advisories read START and END. An alert that flaps (raised again
within ``FLAP_WINDOW`` of clearing) collapses into one FLAPPING row counting
its raises, so a reading hovering at a threshold can't flood the log; an
acknowledgement of that alert ends the run.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo

from mfdhome.mfd.history import AlertEvent, EventKind
from mfdhome.model.alert import AlertDef, LoggedEntity, Severity, System
from mfdhome.model.binding import Status
from mfdhome.model.page import LogElement
from mfdhome.render.alerts import SEVERITY_STATUS, AlertView
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke, text_at
from mfdhome.themes.theme import Theme

#: A raise this soon after the same alert cleared continues a flapping run.
FLAP_WINDOW = timedelta(minutes=5)
#: Events further apart than this are separated by a rule (batches read as blocks).
BATCH_GAP = timedelta(minutes=1)
ROW_HEIGHT = 24.0
MARK_SIZE = 12.0
CHAR_WIDTH = 0.6  # of the font size: DejaVu Sans Mono's advance
#: Width of the event column (RAISED, ACK <who>, FLAPPING x<n>, a logged state such as
#: ARMED VACATION), in characters.
EVENT_CHARS = 14


@dataclass(frozen=True)
class LogRow:
    """One log line. ``alert`` is ``None`` for connection and state rows; a state
    row (a logged entity's change) has ``entity`` and ``state``.

    ``flaps`` counts the raises merged into a flapping row (1: a plain row);
    ``at`` is then the first raise.
    """

    at: datetime
    kind: EventKind
    alert: AlertDef | None = None
    by: str | None = None
    flaps: int = 1
    entity: LoggedEntity | None = None
    state: str | None = None


@dataclass
class _Run:
    index: int  # the run's RAISED row
    clear: int | None = None  # its latest CLEARED row, while one is pending


def log_rows(
    events: Iterable[AlertEvent],
    alerts: Mapping[str, AlertDef],
    systems: Sequence[str] = (),
    logged: Mapping[str, LoggedEntity] | None = None,
) -> list[LogRow]:
    """History rows, newest first, limited to ``systems`` if given.

    Connection rows only appear in an unfiltered log; events for alerts (or
    logged entities, from ``logged``) no longer defined are skipped.
    """
    rows: list[LogRow | None] = []
    runs: dict[str, _Run] = {}
    for event in sorted(events, key=lambda e: e.at):
        if event.kind is EventKind.STATE:
            entity = (logged or {}).get(event.entity_id or "")
            if entity is not None and (not systems or entity.system in systems):
                rows.append(LogRow(event.at, event.kind, entity=entity, state=event.state))
            continue
        if event.alert_id is None:
            if not systems:
                rows.append(LogRow(event.at, event.kind))
            continue
        alert = alerts.get(event.alert_id)
        if alert is None or (systems and alert.system not in systems):
            continue
        run = runs.get(alert.id)
        match event.kind:
            case EventKind.RAISED if run is not None and run.clear is not None:
                cleared = rows[run.clear]
                assert cleared is not None
                if event.at - cleared.at <= FLAP_WINDOW:
                    rows[run.clear] = None  # flapping: fold the clear and this raise in
                    raised = rows[run.index]
                    assert raised is not None
                    rows[run.index] = replace(raised, flaps=raised.flaps + 1)
                    run.clear = None
                    continue
                rows.append(LogRow(event.at, event.kind, alert))
                runs[alert.id] = _Run(len(rows) - 1)
            case EventKind.RAISED:
                rows.append(LogRow(event.at, event.kind, alert))
                runs[alert.id] = _Run(len(rows) - 1)
            case EventKind.CLEARED:
                rows.append(LogRow(event.at, event.kind, alert))
                if run is not None:
                    run.clear = len(rows) - 1
            case _:
                rows.append(LogRow(event.at, event.kind, alert, event.by))
                runs.pop(alert.id, None)
    return [row for row in reversed(rows) if row is not None]


def rows_per_page(element: LogElement) -> int:
    """How many rows fit below the header line."""
    return max(1, int(element.size[1] // ROW_HEIGHT) - 1)


def page_count(element: LogElement, rows: int) -> int:
    """Pages needed for ``rows`` rows (at least one, even when empty)."""
    return max(1, math.ceil(rows / rows_per_page(element)))


def event_text(row: LogRow) -> str:
    """The action column: what happened."""
    if row.entity is not None:
        return (row.state or "").upper().replace("_", " ")
    if row.alert is None:
        return ""
    if row.flaps > 1:
        return f"FLAPPING x{row.flaps}"
    advisory = row.alert.severity is Severity.ADVISORY
    match row.kind:
        case EventKind.RAISED:
            return "START" if advisory else "RAISED"
        case EventKind.CLEARED:
            return "END" if advisory else "CLEARED"
        case _:
            return f"ACK {row.by.upper()}" if row.by else "ACK"


def _message(row: LogRow) -> tuple[str, str]:
    """(system column, message column)."""
    if row.entity is not None:
        return row.entity.system, row.entity.label
    if row.alert is None:
        lost = row.kind is EventKind.CONNECTION_LOST
        return "HA", "CONNECTION LOST" if lost else "CONNECTION RESTORED"
    return row.alert.system, row.alert.message


def _clip(text: str, chars: int) -> str:
    if chars <= 0:
        return ""
    return text if len(text) <= chars else text[: max(chars - 1, 0)] + "…"


def _text(x: float, y: float, text: str, anchor: str, color: str, theme: Theme) -> str:
    return text_at(x, y, text, theme, theme.font_size, color, anchor=anchor)


def _mark(x: float, y: float, severity: Severity, theme: Theme) -> str:
    """A severity square: filled for warning, outlined (heavier on mono) otherwise."""
    status = SEVERITY_STATUS[severity]
    fill = theme.color(status) if severity is Severity.WARNING else "none"
    half = MARK_SIZE / 2
    return svg.rect(
        x,
        y - half,
        MARK_SIZE,
        MARK_SIZE,
        {"fill": fill, **stroke(status, theme, theme.symbol_stroke_width)},
    )


def _local(when: datetime, tz: tzinfo | None) -> datetime:
    return when.astimezone(tz)


def alert_log(element: LogElement, view: AlertView, theme: Theme) -> str:
    """Render one page (``view.log_page``, 0 = newest) of the log into the element's box."""
    rows = log_rows(view.history, {a.id: a for a in view.alerts}, element.systems, view.logged)
    per_page = rows_per_page(element)
    page = min(max(view.log_page, 0), page_count(element, len(rows)) - 1)
    shown = rows[page * per_page : (page + 1) * per_page]
    left, top = element.at
    right = left + element.size[0]
    char = theme.font_size * CHAR_WIDTH
    # Columns: date, time, mark, system, event (what happened), then the message,
    # which takes the rest of the row.
    x_time = left + 6 * char
    x_mark = x_time + 9 * char
    x_system = x_mark + MARK_SIZE + char
    x_event = x_system + 7 * char
    event_chars = EVENT_CHARS
    x_message = x_event + (event_chars + 1) * char
    message_chars = int((right - x_message) // char)

    header_y = top + ROW_HEIGHT / 2
    scope = " · ".join(_system_label(view.systems, s) for s in element.systems) or "ALL SYSTEMS"
    count = (
        f"{page * per_page + 1}-{page * per_page + len(shown)} OF {len(rows)}"
        if rows
        else "NO EVENTS"
    )
    parts = [
        _text(left, header_y, scope, "start", theme.text_color, theme),
        _text(right, header_y, count, "end", theme.text_color, theme),
        svg.line(
            left,
            top + ROW_HEIGHT,
            right,
            top + ROW_HEIGHT,
            {"stroke": theme.text_color, "stroke-width": 1},
        ),
    ]
    rule = theme.color(Status.UNAVAILABLE)
    previous_date = None
    for i, row in enumerate(shown):
        y = top + ROW_HEIGHT * (i + 1.5)
        local = _local(row.at, view.tz)
        if local.date() != previous_date:
            parts.append(_text(left, y, f"{local:%m-%d}", "start", theme.text_color, theme))
            previous_date = local.date()
        parts.append(_text(x_time, y, f"{local:%H:%M:%S}", "start", theme.text_color, theme))
        system, message = _message(row)
        if row.alert is not None:
            parts.append(_mark(x_mark, y, row.alert.severity, theme))
        if row.alert is not None or row.entity is not None:
            system = _system_label(view.systems, system)
        parts.append(_text(x_system, y, _clip(system, 6), "start", theme.text_color, theme))
        parts.append(
            _text(x_message, y, _clip(message, message_chars), "start", theme.text_color, theme)
        )
        event = event_text(row)
        if event:
            lit = row.alert is not None and (row.kind is EventKind.RAISED or row.flaps > 1)
            color = (
                theme.text_in(SEVERITY_STATUS[row.alert.severity])
                if lit and row.alert is not None
                else theme.text_color
            )
            parts.append(_text(x_event, y, _clip(event, event_chars), "start", color, theme))
        if i + 1 < len(shown) and row.at - shown[i + 1].at > BATCH_GAP:
            rule_y = top + ROW_HEIGHT * (i + 2)
            parts.append(svg.line(left, rule_y, right, rule_y, {"stroke": rule, "stroke-width": 1}))
    return "".join(parts)


def _system_label(systems: Mapping[str, System], system: str) -> str:
    known = systems.get(system)
    return known.label if known is not None else system
