"""Claude Code hook: record where a session is working and what it touched.

Wired to the Stop and SessionEnd events by `work-ledger install`. Claude Code
sends JSON on stdin with session_id, transcript_path, cwd and hook_event_name.
Writes one file per session:

    <ledger_dir>/sessions/<host>/<session_id>.json

Standard library only, so it starts fast. Never fails loudly: every error
path exits 0 so a hook problem can't interrupt a Claude session.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from work_ledger import config, gitinfo, transcript


def update_record(existing: dict, payload: dict, host: str, now: str) -> dict:
    cwd = payload.get("cwd") or os.getcwd()
    tpath = payload.get("transcript_path")

    scan_state = dict(existing.get("scan") or {})
    if tpath:
        if scan_state.get("path") != tpath:
            scan_state = {"path": tpath}
        transcript.scan(tpath, scan_state)
        scan_state["path"] = tpath

    # In a Claude Code worktree session, cwd can stay at the main repo.
    wt = scan_state.get("worktree_path")
    if wt and os.path.isdir(wt):
        folder = gitinfo.toplevel(wt) or wt
    else:
        folder = gitinfo.toplevel(cwd) or cwd

    title = (
        payload.get("session_title")
        or scan_state.get("ai_title")
        or scan_state.get("first_prompt")
        or existing.get("title")
    )

    return {
        **existing,
        "session_id": payload["session_id"],
        "host": host,
        "folder": folder,
        # `claude --resume` must run from the launch directory; keep the first cwd.
        "cwd": existing.get("cwd") or cwd,
        "last_cwd": cwd,
        "transcript_path": tpath,
        "first_seen": existing.get("first_seen") or now,
        "last_seen": now,
        "last_event": payload.get("hook_event_name", "unknown"),
        "title": title,
        "last_prompt": scan_state.get("last_prompt") or existing.get("last_prompt"),
        "claude_files": scan_state.get("claude_files", []),
        # Which app ran the session (e.g. "cli"); see docs/transcript-findings.md.
        "entrypoint": scan_state.get("entrypoint") or existing.get("entrypoint"),
        "session_kind": scan_state.get("session_kind") or existing.get("session_kind"),
        **gitinfo.info(folder),
        "scan": scan_state,
    }


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def append_obsidian_daily(daily_dir: Path, record: dict) -> None:
    """Log a line to today's daily note, only if the note already exists."""
    note = daily_dir / f"{datetime.now():%Y-%m-%d}.md"
    if not note.exists():
        return
    where = record.get("repo") or Path(record["folder"]).name
    if record.get("branch"):
        where += f":{record['branch']}"
    line = (
        f"- {datetime.now():%H:%M} Claude [{record['host']}] {where} — "
        f"{record.get('title') or '(untitled)'}\n"
    )
    with open(note, "a", encoding="utf-8") as f:
        f.write(line)


def run(stdin=None) -> None:
    try:
        payload = json.load(stdin or sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if not isinstance(payload, dict) or not payload.get("session_id"):
        return

    cfg = config.load()
    path = cfg.ledger_dir / "sessions" / cfg.host / f"{payload['session_id']}.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    now = datetime.now(UTC).isoformat(timespec="seconds")
    record = update_record(existing, payload, cfg.host, now)

    if (
        payload.get("hook_event_name") == "SessionEnd"
        and cfg.obsidian_daily_dir
        and not existing.get("logged_to_obsidian")
    ):
        try:
            append_obsidian_daily(cfg.obsidian_daily_dir, record)
            record["logged_to_obsidian"] = True
        except OSError:
            pass

    atomic_write(path, record)


def main() -> None:
    try:
        run()
    except Exception:  # never break the user's Claude session
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
