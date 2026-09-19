# Claude Code data: verified findings (2026-09-18)

Sources: code.claude.com hooks and settings docs; `tools/probe_transcripts.py` on Alex's Mac (1 transcript).

## Hook payloads (docs)
- Common fields on every event: `session_id`, `transcript_path`, `cwd`, `hook_event_name`.
- `SessionEnd`: adds `reason`. Default timeout 1.5 s; raise with a per-hook `timeout`.
- `Stop`: adds `last_assistant_message`, `background_tasks`, `session_crons`.
- `UserPromptSubmit`: adds `prompt`, optional `session_title`.
- `SessionStart`: adds `source` (startup/resume/clear/compact/fork), optional `session_title`.

## Transcript JSONL (observed)
- `ai-title` entries carry `aiTitle`, Claude's own short title (e.g. "modernize resume latex"). Updated during the session; take the last one.
- `last-prompt` entries carry `lastPrompt`.
- `agent-name` entries carry `agentName` (matched `aiTitle` here).
- Most entries carry `cwd`, `gitBranch`, `slug`, `sessionKind`, `entrypoint`, `version`.
- `worktree-state` entries carry `worktreeSession`: `originalCwd`, `preEnterOriginalCwd`, `worktreePath`, `worktreeName`, ….
- `relocated` entries carry `relocatedCwd`.
- User `message.content` is a str or a list of blocks; most list items are `tool_result`. `first_prompt()` picked a sensible title.

## Implications
- Native worktrees live at `<repo>/.claude/worktrees/<name>`, on a branch of the same name (`claude --worktree <name>` / EnterWorktree).
- In a worktree session, `cwd` stayed the main repo while `gitBranch` showed the worktree branch. The hook runs git in `project_dir`, so it would record the main repo's branch. Read `worktreeSession.worktreePath` from the transcript instead.
- Transcripts are deleted after `cleanupPeriodDays` (default 30). Ledger entries older than that can't be resumed with `claude --resume`. Consider `"cleanupPeriodDays": 3650` on each host. (The Mac sees little Claude Code use, so its single transcript says little about cleanup.)
- Re-run the probe on the VM, where most sessions happen.

# Codex rollout data: verified findings (2026-09-18)

Source: 12 rollout files in `~/.codex/sessions` on Alex's Mac, 2026-09-01 to 09-16.

## Layout
- Rollouts: `~/.codex/sessions/**/rollout-<timestamp>-<uuid>.jsonl`. Archived ones move to `~/.codex/archived_sessions/`, so a sweep must read both.
- `~/.codex/session_index.jsonl` maps `id` to `thread_name`, appending a line per rename. The last line for an id is the current name. 9 of 12 sessions had an entry.

## Rollout JSONL (observed)
- Every line has `timestamp` (RFC3339Nano) and `type`; most carry a `payload` object.
- Line types seen: `event_msg`, `response_item`, `turn_context`, `world_state`, `session_meta`.
- `session_meta.payload` carries `id`, `cwd` (the launch directory), `cli_version`.
- `turn_context.payload` carries `cwd` and `model`, once per turn; `cwd` can change mid-session.
- `world_state.payload.state.environments` is authoritative:
  - `environments.local.cwd` is the working directory.
  - `filesystem` is **XML inside a JSON string**, holding `<workspace_roots><root>…</root></workspace_roots>` and a `permission_profile` listing read/write paths.
- `response_item.payload` with `type: message` carries `role` and a `content` list of `input_text` (user) or `output_text` (assistant) blocks.

## No structured file edits
Every file-touching call across all 12 sessions was `exec` (164), `exec_command` (36) or `js` (10). Their `input` is a raw shell or JavaScript string, e.g.
`const r = await tools.exec_command({"cmd":"git status --short && rg -n …","workdir":"/Users/alex.hasha/repos/heat_pump_analysis"})`.
There is no `input.file_path` equivalent, so Codex sessions record no `claude_files`. Key files fall back to `dirty_files` then `branch_files`.

## Boilerplate in user-role messages
Codex emits its own context as `role: user` messages. Prefixes seen, with counts:
- `The following is the Codex agent history…` (27)
- `# Context from my IDE setup:` (11)
- `<recommended_plugins>` (7), `<environment_context>` (6), `<in-app-browser-context` (4)

Anything starting with `<` is a tagged context block, so that prefix plus the two `#`/`The following` forms covers what was observed. Three of 12 sessions had no real user prompt at all; those rely on the index's thread name for a title.

## Implications
- `workspace_roots` often lists directories that are not co-equal repos: Codex's own `~/.codex/visualizations/<date>/<id>`, and the scratch parent `~/Documents/Codex` beside its own child. Roots above, below or inside the Codex dir are dropped.
- There is no per-turn hook. `notify` in `~/.codex/config.toml` takes a single program and was already in use, so capture is pull-based.
- No `codex` binary was on PATH, so there is no resume command; `wl claude` starts a fresh Claude session in a Codex task's folder.
