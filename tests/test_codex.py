from __future__ import annotations

from pathlib import Path

from conftest import write_transcript

from work_ledger import codex

FS = (
    "<filesystem><workspace_roots>"
    "<root>/repo/a</root><root>/repo/b</root>"
    "</workspace_roots><permission_profile type='managed'/></filesystem>"
)


def world_state(cwd: str, filesystem: str = FS, ts: str = "2026-09-02T12:56:07.123Z") -> dict:
    return {
        "timestamp": ts,
        "type": "world_state",
        "payload": {
            "full": True,
            "state": {
                "environments": {
                    "environments": {"local": {"cwd": cwd, "shell": "zsh"}},
                    "filesystem": filesystem,
                }
            },
        },
    }


def test_scan_reads_cwd_and_workspace_roots_from_world_state(tmp_path):
    path = write_transcript(tmp_path / "rollout.jsonl", [world_state("/repo/a")])

    state = codex.scan(str(path), {})

    assert state["cwd"] == "/repo/a"
    assert state["roots"] == ["/repo/a", "/repo/b"]


def test_scan_records_first_and_last_timestamps(tmp_path):
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            world_state("/repo/a", ts="2026-09-02T12:56:07.123Z"),
            {"timestamp": "2026-09-02T13:10:00.000Z", "type": "turn_context", "payload": {}},
        ],
    )

    state = codex.scan(str(path), {})

    assert state["first_timestamp"] == "2026-09-02T12:56:07+00:00"
    assert state["last_timestamp"] == "2026-09-02T13:10:00+00:00"


def test_scan_falls_back_to_session_meta_cwd_without_world_state(tmp_path):
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            {
                "timestamp": "2026-09-02T12:56:07.123Z",
                "type": "session_meta",
                "payload": {"id": "01a0", "cwd": "/repo/c", "cli_version": "1.2"},
            }
        ],
    )

    state = codex.scan(str(path), {})

    assert state["cwd"] == "/repo/c"
    assert state["roots"] == []


def test_world_state_cwd_wins_over_session_meta(tmp_path):
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            {"type": "session_meta", "payload": {"id": "01a0", "cwd": "/repo/launch"}},
            world_state("/repo/a"),
        ],
    )

    assert codex.scan(str(path), {})["cwd"] == "/repo/a"


def msg(role: str, text: str, kind: str = "input_text") -> dict:
    return {
        "timestamp": "2026-09-02T12:57:00.000Z",
        "type": "response_item",
        "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]},
    }


def test_scan_takes_first_and_last_user_prompts(tmp_path):
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            world_state("/repo/a"),
            msg("user", "review the heat pump model"),
            msg("assistant", "looking now", "output_text"),
            msg("user", "now check the oil comparison"),
        ],
    )

    state = codex.scan(str(path), {})

    assert state["first_prompt"] == "review the heat pump model"
    assert state["last_prompt"] == "now check the oil comparison"


def test_scan_skips_system_boilerplate_prompts(tmp_path):
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            world_state("/repo/a"),
            msg("user", "# AGENTS.md\nproject instructions"),
            msg("user", "<environment_context>cwd=/repo/a</environment_context>"),
            msg("user", "<system-reminder>be good</system-reminder>"),
            msg("user", "the real question"),
        ],
    )

    state = codex.scan(str(path), {})

    assert state["first_prompt"] == "the real question"
    assert state["last_prompt"] == "the real question"


def test_scan_skips_the_boilerplate_codex_really_emits(tmp_path):
    """Prefixes taken from real rollout files, not guessed."""
    path = write_transcript(
        tmp_path / "r.jsonl",
        [
            world_state("/repo/a"),
            msg("user", "The following is the Codex agent history added since your last turn"),
            msg("user", "# Context from my IDE setup:\n## Active file: hello_hf.py"),
            msg("user", "<recommended_plugins> Here is a list of plugins that are available"),
            msg("user", '<in-app-browser-context source="ambient-ui-state"> This is'),
            msg("user", "FWIW, the oil boiler had a non-zero standby consumption"),
        ],
    )

    state = codex.scan(str(path), {})

    assert state["first_prompt"] == "FWIW, the oil boiler had a non-zero standby consumption"


def test_thread_names_reads_last_entry_per_session_id(tmp_path):
    """The index appends a line per rename; the last one is the current name."""
    index = tmp_path / "session_index.jsonl"
    write_transcript(
        index,
        [
            {"id": "01a0", "thread_name": "New voice chat", "updated_at": "2026-09-01T15:11:21Z"},
            {"id": "01a0", "thread_name": "Projektverbindung", "updated_at": "2026-09-01T15:11:39Z"},
            {"id": "01b0", "thread_name": "Review Span Monitor", "updated_at": "2026-09-01T15:14Z"},
        ],
    )

    names = codex.thread_names(index)

    assert names == {"01a0": "Projektverbindung", "01b0": "Review Span Monitor"}


def test_thread_names_is_empty_when_the_index_is_missing(tmp_path):
    assert codex.thread_names(tmp_path / "nope.jsonl") == {}


def test_config_codex_dir_defaults_and_env_override(monkeypatch, tmp_path):
    from work_ledger import config

    assert config.load().codex_dir == Path.home() / ".codex"
    monkeypatch.setenv("WORK_LEDGER_CODEX_DIR", str(tmp_path / "cx"))
    assert config.load().codex_dir == tmp_path / "cx"


def test_update_record_accepts_an_alternate_scanner(tmp_path):
    from work_ledger import hook

    path = write_transcript(tmp_path / "r.jsonl", [world_state(str(tmp_path))])
    payload = {"session_id": "01a0", "cwd": str(tmp_path), "transcript_path": str(path),
               "hook_event_name": "codex"}

    record = hook.update_record({}, payload, "testhost", "2026-09-02T13:00:00+00:00",
                                scan_fn=codex.scan)

    assert record["scan"]["roots"] == ["/repo/a", "/repo/b"]
    assert record["folder"] == str(tmp_path)


def session_meta(sid: str, cwd: str) -> dict:
    return {
        "timestamp": "2026-09-02T12:56:00.000Z",
        "type": "session_meta",
        "payload": {"id": sid, "cwd": cwd, "cli_version": "1.2"},
    }


def codex_home(tmp_path, rollouts, names=None, archived=None):
    """A ~/.codex layout: rollouts, optional archived rollouts, a session index."""
    cx = tmp_path / "codex"
    for sub, group in (("sessions", rollouts), ("archived_sessions", archived or {})):
        for name, entries in (group or {}).items():
            write_transcript(cx / sub / f"{name}.jsonl", entries)
    write_transcript(
        cx / "session_index.jsonl",
        [{"id": k, "thread_name": v} for k, v in (names or {}).items()],
    )
    return cx


def sweep_cfg(monkeypatch, cx):
    from work_ledger import config

    monkeypatch.setenv("WORK_LEDGER_CODEX_DIR", str(cx))
    return config.load()


def test_sweep_writes_a_record_for_a_new_rollout(tmp_path, repo, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    fs = (
        f"<filesystem><workspace_roots><root>{repo}</root>"
        f"<root>{other}</root></workspace_roots></filesystem>"
    )
    cx = codex_home(
        tmp_path,
        {"rollout-1": [session_meta("01a0", str(repo)), world_state(str(repo), fs)]},
        names={"01a0": "Review heat pump analysis"},
    )
    cfg = sweep_cfg(monkeypatch, cx)

    [record] = codex.sweep(cfg)

    assert record["session_id"] == "codex-01a0"
    assert record["source"] == "codex"
    assert record["title"] == "Review heat pump analysis"
    assert record["folder"] == str(repo)
    assert record["branch"] == "main"
    assert record["roots"] == [str(other)]


def test_sweep_drops_roots_inside_the_codex_dir_and_missing_dirs(tmp_path, repo, monkeypatch):
    cx = tmp_path / "codex"
    viz = cx / "visualizations" / "2026"
    viz.mkdir(parents=True)
    fs = (
        f"<filesystem><workspace_roots><root>{repo}</root><root>{viz}</root>"
        f"<root>{tmp_path / 'gone'}</root></workspace_roots></filesystem>"
    )
    codex_home(tmp_path, {"rollout-1": [session_meta("01a0", str(repo)), world_state(str(repo), fs)]})
    cfg = sweep_cfg(monkeypatch, cx)

    [record] = codex.sweep(cfg)

    assert record["roots"] == []


def test_sweep_skips_files_it_already_read(tmp_path, repo, monkeypatch):
    cx = codex_home(tmp_path, {"rollout-1": [session_meta("01a0", str(repo)), world_state(str(repo))]})
    cfg = sweep_cfg(monkeypatch, cx)

    assert len(codex.sweep(cfg)) == 1
    assert codex.sweep(cfg) == []


def test_sweep_covers_archived_sessions(tmp_path, repo, monkeypatch):
    cx = codex_home(
        tmp_path,
        {},
        archived={"rollout-old": [session_meta("01b0", str(repo)), world_state(str(repo))]},
    )
    cfg = sweep_cfg(monkeypatch, cx)

    [record] = codex.sweep(cfg)

    assert record["session_id"] == "codex-01b0"


def test_sweep_is_a_noop_without_a_codex_dir(tmp_path, monkeypatch):
    cfg = sweep_cfg(monkeypatch, tmp_path / "absent")

    assert codex.sweep(cfg) == []


def test_load_sessions_sweeps_codex(tmp_path, repo, monkeypatch):
    from work_ledger import ledger

    cx = codex_home(tmp_path, {"rollout-1": [session_meta("01a0", str(repo)), world_state(str(repo))]})
    cfg = sweep_cfg(monkeypatch, cx)

    [task] = ledger.load_tasks(cfg)

    assert task["folder"] == str(repo)
    assert [s["source"] for s in task["sessions"]] == ["codex"]


def test_build_tasks_unions_roots_across_sessions(tmp_path, monkeypatch):
    from work_ledger import config, ledger

    cfg = config.load()
    base = {"host": "testhost", "folder": "/f", "source": "codex"}
    sessions = [
        {**base, "session_id": "codex-1", "last_seen": "2026-09-02T12:00:00+00:00",
         "roots": ["/a"]},
        {**base, "session_id": "codex-2", "last_seen": "2026-09-02T13:00:00+00:00",
         "roots": ["/b", "/a"]},
    ]

    [task] = ledger.build_tasks(sessions, cfg)

    assert task["session_roots"] == ["/a", "/b"]


def test_prepare_opens_session_roots_alongside_the_folder(tmp_path, repo):
    from work_ledger import config, vscode

    other = tmp_path / "other"
    other.mkdir()
    task = {"id": "t1", "folder": str(repo), "session_roots": [str(other)],
            "extra_folders": [], "claude_files": [], "dirty_files": [], "branch_files": []}

    prep = vscode.prepare(config.load(), task, sync=False)

    assert prep["folders"] == [str(repo), str(other)]


def test_wl_claude_on_a_codex_task_starts_a_fresh_session(tmp_path, repo, monkeypatch):
    from click.testing import CliRunner

    from work_ledger import cli

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    cx = codex_home(tmp_path, {"rollout-1": [session_meta("01a0", str(repo)), world_state(str(repo))]},
                    names={"01a0": "heat pump"})
    sweep_cfg(monkeypatch, cx)

    result = CliRunner().invoke(cli.cli, ["claude", "--dry-run", "heat"])

    assert result.exit_code == 0, result.output
    assert "--resume" not in result.output
    assert result.output.strip().endswith("claude")


def test_clean_roots_drops_ancestors_and_descendants_of_the_folder(tmp_path):
    """A root above or below the task folder adds nothing to the workspace."""
    folder = tmp_path / "Codex" / "2026-09-15" / "you"
    folder.mkdir(parents=True)
    inside = folder / "sub"
    inside.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    roots = [str(tmp_path / "Codex"), str(inside), str(sibling)]

    assert codex.clean_roots(roots, str(folder), tmp_path / "codex-home") == [str(sibling)]
