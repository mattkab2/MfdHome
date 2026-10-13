"""Static fixture source: load a recorded HA state snapshot from JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mfdhome.model.state import StateSnapshot, snapshot_from_ha_states

logger = logging.getLogger(__name__)


def load_fixture(path: str | Path) -> StateSnapshot:
    """Load a JSON file in the HA ``/api/states`` shape (a list of state objects)."""
    with Path(path).open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of HA state objects")
    snapshot = snapshot_from_ha_states(data)
    logger.debug("loaded %d entities from %s", len(snapshot), path)
    return snapshot
