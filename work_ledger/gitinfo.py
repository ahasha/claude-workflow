"""Git facts about a working folder. Standard library only."""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_LISTED = 200


def git(cwd: str | Path, *args: str, strip: bool = True) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() if strip else out.stdout


def toplevel(path: str | Path) -> str | None:
    return git(path, "rev-parse", "--show-toplevel") or None


def default_base(folder: str | Path) -> str | None:
    """The branch this repo's work merges into: origin/HEAD, else main or master."""
    if ref := git(folder, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"):
        return ref
    for name in ("main", "master"):
        if git(folder, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return None


def dirty_files(folder: str | Path) -> list[str]:
    """Paths with uncommitted changes, relative to the folder. Deletions excluded."""
    out = git(folder, "status", "--porcelain=v1", "-z", strip=False)
    if not out:
        return []
    entries = out.split("\0")
    files: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        if xy[0] in "RC":
            i += 1  # the next entry is the rename source
        if "D" in xy or path.endswith("/"):
            continue
        files.append(path)
    return files[:MAX_LISTED]


def branch_files(folder: str | Path, branch: str | None) -> list[str]:
    """Paths changed since the branch left the default branch (committed or not)."""
    base = default_base(folder)
    if not base or not branch or branch in (base, base.split("/", 1)[-1]):
        return []
    merge_base = git(folder, "merge-base", "HEAD", base)
    if not merge_base:
        return []
    out = git(folder, "diff", "--name-only", "--diff-filter=d", merge_base)
    return out.splitlines()[:MAX_LISTED] if out else []


def info(folder: str | Path) -> dict:
    top = toplevel(folder)
    if not top:
        return {
            "repo": None,
            "repo_id": None,
            "main_repo": None,
            "branch": None,
            "is_worktree": False,
            "dirty_files": [],
            "branch_files": [],
        }

    branch = git(top, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = "(detached " + (git(top, "rev-parse", "--short", "HEAD") or "?") + ")"

    # In a linked worktree, --git-common-dir points at the main repo's .git.
    common = git(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main_repo = str(Path(common).parent) if common else top

    # The root commit survives moving or renaming the folder.
    roots = git(top, "rev-list", "--max-parents=0", "HEAD")
    repo_id = min(roots.split()) if roots else None

    return {
        "repo": Path(main_repo).name,
        "repo_id": repo_id,
        "main_repo": main_repo,
        "branch": branch,
        "is_worktree": Path(main_repo).resolve() != Path(top).resolve(),
        "dirty_files": dirty_files(top),
        "branch_files": branch_files(top, branch),
    }
