"""The four bezel keys: what each position does on the current page.

Keys are identified by position (1 to 4, left to right), like physical buttons
whose labels are drawn beside them. Key 1 is always PREV and key 4 always
NEXT, so every page can be left; the middle two depend on the page:

- a page with an alert log: PG UP, PG DN
- the display's alerts page: ACK (ALERTS would go nowhere), LOCK
- any other page: ALERTS, LOCK

A locked display can't change pages, so it can never reach a page without
LOCK while locked, and nobody can lock it there: the lock can't get stuck.
"""

from __future__ import annotations

from enum import StrEnum

from mfdhome.mfd.display import Display

#: Key positions, left to right, as sent by displays.
KEY_SLOTS = ("1", "2", "3", "4")


class Action(StrEnum):
    """What a key does."""

    PREV = "prev"
    NEXT = "next"
    ALERTS = "alerts"
    LOCK = "lock"
    ACK = "ack"
    PAGE_UP = "page_up"  # older log entries
    PAGE_DOWN = "page_down"  # newer log entries


type KeyActions = tuple[Action, Action, Action, Action]

DEFAULT_ACTIONS: KeyActions = (Action.PREV, Action.ALERTS, Action.LOCK, Action.NEXT)


def key_actions(display: Display, page_id: str, paged: bool = False) -> KeyActions:
    """The four keys' actions on ``page_id``; ``paged`` when the page has an alert log."""
    if paged:
        return (Action.PREV, Action.PAGE_UP, Action.PAGE_DOWN, Action.NEXT)
    if page_id == display.alerts_page:
        return (Action.PREV, Action.ACK, Action.LOCK, Action.NEXT)
    return DEFAULT_ACTIONS


def slot_index(key: str) -> int | None:
    """``"1"``..``"4"`` -> 0..3; ``None`` for anything else."""
    return KEY_SLOTS.index(key) if key in KEY_SLOTS else None
