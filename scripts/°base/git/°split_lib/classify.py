"""AI/base content classification for paths and commits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

AI_IGNORE_FILENAME = ".ai-ignore"

# Matches this repo's real commit convention, e.g.:
#   "ai: updated prompt"
#   "[base] topic: ai: Run: ..."
#   "[dumper] init script: ai: Run: ..."
# but not "aisle: fix typo" or "said: hello".
AI_SUBJECT_RE = re.compile(r"^(\[.*\]\s*)?.*\bai:")


def ai_ignore_path(repo_root: Path | None = None) -> Path:
    return (repo_root or Path.cwd()) / AI_IGNORE_FILENAME
# end def


def ai_ignore_rules(ignore_file: Path | None = None) -> list[str]:
    path = ignore_file or ai_ignore_path()
    if not path.is_file():
        return []
    # end if

    return [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
# end def


def path_matches_glob(path: PurePosixPath, pattern: str) -> bool:
    pattern = pattern.removeprefix("/")
    if pattern.endswith("/"):
        pattern = f"{pattern}**"
    # end if

    patterns = [pattern]
    if "/" not in pattern:
        patterns.extend((f"**/{pattern}", f"{pattern}/**", f"**/{pattern}/**"))
    # end if
    return any(path.full_match(candidate) for candidate in patterns)
# end def


def is_ai_base_path(path: str, *, ignore_file: Path | None = None) -> bool:
    path_parts = PurePosixPath(path)
    is_ai_path = False

    for rule in ai_ignore_rules(ignore_file):
        is_negation = rule.startswith("!")
        pattern = rule[1:] if is_negation else rule
        if path_matches_glob(path_parts, pattern):
            is_ai_path = not is_negation
        # end if
    # end for

    return is_ai_path
# end def


@dataclass(frozen=True)
class CommitClassification:
    sha: str
    subject: str
    paths: tuple[str, ...]
    is_ai_only_commit: bool
    is_ai_tainted_commit: bool
    is_code_containing_commit: bool


def classify_commit(
    sha: str,
    subject: str,
    paths: Sequence[str],
    *,
    ignore_file: Path | None = None,
) -> CommitClassification:
    paths = tuple(paths)
    ai_flags = [is_ai_base_path(path, ignore_file=ignore_file) for path in paths]

    is_ai_only = bool(paths) and all(ai_flags)
    is_code_containing = any(not flag for flag in ai_flags)
    is_ai_tainted = is_ai_only or any(ai_flags) or bool(AI_SUBJECT_RE.match(subject))

    return CommitClassification(
        sha=sha,
        subject=subject,
        paths=paths,
        is_ai_only_commit=is_ai_only,
        is_ai_tainted_commit=is_ai_tainted,
        is_code_containing_commit=is_code_containing,
    )
