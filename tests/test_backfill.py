import json

from click.testing import CliRunner
from conftest import edit, sh, user, write_transcript

from work_ledger import backfill, cli, config, install


def projects(home):
    return home / ".claude" / "projects"


def ts(minute: int) -> str:
    return f"2026-09-10T12:{minute:02d}:00.500Z"


def test_backfill_builds_records(isolated_home, repo):
    wt = repo / ".claude/worktrees/feature"
    (wt / "a.py").write_text("changed\n")
    write_transcript(
        projects(isolated_home) / "-proj" / "s-live.jsonl",
        [
            {"timestamp": ts(1), "cwd": str(repo), "gitBranch": "main", **user("Refactor a")},
            {"timestamp": ts(2), "worktreeSession": {"worktreePath": str(wt)}},
            {"timestamp": ts(5), **edit(str(wt / "a.py"))},
            {"type": "ai-title", "aiTitle": "refactor a"},
        ],
    )
    write_transcript(
        projects(isolated_home) / "-proj" / "s-empty.jsonl",
        [{"type": "summary", "summary": "nothing"}],
    )

    cfg = config.load()
    results = backfill.backfill(cfg, install.claude_dir())
    assert sorted(s for s, _ in results) == ["added", "empty"]

    rec = json.loads((cfg.ledger_dir / "sessions/testhost/s-live.json").read_text())
    assert rec["folder"] == str(wt) and rec["branch"] == "feature"
    assert rec["title"] == "refactor a" and rec["cwd"] == str(repo)
    assert rec["first_seen"] == "2026-09-10T12:01:00+00:00"
    assert rec["last_seen"] == "2026-09-10T12:05:00+00:00"
    assert rec["last_event"] == "backfill"

    # Second run leaves existing records alone unless forced.
    assert sorted(s for s, _ in backfill.backfill(cfg, install.claude_dir())) == ["empty", "exists"]
    assert "updated" in [s for s, _ in backfill.backfill(cfg, install.claude_dir(), force=True)]


def test_removed_worktree_stays_its_own_task(isolated_home, repo):
    wt = repo / ".claude/worktrees/feature"
    sh(repo, "git", "worktree", "remove", str(wt))
    write_transcript(
        projects(isolated_home) / "-proj" / "s1.jsonl",
        [
            {"timestamp": ts(1), "cwd": str(repo), "gitBranch": "feature", **user("Old idea")},
            {"worktreeSession": {"worktreePath": str(wt)}},
        ],
    )
    cfg = config.load()
    [(status, rec)] = backfill.backfill(cfg, install.claude_dir())
    assert status == "added"
    assert rec["folder"] == str(wt) and rec["branch"] == "feature"
    assert rec["main_repo"] == str(repo) and rec["is_worktree"]


def test_cli_dry_run_writes_nothing(isolated_home, repo):
    write_transcript(
        projects(isolated_home) / "-proj" / "s1.jsonl",
        [{"timestamp": ts(1), "cwd": str(repo), **user("Hello")}],
    )
    result = CliRunner().invoke(cli.cli, ["backfill", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "proj:main" in result.output and "would add 1" in result.output
    assert not (isolated_home / ".work-ledger/sessions").exists()
