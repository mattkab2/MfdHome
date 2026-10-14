"""Turn validated schema models into frozen model objects, with context checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ValidationError

from mfdhome.conditions.model import TRUE, AllOf, AnyOf, ChannelRef, Condition, Op, Rule
from mfdhome.conditions.sugar import Thresholds, state_map_rules
from mfdhome.config.errors import Issues, Loc
from mfdhome.config.schema import (
    AlertModel,
    AlertsModel,
    DefsModel,
    ExprModel,
    LineModel,
    NameModel,
    NodeModel,
    PageModel,
    ReadoutModel,
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
from mfdhome.model.alert import AlertDef, Severity, System
from mfdhome.model.binding import EntityRef, Status
from mfdhome.model.page import (
    Element,
    FlowSpec,
    LineElement,
    LineLook,
    LineStyle,
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
from mfdhome.render.format import FORMATS, is_valid_format
from mfdhome.symbols.geometry import port_point
from mfdhome.symbols.registry import LINE_CHANNELS, LINE_PRIMARY, REGISTRY
from mfdhome.symbols.tile import TILE_HEIGHT, TILE_WIDTH
from mfdhome.themes.builtin import THEMES


@dataclass(frozen=True)
class Defs:
    """Resolved shared definitions."""

    thresholds: Mapping[str, Thresholds] = field(default_factory=lambda: MappingProxyType({}))
    conditions: Mapping[str, AnyOf] = field(default_factory=lambda: MappingProxyType({}))
    line_styles: Mapping[str, LineStyle] = field(default_factory=lambda: MappingProxyType({}))

    def merge(self, other: Defs) -> tuple[Defs, list[str]]:
        """Combine two sets of defs; returns the result and any duplicated names."""
        kinds = ("thresholds", "conditions", "line_styles")
        dupes = sorted(
            f"{kind}.{name}"
            for kind in kinds
            for name in getattr(self, kind).keys() & getattr(other, kind).keys()
        )
        merged = Defs(*(MappingProxyType({**getattr(self, k), **getattr(other, k)}) for k in kinds))
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
            if isinstance(cond.ref, ChannelRef):
                yield cond.ref.channel


# --- conditions -------------------------------------------------------------------------------


type Bound = Mapping[str, EntityRef] | None

#: ``bound`` value for contexts that have no channels at all (alerts).
NO_CHANNELS: Mapping[str, EntityRef] = MappingProxyType({})


class _Exprs:
    """Builds DNF expressions, resolving ``use`` against named conditions.

    ``bound`` is the evaluating element's channels; when given, channel
    references are checked against it where they are written (or at the
    ``use`` site for named conditions). Named conditions themselves are built
    with ``bound=None``, since they may be used by several elements.
    """

    def __init__(
        self, named: Mapping[str, ExprModel], resolved: Mapping[str, AnyOf], prefix: Loc = ()
    ) -> None:
        self.named = named
        self.prefix = prefix
        self.resolved = dict(resolved)
        self.resolving: list[str] = []

    def use(self, name: str, loc: Loc, issues: Issues, bound: Bound = None) -> AnyOf:
        expr = self._resolve(name, loc, issues)
        if bound is not None:
            for channel in sorted(set(_channels(expr)) - bound.keys()):
                if bound is NO_CHANNELS:
                    message = (
                        f"condition {name!r} uses channel {channel!r}; alerts can only use 'entity'"
                    )
                else:
                    message = f"condition {name!r} uses channel {channel!r}, which is not bound"
                issues.add(loc, message)
        return expr

    def _resolve(self, name: str, loc: Loc, issues: Issues) -> AnyOf:
        if name in self.resolved:
            return self.resolved[name]
        if name not in self.named:
            issues.add(loc, f"unknown condition {name!r}")
            return AnyOf()
        if name in self.resolving:
            chain = " -> ".join([*self.resolving[self.resolving.index(name) :], name])
            issues.add(loc, f"condition cycle: {chain}")
            return AnyOf()
        self.resolving.append(name)
        expr = self.expr(self.named[name], (*self.prefix, "conditions", name), issues)
        self.resolving.pop()
        self.resolved[name] = expr
        return expr

    def condition(self, term: TermModel, loc: Loc, issues: Issues, bound: Bound) -> AnyOf:
        if term.channel is not None:
            ref: ChannelRef | EntityRef = ChannelRef(term.channel)
            if bound is NO_CHANNELS:
                issues.add((*loc, "channel"), "alerts have no channels; use 'entity'")
            elif bound is not None and term.channel not in bound:
                issues.add((*loc, "channel"), f"channel {term.channel!r} is not bound")
        else:
            ref = EntityRef(str(term.entity), term.attribute)
        [op] = term.predicates()
        operand: Any = {
            "eq": term.eq,
            "ne": term.ne,
            "in": tuple(term.in_ or ()),
            "not_in": tuple(term.not_in or ()),
            "lt": term.lt,
            "le": term.le,
            "gt": term.gt,
            "ge": term.ge,
            "between": term.between,
            "unavailable": term.unavailable,
        }[op]
        return AnyOf((AllOf((Condition(ref, Op(op), operand),)),))

    def conjunction(
        self, terms: list[TermModel], loc: Loc, issues: Issues, bound: Bound = None
    ) -> AnyOf:
        result = TRUE
        for i, term in enumerate(terms):
            if term.all_ is not None:
                issues.add((*loc, i, "all"), "'all' groups are only allowed directly under 'any'")
            elif term.use is not None:
                result = result.and_(self.use(term.use, (*loc, i, "use"), issues, bound))
            else:
                result = result.and_(self.condition(term, (*loc, i), issues, bound))
        return result

    def expr(self, model: ExprModel, loc: Loc, issues: Issues, bound: Bound = None) -> AnyOf:
        if model.when is not None:
            return self.conjunction(model.when, (*loc, "when"), issues, bound)
        result = AnyOf()
        for i, term in enumerate(model.any_ or ()):
            item = (*loc, "any", i)
            if term.all_ is not None:
                result = result.or_(self.conjunction(term.all_, (*item, "all"), issues, bound))
            elif term.use is not None:
                result = result.or_(self.use(term.use, (*item, "use"), issues, bound))
            else:
                result = result.or_(self.condition(term, item, issues, bound))
        return result


def build_defs(
    model: DefsModel, issues: Issues, base: Defs | None = None, prefix: Loc = ("defs",)
) -> Defs:
    """Resolve a defs model; named conditions may ``use`` each other and ``base`` conditions.

    ``prefix`` is where the defs sit in their file: under ``defs`` in a page,
    at the top level of a shared defs file.
    """
    base = base or Defs()
    exprs = _Exprs(model.conditions, base.conditions, prefix)
    conditions = {
        name: exprs.use(name, (*prefix, "conditions", name), issues) for name in model.conditions
    }
    thresholds = {name: _thresholds(t) for name, t in model.thresholds.items()}
    styles = {}
    for name, style in model.line_styles.items():
        for theme in style.themes:
            if theme not in THEMES:
                issues.add(
                    (*prefix, "line_styles", name, "themes", theme),
                    f"unknown theme {theme!r}; expected: {', '.join(THEMES)}",
                )
        variants = {t: LineLook(v.weight, v.casing) for t, v in style.themes.items()}
        styles[name] = LineStyle(
            name, LineLook(style.weight, style.casing), MappingProxyType(variants)
        )
    return Defs(
        MappingProxyType(thresholds), MappingProxyType(conditions), MappingProxyType(styles)
    )


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


class _ElementBuilder:
    def __init__(self, defs: Defs, alerts: Alerts, issues: Issues) -> None:
        self.pending: list[_PendingLine] = []
        self.defs = defs
        self.alerts = alerts
        self.alert_ids = {a.id for a in alerts.alerts}
        self.issues = issues
        self.exprs = _Exprs({}, defs.conditions)

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
        return {k: EntityRef(v.entity, v.attribute) for k, v in model.bind.items() if k in allowed}

    def bound_channel(self, channel: str, bound: Mapping[str, EntityRef], loc: Loc) -> bool:
        if channel not in bound:
            self.issues.add(loc, f"channel {channel!r} is not bound on this element")
            return False
        return True

    def status(
        self, model: StatusModel | None, primary: str, bound: Mapping[str, EntityRef], loc: Loc
    ) -> StatusSpec:
        if model is None:
            return StatusSpec()
        rules: list[Rule] = []
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
            when = self.exprs.expr(rule, (*loc, "rules", i), self.issues, bound)
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
        self, models: list[ReadoutModel], bound: Mapping[str, EntityRef], loc: Loc
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
            known = ", ".join(["line", "text", "tile", "tile_grid", *sorted(REGISTRY)])
            self.issues.add((*loc, "type"), f"unknown type {model.type!r}; expected: {known}")
            return None
        bound = self.bind(model, spec.channels, spec.required, loc)
        try:
            params = spec.params(model.params)
        except ValueError as exc:
            self.issues.add((*loc, "params"), str(exc))
            params = MappingProxyType({})
        return SymbolElement(
            id=model.id,
            type=model.type,
            at=model.at,
            bind=MappingProxyType(bound),
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
        if model.points is None:
            assert model.from_ is not None and model.to is not None
            self.pending.append(
                _PendingLine(model.id, model.from_, tuple(model.via), model.to, loc)
            )
        return LineElement(
            id=model.id,
            points=tuple(model.points or ()),
            bind=MappingProxyType(bound),
            name=self.name(model.name, (*loc, "name")),
            status=self.status(model.status, LINE_PRIMARY, bound, (*loc, "status")),
            readouts=self.readouts(model.readouts, bound, (*loc, "readouts")),
            flow=flow,
            style=self.line_style(model.style, (*loc, "style")),
            look=LineLook(model.weight, model.casing),
        )

    def line_style(self, name: str | None, loc: Loc) -> LineStyle:
        if name is None:
            return LineStyle()
        style = self.defs.line_styles.get(name)
        if style is None:
            known = ", ".join(self.defs.line_styles) or "none defined"
            self.issues.add(loc, f"unknown line style {name!r}; expected: {known}")
            return LineStyle()
        return style

    def tile_grid(self, model: TileGridModel, loc: Loc) -> list[Element]:
        centers = grid_centers(
            model.at, len(model.tiles), model.columns, (TILE_WIDTH, TILE_HEIGHT), model.gap
        )
        tiles: list[Element] = []
        for i, (system, center) in enumerate(zip(model.tiles, centers, strict=True)):
            self.system(system, (*loc, "tiles", i))
            tiles.append(TileElement(f"{model.id}.{system}", center, system))
        return tiles

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
        local = build_defs(model.defs, issues, base=shared)
        defs, dupes = shared.merge(local)
        for dupe in dupes:
            issues.add(("defs", *dupe.split(".")), f"{dupe} is already defined in shared defs")
    builder = _ElementBuilder(defs, alerts or Alerts(), issues)
    elements: list[Element] = []
    seen: set[str] = set()
    for i, raw in enumerate(model.elements):
        for element in builder.element(raw, ("elements", i)):
            if element.id in seen:
                issues.add(("elements", i, "id"), f"duplicate element id {element.id!r}")
            seen.add(element.id)
            elements.append(element)
    elements = _connect(elements, builder.pending, issues)
    return Page(model.page, model.title, model.canvas.width, model.canvas.height, tuple(elements))


#: Lines attached to a node at which a junction dot is drawn.
JUNCTION_DEGREE = 3


def _endpoint(
    end: Endpoint, by_id: Mapping[str, Element], loc: Loc, issues: Issues, degree: Counter[str]
) -> Point | None:
    if not isinstance(end, str):
        return end
    if end in by_id:
        target, port = by_id[end], None
    else:
        element_id, _, port_name = end.rpartition(".")
        if element_id not in by_id:
            issues.add(loc, f"unknown element {end!r}; use a node id or 'element.port'")
            return None
        target, port = by_id[element_id], port_name
    try:
        point = port_point(target, port)
    except ValueError as exc:
        issues.add(loc, str(exc))
        return None
    if isinstance(target, NodeElement):
        degree[target.id] += 1
    return point


def _connect(
    elements: Sequence[Element], pending: Sequence[_PendingLine], issues: Issues
) -> list[Element]:
    """Resolve line endpoints to points and mark junction nodes."""
    by_id = {e.id: e for e in elements}
    degree: Counter[str] = Counter()
    points: dict[str, tuple[Point, ...]] = {}
    for line in pending:
        start = _endpoint(line.start, by_id, (*line.loc, "from"), issues, degree)
        end = _endpoint(line.end, by_id, (*line.loc, "to"), issues, degree)
        if start is not None and end is not None:
            points[line.id] = (start, *line.via, end)
    out: list[Element] = []
    for e in elements:
        if isinstance(e, LineElement) and e.id in points:
            e = replace(e, points=points[e.id])
        elif isinstance(e, NodeElement) and degree[e.id] >= JUNCTION_DEGREE:
            e = replace(e, junction=True)
        out.append(e)
    return out


# --- alerts -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Alerts:
    """Systems and alert definitions, in file order."""

    systems: Mapping[str, System] = field(default_factory=lambda: MappingProxyType({}))
    alerts: tuple[AlertDef, ...] = ()

    def by_id(self) -> Mapping[str, AlertDef]:
        """Alerts keyed by id."""
        return MappingProxyType({a.id: a for a in self.alerts})


def build_alerts(model: AlertsModel, defs: Defs, issues: Issues) -> Alerts:
    """Build alerts; conditions may use only ``entity`` references and defs conditions."""
    systems = {sid: System(sid, s.label) for sid, s in model.systems.items()}
    exprs = _Exprs({}, defs.conditions)
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
        condition = exprs.expr(a, loc, issues, NO_CHANNELS)
        alerts.append(AlertDef(a.id, Severity(a.severity), a.system, a.message, condition, a.page))
    return Alerts(MappingProxyType(systems), tuple(alerts))
