"""Every entity a config refers to, and where."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator

from mfdhome.conditions.model import AnyOf, Rule
from mfdhome.config.load import Config
from mfdhome.model.binding import EntityRef
from mfdhome.model.page import Element, GroupElement, LineElement, SymbolElement


def _in_expr(expr: AnyOf) -> Iterator[str]:
    for term in expr.terms:
        for cond in term.conditions:
            for ref in cond.refs():
                if isinstance(ref, EntityRef):
                    yield ref.entity_id


def _in_rules(rules: Iterable[Rule]) -> Iterator[str]:
    for rule in rules:
        yield from _in_expr(rule.when)


def _in_element(element: Element) -> Iterator[str]:
    if isinstance(element, (SymbolElement, LineElement)):
        yield from (ref.entity_id for ref in element.bind.values() if isinstance(ref, EntityRef))
    if isinstance(element, (SymbolElement, LineElement, GroupElement)):
        yield from _in_rules(element.status.rules)
    if isinstance(element, GroupElement):
        for item in element.items:
            yield from _in_element(item)


def entity_uses(config: Config) -> dict[str, list[str]]:
    """entity_id -> where it is used (``page:element``, ``alert:id``, ``defs:...``)."""
    uses: defaultdict[str, list[str]] = defaultdict(list)
    for page in config.pages.values():
        for element in page.elements:
            for entity_id in _in_element(element):
                uses[entity_id].append(f"{page.id}:{element.id}")
    for alert in config.alerts.alerts:
        for entity_id in _in_expr(alert.condition):
            uses[entity_id].append(f"alert:{alert.id}")
    for name, expr in config.defs.conditions.items():
        for entity_id in _in_expr(expr):
            uses[entity_id].append(f"defs:conditions.{name}")
    for entity_id in config.defs.stale_after.entities:
        uses[entity_id].append("defs:stale_after")
    return {k: sorted(set(v)) for k, v in sorted(uses.items())}
