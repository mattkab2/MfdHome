"""Persisting the alert history as JSON Lines: one event per line, appended."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from mfdhome.mfd.history import AlertEvent, EventKind

logger = logging.getLogger(__name__)


def event_to_json(event: AlertEvent) -> dict[str, Any]:
    """One event as plain JSON data (absent fields left out)."""
    data: dict[str, Any] = {"at": event.at.isoformat(), "kind": event.kind.value}
    if event.alert_id is not None:
        data["alert"] = event.alert_id
    if event.by is not None:
        data["by"] = event.by
    if event.entity_id is not None:
        data["entity"] = event.entity_id
    if event.state is not None:
        data["state"] = event.state
    return data


def event_from_json(data: Any) -> AlertEvent:
    """Parse ``event_to_json`` output; raises ``ValueError`` on malformed data."""
    if not isinstance(data, dict):
        raise ValueError("not an object")
    try:
        at = datetime.fromisoformat(data["at"])
        kind = EventKind(data["kind"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing or bad field: {exc}") from exc
    if at.tzinfo is None:
        raise ValueError("timestamp without a time zone")
    texts = [data.get(key) for key in ("alert", "by", "entity", "state")]
    if not all(isinstance(t, str | None) for t in texts):
        raise ValueError("bad alert, by, entity or state")
    alert, by, entity, state = texts
    return AlertEvent(at, kind, alert, by, entity, state)


class HistoryStore:
    """A JSON Lines file of events. Appends are cheap; pruning rewrites atomically."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[AlertEvent]:
        """Every readable event, in file order. Malformed lines are skipped."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError as exc:
            logger.warning("starting with no alert history: cannot read %s: %s", self.path, exc)
            return []
        events = []
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                events.append(event_from_json(json.loads(line)))
            except ValueError as exc:
                logger.warning("ignoring %s line %d: %s", self.path, number, exc)
        return events

    def append(self, events: Iterable[AlertEvent]) -> None:
        """Add events to the end of the file."""
        lines = "".join(json.dumps(event_to_json(e)) + "\n" for e in events)
        if not lines:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(lines)

    def replace(self, events: Iterable[AlertEvent]) -> None:
        """Rewrite the file with exactly ``events`` (used after pruning)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("".join(json.dumps(event_to_json(e)) + "\n" for e in events), "utf-8")
        os.replace(tmp, self.path)
