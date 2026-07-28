#!/usr/bin/env python3
"""Tag the current `HEAD` commit as a backup, so it stays reachable (and thus
safe from `git gc`) even if the branch it's on gets reset, rebased away from,
or deleted.

Tag name: `bak/<full-hash-of-HEAD>`.

Usage:
    python3 scripts/°base/git/tag-backup.py
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()
    tag = f"bak/{head}"

    result = subprocess.run(["git", "tag", tag, head])
    if result.returncode != 0:
        return result.returncode

    print(f"Tagged HEAD ({head}) as {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
