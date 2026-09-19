<!-- Run from any directory: `claude -p "$(cat ~/.work-ledger/prompts/weekly-sweep.md)"`, or paste into a session. -->

Read every JSON file under ~/.work-ledger/sessions/. Group the sessions by `repo_root`
(one group per repo/worktree folder). For each group:

1. Check the folder still exists. If it doesn't, list it under "Gone".
2. Run `git -C <folder> status --short` and `git -C <folder> log -1 --format='%cr %s'`.
3. Check whether the branch is merged into the repo's default branch
   (`git -C <main_repo> branch --merged <default>`).

Then give me one short table with columns: folder, branch, last activity, uncommitted
files, merged?, and your recommendation (keep / archive / remove worktree).

Do not delete, archive, or modify anything. After the table, print the exact commands
(`git worktree remove ...`, `resume archive ...`) for the ones you recommend, and wait
for me to confirm.
