"""Follow a repo that moved: fold the old location's records into the new one.

Runs from the hook the first time a session is recorded in a repo. A record is
stale when its main repo is no longer a git checkout on this host (an empty
leftover folder counts) and it belongs to the same repo (same root commit;
older records without one match on repo name).
Its paths are rebased onto the new location, so it groups with the new
sessions, and its task metadata (note, title, archived) moves too.

Standard library only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from work_ledger import hook
from work_ledger.config import Config

PATH_FIELDS = ("folder", "main_repo", "last_cwd")


def rebase(path: str, old: str, new: str) -> str:
    if path == old or path.startswith(old + os.sep):
        return new + path[len(old) :]
    return path


def is_stale(rec: dict, record: dict) -> bool:
    old = rec.get("main_repo")
    if not old or old == record["main_repo"] or os.path.exists(os.path.join(old, ".git")):
        return False
    if rec.get("repo_id"):
        return rec["repo_id"] == record["repo_id"]
    return rec.get("repo") == record.get("repo")


def move_meta(cfg: Config, old_folder: str, new_folder: str) -> None:
    """Carry task metadata to the new task id; anything already there wins."""
    from work_ledger.ledger import task_id  # avoids an import cycle at load time

    old = cfg.ledger_dir / "tasks" / cfg.host / f"{task_id(cfg.host, old_folder)}.json"
    new = cfg.ledger_dir / "tasks" / cfg.host / f"{task_id(cfg.host, new_folder)}.json"
    if not old.exists() or old == new:
        return
    old_meta = hook.read_existing(old)
    new_meta = hook.read_existing(new)
    merged = {**old_meta, **new_meta, "folder": new_folder}
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    old.unlink()


def reconcile(cfg: Config, record: dict) -> int:
    """Rewrite stale records of this host to `record`'s repo. Returns how many moved."""
    new_main = record.get("main_repo")
    if not new_main or not record.get("repo_id") or not os.path.isdir(new_main):
        return 0

    moved = 0
    for path in Path(cfg.ledger_dir, "sessions", cfg.host).glob("*.json"):
        rec = hook.read_existing(path)
        if rec.get("session_id") == record["session_id"] or not is_stale(rec, record):
            continue
        old_main = rec["main_repo"]
        old_folder = rec.get("folder")
        for key in PATH_FIELDS:
            if rec.get(key):
                rec[key] = rebase(rec[key], old_main, new_main)
        rec["claude_files"] = [rebase(f, old_main, new_main) for f in rec.get("claude_files") or []]
        rec["repo_id"] = record["repo_id"]
        rec["moved_from"] = old_main
        hook.atomic_write(path, rec)
        if old_folder and old_folder != rec["folder"]:
            move_meta(cfg, old_folder, rec["folder"])
        moved += 1
    return moved
