#!/usr/bin/env bash
# Install work-ledger on this machine. Safe to re-run.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${WORK_LEDGER_DIR:-$HOME/.work-ledger}"
BIN="$HOME/.local/bin"
SETTINGS="$HOME/.claude/settings.json"

command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/)"; exit 1; }
command -v fzf >/dev/null || echo "note: fzf not found; resume will use a numbered menu instead."

mkdir -p "$DEST"/{bin,hooks,config,prompts,sessions} "$BIN" "$(dirname "$SETTINGS")"
cp "$SRC"/bin/resume "$DEST"/bin/
cp "$SRC"/hooks/record_session.py "$DEST"/hooks/
cp "$SRC"/config/* "$DEST"/config/
cp "$SRC"/prompts/* "$DEST"/prompts/
chmod +x "$DEST"/bin/resume "$DEST"/hooks/record_session.py
ln -sf "$DEST/bin/resume" "$BIN/resume"

# Warm uv's cache so the first `resume` (and remote `resume dump`) is fast.
"$DEST/bin/resume" --help >/dev/null

# Merge the hooks into ~/.claude/settings.json, keeping a backup and any existing hooks.
python3 - "$SETTINGS" "$DEST/config/settings.hooks.json" <<'PY'
import json, shutil, sys
from pathlib import Path

settings_path, snippet_path = Path(sys.argv[1]), Path(sys.argv[2])
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
if settings_path.exists():
    shutil.copy(settings_path, settings_path.with_suffix(".json.bak"))

snippet = json.loads(snippet_path.read_text())
hooks = settings.setdefault("hooks", {})
for event, groups in snippet["hooks"].items():
    existing = hooks.setdefault(event, [])
    commands = {h.get("command") for g in existing for h in g.get("hooks", [])}
    for group in groups:
        if not any(h["command"] in commands for h in group["hooks"]):
            existing.append(group)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"hooks merged into {settings_path}")
PY

cat <<MSG

Installed to $DEST.
Next steps:
  1. Add to your shell rc:   source $DEST/config/shell.sh
  2. Make sure $BIN is on your PATH.
  3. Paste $DEST/config/CLAUDE.md-additions.md into ~/.claude/CLAUDE.md.
  4. Use Claude Code as normal, then run: resume
MSG
