"""Incremental reader for Claude Code transcript JSONL. Standard library only.

Field names were checked against a real transcript; see docs/transcript-findings.md.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
TITLE_MAX = 90
PROMPT_MAX = 200
MAX_FILES = 100


def clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def text_of(content) -> str:
    """Plain text from a message's content field (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def norm_ts(ts: str) -> str | None:
    """Transcript timestamps ("...T19:23:00.123Z") in the ledger's format ("...+00:00")."""
    try:
        return datetime.fromisoformat(ts).astimezone(UTC).isoformat(timespec="seconds")
    except ValueError:
        return None


def _handle(entry: dict, state: dict) -> None:
    if isinstance(entry.get("timestamp"), str) and (ts := norm_ts(entry["timestamp"])):
        state.setdefault("first_timestamp", ts)
        state["last_timestamp"] = ts
    if isinstance(entry.get("cwd"), str) and entry["cwd"]:
        state.setdefault("cwd", entry["cwd"])
    if isinstance(entry.get("gitBranch"), str) and entry["gitBranch"]:
        state["git_branch"] = entry["gitBranch"]
    if entry.get("aiTitle"):
        state["ai_title"] = clip(str(entry["aiTitle"]), TITLE_MAX)
    if entry.get("lastPrompt"):
        state["last_prompt"] = clip(str(entry["lastPrompt"]), PROMPT_MAX)
    for key, name in (("entrypoint", "entrypoint"), ("sessionKind", "session_kind")):
        if isinstance(entry.get(key), str):
            state[name] = entry[key]
    if "worktreeSession" in entry:
        ws = entry["worktreeSession"]
        state["worktree_path"] = ws.get("worktreePath") if isinstance(ws, dict) else None

    msg = entry.get("message")
    if not isinstance(msg, dict):
        return
    kind = entry.get("type")

    if kind == "user" and not state.get("first_prompt"):
        if entry.get("isMeta") or entry.get("toolUseResult"):
            return
        text = text_of(msg.get("content")).strip()
        # Skip slash-command wrappers, caveats and other system-injected text.
        if text and not text.startswith("<"):
            state["first_prompt"] = clip(text, TITLE_MAX)

    elif kind == "assistant" and isinstance(msg.get("content"), list):
        files = state.setdefault("claude_files", [])
        for block in msg["content"]:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            if block.get("name") not in EDIT_TOOLS:
                continue
            args = block.get("input") or {}
            path = args.get("file_path") or args.get("notebook_path")
            if isinstance(path, str) and path:
                if path in files:
                    files.remove(path)
                files.append(path)  # most recent last
        del files[:-MAX_FILES]


def scan(path: str, state: dict) -> dict:
    """Read new complete lines since state["offset"] and fold them into state."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return state
    offset = state.get("offset", 0)
    if size < offset:  # rewritten or truncated: start over
        state.clear()
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read()
    end = chunk.rfind(b"\n")
    if end < 0:
        return state
    for line in chunk[: end + 1].splitlines():
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(entry, dict):
            _handle(entry, state)
    state["offset"] = offset + end + 1
    return state
