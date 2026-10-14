"""Soft keys: PREV, ALERTS, LOCK and NEXT in the bottom strip, around the banner."""

from __future__ import annotations

from dataclasses import dataclass

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font
from mfdhome.symbols.tile import TileLook, attention_group, panel
from mfdhome.themes.theme import Theme

#: Width of each key, in canvas units.
KEY_WIDTH = 100.0
#: Key actions in left-to-right order; the banner sits between the second and third.
KEYS = ("prev", "alerts", "lock", "next")
LABELS = {"prev": "◀ PREV", "alerts": "ALERTS", "lock": "LOCK", "next": "NEXT ▶"}


@dataclass(frozen=True)
class Controls:
    """What the soft keys show.

    ``alerts`` is the color role of the most urgent unacknowledged
    caution/warning (``None`` when there is none): the ALERTS key is then lit
    with the attention cue. ``locked`` shows the LOCK key engaged.
    """

    alerts: Status | None = None
    locked: bool = False


def key_boxes(strip: Box) -> dict[str, Box]:
    """Each key's box within ``strip``: two keys at each end."""
    left, top, right, bottom = strip.left, strip.top, strip.right, strip.bottom
    return {
        "prev": Box(left, top, left + KEY_WIDTH, bottom),
        "alerts": Box(left + KEY_WIDTH, top, left + 2 * KEY_WIDTH, bottom),
        "lock": Box(right - 2 * KEY_WIDTH, top, right - KEY_WIDTH, bottom),
        "next": Box(right - KEY_WIDTH, top, right, bottom),
    }


def banner_box(strip: Box) -> Box:
    """Where the banner goes when keys are shown: between the inner keys."""
    return Box(strip.left + 2 * KEY_WIDTH, strip.top, strip.right - 2 * KEY_WIDTH, strip.bottom)


def _key(name: str, box: Box, look: TileLook, label: str, theme: Theme) -> str:
    parts, text_color = panel(box, look, theme, opaque=True, ring=False)
    parts.append(
        svg.element(
            "text",
            {
                "x": box.cx,
                "y": box.cy,
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                **font(theme, theme.font_size, text_color),
            },
            [svg.text(label)],
        )
    )
    return svg.element("g", {"id": f"key-{name}"}, [attention_group(parts, look.attention, theme)])


def soft_keys(strip: Box, controls: Controls, theme: Theme) -> str:
    """Render the four keys into ``strip``.

    Idle keys are dim outlines; ALERTS lights in the alert's color with the
    attention cue; an engaged LOCK lights in the active color and reads LOCKED.
    """
    boxes = key_boxes(strip)
    looks = {
        "prev": TileLook(None),
        "alerts": TileLook(controls.alerts, attention=controls.alerts is not None),
        "lock": TileLook(Status.ACTIVE if controls.locked else None),
        "next": TileLook(None),
    }
    labels = {**LABELS, "lock": "LOCKED" if controls.locked else "LOCK"}
    return "".join(_key(name, boxes[name], looks[name], labels[name], theme) for name in KEYS)
