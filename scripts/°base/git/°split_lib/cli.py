from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import branches, classify, git_ops, push_checks
from . import history_master as history_master_lib
from . import rebase_to_master as rebase_to_master_lib
from . import sync_splits as sync_splits_lib
from . import sync_unclean as sync_unclean_lib


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


def _sync_splits(args: argparse.Namespace, *, repo_root: Path, main_branch: str) -> int:
    if args.direction == "to-clean-history":
        targets = [args.branch] if args.branch else sync_splits_lib.discover_unclean_branches(repo_root)
        for branch in targets:
            result = sync_splits_lib.sync_branch(
                branch, repo_root=repo_root, main_branch=main_branch, dry_run=args.dry_run
            )
            print(
                f"{branch}: clean +{result.clean_commits_created} "
                f"(skipped {result.clean_commits_skipped_ai_only}), "
                f"history +{result.history_commits_created}"
            )
        return 0

    # to-unclean
    targets = [args.branch] if args.branch else sync_splits_lib.discover_unclean_branches(repo_root)
    exit_code = 0
    for branch in targets:
        try:
            result = sync_unclean_lib.reconstruct_unclean(
                branch,
                repo_root=repo_root,
                main_branch=main_branch,
                allow_diverge_rewrite=args.allow_diverge_rewrite,
                force=args.force,
                dry_run=args.dry_run,
            )
        except ValueError as exc:
            print(f"{branch}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"{branch}: {result}")
        if result.get("divergences_found") and not args.allow_diverge_rewrite:
            exit_code = 1
    return exit_code


def _update_history_master(args: argparse.Namespace, *, repo_root: Path, main_branch: str) -> int:
    try:
        result = history_master_lib.update_history_master(
            repo_root=repo_root,
            main_branch=main_branch,
            force_merge=args.force_merge,
            pull_master=args.pull_master,
            pull_base=args.pull_base,
            yes=args.yes,
            continue_=args.continue_,
            abort=args.abort,
            dry_run=args.dry_run,
        )
    except history_master_lib.HistoryMasterError as exc:
        print(f"update-history-master: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0 if result.get("status") != "conflict" else 1


def _rebase_branches_to_master(args: argparse.Namespace, *, repo_root: Path, main_branch: str) -> int:
    targets = [args.branch] if args.branch else sync_splits_lib.discover_unclean_branches(repo_root)
    exit_code = 0
    for branch in targets:
        try:
            result = rebase_to_master_lib.rebase_branches_to_master(
                branch, repo_root=repo_root, main_branch=main_branch, yes=args.yes, dry_run=args.dry_run
            )
        except ValueError as exc:
            print(f"{branch}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"{branch}: {result}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="split.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_push = subparsers.add_parser(
        "check-push", help="Enforce clean/unclean/history push name+content policy."
    )
    check_push.add_argument("--remote-name", required=True)
    check_push.add_argument("--remote-url", required=True)

    sync_splits = subparsers.add_parser(
        "sync-splits", help="Generate/update clean+history from unclean, or reconstruct unclean from them."
    )
    sync_splits.add_argument("branch", nargs="?", help="Base branch name. Omit to process all ai/UNCLEAN/* branches.")
    sync_splits.add_argument(
        "--direction", choices=["to-clean-history", "to-unclean"], default="to-clean-history"
    )
    sync_splits.add_argument("--dry-run", action="store_true")
    sync_splits.add_argument("--force", action="store_true")
    sync_splits.add_argument("--allow-diverge-rewrite", action="store_true")

    update_history = subparsers.add_parser("update-history-master", help="Rebuild ai/history/master.")
    update_history.add_argument("--force-merge", action="append", default=[], metavar="BRANCH")
    update_history.add_argument("--pull-master", action="store_true")
    update_history.add_argument("--pull-base", action="store_true")
    update_history.add_argument("--yes", action="store_true")
    update_history.add_argument("--continue", dest="continue_", action="store_true")
    update_history.add_argument("--abort", action="store_true")
    update_history.add_argument("--dry-run", action="store_true")

    rebase_branches = subparsers.add_parser(
        "rebase-branches-to-master", help="Rebase clean/history/unclean onto their current masters."
    )
    rebase_branches.add_argument("branch", nargs="?", help="Base branch name. Omit to process all detected branches.")
    rebase_branches.add_argument("--yes", action="store_true")
    rebase_branches.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "check-push":
        stdin_text = sys.stdin.read()
        root = git_ops.repo_root()
        return _check_push(args.remote_name, args.remote_url, stdin_text, repo_root=root)

    if args.command == "sync-splits":
        root = git_ops.repo_root()
        main_branch = branches.detect_main_branch(root)
        return _sync_splits(args, repo_root=root, main_branch=main_branch)

    if args.command == "update-history-master":
        root = git_ops.repo_root()
        main_branch = branches.detect_main_branch(root)
        return _update_history_master(args, repo_root=root, main_branch=main_branch)

    if args.command == "rebase-branches-to-master":
        root = git_ops.repo_root()
        main_branch = branches.detect_main_branch(root)
        return _rebase_branches_to_master(args, repo_root=root, main_branch=main_branch)

    parser.error(f"Unknown command: {args.command}")
    return 2
