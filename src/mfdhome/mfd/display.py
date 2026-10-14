"""Display configuration: what a physical display shows and how."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Display:
    """A physical display.

    It shows one page at a time, chosen by the viewer from ``pages`` (which
    always includes ``home``). A display with a single page, such as a mirror,
    is fixed to it. ``theme`` names a built-in theme; ``width``/``height`` are
    its pixel size.
    """

    id: str
    theme: str
    width: int
    height: int
    home: str
    pages: tuple[str, ...]

    def can_show(self, page_id: str) -> bool:
        """Whether a viewer may select ``page_id`` on this display."""
        return page_id in self.pages
