<!-- Run from any directory: claude -p "$(cat prompts/weekly-sweep.md)", or paste into a session. -->

Run `work-ledger list --all --local` to see this machine's tasks, then read the session
files under ~/.work-ledger/sessions/<this host>/. Group them by `folder`. For each folder:

1. Check it still exists. If it doesn't, list it under "Gone".
2. Run `git -C <folder> status --short` and `git -C <folder> log -1 --format='%cr %s'`.
3. Check whether the branch is merged into the repo's default branch
   (`git -C <main_repo> branch --merged <default>`).

Then give me one short table with columns: folder, branch, last activity, uncommitted
files, merged?, and your recommendation (keep / archive / remove worktree).

Do not delete, archive, or modify anything. After the table, print the exact commands
(`git worktree remove ...`, `work-ledger archive ...`) for the ones you recommend, and wait
for me to confirm.
