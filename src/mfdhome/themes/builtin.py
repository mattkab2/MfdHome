"""Built-in themes, one per display type."""

from types import MappingProxyType

from mfdhome.model.binding import Status
from mfdhome.themes import gruvbox
from mfdhome.themes.theme import Attention, AttentionKind, Theme, TileFill

_GRUVBOX_STATUS = MappingProxyType(
    {
        Status.NORMAL: gruvbox.AQUA,
        Status.CAUTION: gruvbox.YELLOW,
        Status.WARNING: gruvbox.RED,
        Status.ACTIVE: gruvbox.BLUE,
        Status.UNAVAILABLE: gruvbox.GRAY,
    }
)
_FONT = "DejaVu Sans Mono, monospace"

#: LCD/LED panels (workshop tablet): Gruvbox dark background, filled lit tiles, 1 Hz flash.
LCD = Theme(
    name="lcd",
    background=gruvbox.BG0_H,
    colors=_GRUVBOX_STATUS,
    text_color=gruvbox.FG,
    dim=gruvbox.BG2,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.FLASH, period=1.0, low_opacity=0.25),
    tile_fill=MappingProxyType(
        {
            Status.WARNING: TileFill.FILLED,
            Status.CAUTION: TileFill.FILLED,
            Status.ACTIVE: TileFill.OUTLINE,
        }
    ),
)

#: Two-way mirror: pure black (anything else lights the glass), thin lines,
#: outlined tiles (no large light areas), slow pulse.
MIRROR = Theme(
    name="mirror",
    background="#000000",
    colors=_GRUVBOX_STATUS,
    text_color=gruvbox.FG,
    dim=gruvbox.BG2,
    line_width=2.0,
    symbol_stroke_width=1.5,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.PULSE, period=2.5, low_opacity=0.35),
    tile_fill=MappingProxyType({}),
    casing_width=6.0,
    casing_wall=1.5,
    max_line_weight=2.0,
)

_BLACK = "#000000"

_WHITE = "#ffffff"

#: Monochrome e-paper: black on white, no animation. Severity is carried by
#: stroke weight and fill: dark tiles are text only (``dim`` is the paper
#: color), advisory a thin outline, caution heavy, warning inverted.
#: Unacknowledged gets a ring.
EINK_MONO = Theme(
    name="eink_mono",
    background=_WHITE,
    colors=MappingProxyType(dict.fromkeys(Status, _BLACK)),
    text_color=_BLACK,
    dim=_WHITE,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.RING),
    tile_fill=MappingProxyType({Status.WARNING: TileFill.FILLED}),
    status_weight=MappingProxyType({Status.CAUTION: 2.0, Status.WARNING: 3.0}),
)

THEMES = MappingProxyType({t.name: t for t in (LCD, MIRROR, EINK_MONO)})
