"""Persisting the shared alert board, so latched alerts survive restarts."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from mfdhome.mfd.alerts import AlertState, Board, Phase

logger = logging.getLogger(__name__)


def _time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse_time(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def board_to_json(board: Board) -> dict[str, Any]:
    """The board as plain JSON data."""
    return {
        alert_id: {
            "phase": state.phase.value,
            "since": _time(state.since),
            "acked_by": state.acked_by,
            "acked_at": _time(state.acked_at),
        }
        for alert_id, state in sorted(board.items())
    }


def board_from_json(data: Any) -> Board:
    """Parse ``board_to_json`` output; malformed entries are skipped."""
    board = {}
    for alert_id, raw in (data or {}).items() if isinstance(data, dict) else ():
        try:
            board[alert_id] = AlertState(
                Phase(raw["phase"]),
                _parse_time(raw.get("since")),
                raw.get("acked_by"),
                _parse_time(raw.get("acked_at")),
            )
        except KeyError, TypeError, ValueError:
            logger.warning("ignoring malformed board entry %r", alert_id)
    return board


class BoardStore:
    """A JSON file holding the board. Writes are atomic (temp file, then rename)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> Board:
        """The saved board, or an empty one if there is none or it is unreadable."""
        try:
            return board_from_json(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning("starting with an empty alert board: cannot read %s: %s", self.path, exc)
            return {}

    def save(self, board: Board) -> None:
        """Write the board."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(board_to_json(board), indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
