#!/usr/bin/env python3
"""Commit Codex memory and mirror its durable notes into the current repo."""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import _is_inside_base_repo  # noqa: E402

CODEX_SOURCE_DIR = Path("extensions/ad_hoc")


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


def _project_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    # end if
    return Path(result.stdout.strip()).resolve()
# end def


def _mirror_root(project_root: Path) -> Path:
    if _is_inside_base_repo(project_root):
        return project_root / "ai" / "°base" / "memory" / "codex"
    # end if
    return project_root / "ai" / "memory" / "codex"
# end def


def _sync_mirror(source_root: Path, project_root: Path) -> list[str]:
    """Mirror Codex's durable ad-hoc notes into the current project tree."""
    source_dir = source_root / CODEX_SOURCE_DIR
    destination_dir = _mirror_root(project_root) / CODEX_SOURCE_DIR
    source_paths = set(source_dir.glob("*.md")) if source_dir.is_dir() else set()
    changed: list[str] = []

    for source in sorted(source_paths):
        destination = destination_dir / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        same = False
        if destination.is_symlink():
            try:
                same = destination.resolve() == source.resolve()
            except OSError:
                pass
            # end try
        elif destination.exists():
            try:
                same = destination.stat().st_ino == source.stat().st_ino and destination.stat().st_dev == source.stat().st_dev
            except OSError:
                pass
            # end try
        # end if
        if same:
            continue
        # end if
        if destination.is_symlink() or destination.exists():
            destination.unlink()
        # end if
        try:
            os.link(source, destination)
        except OSError:
            destination.symlink_to(source)
        # end try
        changed.append(str(destination.relative_to(project_root)))
    # end for

    if destination_dir.is_dir():
        for destination in sorted(destination_dir.glob("*.md")):
            if destination.name in {source.name for source in source_paths}:
                continue
            # end if
            destination.unlink()
            changed.append(str(destination.relative_to(project_root)))
        # end for
    # end if
    return changed
# end def


def _changed_paths(repository: Path) -> list[str]:
    result = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    # end if
    return [line[3:] if len(line) > 3 else line for line in result.stdout.splitlines() if line]
# end def


def _commit_pending(repository: Path) -> bool:
    paths = _changed_paths(repository)
    if not paths:
        return False
    # end if
    conflicts = _git(repository, "diff", "--name-only", "--diff-filter=U")
    if conflicts.returncode != 0:
        raise RuntimeError(conflicts.stderr.strip() or "git diff failed")
    # end if
    if conflicts.stdout.strip():
        raise RuntimeError("Codex memory repository has unresolved conflicts:\n" + conflicts.stdout.strip())
    # end if
    staged = _git(repository, "add", "--all", "--", ".")
    if staged.returncode != 0:
        raise RuntimeError(staged.stderr.strip() or "git add failed")
    # end if
    body = "\n".join(f"- {path}" for path in paths)
    committed = _git(repository, "commit", "--no-verify", "-m", "ai: record codex memory", "-m", body)
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip() or committed.stdout.strip() or "git commit failed")
    # end if
    return True
# end def


def _commit_project_mirror(project_root: Path, paths: list[str]) -> bool:
    if not paths:
        return False
    # end if
    unique_paths = sorted(set(paths))
    staged = _git(project_root, "add", "--all", "--", *unique_paths)
    if staged.returncode != 0:
        raise RuntimeError(staged.stderr.strip() or "git add failed for Codex memory mirror")
    # end if
    body = "\n".join(f"- {path}" for path in unique_paths)
    committed = _git(
        project_root,
        "commit",
        "--no-verify",
        "--only",
        *unique_paths,
        "-m",
        "ai: sync codex memory",
        "-m",
        body,
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip() or committed.stdout.strip() or "git commit failed for Codex memory mirror")
    # end if
    return True
# end def


def main() -> int:
    """Run only for the Codex-rendered hook invocation."""
    if len(sys.argv) < 2 or sys.argv[1] != "codex":
        return 0
    # end if
    repository = _codex_memory_repo()
    project_root = _project_root()
    if repository is None or project_root is None:
        return 0
    # end if
    try:
        lock_path = repository / ".git" / "codex-memory-hook.lock"
        with lock_path.open("a", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            # end try
            _commit_pending(repository)
            mirrored = _sync_mirror(repository, project_root)
            if _commit_project_mirror(project_root, mirrored):
                print("record-codex-memory: synced Codex memory into the project")
            # end if
        # end with
    except (OSError, RuntimeError) as exc:
        print(f"record-codex-memory: {exc}", file=sys.stderr)
        return 1
    # end try
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
