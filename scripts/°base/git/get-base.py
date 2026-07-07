#!/usr/bin/env python3
"""Standalone, dependency-free bootstrap launcher.

Adds/fetches the `base` remote and sets up a local worktree so the full
`°split_lib` tooling becomes reachable, then delegates to it -- without
needing `base` merged into the current repo/branch at all, and without ever
touching the currently checked-out branch or working tree.

Deliberately stdlib-only (no imports from `°split_lib`), since none of that
exists yet when this file is fetched standalone -- it's meant to be run as:

    curl -fsSL https://raw.githubusercontent.com/luckydonald/base/master/scripts/°base/git/get-base.py | python3 - bootstrap-branch feature

or locally, once a copy is reachable on disk:

    python3 scripts/°base/git/get-base.py update-history-master --yes

Env:
    BASE_GIT_USERNAME  GitHub username/org the `base` remote points at (default: luckydonald)

The remote is always named literally "base" -- not configurable -- so it's
never confused with `origin` or some unrelated remote that happens to have
its own branch called `base`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REMOTE_NAME = "base"
REMOTE_BRANCH = "base"
DEFAULT_USERNAME = "luckydonald"


def _run(args: list[str], cwd: Path | None = None, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def find_repo_root(cwd: Path | None = None) -> Path:
    result = _run(["rev-parse", "--show-toplevel"], cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"get-base.py: not inside a git repository ({result.stderr.strip()})")
    return Path(result.stdout.strip())


def remote_url(username: str) -> str:
    return f"https://{username}@github.com/{username}/base.git"


def ensure_base_remote(repo_root: Path, username: str) -> None:
    existing = _run(["remote", "get-url", REMOTE_NAME], cwd=repo_root, check=False)
    if existing.returncode == 0:
        return  # already configured -- respect whatever URL is there, never overwrite
    _run(["remote", "add", REMOTE_NAME, remote_url(username)], cwd=repo_root)


def fetch_base(repo_root: Path) -> None:
    _run(["fetch", REMOTE_NAME, REMOTE_BRANCH], cwd=repo_root)


def worktree_path(repo_root: Path) -> Path:
    return repo_root / ".git" / "base-tools"


def _is_valid_worktree(path: Path) -> bool:
    if not path.exists():
        return False
    result = _run(["rev-parse", "--show-toplevel"], cwd=path, check=False)
    return result.returncode == 0 and Path(result.stdout.strip()) == path


def ensure_worktree(repo_root: Path) -> Path:
    path = worktree_path(repo_root)
    ref = f"{REMOTE_NAME}/{REMOTE_BRANCH}"

    if _is_valid_worktree(path):
        _run(["fetch", REMOTE_NAME, REMOTE_BRANCH], cwd=path)
        _run(["checkout", "--detach", ref], cwd=path)
        return path

    _run(["worktree", "add", "--detach", str(path), ref], cwd=repo_root)
    return path


def delegate(repo_root: Path, worktree: Path, argv: list[str]) -> None:
    split_py = worktree / "scripts" / "°base" / "git" / "split.py"
    os.execvp(sys.executable, [sys.executable, str(split_py), "--repo-root", str(repo_root), *argv])


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    username = os.environ.get("BASE_GIT_USERNAME", DEFAULT_USERNAME)

    repo_root = find_repo_root()
    ensure_base_remote(repo_root, username)
    fetch_base(repo_root)
    worktree = ensure_worktree(repo_root)
    delegate(repo_root, worktree, argv)
    return 0  # unreachable once delegate() execs, kept for testability


if __name__ == "__main__":
    raise SystemExit(main())
