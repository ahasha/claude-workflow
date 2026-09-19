"""Wire the hook into Claude Code's user settings."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

# Hook commands from this package or the earlier prototype, replaced on install.
OUR_MARKERS = ("record_session.py", "work-ledger-hook", "work_ledger.hook")
EVENTS = {"Stop": None, "SessionEnd": 10}  # event -> timeout in seconds (SessionEnd default is 1.5)


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def claude_settings_path() -> Path:
    return claude_dir() / "settings.json"


def hook_command() -> str:
    """Absolute path to the hook, since hooks may not see ~/.local/bin on PATH."""
    beside = Path(sys.executable).parent / "work-ledger-hook"
    if beside.exists():
        return shlex.quote(str(beside))
    if found := shutil.which("work-ledger-hook"):
        return shlex.quote(found)
    return f"{shlex.quote(sys.executable)} -m work_ledger.hook"


def is_ours(hook: dict) -> bool:
    return any(m in str(hook.get("command", "")) for m in OUR_MARKERS)


def merge_hooks(settings: dict, command: str) -> dict:
    hooks = settings.setdefault("hooks", {})
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = [h for h in group.get("hooks", []) if not is_ours(h)]
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    for event, timeout in EVENTS.items():
        entry: dict = {"type": "command", "command": command}
        if timeout:
            entry["timeout"] = timeout
        hooks.setdefault(event, []).append({"hooks": [entry]})
    return settings


def apply(settings_path: Path, command: str, retention_days: int | None) -> Path | None:
    """Update Claude Code settings in place. Returns the backup path, if one was made."""
    settings: dict = {}
    backup = None
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        backup = settings_path.with_suffix(".json.bak")
        shutil.copy(settings_path, backup)
    merge_hooks(settings, command)
    if retention_days:
        settings["cleanupPeriodDays"] = retention_days
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return backup
