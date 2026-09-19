from conftest import edit, user, write_transcript

from work_ledger import transcript


def test_scan_reads_fields(tmp_path):
    t = write_transcript(
        tmp_path / "t.jsonl",
        [
            {"type": "user", "isMeta": True, "message": {"content": "caveat"}},
            user("<command-name>/clear</command-name>"),
            user([{"type": "text", "text": "Fix   the\nbackfill"}]),
            {
                "type": "user",
                "toolUseResult": {"x": 1},
                "message": {"content": [{"type": "tool_result", "content": "ok"}]},
            },
            user("second prompt"),
            {"type": "ai-title", "aiTitle": "old title"},
            {"type": "ai-title", "aiTitle": "fix backfill"},
            {"type": "last-prompt", "lastPrompt": "make watch doesn't work"},
            {"type": "worktree-state", "worktreeSession": {"worktreePath": "/w/feature"}},
            {"type": "user", "entrypoint": "cli", "sessionKind": "bg", "message": {"content": "x"}},
            edit("/w/feature/a.py"),
            edit("/w/feature/b.py"),
            edit("/w/feature/a.py"),
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/w/feature/c.py"},
                        }
                    ]
                },
            },
        ],
    )
    st = transcript.scan(str(t), {})
    assert st["first_prompt"] == "Fix the backfill"
    assert st["ai_title"] == "fix backfill"
    assert st["last_prompt"] == "make watch doesn't work"
    assert st["worktree_path"] == "/w/feature"
    assert st["claude_files"] == ["/w/feature/b.py", "/w/feature/a.py"]
    assert (st["entrypoint"], st["session_kind"]) == ("cli", "bg")


def test_scan_is_incremental(tmp_path):
    t = write_transcript(tmp_path / "t.jsonl", [user("hello"), edit("/x/a.py")])
    st = transcript.scan(str(t), {})
    first_offset = st["offset"]
    assert first_offset == t.stat().st_size

    # A partial trailing line is left for the next scan.
    with t.open("a") as f:
        f.write('{"type": "ai-title", "aiTitle": "par')
    transcript.scan(str(t), st)
    assert st["offset"] == first_offset and "ai_title" not in st

    with t.open("a") as f:
        f.write('tial"}\n')
    write_transcript(t, [edit("/x/b.py")], mode="a")
    transcript.scan(str(t), st)
    assert st["ai_title"] == "partial"
    assert st["claude_files"] == ["/x/a.py", "/x/b.py"]
    assert st["first_prompt"] == "hello"


def test_worktree_cleared(tmp_path):
    t = write_transcript(
        tmp_path / "t.jsonl",
        [{"worktreeSession": {"worktreePath": "/w"}}, {"worktreeSession": None}],
    )
    assert transcript.scan(str(t), {})["worktree_path"] is None


def test_missing_and_garbage(tmp_path):
    assert transcript.scan(str(tmp_path / "nope.jsonl"), {}) == {}
    t = tmp_path / "g.jsonl"
    t.write_text("not json\n[1,2]\n")
    assert transcript.scan(str(t), {})["offset"] == t.stat().st_size
