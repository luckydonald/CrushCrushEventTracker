"""Guards `.gitattributes` during a `base/base` merge.

`README.md`/`.gitignore` (see history_master.FIRST_FOLD_AUTO_RESOLVE_PATHS /
sync_splits.KNOWN_NOISY_MERGE_PATHS) are safe to auto-resolve in favor of
whatever base ships, since they're just text. `.gitattributes` is different:
if base's copy newly turns on `filter=lfs` for an extension that the target
repo's own history already has *non*-LFS blobs for (e.g. it committed PNGs
before ever adopting base), silently adopting base's rules -- even via a
perfectly clean, non-conflicting merge -- causes checkout/smudge-filter
mismatches between the old plain blobs and anything touched after the
merge. So this is the inverse of the README/.gitignore case: base's version
must NOT win, and this has to be checked even when there's no textual
conflict at all (a repo with no `.gitattributes` yet merges base's in with
zero conflict, which is exactly the dangerous case).

Used by history_master.py (folding base/base into ai/history/{main}) and
sync_splits.py (a real merge attempt for a merge commit found inside
ai/UNCLEAN/*).
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

from . import git_ops

GITATTRIBUTES_PATH = ".gitattributes"

# Matches a gitattributes line like `*.png  filter=lfs diff=lfs merge=lfs -text`
# -- the pattern is the first whitespace-delimited token, "filter=lfs" appears
# somewhere in the attribute list that follows.
_LFS_LINE_RE = re.compile(r"^(\S+)\s+.*\bfilter=lfs\b")


def _parse_lfs_patterns(gitattributes_text: str) -> set[str]:
    patterns: set[str] = set()
    for line in gitattributes_text.splitlines():
        match = _LFS_LINE_RE.match(line.strip())
        if match:
            patterns.add(match.group(1))
    return patterns


def _gitattributes_lfs_patterns(ref: str, cwd: Path) -> set[str]:
    """LFS-filtered glob patterns from `.gitattributes` as it exists at
    `ref`. Empty set if `ref` has no `.gitattributes` at all."""
    entry = git_ops.ls_tree_entry(ref, GITATTRIBUTES_PATH, cwd)
    if entry is None:
        return set()
    content = git_ops.show_path_at(ref, GITATTRIBUTES_PATH, cwd).decode(errors="replace")
    return _parse_lfs_patterns(content)


def _matches_any_pattern(basename: str, patterns: set[str]) -> bool:
    return any(fnmatch.fnmatch(basename, pattern) for pattern in patterns)


def _historical_basenames(ref: str, cwd: Path) -> set[str]:
    """Every basename that has ever appeared in `ref`'s own reachable
    history (added, modified, renamed, or since-deleted) -- not just what's
    currently checked out. A since-deleted file's blob is still reachable
    (checkout of an old revision, `git show`, `git blame`, ...), so a
    retroactive attribute change still affects it.
    """
    result = subprocess.run(
        ["git", "log", ref, "--name-only", "--pretty=format:"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    basenames: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            basenames.add(Path(line).name)
    return basenames


def should_protect(base_sha: str, onto: str, cwd: Path) -> bool:
    """True if adopting `base_sha`'s `.gitattributes` LFS rules onto `onto`
    would newly enable LFS filtering (a pattern `onto`'s own current
    `.gitattributes` doesn't already have) for an extension that `onto`'s
    own history already has non-LFS blobs for.
    """
    base_patterns = _gitattributes_lfs_patterns(base_sha, cwd)
    if not base_patterns:
        return False
    onto_patterns = _gitattributes_lfs_patterns(onto, cwd)
    new_patterns = base_patterns - onto_patterns
    if not new_patterns:
        return False
    basenames = _historical_basenames(onto, cwd)
    return any(_matches_any_pattern(name, new_patterns) for name in basenames)


def restore_original(base_sha: str, onto: str, cwd: Path) -> bool:
    """If `should_protect(base_sha, onto, cwd)`, restore `onto`'s original
    `.gitattributes` into the current working tree + index (or remove it
    entirely, if `onto` never had one) instead of whatever the merge just
    produced -- undoing base's change regardless of whether it came from a
    clean auto-merge or a conflict resolution. No-op (returns False) when
    protection isn't needed, including a merge that would legitimately just
    reproduce `onto`'s own content.
    """
    if not should_protect(base_sha, onto, cwd):
        return False

    entry = git_ops.ls_tree_entry(onto, GITATTRIBUTES_PATH, cwd)
    target = cwd / GITATTRIBUTES_PATH
    if entry is None:
        if target.exists():
            target.unlink()
        subprocess.run(
            ["git", "rm", "-f", "--cached", "--ignore-unmatch", "--", GITATTRIBUTES_PATH],
            cwd=cwd,
            capture_output=True,
        )
    else:
        content = git_ops.show_path_at(onto, GITATTRIBUTES_PATH, cwd)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        subprocess.run(
            ["git", "add", "--", GITATTRIBUTES_PATH],
            cwd=cwd,
            check=True,
            capture_output=True,
        )
    return True
