"""Build ledger records from transcripts Claude Code still has on this machine."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from work_ledger import hook, transcript
from work_ledger.config import Config


def find_transcripts(claude_dir: Path, days: int = 0) -> list[Path]:
    """Top-level session transcripts (<project>/<session>.jsonl), oldest first."""
    files = list((claude_dir / "projects").glob("*/*.jsonl"))
    if days > 0:
        cutoff = time.time() - days * 86400
        files = [f for f in files if f.stat().st_mtime >= cutoff]
    return sorted(files, key=lambda f: f.stat().st_mtime)


def backfill(
    cfg: Config, claude_dir: Path, days: int = 0, force: bool = False, dry_run: bool = False
) -> list[tuple[str, dict]]:
    """Returns (status, record) pairs; status is added, updated, exists or empty."""
    results: list[tuple[str, dict]] = []
    for t in find_transcripts(claude_dir, days):
        sid = t.stem
        path = hook.session_path(cfg, sid)
        existing = hook.read_existing(path) if path.exists() else {}
        if existing and not force:
            results.append(("exists", existing))
            continue

        state = transcript.scan(str(t), {"path": str(t)})
        if not state.get("cwd") or not (state.get("first_prompt") or state.get("ai_title")):
            results.append(("empty", {"session_id": sid, "transcript_path": str(t)}))
            continue

        mtime = datetime.fromtimestamp(t.stat().st_mtime, UTC).isoformat(timespec="seconds")
        payload = {
            "session_id": sid,
            "cwd": state["cwd"],
            "transcript_path": str(t),
            "hook_event_name": "backfill",
        }
        record = hook.update_record(
            {**existing, "scan": state}, payload, cfg.host, state.get("last_timestamp") or mtime
        )
        if not dry_run:
            hook.atomic_write(path, record)
        results.append(("updated" if existing else "added", record))
    return results
