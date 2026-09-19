"""Read session records and group them into tasks (one working folder on one host)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from work_ledger import gitinfo, hook, relocate
from work_ledger.config import Config

USER_FIELDS = ("note", "archived", "extra_folders")


def task_id(host: str, folder: str) -> str:
    return hashlib.sha1(f"{host}:{folder}".encode()).hexdigest()[:8]


def parse_ts(ts: str | None) -> datetime:
    floor = datetime.min.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(ts) if ts else floor
    except ValueError:
        return floor


# ------------------------------------------------------------------ sessions


def read_local_sessions(cfg: Config) -> list[dict]:
    records = []
    for path in (cfg.ledger_dir / "sessions").glob("*/*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict) and rec.get("session_id"):
            records.append(rec)
    return records


def fetch_remote(cfg: Config, alias: str) -> list[dict]:
    """Ask a remote host for its own records (for ledgers that aren't synced)."""
    cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=4",
        "-o",
        "BatchMode=yes",
        alias,
        f"{cfg.remote_command} dump",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    records = []
    for line in out.stdout.splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def load_sessions(cfg: Config, local_only: bool = False) -> list[dict]:
    records = read_local_sessions(cfg)
    if local_only:
        return records
    hosts = {r.get("host") for r in records}
    for host, alias in cfg.remotes.items():
        # A synced ledger already has this host's records.
        if host != cfg.host and host not in hosts:
            records += [r for r in fetch_remote(cfg, alias) if r.get("host") == host]
    return records


# ------------------------------------------------------------------ tasks


def meta_path(cfg: Config, host: str, tid: str) -> Path:
    return cfg.ledger_dir / "tasks" / host / f"{tid}.json"


def load_meta(cfg: Config, host: str, tid: str) -> dict:
    try:
        return json.loads(meta_path(cfg, host, tid).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_meta(cfg: Config, task: dict, **changes) -> None:
    path = meta_path(cfg, task["host"], task["id"])
    data = load_meta(cfg, task["host"], task["id"])
    data.update(changes, host=task["host"], folder=task["folder"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_manual(cfg: Config, folder: str) -> dict:
    """Record a task for work done outside local Claude Code (Cowork, by hand).

    Writes a session-style record, so it groups with any Claude sessions in the
    same folder. Re-running it marks the task as touched now.
    """
    top = gitinfo.toplevel(folder) or folder
    sid = f"manual-{task_id(cfg.host, top)}"
    path = hook.session_path(cfg, sid)
    existing = hook.read_existing(path) if path.exists() else {}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    record = {
        **existing,
        "session_id": sid,
        "source": "manual",
        "host": cfg.host,
        "folder": top,
        "cwd": top,
        "first_seen": existing.get("first_seen") or now,
        "last_seen": now,
        "last_event": "manual",
        **gitinfo.info(top),
    }
    hook.atomic_write(path, record)
    relocate.reconcile(cfg, record)
    return record


def build_tasks(sessions: list[dict], cfg: Config) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for s in sessions:
        folder = s.get("folder") or s.get("repo_root") or s.get("project_dir") or s.get("cwd")
        if not folder:
            continue
        groups.setdefault((s.get("host", "?"), folder), []).append(s)

    tasks = []
    for (host, folder), group in groups.items():
        # Records written in the same second tie on last_seen; tie-break so the
        # order never depends on which file the glob happened to read first.
        group.sort(
            key=lambda s: (s.get("last_seen") or "", s.get("first_seen") or "", s["session_id"])
        )
        latest = group[-1]

        claude_files: list[str] = []
        for s in group:
            for f in s.get("claude_files") or []:
                if f in claude_files:
                    claude_files.remove(f)
                claude_files.append(f)

        def last(key: str, group=group):
            return next((s[key] for s in reversed(group) if s.get(key)), None)

        tid = task_id(host, folder)
        task = {
            "id": tid,
            "host": host,
            "folder": folder,
            "repo": latest.get("repo"),
            "main_repo": latest.get("main_repo"),
            "branch": latest.get("branch"),
            "is_worktree": bool(latest.get("is_worktree")),
            "title": last("title"),
            "last_prompt": last("last_prompt"),
            "first_seen": min(s.get("first_seen") or "" for s in group),
            "last_seen": latest.get("last_seen"),
            "claude_files": claude_files,
            "dirty_files": latest.get("dirty_files") or [],
            "branch_files": latest.get("branch_files") or [],
            "sessions": [
                {
                    k: s.get(k)
                    for k in ("session_id", "cwd", "last_seen", "title", "entrypoint", "source")
                }
                for s in reversed(group)
            ],
            "note": None,
            "archived": False,
            "extra_folders": [],
        }
        meta = load_meta(cfg, host, tid)
        task.update({k: meta[k] for k in USER_FIELDS if k in meta})
        if meta.get("title"):  # set with `wl add -t`; wins over Claude's titles
            task["title"] = meta["title"]
        tasks.append(task)

    tasks.sort(key=lambda t: t.get("last_seen") or "", reverse=True)
    return tasks


def load_tasks(
    cfg: Config, include_archived: bool = False, local_only: bool = False, days: int | None = None
) -> list[dict]:
    tasks = build_tasks(load_sessions(cfg, local_only=local_only), cfg)
    if not include_archived:
        tasks = [t for t in tasks if not t.get("archived")]
    days = cfg.days if days is None else days
    if days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        tasks = [t for t in tasks if parse_ts(t.get("last_seen")) >= cutoff]
    return tasks


def find_task(cfg: Config, tid: str) -> dict | None:
    for t in load_tasks(cfg, include_archived=True, local_only=True, days=0):
        if t["id"] == tid:
            return t
    return None


def key_files(task: dict, max_files: int) -> list[str]:
    """Files worth opening, most relevant first. Checks existence, so run on the task's host."""
    roots = [Path(task["folder"])] + [Path(f) for f in task.get("extra_folders") or []]
    folder = roots[0]
    candidates = (
        list(reversed(task.get("claude_files") or []))
        + [str(folder / p) for p in task.get("dirty_files") or []]
        + [str(folder / p) for p in task.get("branch_files") or []]
    )
    out: list[str] = []
    for c in candidates:
        path = os.path.normpath(c)
        if path in out or not os.path.isfile(path):
            continue
        if not any(Path(path).is_relative_to(r) for r in roots):
            continue  # e.g. edits to ~/.claude/CLAUDE.md
        out.append(path)
        if len(out) >= max_files:
            break
    return out
