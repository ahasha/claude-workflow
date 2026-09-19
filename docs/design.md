# work-ledger design

## Goal
Pick a unit of work by what it was about, then land in VS Code with the right folder, the right files open, and the right `.venv` as the Python interpreter. Works on macOS and Ubuntu, across several machines.

`claude --resume` is a secondary convenience.

## Unit of work: a task
A task is one working folder (usually a git worktree) on one host.
- Key: `(host, folder)`. ID: first 8 hex chars of `sha1("host:folder")`.
- Claude sessions are evidence attached to a task. Several sessions can share a task.

## Data flow
1. `work-ledger-hook` runs on Claude Code's `Stop` and `SessionEnd` events.
2. It writes one file per session: `<ledger>/sessions/<host>/<session_id>.json`.
3. `work-ledger` groups session files into tasks when it runs. Nothing else is stored, except task notes and archive flags in `<ledger>/tasks/<host>/<task_id>.json`.

One file per session and per task means the ledger dir can be synced (git, Syncthing, Dropbox) with no merge conflicts.

## Session record
Location
- `folder`: the worktree root. Taken from the transcript's `worktreeSession.worktreePath` if set, else the git toplevel of `cwd`, else `cwd`.
- `repo`, `main_repo`, `branch`, `is_worktree`: from git in `folder`.
- `cwd`: the hook's `cwd`, kept for `claude --resume`.

Intent
- `title`: last `aiTitle` in the transcript, else the first real user prompt.
- `last_prompt`: last `lastPrompt`.

Files
- `claude_files`: files Claude edited (`Edit`, `Write`, `MultiEdit`, `NotebookEdit` tool calls), most recent last.
- `dirty_files`: `git status --porcelain`, excluding deletions.
- `branch_files`: `git diff --name-only <merge-base with default branch>`.

If the transcript's worktree has since been removed, the session keeps that worktree path as its folder, takes `branch` from the transcript's `gitBranch`, and takes repo facts from `cwd`.

`first_seen` comes from the transcript's first `timestamp`. `work-ledger backfill` builds records the same way from transcripts already on disk, with `last_seen` from the last timestamp.

The transcript is read incrementally from a stored byte offset, so the per-turn `Stop` hook stays cheap on long sessions.

## Opening a task in VS Code
`work-ledger prepare <task_id>` runs on the task's host. It:
1. Runs `uv sync` in each folder that has a `pyproject.toml` and no `.venv`.
2. Writes `<ledger>/workspaces/<task_id>.code-workspace` with the task's folders and `python.defaultInterpreterPath` set to the first folder's `.venv/bin/python`.
3. Prints the workspace path and the key files to open, as JSON.

`work-ledger open` picks a task and then:
- Local host: runs `prepare`, then `code <workspace> <files…>`.
- Remote host: runs `prepare` over ssh, then `code --file-uri vscode-remote://ssh-remote+<alias><path>` for the workspace and each file.
- Other host with no ssh route: prints which machine the task is on.

Key files: `claude_files` (most recent first), then `dirty_files`, then `branch_files`; existing files only, deduplicated, capped at `max_files` (default 8).

## Manual tasks
`work-ledger add [folder] [-t title]` records work that Claude Code didn't, such as cloud Cowork sessions. It writes `sessions/<host>/manual-<task_id>.json` with `source: manual`, so it groups like any session. A `-t` title is stored in the task's meta file and overrides Claude's titles. `work-ledger claude` on a task with only manual records starts a new session in its folder.

## Multi-repo tasks
A task can list extra folders (`work-ledger add <folder> --to <words>`). They appear as extra roots in the workspace. Only the first folder's `.venv` becomes the interpreter.

Codex sessions supply their own roots, so a task's workspace folders are its folder, then `session_roots` (union of its sessions' roots), then the user's `extra_folders`. `extra_folders` stays a user field: a sweep never writes to it, so a folder removed by hand is not added back.

## Codex sessions
Codex has no per-turn hook, so its sessions are swept rather than pushed. `ledger.load_sessions` calls `codex.sweep` before reading, so any `wl` command folds in new Codex work.

`codex.scan` produces the same state dict as `transcript.scan`, and `hook.update_record` takes a `scan_fn`, so one record builder serves both. Records get `source: "codex"` and an id of `codex-<session id>`.

The sweep keeps `<ledger>/state/<host>/codex-sweep.json`, mapping each rollout path to its mtime and size, and re-reads a file only when one changes. Records are durable, so a rollout Codex later prunes stays in the ledger.

Titles come from `~/.codex/session_index.jsonl` (`thread_name`), which beats a first prompt. See `docs/transcript-findings.md` for the rollout fields and the boilerplate prefixes.

## Hosts
- Each machine gets a fixed `host` name at install time, stored in `~/.config/work-ledger/config.toml`. Mac hostnames drift, so `gethostname()` is only the default.
- `remotes` maps host names to ssh aliases, for hosts VS Code can reach through Remote-SSH.
- If a remote host's records are missing from the local ledger (no sync), `work-ledger` fetches them with `ssh <alias> work-ledger dump`.

## Packaging
- uv package, flat layout (`work_ledger/`), click CLI.
- Install on each machine: `uv tool install git+<repo-url>`, then `work-ledger install`.
- Two entry points: `work-ledger` (alias `wl`) and `work-ledger-hook` (standard library only, for speed).
- `work-ledger install` writes the config and merges hooks into `~/.claude/settings.json` using absolute paths, since hooks may not see `~/.local/bin` on PATH. It removes hooks from the prototype and optionally raises `cleanupPeriodDays`.

## Unverified
- Whether `worktreeSession` is cleared on `ExitWorktree`.
- Tool-call shape for edited files in transcripts: this assumes `tool_use` blocks with `input.file_path`.
- Whether the Python extension respects `python.defaultInterpreterPath` in a workspace file when it has already chosen an interpreter.
- Multiple `--file-uri` arguments in one `code` call.

## Moved repos
Tasks are keyed by host and folder, so moving a repo would strand its old task. The hook records `repo_id` (the git root commit). The first time it records a session in a repo, `relocate.reconcile` looks for this host's records whose `main_repo` no longer exists and that share the `repo_id` (older records without one match on repo name). It rebases their `folder`, `main_repo`, `last_cwd` and `claude_files` onto the new location, sets `moved_from`, and moves the task's note/title/archived metadata to the new task id. `cwd` is kept, since `claude --resume` depends on it. `wl add` runs the same check.
