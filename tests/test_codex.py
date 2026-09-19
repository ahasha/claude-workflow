from __future__ import annotations

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
