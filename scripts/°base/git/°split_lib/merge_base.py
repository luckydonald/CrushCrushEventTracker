"""Merge `base/base` into the CURRENT branch of a consuming repo -- the
"adopt base's updates" direction, as opposed to this package's usual clean/
unclean/history split-branch bookkeeping (base's own internal concern,
`sync_splits.py`/`history_master.py`). Reuses the same predictable-conflict
auto-resolution (README.md/.gitignore, `.gitattributes` safety) that
`history_master.py` already proved out for folding `base/base` into the
shadow `ai/history/<main>` branch, just applied directly to the real branch
a consuming repo actually ships from.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import git_ops, gitattributes_safety
from .history_master import FIRST_FOLD_AUTO_RESOLVE_PATHS


class MergeBaseError(Exception):
    pass
# end class


def _git(args: list[str], cwd: Path, *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)
# end def


def _conflicted_paths(cwd: Path) -> list[str]:
    result = _git(["diff", "--name-only", "--diff-filter=U"], cwd)
    return [line for line in result.stdout.splitlines() if line]
# end def


def _refuse_if_dirty(cwd: Path) -> None:
    result = _git(["status", "--porcelain"], cwd)
    if result.stdout.strip():
        raise MergeBaseError("Working tree is dirty -- commit or stash before merging base/base.")
    # end if
# end def


def _auto_resolve_predictable_conflicts(base_sha: str, conflicted: list[str], cwd: Path) -> set[str]:
    """Auto-resolve README.md/.gitignore in favor of base_sha's copy, mirroring
    history_master._auto_resolve_first_fold_conflicts. Returns the subset of
    `conflicted` actually resolved (and staged via `git add`)."""
    resolved: set[str] = set()
    for path in conflicted:
        if path not in FIRST_FOLD_AUTO_RESOLVE_PATHS:
            continue
        # end if
        content = git_ops.show_path_at(base_sha, path, cwd)
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        _git(["add", "--", path], cwd, check=True)
        resolved.add(path)
    # end for
    return resolved
# end def


def merge_base_into_current_branch(cwd: Path, message_prefix: str = "") -> str:
    """Fetch `base` and merge `base/base` into whatever branch is currently
    checked out, auto-resolving README.md/.gitignore conflicts and guarding
    `.gitattributes` the same way `history_master.py`'s base/base folding
    does. Returns the new HEAD sha.

    Raises MergeBaseError if the tree is dirty going in, the fetch/merge
    fails for a non-conflict reason, or conflicts remain after the
    auto-resolution pass -- left in place for manual resolution, same as a
    normal failed `git merge` would leave them.
    """
    _refuse_if_dirty(cwd)

    fetch = _git(["fetch", "base"], cwd)
    if fetch.returncode != 0:
        raise MergeBaseError(f"git fetch base failed: {fetch.stderr}")
    # end if

    base_sha = _git(["rev-parse", "base/base"], cwd, check=True).stdout.strip()
    unrelated = git_ops.merge_base("HEAD", base_sha, cwd) is None
    merge_args = ["merge", "--no-commit", "--no-ff"]
    if unrelated:
        merge_args.append("--allow-unrelated-histories")
    # end if
    merge_args.append("base/base")
    result = _git(merge_args, cwd)

    if result.returncode != 0:
        conflicted = _conflicted_paths(cwd)
        if not conflicted:
            git_ops.merge_abort(cwd)
            raise MergeBaseError(f"merge of base/base failed for a non-conflict reason: {result.stderr}")
        # end if

        gitattributes_resolved = (
            gitattributes_safety.GITATTRIBUTES_PATH in conflicted
            and gitattributes_safety.restore_original(base_sha, "HEAD", cwd)
        )
        auto_resolved = _auto_resolve_predictable_conflicts(base_sha, conflicted, cwd)
        if gitattributes_resolved:
            auto_resolved = auto_resolved | {gitattributes_safety.GITATTRIBUTES_PATH}
        # end if

        still_conflicted = [path for path in conflicted if path not in auto_resolved]
        if still_conflicted:
            raise MergeBaseError(
                "Merge has unresolved conflicts beyond the predictable set "
                f"(README.md/.gitignore/.gitattributes): {', '.join(still_conflicted)}. "
                "Resolve them by hand, then `git commit`."
            )
        # end if
    else:
        # Merged cleanly -- but a clean merge is exactly how a risky
        # .gitattributes change slips through unnoticed.
        gitattributes_safety.restore_original(base_sha, "HEAD", cwd)
    # end if

    _git(["-c", "core.editor=true", "commit", "--no-edit"], cwd, check=True)
    new_sha = _git(["rev-parse", "HEAD"], cwd, check=True).stdout.strip()

    if message_prefix:
        message = git_ops.commit_message(new_sha, cwd)
        if not message.startswith(message_prefix):
            _git(["commit", "--amend", "-m", f"{message_prefix}{message}"], cwd, check=True)
            new_sha = _git(["rev-parse", "HEAD"], cwd, check=True).stdout.strip()
        # end if
    # end if

    return new_sha
# end def
