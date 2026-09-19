<!-- Paste into ~/.claude/CLAUDE.md, adjusting paths to taste. -->

## Environments
- Never activate virtualenvs. Run Python through `uv run` so the project's `.venv` is picked up from the working directory.
- After creating or switching to a git worktree, run `uv sync` in it before anything else.

## Worktrees and branches
- Create worktrees under `~/code/.worktrees/<repo>--<branch>`. Never inside the repo itself or in /tmp.
- Name branches after the idea being worked on (e.g. `retroscore-dedupe`) so they are recognizable weeks later. Avoid ticket numbers alone or names like `fix-2`.
- When work on a worktree's branch is merged, say so and offer to remove the worktree.

## Handoff
- When I say I'm stopping, write a 3-line `HANDOFF.md` at the worktree root: what was done, what's next, anything blocking. Keep it untracked (add it to `.git/info/exclude`).
