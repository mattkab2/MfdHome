"""Reading YAML config files from disk."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from mfdhome.config.build import Defs, build_defs, build_page, validate
from mfdhome.config.errors import ConfigError, Issue, Issues
from mfdhome.config.schema import DefsModel, PageModel
from mfdhome.model.page import Page

logger = logging.getLogger(__name__)

DEFS_FILE = "defs.yaml"
PAGES_DIR = "pages"


@dataclass(frozen=True)
class Config:
    """A loaded config directory."""

    defs: Defs
    pages: Mapping[str, Page]


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
    """Load a shared defs file (``thresholds`` and ``conditions``)."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(DefsModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    defs = build_defs(model, issues, prefix=())
    issues.raise_if_any()
    return defs


def load_page(path: str | Path, defs: Defs | None = None) -> Page:
    """Load and validate one page file against shared ``defs``."""
    path = Path(path)
    tree = _read(path)
    issues = Issues(path, tree)
    model = validate(PageModel, _plain(tree) or {}, (), issues)
    issues.raise_if_any()
    assert model is not None
    page = build_page(model, defs or Defs(), issues)
    issues.raise_if_any()
    logger.debug("loaded page %s from %s", page.id, path)
    return page


def load_config(directory: str | Path) -> Config:
    """Load ``defs.yaml`` (optional) and every ``pages/*.yaml`` under ``directory``.

    Problems in all files are collected and raised together.
    """
    directory = Path(directory)
    defs_path = directory / DEFS_FILE
    defs = load_defs(defs_path) if defs_path.exists() else Defs()
    pages: dict[str, Page] = {}
    sources: dict[str, Path] = {}
    problems: list[Issue] = []
    for path in sorted((directory / PAGES_DIR).glob("*.yaml")):
        try:
            page = load_page(path, defs)
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
    return Config(defs, MappingProxyType(pages))
