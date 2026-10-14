"""Pydantic schema for page and defs YAML files.

These models only check the shape of the input. ``build`` turns them into the
frozen model types and does the checks that need context (symbol registry,
defs lookups, bound channels). Nothing outside ``config`` sees these classes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Level = Literal["normal", "caution", "warning"]
Scalar = str | float
Coord = tuple[float, float]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
Ident = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]*$")]
EntityId = Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")]

PREDICATES = ("eq", "ne", "in", "not_in", "lt", "le", "gt", "ge", "between", "unavailable")


class Strict(BaseModel):
    """Base: unknown keys are errors, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BindModel(Strict):
    """``{entity, attribute}``; a bare string is shorthand for ``{entity: ...}``."""

    entity: EntityId
    attribute: str | None = None


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
    lt: float | None = None
    le: float | None = None
    gt: float | None = None
    ge: float | None = None
    between: Coord | None = None
    unavailable: bool | None = None

    def predicates(self) -> list[str]:
        """Names of the predicates set on this term."""
        values = {
            "eq": self.eq,
            "ne": self.ne,
            "in": self.in_,
            "not_in": self.not_in,
            "lt": self.lt,
            "le": self.le,
            "gt": self.gt,
            "ge": self.ge,
            "between": self.between,
            "unavailable": self.unavailable,
        }
        return [name for name in PREDICATES if values[name] is not None]

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


class StatusModel(Strict):
    """Status rules plus ``thresholds``/``map`` shorthands on the ``from`` channel."""

    from_: str | None = Field(default=None, alias="from")
    thresholds: str | ThresholdsModel | None = None
    map: dict[str, Level] | None = None
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


class ReadoutModel(Strict):
    """A displayed channel value."""

    value: str
    format: str = "number"
    unit: str | None = None
    abs: bool = False
    anchor: str | None = None
    along: Fraction = 0.5
    offset: Coord = (0.0, 0.0)


class FlowModel(Strict):
    """Flow arrow rule; ``flow: true`` is shorthand for the defaults."""

    from_: str = Field(default="power", alias="from")
    threshold: Annotated[float, Field(ge=0.0)] = 10.0


def _shorthand(key: str) -> Any:
    def convert(value: Any) -> Any:
        return {key: value} if isinstance(value, str) else value

    return convert


class _Bound(Strict):
    """Fields shared by symbols and lines."""

    id: Ident
    type: str
    bind: dict[str, BindModel] = {}
    name: NameModel | None = None
    status: StatusModel | None = None
    readouts: list[ReadoutModel] = []

    @field_validator("bind", mode="before")
    @classmethod
    def _bind_shorthand(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _shorthand("entity")(v) for k, v in value.items()}
        return value

    @field_validator("name", mode="before")
    @classmethod
    def _name_shorthand(cls, value: Any) -> Any:
        return _shorthand("text")(value)


class SymbolModel(_Bound):
    """A registered symbol type at a point."""

    at: Coord
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    params: dict[str, Any] = {}


Endpoint = Coord | str


class LineModel(_Bound):
    """A line: explicit ``points``, or ``from``/``to`` endpoints with optional ``via`` bends.

    An endpoint is a coordinate, a node id, or ``element.port``.
    """

    type: Literal["line"]
    points: Annotated[list[Coord], Field(min_length=2)] | None = None
    from_: Endpoint | None = Field(default=None, alias="from")
    to: Endpoint | None = None
    via: list[Coord] = []
    flow: FlowModel | None = None

    @model_validator(mode="after")
    def _one_geometry(self) -> Self:
        ends = (self.from_ is not None, self.to is not None)
        if self.points is not None:
            if any(ends) or self.via:
                raise ValueError("give either 'points' or 'from'/'to' (with optional 'via')")
        elif ends != (True, True):
            raise ValueError("a line needs 'points', or both 'from' and 'to'")
        return self

    @field_validator("flow", mode="before")
    @classmethod
    def _flow_shorthand(cls, value: Any) -> Any:
        if value is True:
            return {}
        if value is False:
            return None
        return value


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


class TileGridModel(Strict):
    """A grid of tiles; ``at`` is the grid's top-left corner. Expanded at load time."""

    id: Ident
    type: Literal["tile_grid"]
    at: Coord
    columns: Annotated[int, Field(ge=1)]
    gap: Coord = (16.0, 16.0)
    tiles: Annotated[list[Ident], Field(min_length=1)]

    @field_validator("gap", mode="before")
    @classmethod
    def _gap_shorthand(cls, value: Any) -> Any:
        return [value, value] if isinstance(value, (int, float)) else value


class DefsModel(Strict):
    """Shared definitions: named thresholds and named conditions."""

    thresholds: dict[Ident, ThresholdsModel] = {}
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
    page: Ident | None = None

    @model_validator(mode="after")
    def _page_for_preempting(self) -> Self:
        if self.severity != "advisory" and self.page is None:
            raise ValueError(f"a {self.severity} alert needs a 'page' to show when it preempts")
        return self


class AlertsModel(Strict):
    """The alerts file. Alerts are validated one by one so all problems surface."""

    systems: dict[Ident, SystemModel] = {}
    alerts: list[dict[str, Any]] = []


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


#: pydantic model class names, used to drop union tags from error locations.
MODEL_NAMES = frozenset(
    {
        "BindModel",
        "TermModel",
        "ExprModel",
        "RuleModel",
        "ThresholdsModel",
        "StatusModel",
        "NameModel",
        "ReadoutModel",
        "FlowModel",
        "SymbolModel",
        "LineModel",
        "TextModel",
        "TileModel",
        "NodeModel",
        "TileGridModel",
        "SystemModel",
        "AlertModel",
        "AlertsModel",
    }
)
