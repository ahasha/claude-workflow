from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("WORK_LEDGER_HOST", "testhost")
    monkeypatch.setenv("WORK_LEDGER_DIR", str(home / ".work-ledger"))
    monkeypatch.delenv("WORK_LEDGER_CONFIG", raising=False)
    for var, val in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }.items():
        monkeypatch.setenv(var, val)
    return home


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    """A repo on main with one commit, plus a linked worktree on branch `feature`."""
    r = tmp_path / "proj"
    r.mkdir()
    sh(r, "git", "init", "-q", "-b", "main")
    (r / "a.py").write_text("a = 1\n")
    (r / "b.py").write_text("b = 1\n")
    sh(r, "git", "add", ".")
    sh(r, "git", "commit", "-q", "-m", "init")
    sh(r, "git", "worktree", "add", "-q", "-b", "feature", str(r / ".claude/worktrees/feature"))
    return r


def write_transcript(path: Path, entries: list[dict], mode: str = "w") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode) as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


def edit(path: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]
        },
    }


def user(text) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}
