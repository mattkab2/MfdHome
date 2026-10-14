"""Resolving a line's style for a theme."""

from __future__ import annotations

from dataclasses import dataclass

from mfdhome.model.page import LineElement
from mfdhome.themes.theme import Theme


@dataclass(frozen=True)
class ResolvedLook:
    """Final line appearance for one theme."""

    weight: float
    casing: bool


def resolve_look(element: LineElement, theme: Theme) -> ResolvedLook:
    """Resolve a line's appearance. Later steps override earlier ones:

    1. defaults: weight 1, cased;
    2. the style's base look;
    3. the style's variant for this theme;
    4. the element's own look (its ``weight`` multiplies; ``casing`` replaces);
    5. theme policy, always honored: casing only if allowed, weight capped.

    (Per-display overrides will slot in before step 5 when display
    configurations exist.)
    """
    weight, casing = 1.0, True
    for look in (element.style.base, element.style.themes.get(theme.name)):
        if look is None:
            continue
        weight = look.weight if look.weight is not None else weight
        casing = look.casing if look.casing is not None else casing
    if element.look.weight is not None:
        weight *= element.look.weight
    if element.look.casing is not None:
        casing = element.look.casing
    return ResolvedLook(min(weight, theme.max_line_weight), casing and theme.casing_allowed)
