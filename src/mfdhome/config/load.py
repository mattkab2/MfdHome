"""Reading YAML config files from disk."""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from mfdhome.config.build import (
    Alerts,
    Defs,
    build_alerts,
    build_defs,
    build_displays,
    build_page,
    validate,
)
from mfdhome.config.errors import ConfigError, Issue, Issues
from mfdhome.config.schema import (
    AlertsModel,
    DefsModel,
    DisplaysModel,
    PageModel,
    ScenarioModel,
)
from mfdhome.mfd.display import Display
from mfdhome.model.page import Page
from mfdhome.model.state import EntityState
from mfdhome.sources.fixture import load_fixture
from mfdhome.sources.scenario import Scenario, Step

logger = logging.getLogger(__name__)

DEFS_FILE = "defs.yaml"
ALERTS_FILE = "alerts.yaml"
DISPLAYS_FILE = "displays.yaml"
PAGES_DIR = "pages"


@dataclass(frozen=True)
class Config:
    """A loaded config directory."""

    defs: Defs
    pages: Mapping[str, Page]
    alerts: Alerts = field(default_factory=Alerts)
    displays: Mapping[str, Display] = field(default_factory=dict)


def _plain(node: Any) -> Any:
    """Convert ruamel round-trip nodes to plain dicts, lists, str, int and float."""
    if isinstance(node, Mapping):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, str):
        return str(node)
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    return node


def _read(path: Path) -> Any:
    """Parse YAML 1.2 with line info. Syntax errors become a ``ConfigError``."""
    yaml = YAML(typ="rt")
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.load(fh)
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = None if mark is None else mark.line + 1
        raise ConfigError([Issue(path, line, "", exc.problem or str(exc))]) from exc


def load_defs(path: str | Path) -> Defs:
    """Load a shared defs file (thresholds, maps, conditions, ``stale_after`` and
    ``averaging``)."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(DefsModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    defs = build_defs(model, issues, prefix=())
    issues.raise_if_any()
    return defs


def load_alerts(path: str | Path, defs: Defs | None = None) -> Alerts:
    """Load an alerts file (``systems``, ``alerts`` and ``log``)."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(AlertsModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    alerts = build_alerts(model, defs or Defs(), issues)
    issues.raise_if_any()
    return alerts


def load_page(path: str | Path, defs: Defs | None = None, alerts: Alerts | None = None) -> Page:
    """Load and validate one page file against shared ``defs`` and ``alerts``."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(PageModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    page = build_page(model, defs or Defs(), issues, alerts)
    issues.raise_if_any()
    logger.debug("loaded page %s from %s", page.id, path)
    return page


def load_config(directory: str | Path) -> Config:
    """Load ``defs.yaml``, ``alerts.yaml`` and ``displays.yaml`` (all optional) and
    ``pages/*.yaml``.

    Problems in all page files are collected and raised together.
    """
    directory = Path(directory)
    defs_path = directory / DEFS_FILE
    defs = load_defs(defs_path) if defs_path.exists() else Defs()
    alerts_path = directory / ALERTS_FILE
    alerts = load_alerts(alerts_path, defs) if alerts_path.exists() else Alerts()
    pages: dict[str, Page] = {}
    sources: dict[str, Path] = {}
    problems: list[Issue] = []
    for path in sorted((directory / PAGES_DIR).glob("*.yaml")):
        try:
            page = load_page(path, defs, alerts)
        except ConfigError as exc:
            problems.extend(exc.issues)
            continue
        if page.id in pages:
            problems.append(
                Issue(
                    path,
                    None,
                    "page",
                    f"duplicate page id {page.id!r} (also in {sources[page.id]})",
                )
            )
            continue
        pages[page.id] = page
        sources[page.id] = path
    if problems:
        raise ConfigError(problems)
    displays_path = directory / DISPLAYS_FILE
    displays = load_displays(displays_path, pages.keys()) if displays_path.exists() else {}
    return Config(defs, pages, alerts, displays)


def load_displays(path: str | Path, page_ids: Collection[str]) -> dict[str, Display]:
    """Load a displays file; every theme and page it names must exist."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(DisplaysModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    displays = build_displays(model, page_ids, issues)
    issues.raise_if_any()
    return displays


def load_scenario(path: str | Path) -> Scenario:
    """Load a scenario file (``serve --scenario``): a starting states file and timed steps."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(ScenarioModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    base = {}
    if model.states is not None:
        states_path = path.parent / model.states
        try:
            base = dict(load_fixture(states_path))
        except (OSError, ValueError) as exc:
            message = f"cannot read {states_path}: {exc}"
            raise ConfigError([Issue(path, None, "states", message)]) from exc
    steps = tuple(
        sorted(
            (
                Step(
                    s.at,
                    {e: EntityState(v.state, dict(v.attributes or {})) for e, v in s.set.items()},
                    frozenset(s.remove),
                    s.connected,
                    frozenset(e for e, v in s.set.items() if v.attributes is None),
                )
                for s in model.steps
            ),
            key=lambda step: step.at,
        )
    )
    return Scenario(base, steps, model.loop)
