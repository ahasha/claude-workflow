import io
import json

from click.testing import CliRunner

from work_ledger import cli, config, hook, install


def test_merge_hooks_replaces_ours_and_keeps_others():
    settings = {
        "model": "x",
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ~/.work-ledger/hooks/record_session.py",
                        },
                        {"type": "command", "command": "say done"},
                    ]
                }
            ],
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "guard"}]}],
            "SessionEnd": [
                {"hooks": [{"type": "command", "command": "python3 record_session.py"}]}
            ],
        },
    }
    for _ in range(2):  # idempotent
        install.merge_hooks(settings, "/t/work-ledger-hook")
    hooks = settings["hooks"]
    assert hooks["Stop"] == [
        {"hooks": [{"type": "command", "command": "say done"}]},
        {"hooks": [{"type": "command", "command": "/t/work-ledger-hook"}]},
    ]
    assert hooks["SessionEnd"] == [
        {"hooks": [{"type": "command", "command": "/t/work-ledger-hook", "timeout": 10}]}
    ]
    assert hooks["PreToolUse"][0]["matcher"] == "Bash"
    assert settings["model"] == "x"


def test_install_command(isolated_home, monkeypatch):
    settings = isolated_home / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text('{"theme": "dark"}')
    result = CliRunner().invoke(
        cli.cli, ["install", "--host", "mbp", "--remote", "vm=devbox", "--retention-days", "3650"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(settings.read_text())
    assert data["theme"] == "dark" and data["cleanupPeriodDays"] == 3650
    assert (
        "work-ledger-hook" in data["hooks"]["Stop"][0]["hooks"][0]["command"]
        or "work_ledger.hook" in data["hooks"]["Stop"][0]["hooks"][0]["command"]
    )
    assert (isolated_home / ".claude/settings.json.bak").exists()

    cfg_text = (isolated_home / ".config/work-ledger/config.toml").read_text()
    assert 'host = "mbp"' in cfg_text and '"vm" = "devbox"' in cfg_text
    monkeypatch.delenv("WORK_LEDGER_HOST")
    cfg = config.load()
    assert cfg.host == "mbp" and cfg.remotes == {"vm": "devbox"}


def test_list_and_open_dry_run(isolated_home, repo, tmp_path, monkeypatch):

    wt = repo / ".claude/worktrees/feature"
    (wt / "a.py").write_text("changed\n")
    hook.run(
        io.StringIO(json.dumps({"session_id": "s1", "cwd": str(wt), "hook_event_name": "Stop"}))
    )
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)  # no fzf, no code
    monkeypatch.setattr(cli.vscode, "code_bin", lambda: "code")

    runner = CliRunner()
    out = runner.invoke(cli.cli, ["list"]).output
    assert "proj:feature" in out

    result = runner.invoke(cli.cli, ["feature", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "code " in result.output and str(wt / "a.py") in result.output

    result = runner.invoke(cli.cli, ["claude", "--dry-run", "feature"])
    assert "claude --resume s1" in result.output


def test_remote_task_without_alias_explains(isolated_home, monkeypatch):
    cfg = config.load()
    d = cfg.ledger_dir / "sessions" / "laptop2"
    d.mkdir(parents=True)
    (d / "x.json").write_text(
        json.dumps(
            {
                "session_id": "x",
                "host": "laptop2",
                "folder": "/f",
                "last_seen": "2099-01-01T00:00:00+00:00",
                "title": "t",
            }
        )
    )
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    result = CliRunner().invoke(cli.cli, ["open", "--dry-run"])
    assert result.exit_code != 0 and "is on laptop2" in result.output
