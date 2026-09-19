import io
import json
import shutil

from conftest import sh

from work_ledger import config, hook, ledger


def run_hook(sid, cwd):
    payload = {"session_id": sid, "cwd": str(cwd), "hook_event_name": "Stop"}
    hook.run(io.StringIO(json.dumps(payload)))


def test_moved_repo_folds_old_task_into_new(repo, tmp_path):
    wt = repo / ".claude" / "worktrees" / "feature"
    run_hook("old-main", repo)
    run_hook("old-wt", wt)
    cfg = config.load()
    old_tasks = ledger.load_tasks(cfg)
    assert len(old_tasks) == 2
    main_task = next(t for t in old_tasks if not t["is_worktree"])
    ledger.save_meta(cfg, main_task, note="keep me", archived=False)

    new = tmp_path / "moved" / repo.name
    new.parent.mkdir()
    shutil.move(str(repo), str(new))
    sh(new, "git", "worktree", "repair")
    run_hook("new-main", new)

    tasks = ledger.load_tasks(cfg, include_archived=True)
    folders = {t["folder"] for t in tasks}
    assert str(repo) not in folders
    assert str(new) in folders
    [main] = [t for t in tasks if t["folder"] == str(new)]
    assert {s["session_id"] for s in main["sessions"]} == {"old-main", "new-main"}
    assert main["note"] == "keep me"
    wt_new = str(new / ".claude" / "worktrees" / "feature")
    assert wt_new in folders


def test_repo_still_at_old_path_is_not_merged(repo, tmp_path):
    run_hook("a", repo)
    clone = tmp_path / "clone"
    sh(tmp_path, "git", "clone", "-q", str(repo), str(clone))
    run_hook("b", clone)
    folders = {t["folder"] for t in ledger.load_tasks(config.load())}
    assert folders == {str(repo), str(clone)}


def test_old_records_without_repo_id_match_on_name(repo, tmp_path):
    run_hook("old", repo)
    cfg = config.load()
    path = hook.session_path(cfg, "old")
    rec = hook.read_existing(path)
    rec.pop("repo_id")
    hook.atomic_write(path, rec)

    new = tmp_path / "elsewhere" / repo.name
    new.parent.mkdir()
    shutil.move(str(repo), str(new))
    run_hook("new", new)
    [task] = ledger.load_tasks(cfg)
    assert task["folder"] == str(new) and len(task["sessions"]) == 2
