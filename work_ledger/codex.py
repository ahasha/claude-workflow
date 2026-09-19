"""Incremental reader for Codex rollout transcripts. Standard library only.

Field names were checked against real rollout files; see docs/transcript-findings.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from work_ledger import transcript

ROOT_RE = re.compile(r"<workspace_roots>(.*?)</workspace_roots>", re.S)
ROOT_ENTRY_RE = re.compile(r"<root>([^<]+)</root>")


# Prefixes seen in real rollout files. Anything starting with "<" is a tagged
# context block (environment_context, recommended_plugins, in-app-browser-context…).
BOILERPLATE = (
    "<",
    "# AGENTS.md",
    "# Context from my IDE setup:",
    "The following is the Codex agent history",
)


def is_boilerplate(text: str) -> bool:
    """Codex emits its own instructions as role=user messages; those aren't prompts."""
    return text.startswith(BOILERPLATE)


def text_of(content) -> str:
    """Plain text from a response_item's content list."""
    if not isinstance(content, list):
        return ""
    return " ".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") in ("input_text", "output_text")
    )


def workspace_roots(filesystem: str) -> list[str]:
    """Roots from the `filesystem` field, which holds XML inside a JSON string."""
    block = ROOT_RE.search(filesystem)
    return ROOT_ENTRY_RE.findall(block.group(1)) if block else []


def _handle(entry: dict, state: dict) -> None:
    if isinstance(entry.get("timestamp"), str) and (ts := transcript.norm_ts(entry["timestamp"])):
        state.setdefault("first_timestamp", ts)
        state["last_timestamp"] = ts

    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return

    # session_meta is the launch directory and turn_context the current one; both
    # are fallbacks, since world_state carries the authoritative environment.
    if entry.get("type") in ("session_meta", "turn_context"):
        if isinstance(payload.get("cwd"), str) and payload["cwd"]:
            state.setdefault("cwd", payload["cwd"])
        if isinstance(payload.get("id"), str) and payload["id"]:
            state.setdefault("session_id", payload["id"])

    if entry.get("type") == "response_item" and payload.get("role") == "user":
        text = text_of(payload.get("content")).strip()
        if text and not is_boilerplate(text):
            state.setdefault("first_prompt", transcript.clip(text, transcript.TITLE_MAX))
            state["last_prompt"] = transcript.clip(text, transcript.PROMPT_MAX)

    if entry.get("type") == "world_state":
        env = ((payload.get("state") or {}).get("environments")) or {}
        local = (env.get("environments") or {}).get("local") or {}
        if isinstance(local.get("cwd"), str) and local["cwd"]:
            state["cwd"] = local["cwd"]
        if isinstance(env.get("filesystem"), str):
            roots = workspace_roots(env["filesystem"])
            if roots:
                state["roots"] = roots


def thread_names(index_path) -> dict[str, str]:
    """Session id to thread name, from Codex's session_index.jsonl.

    The index appends a line per rename, so later lines win.
    """
    names: dict[str, str] = {}
    try:
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict) and entry.get("id") and entry.get("thread_name"):
                    names[entry["id"]] = transcript.clip(
                        str(entry["thread_name"]), transcript.TITLE_MAX
                    )
    except OSError:
        return {}
    return names


def scan(path: str, state: dict) -> dict:
    """Read new complete lines since state["offset"] and fold them into state."""
    transcript.fold(path, state, _handle)
    state.setdefault("roots", [])
    return state


# ------------------------------------------------------------------- sweeping

SESSION_DIRS = ("sessions", "archived_sessions")


def find_rollouts(codex_dir: Path) -> list[Path]:
    """Rollout transcripts under the codex dir, oldest first."""
    files: list[Path] = []
    for sub in SESSION_DIRS:
        files.extend((codex_dir / sub).rglob("*.jsonl"))
    return sorted(files, key=lambda f: f.stat().st_mtime)


def watermark_path(cfg) -> Path:
    return cfg.ledger_dir / "state" / cfg.host / "codex-sweep.json"


def read_watermark(cfg) -> dict[str, list]:
    try:
        data = json.loads(watermark_path(cfg).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def clean_roots(roots: list[str], folder: str, codex_dir: Path) -> list[str]:
    """Drop the task's own folder, Codex's internal dirs and roots that are gone."""
    out = []
    for r in roots:
        p = Path(r)
        if r == folder or r in out or not p.is_dir():
            continue
        if p == codex_dir or codex_dir in p.parents:
            continue
        out.append(r)
    return out


def sweep(cfg) -> list[dict]:
    """Fold Codex rollouts written since the last sweep into the ledger."""
    from work_ledger import hook

    codex_dir = Path(cfg.codex_dir)
    if not codex_dir.is_dir():
        return []

    seen = read_watermark(cfg)
    names = thread_names(codex_dir / "session_index.jsonl")
    records = []
    for path in find_rollouts(codex_dir):
        stat = path.stat()
        stamp = [stat.st_mtime, stat.st_size]
        if seen.get(str(path)) == stamp:
            continue
        seen[str(path)] = stamp

        state = scan(str(path), {"path": str(path)})
        if not state.get("cwd"):
            continue
        sid = state.get("session_id") or path.stem
        record_id = f"codex-{sid}"
        record_path = hook.session_path(cfg, record_id)
        existing = hook.read_existing(record_path) if record_path.exists() else {}
        # The index's thread name is this session's title; it beats a first prompt.
        if name := names.get(sid):
            state["ai_title"] = name

        payload = {
            "session_id": record_id,
            "cwd": state["cwd"],
            "transcript_path": str(path),
            "hook_event_name": "codex-sweep",
        }
        record = hook.update_record(
            {**existing, "scan": state},
            payload,
            cfg.host,
            state.get("last_timestamp") or "",
            scan_fn=scan,
        )
        record["source"] = "codex"
        record["roots"] = clean_roots(state.get("roots") or [], record["folder"], codex_dir)
        hook.atomic_write(record_path, record)
        records.append(record)

    wm = watermark_path(cfg)
    wm.parent.mkdir(parents=True, exist_ok=True)
    wm.write_text(json.dumps(seen), encoding="utf-8")
    return records
