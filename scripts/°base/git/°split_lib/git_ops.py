"""Subprocess glue for the push-check CLI. Kept separate from push_checks.py
so the policy logic stays pure and unit-testable without touching git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def repo_root(cwd: Path | None = None) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def rev_exists(sha: str, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=cwd,
        capture_output=True,
    )
    return result.returncode == 0


def commits_new_to_remote(local_sha: str, remote_sha: str, remote_name: str, cwd: Path) -> list[str]:
    """Commits reachable from local_sha not already reachable from remote_sha.

    Oldest first. Handles branch deletion (empty result) and brand-new
    branches (remote_sha unknown locally, or all-zero) via the same
    ``--not --remotes=`` fallback pre-commit itself uses.
    """
    is_deletion = set(local_sha) == {"0"}
    if is_deletion:
        return []

    is_new_remote_ref = set(remote_sha) == {"0"} or not rev_exists(remote_sha, cwd)
    if is_new_remote_ref:
        args = ["git", "rev-list", "--reverse", local_sha, "--not", f"--remotes={remote_name}"]
    else:
        args = ["git", "rev-list", "--reverse", f"{remote_sha}..{local_sha}"]

    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return [line for line in result.stdout.splitlines() if line]


def changed_paths_for_commit(sha: str, cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def subject_for_commit(sha: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s", sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
