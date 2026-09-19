"""Settings from ~/.config/work-ledger/config.toml, with env var overrides.

Standard library only: the hook imports this.
"""

from __future__ import annotations

import json
import os
import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def config_path() -> Path:
    if env := os.environ.get("WORK_LEDGER_CONFIG"):
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "work-ledger" / "config.toml"


def default_host() -> str:
    return socket.gethostname().split(".")[0].lower()


@dataclass
class Config:
    host: str = field(default_factory=default_host)
    ledger_dir: Path = field(default_factory=lambda: Path.home() / ".work-ledger")
    # host name -> ssh alias, for hosts VS Code can reach with Remote-SSH
    remotes: dict[str, str] = field(default_factory=dict)
    # how to run work-ledger on a remote host over ssh
    remote_command: str = "~/.local/bin/work-ledger"
    max_files: int = 8
    days: int = 60
    obsidian_daily_dir: Path | None = None


def load() -> Config:
    cfg = Config()
    data: dict = {}
    path = config_path()
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}

    if isinstance(data.get("host"), str):
        cfg.host = data["host"]
    if isinstance(data.get("remote_command"), str):
        cfg.remote_command = data["remote_command"]
    if isinstance(data.get("ledger_dir"), str):
        cfg.ledger_dir = Path(data["ledger_dir"]).expanduser()
    if isinstance(data.get("obsidian_daily_dir"), str):
        cfg.obsidian_daily_dir = Path(data["obsidian_daily_dir"]).expanduser()
    for key in ("max_files", "days"):
        if isinstance(data.get(key), int):
            setattr(cfg, key, data[key])
    if isinstance(data.get("remotes"), dict):
        cfg.remotes = {str(k): str(v) for k, v in data["remotes"].items()}

    if env := os.environ.get("WORK_LEDGER_HOST"):
        cfg.host = env
    if env := os.environ.get("WORK_LEDGER_DIR"):
        cfg.ledger_dir = Path(env).expanduser()
    return cfg


def _home_relative(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def dumps(cfg: Config) -> str:
    q = json.dumps  # JSON string escapes are valid TOML basic strings
    lines = [
        "# work-ledger settings. See docs/design.md.",
        f"host = {q(cfg.host)}",
        f"ledger_dir = {q(_home_relative(cfg.ledger_dir))}",
        f"remote_command = {q(cfg.remote_command)}",
        f"max_files = {cfg.max_files}",
        f"days = {cfg.days}",
    ]
    if cfg.obsidian_daily_dir:
        lines.append(f"obsidian_daily_dir = {q(_home_relative(cfg.obsidian_daily_dir))}")
    lines += ["", "# host name = ssh alias, for hosts reachable with VS Code Remote-SSH"]
    lines += ["[remotes]"]
    lines += [f"{q(host)} = {q(alias)}" for host, alias in sorted(cfg.remotes.items())]
    return "\n".join(lines) + "\n"


def save(cfg: Config) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(cfg), encoding="utf-8")
    return path
