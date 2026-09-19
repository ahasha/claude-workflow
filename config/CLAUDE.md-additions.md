<!-- Paste into ~/.claude/CLAUDE.md on each machine. -->

## Environments
- Never activate virtualenvs. Run Python through `uv run` so the project's `.venv` is picked up from the working directory.
- After creating or switching to a git worktree, run `uv sync` in it before anything else.

## Worktrees and branches
- For new work, use a Claude Code worktree (`claude --worktree <name>`, or the EnterWorktree tool). They live at `<repo>/.claude/worktrees/<name>` on a branch of the same name.
- Name worktrees after the idea being worked on (e.g. `retroscore-dedupe`) so they are recognizable weeks later. Avoid ticket numbers alone or names like `fix-2`.
- When a worktree's branch is merged, say so and offer to remove the worktree.
