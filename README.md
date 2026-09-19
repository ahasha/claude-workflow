# work-ledger

Stop remembering which machine, repo, branch, and worktree a piece of work lives in. A Claude Code hook records that for every session, and `resume` takes you back to any of them from anywhere.

```
$ resume dedupe
  2h * vm         retroscore:retroscore-dedupe (wt)   Dedupe the retroscore backfill rows by…
  3d   laptop     capc-tools:main                     [next: add tests] Parse the agenda PDF…
```

Pick a row and you're back in that Claude conversation, in the right folder, on the right host.

## How it works

1. **`hooks/record_session.py`** runs on Claude Code's `Stop` and `SessionEnd` events. It reads the session ID and working directory Claude Code passes on stdin, asks git for the repo, branch, and worktree, takes the first prompt from the transcript as a title, and writes `~/.work-ledger/sessions/<host>/<session_id>.json`. Stdlib only, never exits non-zero, so it can't break a session.
2. **`bin/resume`** is a click CLI that reads those records (plus any remote host's, over ssh), shows them in fzf, and runs `claude --resume <id>` from the session's original folder.
3. **uv** runs `resume` as a single-file script with its click dependency declared inline (PEP 723). No venv to manage.

## Install

On each machine (laptop and VM):

```bash
./install.sh
```

This copies everything to `~/.work-ledger`, links `resume` into `~/.local/bin`, and merges the two hooks into `~/.claude/settings.json` (existing settings and hooks are kept; a `.bak` is written first). Re-running is safe.

Then:

- Add `source ~/.work-ledger/config/shell.sh` to your shell rc.
- Paste `config/CLAUDE.md-additions.md` into `~/.claude/CLAUDE.md`. These rules make venvs and worktree locations predictable, which is what keeps the ledger meaningful.
- Install fzf if you don't have it. Without it you get a numbered menu.

Requires uv, git, and python3 on each host.

## Daily use

| Command | Does |
|---|---|
| `resume [words]` | Pick a session and resume it in Claude Code |
| `resume code [words]` | Open its folder in VS Code (Remote-SSH for VM sessions) |
| `wcd [words]` | `cd` into its folder without starting Claude (local only) |
| `resume list` | Recent sessions, newest first |
| `resume note -m "next: tests" [words]` | Tag a session so it's recognizable later |
| `resume archive [words]` | Hide a finished session (run again to unhide) |

`*` in the list means the folder has uncommitted changes. `(wt)` means it's a worktree. Sessions older than 60 days are hidden; change with `WORK_LEDGER_DAYS`.

Weekly cleanup: run `claude -p "$(cat ~/.work-ledger/prompts/weekly-sweep.md)"`. Claude checks every recorded folder for uncommitted work and merged branches, then proposes what to archive or remove. It only prints commands; it doesn't run them.

## Laptop + VM

Pick one:

- **Read over ssh (default).** On the laptop, set `export WORK_LEDGER_REMOTES="vm"` (your ssh alias). `resume` then lists VM sessions too, and picking one runs `ssh -t vm` into Claude there, or opens VS Code Remote-SSH. Leave `WORK_LEDGER_REMOTES` empty on the VM.
- **Sync the directory.** Put `~/.work-ledger/sessions` under Syncthing or a git repo. Records never conflict because each host writes only its own subfolder. You'd still use the ssh alias to actually resume a VM session.

If you move most development onto the VM and treat the laptop as a thin client, the host dimension mostly goes away.

## Obsidian (optional)

Set `WORK_LEDGER_OBSIDIAN_DAILY_DIR` to your vault root. When a session ends, the hook appends a line like `- 14:32 Claude [vm] retroscore:retroscore-dedupe — Dedupe the…` to today's `YYYY-MM-DD.md`. It only appends to a note that already exists, so your daily-note template stays in charge of creating it.

## Things to know

- **Sessions start being recorded after install.** Earlier sessions won't appear.
- **Removed worktrees.** If a session's folder is gone, `resume` falls back to the main repo and says so. Claude Code stores conversations per launch directory, so `claude --resume` may not find the session from there. Recreate the worktree at the same path if you need the conversation back.
- **The hook runs after every Claude reply.** It shells out to git three times and reads the transcript only until it has a title; this takes tens of milliseconds.
- **Hook input format.** The script relies on `session_id`, `cwd`, `transcript_path`, and `hook_event_name` in the hook payload, and on user messages in the transcript JSONL. If a Claude Code update changes those, the title or git fields may go blank; the hook still won't error.
- **Host name** comes from `hostname`. Override with `WORK_LEDGER_HOST` if your VM's hostname is something unhelpful.

## Files

```
bin/resume                      click CLI (uv inline-script)
hooks/record_session.py         Claude Code hook, stdlib only
config/settings.hooks.json      hook config merged into ~/.claude/settings.json
config/shell.sh                 wcd function, aliases, env var examples
config/CLAUDE.md-additions.md   venv, worktree, and handoff rules for Claude
prompts/weekly-sweep.md         cleanup prompt
install.sh                      installer
```
