"""Incremental reader for Codex rollout transcripts. Standard library only.

Field names were checked against real rollout files; see docs/transcript-findings.md.
"""

from __future__ import annotations

import re

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


def scan(path: str, state: dict) -> dict:
    """Read new complete lines since state["offset"] and fold them into state."""
    transcript.fold(path, state, _handle)
    state.setdefault("roots", [])
    return state
