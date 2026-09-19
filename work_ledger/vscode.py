"""Prepare a task's VS Code workspace and build the command that opens it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from work_ledger import ledger
from work_ledger.config import Config

MAC_CODE = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"


def code_bin() -> str | None:
    if found := shutil.which("code"):
        return found
    return MAC_CODE if os.path.exists(MAC_CODE) else None


def venv_python(folder: str | Path) -> Path:
    return Path(folder) / ".venv" / "bin" / "python"


def ensure_venv(folder: str | Path, messages: list[str]) -> None:
    """Run `uv sync` in a uv project that has no .venv yet (fresh worktrees)."""
    folder = Path(folder)
    if not (folder / "pyproject.toml").exists() or (folder / ".venv").exists():
        return
    if not shutil.which("uv"):
        messages.append(f"uv not found; skipped creating {folder / '.venv'}")
        return
    messages.append(f"uv sync in {folder}")
    # stdout is reserved for `prepare`'s JSON, so send uv's output to stderr.
    subprocess.run(["uv", "sync"], cwd=folder, stdout=sys.stderr, check=False)


def prepare(cfg: Config, task: dict, sync: bool = True) -> dict:
    """Make the task's folders ready and write its .code-workspace. Run on the task's host."""
    messages: list[str] = []
    folder = task["folder"]
    if not os.path.isdir(folder):
        fallback = task.get("main_repo")
        if not fallback or not os.path.isdir(fallback):
            raise FileNotFoundError(f"{folder} no longer exists")
        messages.append(f"{folder} is gone; using {fallback}")
        folder = fallback
    folders = [folder] + [f for f in task.get("extra_folders") or [] if os.path.isdir(f)]

    if sync:
        for f in folders:
            ensure_venv(f, messages)

    settings = {}
    python = venv_python(folders[0])
    if python.exists():
        settings["python.defaultInterpreterPath"] = str(python)

    workspace = cfg.ledger_dir / "workspaces" / cfg.host / f"{task['id']}.code-workspace"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.write_text(
        json.dumps({"folders": [{"path": f} for f in folders], "settings": settings}, indent=2),
        encoding="utf-8",
    )
    return {
        "workspace": str(workspace),
        "folders": folders,
        "files": ledger.key_files({**task, "folder": folders[0]}, cfg.max_files),
        "interpreter": str(python) if python.exists() else None,
        "messages": messages,
    }


def local_command(prep: dict) -> list[str]:
    return [code_bin() or "code", prep["workspace"], *prep["files"]]


def remote_uri(alias: str, path: str) -> str:
    return f"vscode-remote://ssh-remote+{alias}{quote(path)}"


def remote_command(alias: str, prep: dict) -> list[str]:
    cmd = [code_bin() or "code", "--file-uri", remote_uri(alias, prep["workspace"])]
    for f in prep["files"]:
        cmd += ["--file-uri", remote_uri(alias, f)]
    return cmd
