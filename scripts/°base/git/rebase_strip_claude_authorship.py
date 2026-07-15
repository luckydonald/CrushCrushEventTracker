#!/usr/bin/env python3
"""Rebase onto the origin/mane merge-base while removing AI attribution.

Usage:
    python3 rebase_strip_claude_authorship.py            # run the rebase
    python3 rebase_strip_claude_authorship.py --amend-step  # internal: used as --exec callback
"""

from __future__ import annotations

import importlib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
identity = importlib.import_module("°split_lib.identity")

UPSTREAM = "origin/mane"


def capture(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()
# end def


def shell_join(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)
# end def


def head_message() -> str:
    return subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
# end def


def remove_coauthored_by(message: str) -> str:
    kept_lines = [
        line
        for line in message.splitlines(keepends=True)
        if not line.lstrip().casefold().startswith("co-authored-by:")
    ]
    return "".join(kept_lines)
# end def


def head_identities() -> tuple[identity.CommitIdentity, identity.CommitIdentity]:
    values = capture("git", "log", "-1", "--format=%an%x1f%ae%x1f%cn%x1f%ce").split("\x1f")
    author_name, author_email, committer_name, committer_email = values
    return (
        identity.CommitIdentity(author_name, author_email),
        identity.CommitIdentity(committer_name, committer_email),
    )
# end def


def amend_step() -> None:
    """Remove AI author/committer identities and Co-authored-by trailers."""
    author, committer = head_identities()
    original_message = head_message()
    cleaned_message = remove_coauthored_by(original_message)
    has_ai_identity = identity.is_ai_identity(author) or identity.is_ai_identity(committer)
    if not has_ai_identity and cleaned_message == original_message:
        return
    # end if

    replacement_author = author
    replacement_committer = committer
    if has_ai_identity:
        repo_root = Path(capture("git", "rev-parse", "--show-toplevel"))
        remaining = identity.remaining_identity(author, committer)
        replacement = identity.resolve_identity(repo_root, remaining=remaining)
        replacement_author = replacement
        replacement_committer = replacement
    # end if

    env = os.environ.copy()
    env["GIT_COMMITTER_NAME"] = replacement_committer.name
    env["GIT_COMMITTER_EMAIL"] = replacement_committer.email
    subprocess.run(
        [
            "git",
            "commit",
            "--amend",
            "--allow-empty",
            "--allow-empty-message",
            "--author",
            replacement_author.author,
            "--file",
            "-",
        ],
        check=True,
        env=env,
        input=cleaned_message,
        text=True,
    )
# end def


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--amend-step" in args:
        amend_step()
        return 0
    # end if

    subprocess.run(["git", "fetch", "origin", "mane"], check=True)
    merge_base = capture("git", "merge-base", "HEAD", UPSTREAM)
    print(f"Rebasing onto merge-base {merge_base} with {UPSTREAM}, stripping AI attribution...")

    script_path = Path(__file__).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="rebase-strip-claude-"))
    exec_script = tmp / script_path.name
    shutil.copy2(script_path, exec_script)
    # The relocated copy still imports °split_lib.identity by path relative to
    # its own location, so it needs a sibling copy of the package too.
    shutil.copytree(script_path.parent / "°split_lib", tmp / "°split_lib")
    exec_cmd = shell_join([sys.executable, str(exec_script), "--amend-step"])
    try:
        subprocess.run(["git", "rebase", merge_base, "--exec", exec_cmd], check=True)
    except subprocess.CalledProcessError as exc:
        print(
            "\nRebase stopped before AI attribution stripping completed.",
            file=sys.stderr,
        )
        print(f"Kept the rebase --exec callback at: {exec_script}", file=sys.stderr)
        print("Resolve conflicts, stage the resolved files, then run:", file=sys.stderr)
        print("  git rebase --continue", file=sys.stderr)
        print("To abandon the rebase, run:", file=sys.stderr)
        print("  git rebase --abort", file=sys.stderr)
        return exc.returncode
    shutil.rmtree(tmp)
    return 0
# end def


if __name__ == "__main__":
    raise SystemExit(main())
# end if
