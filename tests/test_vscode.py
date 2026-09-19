import json

from work_ledger import config, vscode


def test_prepare_writes_workspace(tmp_path, monkeypatch):
    cfg = config.load()
    folder, extra = tmp_path / "wt", tmp_path / "other"
    (folder / ".venv/bin").mkdir(parents=True)
    (folder / ".venv/bin/python").write_text("")
    (folder / "a.py").write_text("")
    extra.mkdir()
    task = {
        "id": "abc12345",
        "folder": str(folder),
        "extra_folders": [str(extra)],
        "claude_files": [str(folder / "a.py")],
        "dirty_files": [],
        "branch_files": [],
    }

    prep = vscode.prepare(cfg, task)
    ws = json.loads(open(prep["workspace"]).read())
    assert [f["path"] for f in ws["folders"]] == [str(folder), str(extra)]
    assert ws["settings"]["python.defaultInterpreterPath"] == str(folder / ".venv/bin/python")
    assert prep["files"] == [str(folder / "a.py")]

    monkeypatch.setattr(vscode, "code_bin", lambda: "code")
    assert vscode.local_command(prep) == ["code", prep["workspace"], str(folder / "a.py")]
    cmd = vscode.remote_command(
        "vm", {"workspace": "/h/my ws.code-workspace", "files": ["/h/a.py"]}
    )
    assert cmd == [
        "code",
        "--file-uri",
        "vscode-remote://ssh-remote+vm/h/my%20ws.code-workspace",
        "--file-uri",
        "vscode-remote://ssh-remote+vm/h/a.py",
    ]


def test_prepare_syncs_fresh_uv_project(tmp_path, monkeypatch):
    folder = tmp_path / "wt"
    folder.mkdir()
    (folder / "pyproject.toml").write_text("")
    calls = []
    monkeypatch.setattr(vscode.shutil, "which", lambda name: "/bin/uv")
    monkeypatch.setattr(vscode.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["cwd"])))
    task = {"id": "t", "folder": str(folder)}
    prep = vscode.prepare(config.load(), task)
    assert calls == [(["uv", "sync"], folder)]
    assert prep["interpreter"] is None


def test_missing_worktree_falls_back_to_main_repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    task = {"id": "t", "folder": str(tmp_path / "gone"), "main_repo": str(main)}
    prep = vscode.prepare(config.load(), task, sync=False)
    assert prep["folders"] == [str(main)] and "is gone" in prep["messages"][0]
