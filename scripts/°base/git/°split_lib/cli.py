from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import branches, classify, git_ops, push_checks


def _parse_ref_lines(text: str) -> list[push_checks.RefUpdate]:
    updates: list[push_checks.RefUpdate] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        local_ref, local_sha, remote_ref, remote_sha = line.split()
        updates.append(push_checks.RefUpdate(local_ref, local_sha, remote_ref, remote_sha))
    return updates


def _check_push(remote_name: str, remote_url: str, stdin_text: str, *, repo_root: Path) -> int:
    ref_updates = _parse_ref_lines(stdin_text)
    main_branch = branches.detect_main_branch(repo_root)

    all_violations: list[str] = []
    for ref_update in ref_updates:
        if push_checks.is_zero_sha(ref_update.local_sha):
            continue  # deletion

        branch = branches.classify_branch(ref_update.local_ref, main_branch=main_branch)

        shas = git_ops.commits_new_to_remote(
            ref_update.local_sha, ref_update.remote_sha, remote_name, repo_root
        )
        commits = [
            classify.classify_commit(
                sha,
                git_ops.subject_for_commit(sha, repo_root),
                git_ops.changed_paths_for_commit(sha, repo_root),
            )
            for sha in shas
        ]

        violations = push_checks.evaluate_ref_update(ref_update, branch, remote_name, commits)
        all_violations.extend(violations)

    if all_violations:
        print("Push blocked by base branch-split policy:", file=sys.stderr)
        for violation in all_violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="split.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_push = subparsers.add_parser(
        "check-push", help="Enforce clean/unclean/history push name+content policy."
    )
    check_push.add_argument("--remote-name", required=True)
    check_push.add_argument("--remote-url", required=True)

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "check-push":
        stdin_text = sys.stdin.read()
        root = git_ops.repo_root()
        return _check_push(args.remote_name, args.remote_url, stdin_text, repo_root=root)

    parser.error(f"Unknown command: {args.command}")
    return 2
