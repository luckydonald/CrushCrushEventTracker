#!/usr/bin/env python3
"""Tag a commit as a backup ref: `bak/<full commit hash>`.

Usage:
    python3 tag_backup.py            # tag HEAD
    python3 tag_backup.py <commit>   # tag the given commit-ish
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def resolve_commit(commit_ish: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit_ish}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"tag_backup.py: not a valid commit: {commit_ish!r}\n{result.stderr.strip()}")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "commit",
        nargs="?",
        default="HEAD",
        help="Commit-ish to tag (default: HEAD).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    commit_hash = resolve_commit(args.commit)
    tag_name = f"bak/{commit_hash}"

    existing = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag_name}"],
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0:
        print(f"{tag_name} already exists (pointing at {commit_hash})")
        return 0

    subprocess.run(["git", "tag", tag_name, commit_hash], check=True)
    print(f"Tagged {commit_hash} as {tag_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
