"""Config errors that point at the offending file and line."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from mfdhome.config.schema import MODEL_NAMES

type Loc = tuple[str | int, ...]


@dataclass(frozen=True)
class Issue:
    """One problem in a config file."""

    path: Path
    line: int | None
    loc: str
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line is not None else str(self.path)
        return f"{where}: {self.loc}: {self.message}" if self.loc else f"{where}: {self.message}"


class ConfigError(Exception):
    """One or more problems in config files. ``issues`` lists each one."""

    def __init__(self, issues: Sequence[Issue]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


def _is_union_tag(part: str | int) -> bool:
    return isinstance(part, str) and (
        part in MODEL_NAMES
        or part in {"str", "float", "int", "bool", "dict", "list", "tuple"}
        or "[" in part
    )


def clean_loc(loc: Loc) -> Loc:
    """Drop pydantic union-branch tags, which do not appear in the YAML."""
    return tuple(part for part in loc if not _is_union_tag(part))


def format_loc(loc: Loc) -> str:
    """``("elements", 3, "bind", "x")`` -> ``elements[3].bind.x``."""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else part)
    return out


def line_of(tree: object, loc: Loc) -> int | None:
    """1-based line of the deepest node along ``loc`` that exists in the YAML tree."""
    node, line = tree, None
    for part in loc:
        if isinstance(node, CommentedMap) and isinstance(node, Mapping) and part in node:
            line = node.lc.key(part)[0] + 1
            node = node[part]
        elif isinstance(node, CommentedSeq) and isinstance(part, int) and 0 <= part < len(node):
            line = node.lc.item(part)[0] + 1
            node = node[part]
        else:
            break
    if line is None and isinstance(node, (CommentedMap, CommentedSeq)) and node.lc.line is not None:
        line = node.lc.line + 1
    return line


class Issues:
    """Collects issues for one file, so a run reports every problem at once."""

    def __init__(self, path: Path, tree: object) -> None:
        self.path = path
        self.tree = tree
        self.items: list[Issue] = []

    def add(self, loc: Loc, message: str) -> None:
        """Record a problem at ``loc``."""
        loc = clean_loc(loc)
        self.items.append(Issue(self.path, line_of(self.tree, loc), format_loc(loc), message))

    def raise_if_any(self) -> None:
        """Raise ``ConfigError`` if anything was recorded."""
        if self.items:
            raise ConfigError(self.items)
