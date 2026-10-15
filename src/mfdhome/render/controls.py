"""Soft keys: four keys in the bottom strip, two at each end of the banner.

What each key does depends on the page (see ``mfd.keys``); this draws them.
"""

from __future__ import annotations

from dataclasses import dataclass

from mfdhome.layout.anchors import Box
from mfdhome.mfd.keys import DEFAULT_ACTIONS, Action, KeyActions
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font
from mfdhome.symbols.tile import TileLook, attention_group, panel
from mfdhome.themes.theme import Theme

#: Width of each key, in canvas units.
KEY_WIDTH = 100.0
LABELS = {
    Action.PREV: "◀ PREV",
    Action.NEXT: "NEXT ▶",
    Action.ALERTS: "ALERTS",
    Action.LOCK: "LOCK",
    Action.ACK: "ACK",
    Action.PAGE_UP: "▲ PG UP",
    Action.PAGE_DOWN: "▼ PG DN",
}


@dataclass(frozen=True)
class Controls:
    """What the soft keys show.

    ``actions`` is what each key does, left to right. ``alerts`` is the color
    role of the most urgent unacknowledged caution/warning (``None`` when
    there is none): ALERTS or ACK is then lit with the attention cue.
    ``locked`` shows the LOCK key engaged.
    """

    alerts: Status | None = None
    locked: bool = False
    actions: KeyActions = DEFAULT_ACTIONS


def key_boxes(strip: Box) -> tuple[Box, Box, Box, Box]:
    """Each key's box within ``strip``, left to right: two keys at each end."""
    left, top, right, bottom = strip.left, strip.top, strip.right, strip.bottom
    return (
        Box(left, top, left + KEY_WIDTH, bottom),
        Box(left + KEY_WIDTH, top, left + 2 * KEY_WIDTH, bottom),
        Box(right - 2 * KEY_WIDTH, top, right - KEY_WIDTH, bottom),
        Box(right - KEY_WIDTH, top, right, bottom),
    )


def banner_box(strip: Box) -> Box:
    """Where the banner goes when keys are shown: between the inner keys."""
    return Box(strip.left + 2 * KEY_WIDTH, strip.top, strip.right - 2 * KEY_WIDTH, strip.bottom)


def _key(slot: int, box: Box, look: TileLook, label: str, theme: Theme) -> str:
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
    group = attention_group(parts, look.attention, theme)
    return svg.element("g", {"id": f"key-{slot}"}, [group])


def _look(action: Action, controls: Controls) -> TileLook:
    match action:
        case Action.ALERTS | Action.ACK:
            return TileLook(controls.alerts, attention=controls.alerts is not None)
        case Action.LOCK:
            return TileLook(Status.ACTIVE if controls.locked else None)
        case _:
            return TileLook(None)


def soft_keys(strip: Box, controls: Controls, theme: Theme) -> str:
    """Render the four keys into ``strip``, with ids ``key-1`` to ``key-4``.

    Idle keys are dim outlines. ALERTS (or ACK) lights in the alert's color
    with the attention cue; an engaged LOCK lights in the active color and
    reads LOCKED.
    """
    labels = {**LABELS, Action.LOCK: "LOCKED" if controls.locked else "LOCK"}
    return "".join(
        _key(slot, box, _look(action, controls), labels[action], theme)
        for slot, (box, action) in enumerate(
            zip(key_boxes(strip), controls.actions, strict=True), 1
        )
    )
