# work-ledger

Find a unit of Claude Code work and reopen it in VS Code: the right folder, the key files open, and the task's `.venv` as the Python interpreter. Works on macOS and Linux, across several machines.

A Claude Code hook records each session: which host, which worktree and branch, what it was about, and which files it touched. `wl` groups sessions into **tasks** (one working folder on one host) and lets you fuzzy-pick one.

## Install (each machine)

```sh
uv tool install git+https://github.com/ahasha/claude-workflow
work-ledger install --host mbp                  # pick a fixed name per machine
```

`install` is safe to re-run. It:
- writes `~/.config/work-ledger/config.toml`
- adds the hook to `~/.claude/settings.json` (Stop and SessionEnd), keeping a `.bak`
- replaces hooks from the earlier `~/.work-ledger/hooks/record_session.py` prototype

Useful options:
- `--remote vm=devbox`: a host VS Code can reach with Remote-SSH (`devbox` is the ssh alias). Repeatable.
- `--ledger-dir ~/Sync/work-ledger`: put the ledger in a synced folder so every machine sees every task.
- `--retention-days 3650`: keep Claude Code transcripts longer than the default 30 days, so `wl claude` can resume old sessions.

Also recommended:
- `fzf` for the picker (`brew install fzf` / `apt install fzf`). Without it you get a numbered menu.
- VS Code's `code` command on PATH (on macOS: Command Palette → "Shell Command: Install 'code' command in PATH").
- Paste `config/CLAUDE.md-additions.md` into `~/.claude/CLAUDE.md`.

Upgrade with `uv tool upgrade work-ledger`.

## Use

```sh
wl                     # pick a task, open it in VS Code
wl retroscore          # same, pre-filtered
wl claude [words]      # resume the task's latest Claude session instead
wl list                # recent tasks, newest first
wl show [words]        # details: files, sessions, last prompt
wl note -m "next: write tests" [words]
wl archive [words]     # hide a finished task (toggle)
wl add [folder] -t "title"            # task for work Claude Code didn't record (e.g. Cowork)
wl add ~/repos/other --to [words]     # multi-repo task: add a folder to the workspace
cd "$(wl path)"
wl backfill            # add sessions from before install (see below)
```

New sessions are recorded automatically by the hook after every Claude response. `wl backfill` adds older sessions from the transcripts Claude Code still keeps in `~/.claude/projects` (30 days by default). It uses the transcript's own timestamps, skips sessions already in the ledger (`--force` rebuilds them), and supports `--days N` and `--dry-run`. Git facts such as uncommitted files reflect the folder as it is now.

Opening a task:
1. Runs `uv sync` if the folder is a uv project with no `.venv` yet (fresh worktrees).
2. Writes `~/.work-ledger/workspaces/<host>/<task>.code-workspace` with `python.defaultInterpreterPath` set to the task's `.venv`.
3. Opens the workspace plus up to 8 key files: the ones Claude edited most recently, then uncommitted changes, then files changed on the branch.

Tasks on a host in `[remotes]` open through Remote-SSH, with steps 1–2 run on that host over ssh. Tasks on other hosts show which machine they're on.

## Multiple machines

Each host writes only its own `sessions/<host>/` folder, so a synced ledger never conflicts. Without syncing, `wl` fetches `[remotes]` hosts' records over ssh (`work-ledger dump`).

## What gets recorded

| Where the session runs | Recorded |
|---|---|
| Claude Code CLI | Yes |
| Desktop app Code session, Local environment | Yes (same `~/.claude/settings.json`) |
| Desktop app Code session, SSH environment | Yes, if `work-ledger install` was run on that host |
| Cloud sessions, including cloud Cowork | No. Use `wl add` |

`wl add` writes a manual record, so the folder groups with any later Claude sessions there. A title set with `-t` stays the task's title. Re-running `wl add` marks the task as touched now.

## Layout

```
work_ledger/
  cli.py          click CLI (work-ledger, wl)
  hook.py         the hook (work-ledger-hook); standard library only
  transcript.py   incremental transcript reader
  gitinfo.py      branch, worktree, dirty and branch-changed files
  ledger.py       sessions → tasks, notes/archive, key files
  vscode.py       workspace file, uv sync, code command
  install.py      settings.json merge
  config.py       config.toml + env overrides (WORK_LEDGER_HOST, WORK_LEDGER_DIR)
docs/             design and verified Claude Code data findings
tools/probe_transcripts.py   check transcript fields on a machine
prompts/weekly-sweep.md      read-only cleanup review
```

Develop with `uv run pytest` and `uvx ruff check`.
