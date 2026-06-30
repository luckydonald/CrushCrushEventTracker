#!/usr/bin/env python3
"""Rebase the current branch onto its merge-base with origin/mane, rewriting any
claude[bot] author/committer identity to Lucky Lucy's along the way.

Usage:
    python3 rebase_strip_claude_authorship.py            # run the rebase
    python3 rebase_strip_claude_authorship.py --amend-step  # internal: used as --exec callback
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

UPSTREAM = "origin/mane"
CLAUDE_EMAIL = "41898282+claude[bot]@users.noreply.github.com"
NEW_NAME = "✨❯ Lucky Lucy"
NEW_EMAIL = "claude._.ai._.code@luckydonald.de"
NEW_AUTHOR = f"{NEW_NAME} <{NEW_EMAIL}>"


def capture(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def amend_step() -> None:
    """Rewrite HEAD's author/committer if it's the claude[bot] identity."""
    author_email = capture("git", "log", "-1", "--format=%ae")
    committer_email = capture("git", "log", "-1", "--format=%ce")
    if CLAUDE_EMAIL not in (author_email, committer_email):
        return

    env = os.environ.copy()
    env["GIT_COMMITTER_NAME"] = NEW_NAME
    env["GIT_COMMITTER_EMAIL"] = NEW_EMAIL
    subprocess.run(
        ["git", "commit", "--amend", "--no-edit", "--author", NEW_AUTHOR],
        check=True,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--amend-step" in args:
        amend_step()
        return 0

    subprocess.run(["git", "fetch", "origin", "mane"], check=True)
    merge_base = capture("git", "merge-base", "HEAD", UPSTREAM)
    print(f"Rebasing onto merge-base {merge_base} with {UPSTREAM}, stripping claude[bot] authorship...")

    script_path = Path(__file__).resolve()
    exec_cmd = f"{sys.executable} {script_path} --amend-step"
    subprocess.run(["git", "rebase", merge_base, "--exec", exec_cmd], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
