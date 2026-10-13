"""Dark theme: pure black background with thin bright lines (mirror-safe)."""

from types import MappingProxyType

from mfdhome.model.binding import Status
from mfdhome.themes.theme import Theme

DARK = Theme(
    name="dark",
    background="#000000",
    colors=MappingProxyType(
        {
            Status.NORMAL: "#00e060",
            Status.CAUTION: "#ffb000",
            Status.WARNING: "#ff3030",
            Status.ACTIVE: "#00d8ff",
            Status.UNAVAILABLE: "#707070",
        }
    ),
    text_color="#e0e0e0",
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dash="8 6",
    font_family="DejaVu Sans Mono, monospace",
    font_size=16.0,
    label_font_size=20.0,
    allow_animation=False,
)
