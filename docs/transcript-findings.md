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
