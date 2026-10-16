"""Turn validated schema models into frozen model objects, with context checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError

from mfdhome.conditions.model import (
    TRUE,
    AnyOf,
    ChannelRef,
    Condition,
    Op,
    RefOperand,
    Rule,
    ValueRef,
)
from mfdhome.conditions.sugar import Thresholds, state_map_rules
from mfdhome.config.errors import Issues, Loc
from mfdhome.config.schema import (
    AlertModel,
    AlertsModel,
    DefsModel,
    DerivedModel,
    DisplaysModel,
    ExprModel,
    GroupModel,
    LineModel,
    LogModel,
    NameModel,
    NodeModel,
    PageModel,
    ReadoutModel,
    StaleModel,
    StatusModel,
    SymbolModel,
    TermModel,
    TextModel,
    ThresholdsModel,
    TileGridModel,
    TileModel,
)
from mfdhome.layout.anchors import Anchor, anchor_names, parse_anchor
from mfdhome.layout.grid import grid_centers
from mfdhome.layout.path import Point
from mfdhome.layout.route import Elbow, Port, route
from mfdhome.mfd.display import Display
from mfdhome.model.alert import AlertDef, Severity, System
from mfdhome.model.binding import ElementRef, EntityRef, Status
from mfdhome.model.page import (
    Aggregate,
    DerivedChannel,
    Element,
    FlowSpec,
    Frame,
    GridLayout,
    GroupElement,
    LineElement,
    LogElement,
    Name,
    NodeElement,
    Orientation,
    Page,
    Readout,
    StatusSpec,
    SymbolElement,
    TextElement,
    TileElement,
)
from mfdhome.model.state import StalePolicy
from mfdhome.render.panels import PANELS
from mfdhome.symbols.format import FORMATS, is_valid_format
from mfdhome.symbols.geometry import element_box, find_port
from mfdhome.symbols.registry import LINE_CHANNELS, LINE_PRIMARY, REGISTRY
from mfdhome.themes.builtin import THEMES


@dataclass(frozen=True)
class Defs:
    """Resolved shared definitions."""

    thresholds: Mapping[str, Thresholds] = field(default_factory=dict)
    conditions: Mapping[str, AnyOf] = field(default_factory=dict)
    stale_after: StalePolicy = field(default_factory=StalePolicy)

    def merge(self, other: Defs) -> tuple[Defs, list[str]]:
        """Combine two sets of defs; returns the result and any duplicated names."""
        kinds = ("thresholds", "conditions")
        dupes = sorted(
            f"{kind}.{name}"
            for kind in kinds
            for name in getattr(self, kind).keys() & getattr(other, kind).keys()
        )
        merged = Defs(
            thresholds={**self.thresholds, **other.thresholds},
            conditions={**self.conditions, **other.conditions},
            stale_after=self.stale_after,
        )
        return merged, dupes


def validate[M: BaseModel](model: type[M], data: Any, loc: Loc, issues: Issues) -> M | None:
    """Validate ``data`` against ``model``, recording errors under ``loc``."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            message = str(err["msg"]).removeprefix("Value error, ")
            issues.add(loc + tuple(err["loc"]), message)
        return None


def _thresholds(model: ThresholdsModel) -> Thresholds:
    return Thresholds(model.warning_low, model.caution_low, model.caution_high, model.warning_high)


def _channels(expr: AnyOf) -> Iterator[str]:
    for term in expr.terms:
        for cond in term.conditions:
            for ref in cond.refs():
                if isinstance(ref, ChannelRef):
                    yield ref.channel


# --- conditions -------------------------------------------------------------------------------


type Bound = Mapping[str, object] | None

#: ``bound`` value for contexts that have no channels at all (alerts).
NO_CHANNELS: Mapping[str, object] = {}


class _Exprs:
    """Builds DNF expressions, resolving ``use`` against named conditions.

    ``bound`` is the evaluating element's channels; when given, channel
    references are checked against it where they are written (or at the
    ``use`` site for named conditions). Named conditions themselves are built
    with ``bound=None``, since they may be used by several elements.
    ``NO_CHANNELS`` marks contexts without channels (alerts).
    """

    def __init__(
        self,
        named: Mapping[str, ExprModel],
        resolved: Mapping[str, AnyOf],
        issues: Issues,
        prefix: Loc = (),
    ) -> None:
        self.named = named
        self.resolved = dict(resolved)
        self.issues = issues
        self.prefix = prefix
        self.resolving: list[str] = []

    def use(self, name: str, loc: Loc, bound: Bound = None) -> AnyOf:
        expr = self._resolve(name, loc)
        if bound is None:
            return expr
        why = "; alerts can only use 'entity'" if bound is NO_CHANNELS else ", which is not bound"
        for channel in sorted(set(_channels(expr)) - bound.keys()):
            self.issues.add(loc, f"condition {name!r} uses channel {channel!r}{why}")
        return expr

    def _resolve(self, name: str, loc: Loc) -> AnyOf:
        if name in self.resolved:
            return self.resolved[name]
        if name not in self.named:
            self.issues.add(loc, f"unknown condition {name!r}")
            return AnyOf()
        if name in self.resolving:
            chain = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            self.issues.add(loc, f"condition cycle: {chain}")
            return AnyOf()
        self.resolving.append(name)
        expr = self.expr(self.named[name], (*self.prefix, "conditions", name))
        self.resolving.pop()
        self.resolved[name] = expr
        return expr

    def value_ref(
        self, channel: str | None, entity: str | None, attribute: str | None, loc: Loc, bound: Bound
    ) -> ValueRef:
        """A channel or entity reference, checking the channel is bound where it's used."""
        if channel is None:
            return EntityRef(str(entity), attribute)
        if bound is NO_CHANNELS:
            self.issues.add((*loc, "channel"), "alerts have no channels; use 'entity'")
        elif bound is not None and channel not in bound:
            self.issues.add((*loc, "channel"), f"channel {channel!r} is not bound")
        return ChannelRef(channel)

    def condition(self, term: TermModel, loc: Loc, bound: Bound) -> AnyOf:
        ref = self.value_ref(term.channel, term.entity, term.attribute, loc, bound)
        [(op, operand)] = term.predicates().items()
        if isinstance(operand, list):
            operand = tuple(operand)
        elif isinstance(operand, dict):  # compare against another value
            other = self.value_ref(
                operand.get("channel"),
                operand.get("entity"),
                operand.get("attribute"),
                (*loc, op),
                bound,
            )
            operand = RefOperand(other, operand.get("offset", 0.0))
        return AnyOf.single(Condition(ref, Op(op), operand))

    def _term(self, term: TermModel, loc: Loc, bound: Bound) -> AnyOf:
        """One item of a ``when``/``all`` list: a condition or a ``use``."""
        if term.use is not None:
            return self.use(term.use, (*loc, "use"), bound)
        return self.condition(term, loc, bound)

    def conjunction(self, terms: list[TermModel], loc: Loc, bound: Bound = None) -> AnyOf:
        result = TRUE
        for i, term in enumerate(terms):
            if term.all_ is not None:
                self.issues.add(
                    (*loc, i, "all"), "'all' groups are only allowed directly under 'any'"
                )
            else:
                result = result.and_(self._term(term, (*loc, i), bound))
        return result

    def expr(self, model: ExprModel, loc: Loc, bound: Bound = None) -> AnyOf:
        if model.when is not None:
            return self.conjunction(model.when, (*loc, "when"), bound)
        result = AnyOf()
        for i, term in enumerate(model.any_ or ()):
            item = (*loc, "any", i)
            if term.all_ is not None:
                result = result.or_(self.conjunction(term.all_, (*item, "all"), bound))
            else:
                result = result.or_(self._term(term, item, bound))
        return result


def build_defs(
    model: DefsModel, issues: Issues, base: Defs | None = None, prefix: Loc = ("defs",)
) -> Defs:
    """Resolve a defs model; named conditions may ``use`` each other and ``base`` conditions.

    ``prefix`` is where the defs sit in their file: under ``defs`` in a page,
    at the top level of a shared defs file.
    """
    base = base or Defs()
    exprs = _Exprs(model.conditions, base.conditions, issues, prefix)
    conditions = {name: exprs.use(name, (*prefix, "conditions", name)) for name in model.conditions}
    thresholds = {name: _thresholds(t) for name, t in model.thresholds.items()}
    stale = model.stale_after or StaleModel()
    return Defs(thresholds, conditions, StalePolicy(stale.default, stale.entities))


# --- elements ---------------------------------------------------------------------------------


def _anchor(name: str | None, loc: Loc, issues: Issues) -> Anchor | None:
    if name is None:
        return None
    try:
        return parse_anchor(name)
    except ValueError:
        issues.add(loc, f"unknown anchor {name!r}; expected one of: {', '.join(anchor_names())}")
        return None


type Endpoint = tuple[float, float] | str


@dataclass(frozen=True)
class _PendingLine:
    """A line whose ``from``/``to`` endpoints are resolved after every element is built."""

    id: str
    start: Endpoint
    via: tuple[Point, ...]
    end: Endpoint
    loc: Loc
    straight: bool = False
    elbow: Elbow | None = None


class _ElementBuilder:
    def __init__(self, defs: Defs, alerts: Alerts, issues: Issues) -> None:
        self.pending: list[_PendingLine] = []
        self.defs = defs
        self.alerts = alerts
        self.alert_ids = {a.id for a in alerts.alerts}
        self.issues = issues
        self.exprs = _Exprs({}, defs.conditions, issues)

    def system(self, system: str, loc: Loc) -> None:
        if system not in self.alerts.systems:
            known = ", ".join(self.alerts.systems) or "none defined in alerts.yaml"
            self.issues.add(loc, f"unknown system {system!r}; expected: {known}")

    def bind(
        self,
        model: SymbolModel | LineModel,
        allowed: tuple[str, ...],
        required: frozenset[str],
        loc: Loc,
    ) -> dict[str, EntityRef]:
        for channel in model.bind:
            if channel not in allowed:
                self.issues.add(
                    (*loc, "bind", channel),
                    f"unknown channel {channel!r} for {model.type}; expected: {', '.join(allowed)}",
                )
        for channel in sorted(required - model.bind.keys()):
            self.issues.add((*loc, "bind"), f"required channel {channel!r} is not bound")
        return {
            k: EntityRef(v.entity, v.attribute, v.scale, v.unit)
            for k, v in model.bind.items()
            if k in allowed
        }

    def bound_channel(self, channel: str, bound: Mapping[str, object], loc: Loc) -> bool:
        if channel not in bound:
            self.issues.add(loc, f"channel {channel!r} is not bound on this element")
            return False
        return True

    def status(
        self, model: StatusModel | None, primary: str, bound: Mapping[str, object], loc: Loc
    ) -> StatusSpec:
        if model is None:
            return StatusSpec()
        rules: list[Rule] = []
        if not primary and model.from_ is None and (model.thresholds or model.map):
            self.issues.add(loc, "groups have no primary channel; give 'from'")
        source = model.from_ or primary
        if model.thresholds is not None or model.map is not None:
            self.bound_channel(source, bound, (*loc, "from") if model.from_ else loc)
        ref = ChannelRef(source)
        if model.thresholds is not None:
            if isinstance(model.thresholds, str):
                named = self.defs.thresholds.get(model.thresholds)
                if named is None:
                    self.issues.add(
                        (*loc, "thresholds"), f"unknown thresholds {model.thresholds!r}"
                    )
                else:
                    rules.extend(named.rules(ref))
            else:
                rules.extend(_thresholds(model.thresholds).rules(ref))
        if model.map is not None:
            mapping = {k.strip().lower(): Status(v) for k, v in model.map.items()}
            rules.extend(state_map_rules(ref, mapping, Status(model.default or "normal")))
        for i, rule in enumerate(model.rules):
            when = self.exprs.expr(rule, (*loc, "rules", i), bound)
            rules.append(Rule(Status(rule.level), when))
        for i, system in enumerate(model.systems):
            self.system(system, (*loc, "systems", i))
        for i, alert_id in enumerate(model.alerts):
            if alert_id not in self.alert_ids:
                self.issues.add((*loc, "alerts", i), f"unknown alert {alert_id!r}")
        return StatusSpec(tuple(rules), tuple(model.systems), tuple(model.alerts))

    def name(self, model: NameModel | None, loc: Loc) -> Name | None:
        if model is None:
            return None
        anchor = _anchor(model.anchor, (*loc, "anchor"), self.issues)
        return Name(model.text, anchor, model.along, model.offset)

    def readouts(
        self, models: list[ReadoutModel], bound: Mapping[str, object], loc: Loc
    ) -> tuple[Readout, ...]:
        out = []
        for i, r in enumerate(models):
            item = (*loc, i)
            self.bound_channel(r.value, bound, (*item, "value"))
            if not is_valid_format(r.format):
                self.issues.add(
                    (*item, "format"),
                    f"unknown format {r.format!r}; use one of {', '.join(sorted(FORMATS))} "
                    "or a format string like '{:.1f} V'",
                )
            anchor = _anchor(r.anchor, (*item, "anchor"), self.issues)
            out.append(Readout(r.value, r.format, r.unit, r.abs, anchor, r.along, r.offset))
        return tuple(out)

    def symbol(self, model: SymbolModel, loc: Loc) -> SymbolElement | None:
        spec = REGISTRY.get(model.type)
        if spec is None:
            builtin = ["line", "text", "tile", "tile_grid", "node", "group", "alert_log"]
            known = ", ".join([*builtin, *sorted(REGISTRY)])
            self.issues.add((*loc, "type"), f"unknown type {model.type!r}; expected: {known}")
            return None
        bound = self.bind(model, spec.channels, spec.required, loc)
        try:
            params = spec.params(model.params)
        except ValueError as exc:
            self.issues.add((*loc, "params"), str(exc))
            params = {}
        return SymbolElement(
            id=model.id,
            type=model.type,
            at=model.at,
            bind=bound,
            name=self.name(model.name, (*loc, "name")),
            status=self.status(model.status, spec.primary, bound, (*loc, "status")),
            readouts=self.readouts(model.readouts, bound, (*loc, "readouts")),
            orientation=Orientation(model.orientation),
            params=params,
        )

    def line(self, model: LineModel, loc: Loc) -> LineElement:
        bound = self.bind(model, LINE_CHANNELS, frozenset(), loc)
        flow = None
        if model.flow is not None:
            self.bound_channel(model.flow.from_, bound, (*loc, "flow", "from"))
            flow = FlowSpec(model.flow.from_, model.flow.threshold)
        self.pending.append(
            _PendingLine(
                model.id,
                model.from_,
                tuple(model.via),
                model.to,
                loc,
                straight=model.route == "straight",
                elbow=Elbow(model.elbow) if model.elbow else None,
            )
        )
        return LineElement(
            id=model.id,
            bind=bound,
            name=self.name(model.name, (*loc, "name")),
            status=self.status(model.status, LINE_PRIMARY, bound, (*loc, "status")),
            readouts=self.readouts(model.readouts, bound, (*loc, "readouts")),
            flow=flow,
            casing=model.casing,
        )

    def tile_grid(self, model: TileGridModel, loc: Loc) -> list[Element]:
        """Shorthand for a frameless, unpadded group of tiles."""
        tiles: list[Element] = []
        for i, system in enumerate(model.tiles):
            self.system(system, (*loc, "tiles", i))
            tiles.append(TileElement(system, (0.0, 0.0), system))
        layout = GridLayout(model.columns, model.gap, padding=0.0)
        return [_arrange(model.id, model.at, layout, tiles, frame=Frame.NONE)]

    def group(self, model: GroupModel, loc: Loc) -> GroupElement | None:
        items: list[Element] = []
        seen: set[str] = set()
        for i, raw in enumerate(model.items):
            item_loc = (*loc, "items", i)
            if "at" in raw:
                self.issues.add((*item_loc, "at"), "items are positioned by the group's layout")
                continue
            merged = {**model.item_defaults, **raw, "at": [0, 0]}
            kind = merged.get("type")
            if kind not in (*REGISTRY, "tile", "group"):
                self.issues.add(
                    (*item_loc, "type"),
                    f"groups can contain symbols, tiles and groups, not {kind!r}",
                )
                continue
            if kind == "tile" and "id" not in merged and isinstance(merged.get("system"), str):
                merged["id"] = merged["system"]
            for item in self.element(merged, item_loc):
                if item.id in seen:
                    self.issues.add((*item_loc, "id"), f"duplicate item id {item.id!r}")
                seen.add(item.id)
                items.append(item)
        if not items:
            return None
        derived = self.derived(model, items, (*loc, "channels"))
        bound = dict.fromkeys(derived)
        layout = GridLayout(
            model.layout.grid.columns, model.layout.grid.gap, model.layout.grid.padding
        )
        group = _arrange(model.id, model.at, layout, items, frame=Frame(model.frame))
        return replace(
            group,
            name=self.name(model.name, (*loc, "name")),
            channels=derived,
            status=self.status(model.status, "", bound, (*loc, "status")),
            readouts=self.readouts(model.readouts, bound, (*loc, "readouts")),
        )

    def derived(
        self, model: GroupModel, items: Sequence[Element], loc: Loc
    ) -> dict[str, DerivedChannel]:
        available = set().union(*(_channels_of(i) for i in items))
        out = {}
        for name, raw in model.channels.items():
            d = validate(DerivedModel, raw, (*loc, name), self.issues)
            if d is None:
                continue
            if d.count is not None:
                out[name] = DerivedChannel(Aggregate.COUNT, d.count)
                continue
            aggregate, source = next(
                (Aggregate(k), v) for k in ("sum", "min", "max") if (v := getattr(d, k))
            )
            if source not in available:
                known = ", ".join(sorted(available)) or "none"
                self.issues.add(
                    (*loc, name, aggregate.value),
                    f"no item has channel {source!r}; item channels: {known}",
                )
            out[name] = DerivedChannel(aggregate, source)
        return out

    def element(self, raw: dict[str, Any], loc: Loc) -> list[Element]:
        """Build one YAML element; a ``tile_grid`` expands to several."""
        kind = raw.get("type")
        if not isinstance(kind, str):
            self.issues.add((*loc, "type"), "every element needs a 'type'")
            return []
        built: Element | None
        match kind:
            case "text":
                text = validate(TextModel, raw, loc, self.issues)
                built = (
                    None if text is None else TextElement(text.id, text.at, text.text, text.align)
                )
            case "line":
                line = validate(LineModel, raw, loc, self.issues)
                built = None if line is None else self.line(line, loc)
            case "tile":
                t = validate(TileModel, raw, loc, self.issues)
                if t is not None:
                    self.system(t.system, (*loc, "system"))
                built = None if t is None else TileElement(t.id, t.at, t.system, t.label)
            case "node":
                node = validate(NodeModel, raw, loc, self.issues)
                built = None if node is None else NodeElement(node.id, node.at)
            case "group":
                g = validate(GroupModel, raw, loc, self.issues)
                built = None if g is None else self.group(g, loc)
            case "alert_log":
                log = validate(LogModel, raw, loc, self.issues)
                if log is not None:
                    for i, system in enumerate(log.systems):
                        self.system(system, (*loc, "systems", i))
                built = (
                    None
                    if log is None
                    else LogElement(log.id, log.at, log.size, tuple(log.systems))
                )
            case "tile_grid":
                grid = validate(TileGridModel, raw, loc, self.issues)
                return [] if grid is None else self.tile_grid(grid, loc)
            case _:
                symbol = validate(SymbolModel, raw, loc, self.issues)
                built = None if symbol is None else self.symbol(symbol, loc)
        return [] if built is None else [built]


def build_page(
    model: PageModel, shared: Defs, issues: Issues, alerts: Alerts | None = None
) -> Page:
    """Build a page, merging page-local ``defs`` over the shared ones (no redefinition).

    ``alerts`` supplies the systems and alert ids that tiles and status may reference.
    """
    defs = shared
    if model.defs is not None:
        if model.defs.stale_after is not None:
            issues.add(("defs", "stale_after"), "stale_after is house-wide: set it in defs.yaml")
        local = build_defs(model.defs, issues, base=shared)
        defs, dupes = shared.merge(local)
        for dupe in dupes:
            issues.add(("defs", *dupe.split(".")), f"{dupe} is already defined in shared defs")
    builder = _ElementBuilder(defs, alerts or Alerts(), issues)
    elements: list[Element] = []
    locs: dict[str, Loc] = {}
    for i, raw in enumerate(model.elements):
        for element in builder.element(raw, ("elements", i)):
            if element.id in locs:
                issues.add(("elements", i, "id"), f"duplicate element id {element.id!r}")
            locs[element.id] = ("elements", i)
            elements.append(element)
    elements = _connect(elements, builder.pending, issues, locs)
    return Page(model.page, model.title, model.canvas.width, model.canvas.height, tuple(elements))


def _channels_of(element: Element) -> set[str]:
    """Channels an item exposes to its group: bound symbol channels or derived ones."""
    match element:
        case SymbolElement():
            return set(element.bind)
        case GroupElement():
            return set(element.channels)
        case _:
            return set()


def _rename(element: Element, prefix: str) -> Element:
    """Scope an item's id (and, for groups, its items' ids) under ``prefix``."""
    renamed = replace(element, id=f"{prefix}.{element.id}")
    if isinstance(renamed, GroupElement):
        renamed = replace(renamed, items=tuple(_rename(i, prefix) for i in renamed.items))
    return renamed


def _translate(element: Element, dx: float, dy: float) -> Element:
    """Move an item (and a group's items) by (dx, dy)."""
    if isinstance(element, GroupElement):
        return replace(
            element,
            at=(element.at[0] + dx, element.at[1] + dy),
            items=tuple(_translate(i, dx, dy) for i in element.items),
        )
    if isinstance(element, (SymbolElement, TileElement, NodeElement)):
        return replace(element, at=(element.at[0] + dx, element.at[1] + dy))
    return element


def _arrange(
    group_id: str,
    origin: Point,
    layout: GridLayout,
    items: Sequence[Element],
    frame: Frame,
) -> GroupElement:
    """Lay ``items`` out in a grid of cells sized to the largest item, centering each.

    ``origin`` is the group's top-left; item ids are scoped under ``group_id``.
    """
    boxes = [element_box(i) for i in items]
    cell_w = max((b.right - b.left for b in boxes if b), default=0.0)
    cell_h = max((b.bottom - b.top for b in boxes if b), default=0.0)
    pad, (gx, gy) = layout.padding, layout.gap
    inner = (origin[0] + pad, origin[1] + pad)
    centers = grid_centers(inner, len(items), layout.columns, (cell_w, cell_h), layout.gap)
    placed = []
    for item, box, (cx, cy) in zip(items, boxes, centers, strict=True):
        moved = item if box is None else _translate(item, cx - box.cx, cy - box.cy)
        placed.append(_rename(moved, group_id))
    columns = min(layout.columns, len(items))
    rows = -(-len(items) // layout.columns)
    size = (
        2 * pad + columns * cell_w + (columns - 1) * gx,
        2 * pad + rows * cell_h + (rows - 1) * gy,
    )
    return GroupElement(group_id, origin, size, layout, tuple(placed), frame)


#: Lines attached to a node at which a junction dot is drawn.
JUNCTION_DEGREE = 3


def _endpoint(
    end: Endpoint, by_id: Mapping[str, Element], loc: Loc, issues: Issues, degree: Counter[str]
) -> Port | None:
    if not isinstance(end, str):
        return Port(end)
    owner = _item_owner(end, by_id)
    if owner is not None:
        issues.add(
            loc,
            f"cannot connect to {end!r}: items of group {owner.id!r} connect only "
            f"through the group; use '{owner.id}.<port>'",
        )
        return None
    if end in by_id:
        target, port = by_id[end], None
    else:
        element_id, _, port_name = end.rpartition(".")
        if element_id not in by_id:
            issues.add(loc, f"unknown element {end!r}; use a node id or 'element.port'")
            return None
        target, port = by_id[element_id], port_name
    try:
        found = find_port(target, port)
    except ValueError as exc:
        issues.add(loc, str(exc))
        return None
    if isinstance(target, NodeElement):
        degree[target.id] += 1
    return found


def _item_ids(group: GroupElement) -> Iterator[str]:
    for item in group.items:
        yield item.id
        if isinstance(item, GroupElement):
            yield from _item_ids(item)


def _item_owner(end: str, by_id: Mapping[str, Element]) -> GroupElement | None:
    """The top-level group whose item ``end`` names (``item`` or ``item.port``), if any."""
    for group in by_id.values():
        if isinstance(group, GroupElement):
            ids = set(_item_ids(group))
            if end in ids or end.rpartition(".")[0] in ids:
                return group
    return None


def _names_element(ref: object, by_id: Mapping[str, Element]) -> bool:
    """Whether a binding refers to another element's channel (before or after conversion)."""
    if isinstance(ref, ElementRef):
        return True
    return isinstance(ref, EntityRef) and ref.entity_id.rpartition(".")[0] in by_id


def _element_bindings(
    element: LineElement | SymbolElement,
    by_id: Mapping[str, Element],
    issues: Issues,
    loc: Loc,
) -> dict[str, EntityRef | ElementRef]:
    """Turn bindings that name another element's channel (``array.power``) into ElementRefs.

    A binding is an element channel when the part before its last dot is a
    top-level element id. The target must be a symbol or group exposing that
    channel, and the channel must not itself bind another element (no chains).
    """
    out: dict[str, EntityRef | ElementRef] = {}
    for name, ref in element.bind.items():
        target_id, _, channel = (
            ref.entity_id.rpartition(".") if isinstance(ref, EntityRef) else ("", "", "")
        )
        target = by_id.get(target_id)
        if target is None or not isinstance(ref, EntityRef) or ref.attribute is not None:
            out[name] = ref
            continue
        where = (*loc, "bind", name)
        if ref.scale != 1.0 or ref.unit is not None:
            issues.add(where, "'scale' and 'unit' apply to entity bindings, not element channels")
        if not isinstance(target, (SymbolElement, GroupElement)):
            issues.add(where, f"{target_id!r} has no channels to bind to")
        elif channel not in _channels_of(target):
            known = ", ".join(sorted(_channels_of(target))) or "none"
            issues.add(where, f"{target_id!r} has no channel {channel!r}; expected: {known}")
        elif isinstance(target, SymbolElement) and _names_element(target.bind.get(channel), by_id):
            issues.add(
                where, f"{target_id}.{channel} is itself bound to an element; bind to the source"
            )
        out[name] = ElementRef(target_id, channel)
    return out


def _connect(
    elements: Sequence[Element],
    pending: Sequence[_PendingLine],
    issues: Issues,
    locs: Mapping[str, Loc],
) -> list[Element]:
    """Resolve line endpoints to points and mark junction nodes."""
    by_id = {e.id: e for e in elements}
    degree: Counter[str] = Counter()
    points: dict[str, tuple[Point, ...]] = {}
    for line in pending:
        start = _endpoint(line.start, by_id, (*line.loc, "from"), issues, degree)
        end = _endpoint(line.end, by_id, (*line.loc, "to"), issues, degree)
        if start is None or end is None:
            continue
        if line.via or line.straight:
            points[line.id] = (start.point, *line.via, end.point)
        else:
            points[line.id] = route(start, end, line.elbow)
    out: list[Element] = []
    for e in elements:
        if isinstance(e, (LineElement, SymbolElement)):
            bind = _element_bindings(e, by_id, issues, locs.get(e.id, ()))
            e = replace(e, bind=bind)
        if isinstance(e, LineElement) and e.id in points:
            e = replace(e, points=points[e.id])
        elif isinstance(e, NodeElement) and degree[e.id] >= JUNCTION_DEGREE:
            e = replace(e, junction=True)
        out.append(e)
    return out


# --- displays -------------------------------------------------------------------------------


def build_displays(
    model: DisplaysModel, page_ids: Collection[str], issues: Issues
) -> dict[str, Display]:
    """Build displays; themes and pages must exist. ``home`` is always selectable."""
    out = {}
    for display_id, d in model.displays.items():
        loc: Loc = ("displays", display_id)
        if d.theme not in THEMES:
            issues.add((*loc, "theme"), f"unknown theme {d.theme!r}; expected: {', '.join(THEMES)}")
        checks: list[tuple[Loc, str]] = [((*loc, "home"), d.home)]
        if d.alerts_page is not None:
            checks.append(((*loc, "alerts_page"), d.alerts_page))
        checks += [((*loc, "pages", i), page) for i, page in enumerate(d.pages)]
        for where, page in checks:
            if page not in page_ids:
                issues.add(where, f"unknown page {page!r}")
        if d.panel is not None:
            _check_panel(loc, d.theme, d.panel, issues)
        alerts_page = d.alerts_page or d.home
        pages = (d.home, *(p for p in d.pages if p != d.home))
        if alerts_page not in pages:
            pages = (*pages, alerts_page)
        out[display_id] = Display(
            display_id, d.theme, d.size[0], d.size[1], d.home, pages, alerts_page, d.panel
        )
    return out


def _check_panel(loc: Loc, theme: str, panel: str, issues: Issues) -> None:
    """The panel profile must exist and show every color the theme draws."""
    profile = PANELS.get(panel)
    if profile is None:
        issues.add((*loc, "panel"), f"unknown panel {panel!r}; expected: {', '.join(PANELS)}")
        return
    if theme not in THEMES:
        return
    missing = profile.unsupported(THEMES[theme])
    if missing:
        issues.add(
            (*loc, "panel"),
            f"panel {panel!r} cannot show theme {theme!r} (colors {', '.join(sorted(missing))});"
            " use a theme drawn in the panel's colors, such as eink_mono",
        )


# --- alerts -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Alerts:
    """Systems and alert definitions, in file order."""

    systems: Mapping[str, System] = field(default_factory=dict)
    alerts: tuple[AlertDef, ...] = ()

    def by_id(self) -> Mapping[str, AlertDef]:
        """Alerts keyed by id."""
        return {a.id: a for a in self.alerts}


def build_alerts(model: AlertsModel, defs: Defs, issues: Issues) -> Alerts:
    """Build alerts; conditions may use only ``entity`` references and defs conditions."""
    systems = {sid: System(sid, s.label) for sid, s in model.systems.items()}
    exprs = _Exprs({}, defs.conditions, issues)
    alerts: list[AlertDef] = []
    seen: set[str] = set()
    for i, raw in enumerate(model.alerts):
        loc: Loc = ("alerts", i)
        a = validate(AlertModel, raw, loc, issues)
        if a is None:
            continue
        if a.id in seen:
            issues.add((*loc, "id"), f"duplicate alert id {a.id!r}")
        seen.add(a.id)
        if a.system not in systems:
            known = ", ".join(systems) or "none defined"
            issues.add((*loc, "system"), f"unknown system {a.system!r}; expected: {known}")
        condition = exprs.expr(a, loc, NO_CHANNELS)
        hold = a.hold or timedelta(0)
        alerts.append(AlertDef(a.id, Severity(a.severity), a.system, a.message, condition, hold))
    return Alerts(systems, tuple(alerts))
