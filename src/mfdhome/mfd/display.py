"""Display configuration: what a physical display shows and how."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Display:
    """A physical display.

    It shows one page at a time, chosen by the viewer from ``pages`` (which
    always includes ``home``). A display with a single page, such as a mirror,
    is fixed to it. ``theme`` names a built-in theme; ``width``/``height`` are
    its pixel size. ``controls`` draws the soft keys (PREV, ALERTS, LOCK, NEXT);
    ALERTS jumps to ``alerts_page``.
    """

    id: str
    theme: str
    width: int
    height: int
    home: str
    pages: tuple[str, ...]
    controls: bool = False
    alerts_page: str = ""

    def step(self, current: str, delta: int) -> str:
        """The page ``delta`` places from ``current`` in ``pages``, wrapping."""
        index = self.pages.index(current) if current in self.pages else 0
        return self.pages[(index + delta) % len(self.pages)]

    def can_show(self, page_id: str) -> bool:
        """Whether a viewer may select ``page_id`` on this display."""
        return page_id in self.pages
