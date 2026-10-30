"""Running as a Home Assistant add-on: read the add-on's options, sync the house
config from its git repository, then serve.

The Supervisor writes the options to ``/data/options.json``, maps the add-on's
config folder at ``/config`` and its private data at ``/data`` (included in
Home Assistant backups). The house config is either cloned from a git
repository into ``/config/house`` (with a read-only deploy key) on every start,
or placed in ``/config`` by hand. The alert board and history live in
``/data``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The container port displays connect to; Home Assistant maps it to a host port.
PORT = 8099
#: Where a cloned config repository is checked out, inside the config folder.
CHECKOUT = "house"


@dataclass(frozen=True)
class AddonOptions:
    """The add-on's options, as set in Home Assistant.

    ``config_repo`` is the house config's git URL (``git@github.com:me/house.git``),
    or empty to use the config folder as is. ``config_path`` is the config
    directory inside the repository. ``deploy_key`` is a private key with read
    access to it. ``display_token`` gates the display URLs.
    """

    config_repo: str = ""
    config_branch: str = "main"
    config_path: str = "config"
    deploy_key: str = ""
    display_token: str = ""


def read_options(path: Path) -> AddonOptions:
    """Read the Supervisor's options file. The deploy key may be one string or a list
    of lines (Home Assistant's option fields are single-line)."""
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    key = raw.get("deploy_key") or ""
    if isinstance(key, list):
        key = "\n".join(str(line) for line in key)
    return AddonOptions(
        config_repo=str(raw.get("config_repo") or "").strip(),
        config_branch=str(raw.get("config_branch") or "main").strip(),
        config_path=str(raw.get("config_path", "config") or "").strip().strip("/"),
        deploy_key=str(key).strip(),
        display_token=str(raw.get("display_token") or ""),
    )


def git_environment(options: AddonOptions, data_dir: Path) -> dict[str, str]:
    """The environment for git: ssh with the deploy key (written to ``data_dir`` for
    the owner only) and a known-hosts file kept there, trusting a host on first
    use. The key never appears on a command line or in the checkout's config."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if not options.deploy_key:
        return env
    key_file = data_dir / "deploy_key"
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        out.write(options.deploy_key + "\n")  # OpenSSH needs the final newline
    known_hosts = data_dir / "known_hosts"
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {key_file} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
        f"-o UserKnownHostsFile={known_hosts}"
    )
    return env


def _git(args: list[str], env: dict[str, str]) -> None:
    subprocess.run(["git", *args], env=env, check=True, capture_output=True, text=True)


def sync_config(options: AddonOptions, config_dir: Path, data_dir: Path) -> Path:
    """The house config directory to serve, after bringing its repository up to date.

    Without ``config_repo`` it's ``config_dir`` itself. Otherwise the branch is
    cloned (or fetched and reset, discarding local edits) into
    ``config_dir/house``. If that fails but an earlier checkout exists, the
    earlier one is used, with a warning; with no checkout at all it's fatal.
    """
    if not options.config_repo:
        logger.info("serving the config in %s", config_dir)
        return config_dir
    checkout = config_dir / CHECKOUT
    env = git_environment(options, data_dir)
    branch = options.config_branch
    try:
        if (checkout / ".git").is_dir():
            _git(["-C", str(checkout), "fetch", "--depth", "1", "origin", branch], env)
            _git(["-C", str(checkout), "reset", "--hard", "FETCH_HEAD"], env)
        else:
            clone = ["clone", "--depth", "1", "--branch", branch, options.config_repo]
            _git([*clone, str(checkout)], env)
        logger.info("config updated from %s (%s)", options.config_repo, branch)
    except subprocess.CalledProcessError as exc:
        reason = (exc.stderr or "").strip().splitlines()[-1:] or ["git failed"]
        if not (checkout / ".git").is_dir():
            raise SystemExit(f"could not clone {options.config_repo}: {reason[0]}") from exc
        logger.warning("could not update the config (%s); serving the last copy", reason[0])
    return checkout / options.config_path if options.config_path else checkout


def serve_args(config: Path, data_dir: Path) -> list[str]:
    """The ``mfdhome`` arguments that serve ``config`` with state kept in ``data_dir``."""
    return [
        "serve",
        str(config),
        "--port",
        str(PORT),
        "--board",
        str(data_dir / "board.json"),
        "--history",
        str(data_dir / "history.jsonl"),
    ]
