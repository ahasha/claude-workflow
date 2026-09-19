#!/usr/bin/env python3
"""Claude Code hook: record where a session is happening.

Wire this to the Stop and SessionEnd hook events. Claude Code passes a JSON
object on stdin containing session_id, cwd, transcript_path and
hook_event_name. This script writes one JSON file per session to

    $WORK_LEDGER_DIR/sessions/<host>/<session_id>.json

Writing one file per session means no locking, and the directory can be
synced (git, rsync, Syncthing) without merge conflicts.

Stdlib only. Must stay fast and must never fail loudly: a hook error should
not interrupt your Claude session, so every failure path exits 0.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LEDGER_DIR = Path(os.environ.get("WORK_LEDGER_DIR", Path.home() / ".work-ledger"))
HOST = os.environ.get("WORK_LEDGER_HOST") or socket.gethostname().split(".")[0]
TITLE_MAX = 90


def git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_info(cwd: str) -> dict:
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return {"repo_root": None, "repo": None, "branch": None,
                "is_worktree": False, "main_repo": None, "dirty_files": None}

    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = "(detached " + (git(cwd, "rev-parse", "--short", "HEAD") or "?") + ")"

    # In a linked worktree, --git-common-dir points at the main repo's .git.
    common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main_repo = str(Path(common).parent) if common else top
    is_worktree = Path(main_repo).resolve() != Path(top).resolve()

    status = git(cwd, "status", "--porcelain")
    dirty = len(status.splitlines()) if status is not None else None

    return {
        "repo_root": top,
        "repo": Path(main_repo).name,
        "branch": branch,
        "is_worktree": is_worktree,
        "main_repo": main_repo,
        "dirty_files": dirty,
    }


def text_of(content) -> str:
    """Pull plain text out of a transcript message's content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def first_prompt(transcript_path: str | None) -> str | None:
    """Return the first real user prompt in the transcript, as a title."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "user" or entry.get("isMeta"):
                    continue
                msg = entry.get("message") or {}
                text = text_of(msg.get("content")).strip()
                # Skip slash-command wrappers, caveats, and tool results.
                if not text or text.startswith("<"):
                    continue
                text = " ".join(text.split())
                return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1] + "…"
    except OSError:
        return None
    return None


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def append_obsidian_daily(record: dict) -> None:
    """Optionally log a line to today's Obsidian daily note.

    Only appends if the note already exists, so Obsidian's own daily-note
    template stays in charge of creating it.
    """
    vault = os.environ.get("WORK_LEDGER_OBSIDIAN_DAILY_DIR")
    if not vault:
        return
    note = Path(vault).expanduser() / f"{datetime.now():%Y-%m-%d}.md"
    if not note.exists():
        return
    where = record.get("repo") or Path(record["project_dir"]).name
    if record.get("branch"):
        where += f":{record['branch']}"
    line = (f"- {datetime.now():%H:%M} Claude [{record['host']}] {where} — "
            f"{record.get('title') or '(untitled)'}\n")
    with open(note, "a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or os.getcwd()
    if not session_id:
        return

    event = payload.get("hook_event_name", "unknown")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = LEDGER_DIR / "sessions" / HOST / f"{session_id}.json"

    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    record = {
        **existing,
        "session_id": session_id,
        "host": HOST,
        # Claude Code stores sessions by launch directory, and `claude --resume`
        # must run from there. Keep the first cwd we saw.
        "project_dir": existing.get("project_dir") or cwd,
        "last_cwd": cwd,
        "transcript_path": payload.get("transcript_path"),
        "first_seen": existing.get("first_seen") or now,
        "last_seen": now,
        "last_event": event,
        **git_info(existing.get("project_dir") or cwd),
    }

    # Parsing the transcript is cheap but not free; only do it until we have a title.
    if not record.get("title"):
        record["title"] = first_prompt(payload.get("transcript_path"))

    # User-owned fields (note, archived) are carried over via **existing.
    record.setdefault("note", None)
    record.setdefault("archived", False)

    if event == "SessionEnd" and not existing.get("logged_to_obsidian"):
        try:
            append_obsidian_daily(record)
            record["logged_to_obsidian"] = True
        except OSError:
            pass

    atomic_write(path, record)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never break the user's Claude session
        pass
    sys.exit(0)
