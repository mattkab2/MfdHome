"""Running as a Home Assistant add-on: options, syncing the house config from git."""

import json
import logging
import stat
import subprocess
from pathlib import Path

import pytest

from mfdhome import cli
from mfdhome.server.addon import (
    AddonOptions,
    git_environment,
    read_options,
    serve_args,
    sync_config,
)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def house(tmp_path: Path) -> Path:
    """A house config repository (config/ holds the pages), on branch main."""
    repo = tmp_path / "house.git"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "defs.yaml").write_text("# v1\n")
    git("init", "-q", "-b", "main", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "-q", "-m", "v1", cwd=repo)
    return repo


def dirs(tmp_path: Path) -> tuple[Path, Path]:
    config, data = tmp_path / "config", tmp_path / "data"
    config.mkdir()
    data.mkdir()
    return config, data


class TestOptions:
    def test_defaults_without_a_file(self, tmp_path: Path) -> None:
        assert read_options(tmp_path / "missing.json") == AddonOptions()

    def test_read(self, tmp_path: Path) -> None:
        path = tmp_path / "options.json"
        key = ["-----BEGIN OPENSSH PRIVATE KEY-----", "abc", "-----END OPENSSH PRIVATE KEY-----"]
        options = {
            "config_repo": " git@github.com:me/house.git ",
            "config_branch": "develop",
            "config_path": "/config/",
            "deploy_key": key,
            "display_token": "s3cret",
        }
        path.write_text(json.dumps(options))
        read = read_options(path)
        assert read.config_repo == "git@github.com:me/house.git"
        assert (read.config_branch, read.config_path) == ("develop", "config")
        assert read.deploy_key == "\n".join(key)  # lines, as Home Assistant stores them
        assert read.display_token == "s3cret"
        path.write_text(json.dumps({**options, "deploy_key": "one\nstring\n", "config_path": ""}))
        assert read_options(path).deploy_key == "one\nstring"
        assert read_options(path).config_path == ""  # the repository's root


class TestSync:
    def test_without_a_repository_the_config_folder_is_served(self, tmp_path: Path) -> None:
        config, data = dirs(tmp_path)
        assert sync_config(AddonOptions(), config, data) == config

    def test_clones_then_follows_the_branch(self, tmp_path: Path, house: Path) -> None:
        config, data = dirs(tmp_path)
        options = AddonOptions(config_repo=str(house))
        served = sync_config(options, config, data)
        assert served == config / "house" / "config"
        assert (served / "defs.yaml").read_text() == "# v1\n"
        (house / "config" / "defs.yaml").write_text("# v2\n")
        git("commit", "-q", "-am", "v2", cwd=house)
        (served / "defs.yaml").write_text("# edited by hand\n")  # the checkout is managed
        assert (sync_config(options, config, data) / "defs.yaml").read_text() == "# v2\n"

    def test_a_failed_update_keeps_the_last_copy(
        self, tmp_path: Path, house: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config, data = dirs(tmp_path)
        options = AddonOptions(config_repo=str(house))
        sync_config(options, config, data)
        gone = AddonOptions(config_repo=str(house), config_branch="no-such-branch")
        with caplog.at_level(logging.WARNING):
            served = sync_config(gone, config, data)
        assert (served / "defs.yaml").read_text() == "# v1\n"
        assert "serving the last copy" in caplog.text

    def test_a_failed_first_clone_is_fatal(self, tmp_path: Path) -> None:
        config, data = dirs(tmp_path)
        missing = AddonOptions(config_repo=str(tmp_path / "nowhere.git"))
        with pytest.raises(SystemExit, match="could not clone"):
            sync_config(missing, config, data)


def test_deploy_key_is_private_and_never_on_a_command_line(tmp_path: Path) -> None:
    options = AddonOptions(deploy_key="-----BEGIN KEY-----\nabc\n-----END KEY-----")
    env = git_environment(options, tmp_path)
    key = tmp_path / "deploy_key"
    assert key.read_text().endswith("-----END KEY-----\n")  # OpenSSH wants the newline
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert f"-i {key}" in env["GIT_SSH_COMMAND"] and "abc" not in env["GIT_SSH_COMMAND"]
    assert "UserKnownHostsFile=" in env["GIT_SSH_COMMAND"]
    assert "GIT_SSH_COMMAND" not in git_environment(AddonOptions(), tmp_path / "x")


def test_serve_keeps_state_in_the_data_folder() -> None:
    args = serve_args(Path("/config/house/config"), Path("/data"))
    assert args[:2] == ["serve", "/config/house/config"]
    assert args[args.index("--board") + 1] == "/data/board.json"
    assert args[args.index("--history") + 1] == "/data/history.jsonl"
    assert args[args.index("--port") + 1] == "8099"


def test_addon_command_serves_the_synced_config(
    tmp_path: Path, house: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, data = dirs(tmp_path)
    (tmp_path / "options.json").write_text(
        json.dumps({"config_repo": str(house), "display_token": "s3cret"})
    )
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_serve(config: str, *args: object, **kwargs: object) -> None:
        calls.append((config, kwargs))

    monkeypatch.setattr(cli, "serve", fake_serve)
    monkeypatch.setenv("MFD_DISPLAY_TOKEN", "")  # restored after: the command sets it
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor")
    monkeypatch.chdir(tmp_path)  # no .env here
    for name in ("HA_URL", "HA_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    options = ["--options", str(tmp_path / "options.json")]
    assert cli.main(["addon", *options, "--config-dir", str(config), "--data", str(data)]) == 0
    [(served, kwargs)] = calls
    assert served == str(config / "house" / "config")
    assert kwargs["board_path"] == str(data / "board.json")
    assert kwargs["port"] == 8099 and kwargs["display_token"] == "s3cret"
