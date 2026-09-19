import json

from work_ledger import config, ledger


def session(sid, folder, last_seen, **kw):
    return {
        "session_id": sid,
        "host": "testhost",
        "folder": str(folder),
        "last_seen": last_seen,
        "first_seen": last_seen,
        **kw,
    }


def test_groups_sessions_into_tasks(tmp_path):
    cfg = config.load()
    a, b = tmp_path / "a", tmp_path / "b"
    tasks = ledger.build_tasks(
        [
            session("1", a, "2026-09-01T00:00:00+00:00", title="old", claude_files=["x", "y"]),
            session(
                "2",
                a,
                "2026-09-03T00:00:00+00:00",
                title="new",
                claude_files=["x"],
                dirty_files=["d.py"],
            ),
            session("3", b, "2026-09-02T00:00:00+00:00", title="other"),
        ],
        cfg,
    )
    assert [t["title"] for t in tasks] == ["new", "other"]
    t = tasks[0]
    assert t["id"] == ledger.task_id("testhost", str(a))
    assert t["claude_files"] == ["y", "x"]  # most recent last
    assert t["dirty_files"] == ["d.py"]
    assert t["first_seen"].startswith("2026-09-01")
    assert [s["session_id"] for s in t["sessions"]] == ["2", "1"]


def test_meta_and_archive_filter(tmp_path):
    cfg = config.load()
    sessions_dir = cfg.ledger_dir / "sessions" / "testhost"
    sessions_dir.mkdir(parents=True)
    rec = session("1", tmp_path, "2099-01-01T00:00:00+00:00", title="t")
    (sessions_dir / "1.json").write_text(json.dumps(rec))

    [task] = ledger.load_tasks(cfg)
    ledger.save_meta(cfg, task, note="next: tests", archived=True)
    assert ledger.load_tasks(cfg) == []
    [task] = ledger.load_tasks(cfg, include_archived=True)
    assert task["note"] == "next: tests" and task["archived"]


def test_key_files_order_and_filters(tmp_path):
    folder = tmp_path / "wt"
    folder.mkdir()
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (folder / name).write_text("")
    outside = tmp_path / "CLAUDE.md"
    outside.write_text("")
    task = {
        "folder": str(folder),
        "claude_files": [
            str(folder / "a.py"),
            str(outside),
            str(folder / "b.py"),
            str(folder / "gone.py"),
        ],
        "dirty_files": ["c.py", "b.py"],
        "branch_files": ["d.py"],
    }
    got = [p.rsplit("/", 1)[1] for p in ledger.key_files(task, 10)]
    assert got == ["b.py", "a.py", "c.py", "d.py"]
    assert len(ledger.key_files(task, 2)) == 2
