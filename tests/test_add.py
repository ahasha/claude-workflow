import io
import json

from click.testing import CliRunner

from work_ledger import cli, config, hook, ledger


def invoke(*args):
    result = CliRunner().invoke(cli.cli, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_add_creates_task_and_merges_with_claude_sessions(isolated_home, repo, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    invoke("add", str(repo), "-t", "cowork planning")
    [task] = ledger.load_tasks(config.load())
    assert task["title"] == "cowork planning" and task["folder"] == str(repo)
    assert task["branch"] == "main"

    # A later Claude Code session in the same folder joins the task; the chosen title stays.
    hook.run(
        io.StringIO(
            json.dumps(
                {
                    "session_id": "s1",
                    "cwd": str(repo),
                    "session_title": "claude title",
                    "hook_event_name": "Stop",
                }
            )
        )
    )
    [task] = ledger.load_tasks(config.load())
    assert task["title"] == "cowork planning"
    assert [s["session_id"] for s in task["sessions"]][0] == "s1" and len(task["sessions"]) == 2

    out = invoke("claude", "--dry-run", "cowork")
    assert "claude --resume s1" in out


def test_add_without_title_then_claude_starts_fresh(isolated_home, repo, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.chdir(repo)
    invoke("add")
    [task] = ledger.load_tasks(config.load())
    assert task["title"] is None and task["sessions"][0]["source"] == "manual"
    assert invoke("claude", "--dry-run").strip() == f"cd {repo} && claude"


def test_add_to_existing_task(isolated_home, repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    other = tmp_path / "other"
    other.mkdir()
    invoke("add", str(repo), "-t", "main work")
    invoke("add", str(other), "--to", "main work")
    [task] = ledger.load_tasks(config.load())
    assert task["extra_folders"] == [str(other)]
