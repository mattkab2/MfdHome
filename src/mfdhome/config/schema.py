"""Pydantic schema for the page, defs, alerts, displays and scenario YAML files.

These models only check the shape of the input. ``build`` turns them into the
frozen model types and does the checks that need context (symbol registry,
defs lookups, bound channels). Nothing outside ``config`` sees these classes.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Level = Literal["normal", "caution", "warning"]
Scalar = str | float
Coord = tuple[float, float]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
Ident = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]*$")]
EntityId = Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")]

PREDICATES = ("eq", "ne", "in", "not_in", "lt", "le", "gt", "ge", "between", "unavailable")
#: Field names of the predicates (``in`` is a keyword, so its field is ``in_``).
_PREDICATE_FIELDS = {p + "_" if p == "in" else p for p in PREDICATES}


def _shorthand(key: str) -> BeforeValidator:
    """Accept a bare string as ``{key: string}``."""
    return BeforeValidator(lambda v: {key: v} if isinstance(v, str) else v)


#: ``[x, y]``, or one number for both.
Gap = Annotated[Coord, BeforeValidator(lambda v: [v, v] if isinstance(v, (int, float)) else v)]


class Strict(BaseModel):
    """Base: unknown keys are errors, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BindModel(Strict):
    """``{entity, attribute, scale, unit}``; a bare string is shorthand for ``{entity: ...}``.

    ``scale`` multiplies numeric values (``-1`` flips a sign convention, ``1000``
    turns kW into W); ``unit`` replaces the entity's unit after scaling.
    """

    entity: EntityId
    attribute: str | None = None
    scale: float = 1.0
    unit: str | None = None

    @model_validator(mode="after")
    def _nonzero_scale(self) -> Self:
        if self.scale == 0:
            raise ValueError("'scale' must not be 0")
        return self


Bind = Annotated[BindModel, _shorthand("entity")]


class RefOperandModel(Strict):
    """Another value to compare against: a ``channel`` or ``entity`` (with optional
    ``attribute``), plus ``offset``."""

    channel: str | None = None
    entity: EntityId | None = None
    attribute: str | None = None
    offset: float = 0.0

    @model_validator(mode="after")
    def _one_ref(self) -> Self:
        if (self.channel is None) == (self.entity is None):
            raise ValueError("compare against exactly one of 'channel' or 'entity'")
        if self.attribute is not None and self.entity is None:
            raise ValueError("'attribute' is only allowed with 'entity'")
        return self


#: An ordering predicate's operand: a number, or another value (plus an offset).
Compared = float | RefOperandModel


class TermModel(Strict):
    """One item in a condition list.

    Exactly one of: a condition (``channel`` or ``entity`` plus one predicate),
    ``use`` (a named condition from defs), or ``all`` (an AND-group, allowed only
    directly under ``any``).
    """

    channel: str | None = None
    entity: EntityId | None = None
    attribute: str | None = None
    use: str | None = None
    all_: list[TermModel] | None = Field(default=None, alias="all")

    eq: Scalar | None = None
    ne: Scalar | None = None
    in_: list[Scalar] | None = Field(default=None, alias="in")
    not_in: list[Scalar] | None = None
    lt: Compared | None = None
    le: Compared | None = None
    gt: Compared | None = None
    ge: Compared | None = None
    between: Coord | None = None
    unavailable: bool | None = None

    def predicates(self) -> dict[str, Any]:
        """The predicates set on this term, by YAML name, with their operands."""
        return self.model_dump(by_alias=True, exclude_none=True, include=_PREDICATE_FIELDS)

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        refs = [r for r in ("channel", "entity") if getattr(self, r) is not None]
        preds = self.predicates()
        if self.all_ is not None or self.use is not None:
            if refs or preds or self.attribute is not None or (self.all_ and self.use):
                form = "'all'" if self.all_ is not None else "'use'"
                raise ValueError(f"{form} cannot be combined with other keys")
            return self
        if len(refs) != 1:
            raise ValueError("a condition needs exactly one of 'channel' or 'entity'")
        if self.attribute is not None and self.entity is None:
            raise ValueError("'attribute' is only allowed with 'entity'")
        if len(preds) != 1:
            raise ValueError(f"a condition needs exactly one predicate: {', '.join(PREDICATES)}")
        if self.between is not None and self.between[0] > self.between[1]:
            raise ValueError("'between' must be [low, high]")
        return self


class ExprModel(Strict):
    """A condition expression: ``any`` (OR of items) or ``when`` (AND of items)."""

    any_: list[TermModel] | None = Field(default=None, alias="any")
    when: list[TermModel] | None = None

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        if (self.any_ is None) == (self.when is None):
            raise ValueError("give exactly one of 'any' or 'when'")
        return self


class RuleModel(ExprModel):
    """A status rule: ``level`` applies when the expression holds."""

    level: Level


class ThresholdsModel(Strict):
    """Numeric limits; at or beyond a limit takes that level."""

    warning_low: float | None = None
    caution_low: float | None = None
    caution_high: float | None = None
    warning_high: float | None = None


class StateMapModel(Strict):
    """A named state map: levels for listed states, ``default`` for any other."""

    states: dict[str, Level]
    default: Level | None = None


class StatusModel(Strict):
    """Status rules plus ``thresholds``/``map`` shorthands on the ``from`` channel."""

    from_: str | None = Field(default=None, alias="from")
    thresholds: str | ThresholdsModel | None = None
    map: str | dict[str, Level] | None = None
    default: Level | None = None
    rules: list[RuleModel] = []
    systems: list[Ident] = []
    alerts: list[Ident] = []

    @model_validator(mode="after")
    def _default_needs_map(self) -> Self:
        if self.default is not None and self.map is None:
            raise ValueError("'default' is only allowed with 'map'")
        return self


class NameModel(Strict):
    """Element name label; a bare string is shorthand for ``{text: ...}``."""

    text: str
    anchor: str | None = None
    along: Fraction = 0.5
    offset: Coord = (0.0, 0.0)


Name = Annotated[NameModel | None, _shorthand("text")]


class ReadoutModel(Strict):
    """A displayed channel value."""

    value: str
    format: str = "number"
    unit: str | None = None
    abs: bool = False
    anchor: str | None = None
    along: Fraction = 0.5
    offset: Coord = (0.0, 0.0)
    with_flow: bool = False  # lines: only while that direction's arrow is drawn


class TagModel(Strict):
    """A line's service tag; a bare string is shorthand for ``{text: ...}``."""

    text: Annotated[str, Field(min_length=1, max_length=4)]
    along: Annotated[float, Field(ge=0.0, le=1.0)] = 0.25


class FlowModel(Strict):
    """Flow arrow rule; ``flow: true`` is shorthand for the defaults.

    Flow comes from a rate (``from``, ``threshold``) or, with ``when``/``any``
    (the same forms as status rules), from a condition. ``while`` (a
    ``when``-style list) gates flow from a rate: none while it fails, such as
    a feeder with its relay open. On a two-way line (``rate_back`` bound) the
    threshold applies to both directions, and a condition isn't allowed.
    ``reverse`` flips the direction.
    """

    from_: str = Field(default="rate", alias="from")
    threshold: Annotated[float, Field(ge=0.0)] = 0.0
    any_: list[TermModel] | None = Field(default=None, alias="any")
    when: list[TermModel] | None = None
    while_: list[TermModel] | None = Field(default=None, alias="while")
    reverse: bool = False

    @model_validator(mode="after")
    def _rate_or_condition(self) -> Self:
        if self.any_ is not None and self.when is not None:
            raise ValueError("give at most one of 'any' or 'when'")
        if (self.any_ is not None or self.when is not None) and (
            {"from_", "threshold"} & self.model_fields_set
        ):
            raise ValueError("flow from a condition has no 'from' or 'threshold'")
        if self.while_ is not None and (self.any_ is not None or self.when is not None):
            raise ValueError(
                "'while' gates flow from a rate; flow from a condition takes only 'when' or 'any'"
            )
        return self


class _Bound(Strict):
    """Fields shared by symbols and lines."""

    id: Ident
    type: str
    bind: dict[str, Bind] = {}
    name: Name = None
    status: StatusModel | None = None
    readouts: list[ReadoutModel] = []


class SymbolModel(_Bound):
    """A registered symbol type at a point."""

    at: Coord
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    params: dict[str, Any] = {}


Endpoint = Coord | str


class LineModel(_Bound):
    """A line from ``from`` to ``to``: auto-routed, or through ``via`` bends.

    An endpoint is a coordinate, a node id, or ``element.port``.
    """

    type: Literal["line"]
    from_: Endpoint = Field(alias="from")
    to: Endpoint
    via: list[Coord] = []
    route: Literal["auto", "straight"] = "auto"
    elbow: Literal["horizontal-first", "vertical-first"] | None = None
    flow: Annotated[
        FlowModel | None,
        BeforeValidator(lambda v: {} if v is True else None if v is False else v),
    ] = None
    casing: bool = True
    tag: Annotated[
        TagModel | None, BeforeValidator(lambda v: {"text": v} if isinstance(v, str) else v)
    ] = None

    @model_validator(mode="after")
    def _elbow_needs_auto_route(self) -> Self:
        if self.elbow is not None and (self.via or self.route == "straight"):
            raise ValueError("'elbow' only applies to auto-routed 'from'/'to' lines (no 'via')")
        return self


class TextModel(Strict):
    """A static label."""

    id: Ident
    type: Literal["text"]
    at: Coord
    text: str
    align: Literal["start", "middle", "end"] = "middle"


class NodeModel(Strict):
    """A connection point (bus junction)."""

    id: Ident
    type: Literal["node"]
    at: Coord


class TileModel(Strict):
    """An annunciator tile for one system."""

    id: Ident
    type: Literal["tile"]
    at: Coord
    system: Ident
    label: str | None = None


class RoomModel(Strict):
    """A floorplan room: a polygon, a name, and status rules on entities or alerts."""

    id: Ident
    type: Literal["room"]
    points: Annotated[list[Coord], Field(min_length=3)]
    name: str | None = None
    label_at: Coord | None = None
    status: StatusModel | None = None


class WallModel(Strict):
    """A floorplan wall: a polyline, optionally an exterior (heavier) wall."""

    id: Ident
    type: Literal["wall"]
    points: Annotated[list[Coord], Field(min_length=2)]
    exterior: bool = False


class LogModel(Strict):
    """The alert log: a box (top-left ``at``, ``size``), optionally limited to some systems."""

    id: Ident
    type: Literal["alert_log"]
    at: Coord
    size: tuple[Annotated[float, Field(gt=0)], Annotated[float, Field(gt=0)]]
    systems: list[Ident] = []


class TileGridModel(Strict):
    """A grid of tiles; ``at`` is the grid's top-left corner. Expanded at load time."""

    id: Ident
    type: Literal["tile_grid"]
    at: Coord
    columns: Annotated[int, Field(ge=1)]
    gap: Gap = (16.0, 16.0)
    tiles: Annotated[list[Ident], Field(min_length=1)]


class GridModel(Strict):
    """Grid layout: ``columns`` per row; ``padding`` between the frame and the cells."""

    columns: Annotated[int, Field(ge=1)]
    gap: Gap = (16.0, 16.0)
    padding: Annotated[float, Field(ge=0)] = 12.0


class LayoutModel(Strict):
    """How a group positions its items (only ``grid`` for now)."""

    grid: GridModel


class DerivedModel(Strict):
    """A derived channel: exactly one of ``sum``/``min``/``max`` (an item channel)
    or ``count`` (an item status)."""

    sum: str | None = None
    min: str | None = None
    max: str | None = None
    count: Literal["normal", "caution", "warning", "unavailable"] | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        given = [k for k in ("sum", "min", "max", "count") if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError("give exactly one of 'sum', 'min', 'max' or 'count'")
        return self


class GroupModel(Strict):
    """A container; ``at`` is its top-left corner. Items are validated one by one."""

    id: Ident
    type: Literal["group"]
    at: Coord
    layout: LayoutModel
    frame: Literal["outline", "none"] = "outline"
    name: Name = None
    status: StatusModel | None = None
    readouts: list[ReadoutModel] = []
    channels: dict[Ident, dict[str, Any]] = {}  # validated one by one as DerivedModel
    item_defaults: dict[str, Any] = {}
    items: Annotated[list[dict[str, Any]], Field(min_length=1)]


class EnclosureModel(Strict):
    """A frame around elements that share a cabinet; they keep their own places and lines."""

    id: Ident
    type: Literal["enclosure"]
    contains: Annotated[list[Ident], Field(min_length=1)]
    padding: Annotated[float, Field(ge=0)] = 12.0
    name: Name = None


def _duration(value: Any) -> Any:
    """``90``, ``"90s"``, ``"15m"`` or ``"1h"`` -> seconds; other forms pass through."""
    if isinstance(value, str) and value[:-1].replace(".", "", 1).isdigit():
        factor = {"s": 1, "m": 60, "h": 3600}.get(value[-1])
        if factor is not None:
            return float(value[:-1]) * factor
    return value


Duration = Annotated[timedelta, BeforeValidator(_duration)]


class StaleModel(Strict):
    """How long entities may go unreported before their data counts as stale."""

    default: Duration | None = None
    entities: dict[EntityId, Duration] = {}


class AveragingModel(Strict):
    """Entities a time-averaging display averages (``true``) or shows live (``false``),
    overriding the default (Home Assistant measurements)."""

    entities: dict[EntityId, bool] = {}


class DefsModel(Strict):
    """Shared definitions: thresholds, state maps, conditions, staleness limits and
    averaging overrides."""

    stale_after: StaleModel | None = None
    averaging: AveragingModel | None = None
    thresholds: dict[Ident, ThresholdsModel] = {}
    maps: dict[Ident, StateMapModel] = {}
    conditions: dict[Ident, ExprModel] = {}


class SystemModel(Strict):
    """A system: one annunciator tile."""

    label: str


class AlertModel(ExprModel):
    """One alert; its condition uses the same ``any``/``when`` forms as status rules."""

    id: Ident
    severity: Literal["advisory", "caution", "warning"]
    system: Ident
    message: str
    hold: Duration | None = Field(default=None, alias="for")
    life_safety: bool = False


class LoggedModel(Strict):
    """An entity whose state changes go in the alert log."""

    entity: EntityId
    label: str
    system: Ident


class AlertsModel(Strict):
    """The alerts file. Alerts are validated one by one so all problems surface."""

    systems: dict[Ident, SystemModel] = {}
    alerts: list[dict[str, Any]] = []
    log: list[LoggedModel] = []


class DisplayModel(Strict):
    """One display: theme, pixel size, home page, selectable pages, and for e-paper
    its panel and refresh; ``average`` sets an averaging window."""

    theme: str
    size: tuple[Annotated[int, Field(gt=0)], Annotated[int, Field(gt=0)]]
    home: Ident
    pages: list[Ident] = []
    alerts_page: Ident | None = None  # default: home
    panel: str | None = None  # e-paper panel profile: served as PNG snapshots
    refresh: Duration | None = None  # how often a panel fetches its image (default 5m)
    average: Duration | None = None  # averaging window (panels: refresh; 0: live)


class DisplaysModel(Strict):
    """The displays file."""

    displays: dict[Ident, DisplayModel] = {}


class CanvasModel(Strict):
    """Logical canvas size."""

    width: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]


class PageModel(Strict):
    """A page file. Elements are validated one by one against their type's model."""

    page: Ident
    title: str
    canvas: CanvasModel
    defs: DefsModel | None = None
    elements: list[dict[str, Any]] = []


class ScenarioStateModel(Strict):
    """One entity's state in a scenario step: a state string (keeping the entity's
    attributes), or with attributes that replace them."""

    state: str
    attributes: dict[str, Any] | None = None


class ScenarioStepModel(Strict):
    """A scenario step: at ``at``, set and remove entities and maybe (dis)connect."""

    at: Duration
    set: dict[
        EntityId,
        Annotated[
            ScenarioStateModel,
            BeforeValidator(lambda v: {"state": str(v)} if not isinstance(v, dict) else v),
        ],
    ] = {}
    remove: list[EntityId] = []
    connected: bool | None = None


class ScenarioModel(Strict):
    """A scenario file: an optional starting states file, steps, and a loop period."""

    states: str | None = None  # a states JSON file, relative to the scenario file
    loop: Duration | None = None
    steps: list[ScenarioStepModel] = []
