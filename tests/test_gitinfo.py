from conftest import sh

from work_ledger import gitinfo


def test_main_repo(repo):
    info = gitinfo.info(repo)
    assert info["branch"] == "main" and not info["is_worktree"]
    assert info["repo"] == "proj" and info["branch_files"] == []


def test_worktree_dirty_and_branch_files(repo):
    wt = repo / ".claude/worktrees/feature"
    (wt / "c.py").write_text("c\n")
    sh(wt, "git", "add", "c.py")
    sh(wt, "git", "commit", "-q", "-m", "c")
    (wt / "a.py").write_text("changed\n")  # modified
    (wt / "new.py").write_text("new\n")  # untracked
    (wt / "b.py").unlink()  # deleted: excluded
    sh(wt, "git", "mv", "c.py", "d.py")  # renamed

    info = gitinfo.info(wt)
    assert info["is_worktree"] and info["branch"] == "feature"
    assert info["main_repo"] == str(repo)
    assert sorted(info["dirty_files"]) == ["a.py", "d.py", "new.py"]
    assert sorted(info["branch_files"]) == ["a.py", "d.py"]


def test_not_a_repo(tmp_path):
    assert gitinfo.info(tmp_path)["repo"] is None
