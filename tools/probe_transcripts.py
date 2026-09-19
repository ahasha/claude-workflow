#!/usr/bin/env python3
"""Report the shape of recent Claude Code transcripts.

Checks the assumptions work_ledger/transcript.py makes about transcript JSONL.

Usage (from the repo root): uv run tools/probe_transcripts.py [N]
(N most recent transcripts, default 10)
Prints key names, types and counts. Titles are printed so you can judge them;
no other message text is shown.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from work_ledger.transcript import scan

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
root = Path.home() / ".claude" / "projects"
if not root.is_dir():
    sys.exit(f"no transcripts: {root} does not exist")
all_files = list(root.rglob("*.jsonl"))
top_level = [p for p in all_files if p.parent.parent == root]
files = sorted(top_level, key=lambda p: p.stat().st_mtime, reverse=True)[:n]

entry_types: Counter = Counter()
top_keys: Counter = Counter()
user_content_kinds: Counter = Counter()
user_block_types: Counter = Counter()
user_flags: Counter = Counter()
bad_lines = 0

for f in files:
    for line in f.open(encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        entry_types[e.get("type")] += 1
        top_keys.update(e.keys())
        if e.get("type") != "user":
            continue
        for flag in ("isMeta", "isSidechain", "isCompactSummary", "toolUseResult"):
            if e.get(flag):
                user_flags[flag] += 1
        c = (e.get("message") or {}).get("content")
        user_content_kinds[type(c).__name__] += 1
        if isinstance(c, list):
            user_block_types.update(b.get("type") for b in c if isinstance(b, dict))


def show(title: str, c: Counter) -> None:
    print(f"\n## {title}")
    for k, v in c.most_common():
        print(f"  {v:6d}  {k}")


print(f"# {len(files)} transcripts under {root}  (unparseable lines: {bad_lines})")
print(
    f"# .jsonl files: {len(all_files)} total, {len(top_level)} at <project>/<session>.jsonl, "
    f"{len(all_files) - len(top_level)} nested deeper"
)
print(f"# project dirs: {sum(1 for d in root.iterdir() if d.is_dir())}")
show("entry type", entry_types)
show("top-level keys", top_keys)
show("user message.content kind", user_content_kinds)
show("user content block types", user_block_types)
show("user entry flags", user_flags)


def first_prompt(path: Path) -> str | None:
    return scan(str(path), {}).get("first_prompt")


print("\n## titles first_prompt() would pick")
for f in files:
    print(f"  {f.parent.name[-30:]:>30}  {first_prompt(f)!r}")


# Last value seen per transcript for metadata fields Claude Code maintains itself.
META = [
    "aiTitle",
    "lastPrompt",
    "agentName",
    "slug",
    "sessionKind",
    "entrypoint",
    "cwd",
    "gitBranch",
    "relocatedCwd",
    "worktreeSession",
]


def clip(v, width=100) -> str:
    s = v if isinstance(v, str) else json.dumps(v)
    s = " ".join(s.split())
    return s if len(s) <= width else s[: width - 1] + "…"


print("\n## metadata (last value per transcript)")
for f in files:
    last: dict = {}
    for line in f.open(encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        for k in META:
            if e.get(k) not in (None, ""):
                last[k] = e[k]
    print(f"\n  {f.name}")
    for k in META:
        if k in last:
            print(f"    {k:16} {clip(last[k], 200 if k == 'worktreeSession' else 100)}")
