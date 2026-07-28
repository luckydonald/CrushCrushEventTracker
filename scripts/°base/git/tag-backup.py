#!/usr/bin/env python3
"""Tag the current `HEAD` commit as a backup, so it stays reachable (and thus
safe from `git gc`) even if the branch it's on gets reset, rebased away from,
or deleted.

Tag name: `bak/<full-hash-of-HEAD>`.

Usage:
    python3 scripts/°base/git/tag-backup.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    removal = parser.add_mutually_exclusive_group()
    removal.add_argument(
        "--remove-old-tags",
        "--remove-tags",
        "--remove-old",
        "--rm-old",
        "--rm-tags",
        "--rm",
        dest="remove_old_tags",
        action="store_true",
        help="remove tags that point to ancestors of the new backup tag",
    )
    removal.add_argument(
        "--no-remove-old-tags",
        "--no-remove-tags",
        "--no-remove-old",
        "--no-rm-old",
        "--no-rm-tags",
        "--no-rm",
        dest="remove_old_tags",
        action="store_false",
        help="do not offer to remove ancestor tags, even interactively",
    )
    parser.set_defaults(remove_old_tags=None)
    return parser.parse_args(argv)
# end def


def parent_tags(tag: str) -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--merged", tag],
        check=True,
        text=True,
        capture_output=True,
    )
    return [candidate for candidate in result.stdout.splitlines() if candidate != tag]
# end def


def should_remove_tag(tag: str) -> bool:
    try:
        answer = input(f"Remove old tag {tag}? (Y/n) ").strip().lower()
    except EOFError:
        return False
    # end try
    return answer in {"", "y", "yes"}
# end def


def remove_parent_tags(tag: str, interactive: bool) -> int:
    for old_tag in parent_tags(tag):
        if interactive and not should_remove_tag(old_tag):
            continue
        # end if
        result = subprocess.run(["git", "tag", "--delete", old_tag])
        if result.returncode != 0:
            return result.returncode
        # end if
    # end for
    return 0
# end def


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()
    tag = f"bak/{head}"

    result = subprocess.run(["git", "tag", tag, head])
    if result.returncode != 0:
        return result.returncode
    # end if

    print(f"Tagged HEAD ({head}) as {tag}")
    interactive = sys.stdin.isatty()
    if args.remove_old_tags is False or (
        args.remove_old_tags is None and not interactive
    ):
        return 0
    # end if
    return remove_parent_tags(tag, interactive=interactive and args.remove_old_tags is None)
# end def


if __name__ == "__main__":
    sys.exit(main())
