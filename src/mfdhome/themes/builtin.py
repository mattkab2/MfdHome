"""Built-in themes, one per display type (three for e-paper: mono, gray and six-color)."""

from mfdhome.model.binding import Status
from mfdhome.themes import gruvbox
from mfdhome.themes.theme import Attention, AttentionKind, Theme, TileFill

_GRUVBOX_STATUS = {
    Status.NORMAL: gruvbox.AQUA,
    Status.CAUTION: gruvbox.YELLOW,
    Status.WARNING: gruvbox.RED,
    Status.ACTIVE: gruvbox.BLUE,
    Status.UNAVAILABLE: gruvbox.GRAY,
}

_FONT = "DejaVu Sans Mono, monospace"

#: LCD/LED panels (workshop tablet): Gruvbox dark background, filled lit tiles, 1 Hz flash.
LCD = Theme(
    name="lcd",
    background=gruvbox.BG0_H,
    colors=_GRUVBOX_STATUS,
    text_color=gruvbox.FG,
    dim=gruvbox.BG2,
    structure=gruvbox.BG4,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.FLASH, period=1.0, low_opacity=0.25),
    tile_fill={
        Status.WARNING: TileFill.FILLED,
        Status.CAUTION: TileFill.FILLED,
        Status.ACTIVE: TileFill.OUTLINE,
    },
)

#: Two-way mirror: pure black (anything else lights the glass), thin lines,
#: outlined tiles (no large light areas), slow pulse.
MIRROR = Theme(
    name="mirror",
    background="#000000",
    colors=_GRUVBOX_STATUS,
    text_color=gruvbox.FG,
    dim=gruvbox.BG2,
    structure=gruvbox.BG4,
    line_width=2.0,
    symbol_stroke_width=1.5,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.PULSE, period=2.5, low_opacity=0.35),
    tile_fill={},
    casing_width=8.0,
    casing_wall=1.5,
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
    colors=dict.fromkeys(Status, _BLACK),
    text_color=_BLACK,
    dim=_WHITE,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.RING),
    tile_fill={Status.WARNING: TileFill.FILLED},
    status_weight={Status.CAUTION: 2.0, Status.WARNING: 3.0},
)

_GRAY_DARK = "#555555"
_GRAY_LIGHT = "#aaaaaa"

#: Grayscale e-paper (4 or 16 levels): eink_mono's severity cues (stroke weight,
#: fill, line patterns), with structure (walls, rooms, stairs, cabinets) and no
#: data in dark gray and dim things (unlit tiles, quiet frames) in light gray,
#: so they recede as on the LCD. Both grays are exact levels of 4- and 16-gray
#: panels, so nothing depends on quantization.
EINK_GRAY = Theme(
    name="eink_gray",
    background=_WHITE,
    colors={**dict.fromkeys(Status, _BLACK), Status.UNAVAILABLE: _GRAY_DARK},
    text_color=_BLACK,
    dim=_GRAY_LIGHT,
    structure=_GRAY_DARK,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.RING),
    tile_fill={Status.WARNING: TileFill.FILLED},
    status_weight={Status.CAUTION: 2.0, Status.WARNING: 3.0},
)

#: Spectra 6 inks, by their nominal colors (what the panel controller expects).
_INK_RED = "#ff0000"
_INK_YELLOW = "#ffff00"
_INK_BLUE = "#0000ff"
_INK_GREEN = "#00ff00"

#: Six-color e-paper (Spectra 6): the Gruvbox roles drawn in the panel's own
#: inks on white, so nothing depends on nearest-color quantization. There is
#: no gray ink: unavailable is black, told apart by its dotted pattern.
#: Yellow is too pale for text on paper: filled caution tiles carry black
#: text, and outlined (cleared) caution tiles use black text.
EINK_COLOR = Theme(
    name="eink_color",
    background=_WHITE,
    colors={
        Status.NORMAL: _INK_GREEN,
        Status.CAUTION: _INK_YELLOW,
        Status.WARNING: _INK_RED,
        Status.ACTIVE: _INK_BLUE,
        Status.UNAVAILABLE: _BLACK,
    },
    text_color=_BLACK,
    dim=_WHITE,
    line_width=3.0,
    symbol_stroke_width=2.0,
    unavailable_dots="0 6",
    font_family=_FONT,
    font_size=16.0,
    label_font_size=20.0,
    attention=Attention(AttentionKind.RING),
    tile_fill={
        Status.WARNING: TileFill.FILLED,
        Status.CAUTION: TileFill.FILLED,
        Status.ACTIVE: TileFill.FILLED,
    },
    status_weight={Status.CAUTION: 1.5, Status.WARNING: 1.5},
    filled_text={Status.CAUTION: _BLACK},
    faint=frozenset({Status.CAUTION}),
)

THEMES = {t.name: t for t in (LCD, MIRROR, EINK_MONO, EINK_GRAY, EINK_COLOR)}
