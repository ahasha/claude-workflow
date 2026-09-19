import io
import json
from pathlib import Path

from conftest import edit, user, write_transcript

from work_ledger import hook


def run(payload) -> None:
    hook.run(io.StringIO(json.dumps(payload)))


def record(home: Path, sid: str) -> dict:
    return json.loads((home / ".work-ledger/sessions/testhost" / f"{sid}.json").read_text())


def test_worktree_session_recorded_against_worktree(isolated_home, repo, tmp_path):
    wt = repo / ".claude/worktrees/feature"
    (wt / "a.py").write_text("changed\n")
    t = write_transcript(
        tmp_path / "s1.jsonl",
        [
            user("Refactor a"),
            {"type": "worktree-state", "worktreeSession": {"worktreePath": str(wt)}},
            edit(str(wt / "a.py")),
        ],
    )
    # cwd stays at the main repo, as observed in a real worktree session.
    run(
        {"session_id": "s1", "cwd": str(repo), "transcript_path": str(t), "hook_event_name": "Stop"}
    )
    rec = record(isolated_home, "s1")
    assert rec["folder"] == str(wt) and rec["branch"] == "feature"
    assert rec["cwd"] == str(repo)
    assert rec["title"] == "Refactor a"
    assert rec["dirty_files"] == ["a.py"]
    assert rec["claude_files"] == [str(wt / "a.py")]

    write_transcript(t, [{"type": "ai-title", "aiTitle": "refactor a module"}], mode="a")
    run(
        {
            "session_id": "s1",
            "cwd": str(repo),
            "transcript_path": str(t),
            "hook_event_name": "SessionEnd",
        }
    )
    rec2 = record(isolated_home, "s1")
    assert rec2["title"] == "refactor a module"
    assert rec2["first_seen"] == rec["first_seen"] and rec2["last_event"] == "SessionEnd"


def test_user_fields_survive(isolated_home, repo):
    run({"session_id": "s2", "cwd": str(repo), "hook_event_name": "Stop"})
    path = isolated_home / ".work-ledger/sessions/testhost/s2.json"
    data = json.loads(path.read_text())
    data["custom"] = "keep"
    path.write_text(json.dumps(data))
    run(
        {
            "session_id": "s2",
            "cwd": str(repo),
            "hook_event_name": "Stop",
            "session_title": "from payload",
        }
    )
    rec = record(isolated_home, "s2")
    assert rec["custom"] == "keep" and rec["title"] == "from payload"


def test_bad_input_is_silent(isolated_home):
    hook.run(io.StringIO("not json"))
    hook.run(io.StringIO("[]"))
    hook.run(io.StringIO('{"cwd": "/x"}'))
    assert not (isolated_home / ".work-ledger").exists()
