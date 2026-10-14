"""E-paper panel profiles: the exact colors a panel can show.

Rasterization quantizes every pixel to one of these colors, without
dithering (dither noise makes thin lines and small text unreadable). Themes
for a panel should draw in these colors directly, so only edge pixels are
quantized; nearest-color mapping of arbitrary colors is not reliable (Gruvbox
aqua is closer to white than to green).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mfdhome.themes.theme import Theme

type RGB = tuple[int, int, int]


def hex_rgb(color: str) -> RGB:
    """``"#rrggbb"`` -> ``(r, g, b)``."""
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"expected #rrggbb, got {color!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


@dataclass(frozen=True)
class PanelProfile:
    """A panel's palette.

    ``antialias`` is whether edges may be smoothed before quantizing: worth it
    on gray panels, harmful on panels without intermediate tones (edges would
    snap to unrelated colors, e.g. green fringes between black and yellow).
    """

    name: str
    colors: tuple[str, ...]
    antialias: bool

    def rgb(self) -> tuple[RGB, ...]:
        """The palette as RGB triples, in order."""
        return tuple(hex_rgb(c) for c in self.colors)

    def unsupported(self, theme: Theme) -> frozenset[str]:
        """Colors ``theme`` may draw that this panel cannot show."""
        own = {c.lower() for c in self.colors}
        return frozenset(c for c in theme.palette() if c.lower() not in own)


def _grays(levels: int) -> tuple[str, ...]:
    step = 255 // (levels - 1)
    return tuple(f"#{v:02x}{v:02x}{v:02x}" for v in range(0, 256, step))


MONO = PanelProfile("mono", ("#000000", "#ffffff"), antialias=False)
GRAY4 = PanelProfile("gray4", _grays(4), antialias=True)
GRAY16 = PanelProfile("gray16", _grays(16), antialias=True)
#: Spectra 6 panels take the six nominal colors; the controller maps them to its inks.
SPECTRA6 = PanelProfile(
    "spectra6",
    ("#000000", "#ffffff", "#ff0000", "#ffff00", "#0000ff", "#00ff00"),
    antialias=False,
)

PANELS: Mapping[str, PanelProfile] = {p.name: p for p in (MONO, GRAY4, GRAY16, SPECTRA6)}
