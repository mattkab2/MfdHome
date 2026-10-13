"""Display targets: output size for a rendered page."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """A display target. Pages are scaled from their logical canvas to this size."""

    name: str
    width_px: int
    height_px: int
