"""Display configuration: what a physical display shows and how."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Display:
    """A physical display.

    It shows one page at a time, chosen by the viewer from ``pages`` (which
    always includes ``home``). A display with a single page, such as a mirror,
    is fixed to it. ``theme`` names a built-in theme; ``width``/``height`` are
    its pixel size. Displays with more than one page have the four keys
    (``controls``); ALERTS jumps to ``alerts_page``. A display with a ``panel`` (an e-paper
    panel profile name) is served as PNG snapshots quantized to that panel.
    """

    id: str
    theme: str
    width: int
    height: int
    home: str
    pages: tuple[str, ...]
    alerts_page: str = ""
    panel: str | None = None

    @property
    def controls(self) -> bool:
        """Whether the display has keys: only when there is a page to change to."""
        return len(self.pages) > 1

    def step(self, current: str, delta: int) -> str:
        """The page ``delta`` places from ``current`` in ``pages``, wrapping."""
        index = self.pages.index(current) if current in self.pages else 0
        return self.pages[(index + delta) % len(self.pages)]

    def can_show(self, page_id: str) -> bool:
        """Whether a viewer may select ``page_id`` on this display."""
        return page_id in self.pages
