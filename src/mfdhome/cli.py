"""The ``mfdhome`` command line: check configs, dump HA states, serve displays."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import aiohttp

from mfdhome.config import ConfigError, load_config
from mfdhome.config.inventory import entity_uses
from mfdhome.model.state import StateSnapshot, snapshot_from_ha_states
from mfdhome.sources.fixture import load_fixture
from mfdhome.sources.ha import HomeAssistant

logger = logging.getLogger(__name__)

#: Attributes kept by ``dump-states --scrub``; everything else may identify the house.
SCRUB_KEEP_ATTRIBUTES = frozenset({"unit_of_measurement", "device_class", "state_class"})
#: Domains dropped by ``--scrub``: they carry people and locations.
SCRUB_DROP_DOMAINS = frozenset({"person", "device_tracker", "zone", "camera", "image"})


def load_dotenv(path: Path = Path(".env")) -> None:
    """Read ``KEY=VALUE`` lines into the environment; existing variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def ha_credentials() -> tuple[str, str]:
    """``HA_URL`` and ``HA_TOKEN`` from the environment (or ``.env``)."""
    load_dotenv()
    url, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not url or not token:
        raise SystemExit("set HA_URL and HA_TOKEN (environment or .env)")
    return url, token


async def fetch_states() -> list[dict[str, Any]]:
    """Every current HA state, in the ``/api/states`` shape."""
    url, token = ha_credentials()
    async with aiohttp.ClientSession() as session:
        snapshot = await HomeAssistant(url, token, session).states_once()
    return [
        {
            "entity_id": entity_id,
            "state": entity.state,
            "attributes": dict(entity.attributes),
            **({"last_reported": entity.reported.isoformat()} if entity.reported else {}),
        }
        for entity_id, entity in sorted(snapshot.items())
    ]


def scrub(states: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop people/location domains and every attribute not needed to render."""
    return [
        {
            **item,
            "attributes": {
                k: v for k, v in item.get("attributes", {}).items() if k in SCRUB_KEEP_ATTRIBUTES
            },
        }
        for item in states
        if item["entity_id"].partition(".")[0] not in SCRUB_DROP_DOMAINS
    ]


def cmd_check(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"config ok: {len(config.pages)} pages, {len(config.alerts.alerts)} alerts")
    snapshot: StateSnapshot | None = None
    if args.states:
        snapshot = load_fixture(args.states)
    elif args.ha:
        snapshot = snapshot_from_ha_states(asyncio.run(fetch_states()))
    if snapshot is None:
        return 0
    missing = {e: uses for e, uses in entity_uses(config).items() if e not in snapshot}
    for entity_id, uses in missing.items():
        print(f"unknown entity {entity_id}: used by {', '.join(uses)}")
    if missing:
        print(f"{len(missing)} unknown entities", file=sys.stderr)
        return 1
    print("every bound entity exists")
    return 0


def cmd_dump_states(args: argparse.Namespace) -> int:
    states = asyncio.run(fetch_states())
    if args.scrub:
        states = scrub(states)
    text = json.dumps(states, indent=1, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {len(states)} states to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mfdhome", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true", help="log debug output")
    sub = p.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a config directory")
    check.add_argument("config", help="config directory (defs.yaml, alerts.yaml, pages/)")
    source = check.add_mutually_exclusive_group()
    source.add_argument("--states", help="also report entities missing from this states dump")
    source.add_argument("--ha", action="store_true", help="also report entities missing from HA")
    check.set_defaults(run=cmd_check)

    dump = sub.add_parser("dump-states", help="write Home Assistant's current states as JSON")
    dump.add_argument("-o", "--output", help="file to write (default: stdout)")
    dump.add_argument("--scrub", action="store_true", help="drop identifying data")
    dump.set_defaults(run=cmd_dump_states)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``mfdhome`` command."""
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    result: int = args.run(args)
    return result
