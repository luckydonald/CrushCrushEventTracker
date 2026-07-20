#!/usr/bin/env python3
"""Commit pending changes in Codex's standalone global memory repository."""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path


def _codex_memory_repo() -> Path | None:
    """Return the configured Codex memory repository, if it exists."""
    codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    repository = codex_home / "memories"
    if not (repository / ".git").exists():
        return None
    # end if
    return repository
# end def


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        capture_output=True,
        text=True,
    )
# end def


def _changed_paths(repository: Path) -> list[str]:
    result = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    # end if
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        # Porcelain v1 uses a two-column status prefix. Renames have two paths;
        # the complete status line remains useful in the commit body.
        paths.append(line[3:] if len(line) > 3 else line)
    # end for
    return paths
# end def


def _commit_pending(repository: Path) -> bool:
    lock_path = repository / ".git" / "codex-memory-hook.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        paths = _changed_paths(repository)
        if not paths:
            return False
        # end if

        conflicts = _git(repository, "diff", "--name-only", "--diff-filter=U")
        if conflicts.returncode != 0:
            raise RuntimeError(conflicts.stderr.strip() or "git diff failed")
        # end if
        if conflicts.stdout.strip():
            raise RuntimeError(
                "Codex memory repository has unresolved conflicts:\n"
                + conflicts.stdout.strip()
            )
        # end if

        staged = _git(repository, "add", "--all", "--", ".")
        if staged.returncode != 0:
            raise RuntimeError(staged.stderr.strip() or "git add failed")
        # end if
        body = "\n".join(f"- {path}" for path in paths)
        committed = _git(
            repository,
            "commit",
            "--no-verify",
            "-m",
            "ai: record codex memory",
            "-m",
            body,
        )
        if committed.returncode != 0:
            raise RuntimeError(committed.stderr.strip() or committed.stdout.strip() or "git commit failed")
        # end if
        return True
    # end with
# end def


def main() -> int:
    """Run only for the Codex-rendered hook invocation."""
    if len(sys.argv) < 2 or sys.argv[1] != "codex":
        return 0
    # end if
    repository = _codex_memory_repo()
    if repository is None:
        return 0
    # end if
    try:
        if _commit_pending(repository):
            print("record-codex-memory: committed pending memory changes")
        # end if
    except (OSError, RuntimeError) as exc:
        print(f"record-codex-memory: {exc}", file=sys.stderr)
        return 1
    # end try
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
