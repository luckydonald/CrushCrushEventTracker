"""(A) sync-splits forward direction: `ai/UNCLEAN/{branch}` -> `{branch}`
(clean) and -> `ai/history/{branch}` (history).

See ai/°base/todo.md and the sync-splits design plan for the full picture.
This module only implements the forward-replay orchestration; tree-splitting
mechanics live in tree_ops.py, trailer plumbing in trailers.py.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import branches, classify, git_ops, gitattributes_safety, identity, trailers, tree_ops
from . import sync_unclean

SOURCE_TRAILER = "X-Base-Split-Source"
KIND_TRAILER = "X-Base-Split-Kind"
COUNTERPART_TREE_TRAILER = "X-Base-Split-Counterpart-Tree"
ORIGINAL_MERGE_PARENTS_TRAILER = "X-Base-Split-Original-Merge-Parents"
CLEAN_COMMIT_TRAILER = "X-Base-History-Clean-Commit"

# Mirrors history_master.FIRST_FOLD_AUTO_RESOLVE_PATHS: these two files
# predictably differ between any two independently-maintained trees, so a
# real (non-flattened) merge attempt (see build_filtered_merge_commit)
# auto-resolves them in favor of the incoming side rather than surfacing a
# conflict.
KNOWN_NOISY_MERGE_PATHS = ("README.md", ".gitignore")


class UncleanMergeDetected(RuntimeError):
    """A commit in the unclean branch's replay range is a merge commit (2+
    parents) -- sync-splits doesn't guess how to split a merge automatically;
    the CLI layer decides (fake/attempt-real-merge/manual/abort) instead.

    `target` is "clean" or "history" -- which pass (and therefore which
    output ref) hit the merge, since the two passes walk independently and a
    resolution for one doesn't necessarily resolve the other.
    """

    def __init__(self, sha: str, parents: list[str], target: str) -> None:
        super().__init__(
            f"{sha} is a merge commit ({len(parents)} parents); cannot auto-split onto {target}."
        )
        self.sha = sha
        self.parents = parents
        self.target = target


def find_last_synced_source(target_ref: str, cwd: Path) -> str | None:
    """Read the target branch tip's `X-Base-Split-Source` trailer.

    Returns None if the ref doesn't exist or has no such trailer -- the
    forward cursor is read directly off the branch tip, not a side ref.
    """
    tip = git_ops.rev_parse(target_ref, cwd)
    if tip is None:
        return None
    message = git_ops.commit_message(tip, cwd)
    return trailers.read_trailer_value(message, SOURCE_TRAILER, cwd)


def forward_cursor_ref(base_branch: str, target: str) -> str:
    """Ref storing the most recent unclean source processed for one target."""
    assert target in ("clean", "history")
    return f"refs/base-split/forward-cursor/{target}/{base_branch}"
# end def


def find_forward_cursor(base_branch: str, target: str, target_ref: str, cwd: Path) -> str | None:
    """Read the side cursor, falling back to old message trailers once."""
    cursor = git_ops.rev_parse(forward_cursor_ref(base_branch, target), cwd)
    if cursor is not None:
        return cursor
    # end if
    return find_last_synced_source(target_ref, cwd)
# end def


def find_reconstruction_correlated_cursor(unclean_ref: str, target_ref: str, cwd: Path) -> str | None:
    """Fallback cursor for the first forward run after `sync_unclean.
    reconstruct_unclean` built `unclean_ref` from a clean-only/history-only
    branch (e.g. via `bootstrap-branch`).

    That reverse direction tags commits it creates on `unclean_ref` with
    `sync_unclean.RECON_TRAILER`, not `SOURCE_TRAILER` -- so `target_ref`'s
    own tip carries no trailer `find_last_synced_source` can read, even
    though its content is already fully represented on `unclean_ref`.
    Walk `unclean_ref` newest-first and return the first commit whose
    reconstruction trailer resolves to a real commit that is `target_ref`'s
    tip or an ancestor of it -- i.e. the furthest-forward point already
    covered, so replay can resume strictly after it instead of duplicating
    everything back to `merge-base(unclean_ref, lower_bound_ref)`.
    """
    target_tip = git_ops.rev_parse(target_ref, cwd)
    if target_tip is None:
        return None

    for sha in reversed(git_ops.rev_list_reverse(unclean_ref, cwd)):
        message = git_ops.commit_message(sha, cwd)
        candidate = trailers.read_trailer_value(message, sync_unclean.RECON_TRAILER, cwd)
        if candidate is None or not git_ops.rev_exists(candidate, cwd):
            continue
        if candidate == target_tip or git_ops.is_ancestor(candidate, target_tip, cwd):
            return sha
    return None


def commits_to_replay(
    unclean_ref: str,
    last_synced_source: str | None,
    lower_bound_ref: str,
    cwd: Path,
) -> list[str]:
    """Commits on `unclean_ref` still needing replay, oldest first.

    Walked first-parent-only (see git_ops.rev_list_first_parent_reverse):
    `unclean_ref` is allowed to contain a merge commit (e.g. someone merges
    `base/base` straight into it), and a plain range walk would otherwise
    also pull in that merge's entire second-parent ancestry as if each of
    those commits belonged to this branch's own history.
    """
    if last_synced_source is not None:
        return git_ops.rev_list_first_parent_reverse(f"{last_synced_source}..{unclean_ref}", cwd)

    base = git_ops.merge_base(unclean_ref, lower_bound_ref, cwd)
    if base is None:
        return git_ops.rev_list_first_parent_reverse(unclean_ref, cwd)
    return git_ops.rev_list_first_parent_reverse(f"{base}..{unclean_ref}", cwd)


def ensure_branch_started(ref: str, base_ref: str, cwd: Path, *, dry_run: bool = False) -> str:
    """Ensure `ref` exists (creating it at `base_ref`'s tip if missing) and
    return its current tip sha.

    In dry-run mode, no ref is actually created; the "current tip" is
    computed as if it had been.
    """
    tip = git_ops.rev_parse(ref, cwd)
    if tip is not None:
        return tip

    base_tip = git_ops.rev_parse(base_ref, cwd)
    assert base_tip is not None, f"base ref {base_ref!r} does not exist"

    if not dry_run:
        git_ops.create_branch(ref, base_tip, cwd)

    return base_tip


def kind_for(cls: classify.CommitClassification) -> str:
    if cls.is_ai_only_commit:
        return "history"
    if not cls.is_ai_tainted_commit:
        return "code"
    return "mixed"


def _author_info(sha: str, cwd: Path) -> tuple[str, str, str]:
    """Return (author_name, author_email, author_date) for `sha`, author_date
    as a raw git-acceptable date string (`%ad --date=raw`)."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%an%x1f%ae%x1f%ad", "--date=raw", sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    name, email, date = result.stdout.strip().split("\x1f")
    return name, email, date


def _committer_date_now() -> str:
    return "%d +0000" % int(time.time())


def make_split_commit(
    parent: str,
    tree: str,
    source_sha: str,
    kind: str,
    extra_trailers: dict[str, str],
    cwd: Path,
    *,
    include_provenance: bool = True,
) -> str:
    author_name, author_email, author_date = _author_info(source_sha, cwd)
    base_message = git_ops.commit_message(source_sha, cwd)

    if include_provenance:
        trailer_values = {SOURCE_TRAILER: source_sha, KIND_TRAILER: kind}
        trailer_values.update(extra_trailers)
        message = trailers.write_trailers(base_message, trailer_values, cwd)
    else:
        message = trailers.strip_trailers_with_prefix(base_message, "X-Base-")
    # end if
    committer = identity.resolve_identity(
        cwd,
        remaining=identity.CommitIdentity(author_name, author_email),
    )

    return git_ops.commit_tree(
        tree,
        [parent],
        message,
        cwd,
        author_name=author_name,
        author_email=author_email,
        author_date=author_date,
        committer_name=committer.name,
        committer_email=committer.email,
        committer_date=_committer_date_now(),
    )


@dataclass(frozen=True)
class SyncSplitsResult:
    branch: str
    clean_ref: str
    clean_commits_created: int
    clean_commits_skipped_ai_only: int
    clean_commits_skipped_noop: int
    history_ref: str
    history_commits_created: int


def sync_branch(
    base_branch: str,
    *,
    repo_root: Path,
    main_branch: str,
    dry_run: bool = False,
    fake_merges: bool = False,
) -> SyncSplitsResult:
    """`fake_merges`: when a source commit in `ai/UNCLEAN/*`'s replay range is
    itself a merge commit (2+ parents), the default is to raise
    `UncleanMergeDetected` rather than guess how to split it -- the CLI layer
    then decides. Passing `fake_merges=True` instead processes it exactly
    like any ordinary commit: `tree_ops.build_filtered_tree` already diffs
    any commit (merge or not) against only its first parent, so the merge
    lands as one flattened single-parent split commit containing its net
    changes, tagged with `ORIGINAL_MERGE_PARENTS_TRAILER` for provenance.
    """
    cwd = repo_root
    ignore_file = classify.ai_ignore_path(repo_root)
    unclean_ref = branches.unclean_name(base_branch)
    clean_ref = base_branch
    history_ref = branches.history_name(base_branch)
    history_main_ref = branches.history_name(main_branch)

    clean_tip = ensure_branch_started(clean_ref, main_branch, cwd, dry_run=dry_run)

    history_existed = git_ops.rev_parse(history_ref, cwd) is not None
    history_tip = ensure_branch_started(history_ref, history_main_ref, cwd, dry_run=dry_run)
    if not history_existed and not dry_run:
        # Record which ai/history/master commit this branch's history forked
        # from, so update-history-master can later replay only the commits
        # unique to it without relying on a merge-base fallback.
        git_ops.create_branch(branches.history_fork_point_ref(base_branch), history_tip, cwd)

    # --- clean pass ---
    clean_last_source = find_forward_cursor(base_branch, "clean", clean_ref, cwd)
    if clean_last_source is None:
        clean_last_source = find_reconstruction_correlated_cursor(unclean_ref, clean_ref, cwd)
    clean_source_shas = commits_to_replay(unclean_ref, clean_last_source, main_branch, cwd)

    source_to_clean_commit: dict[str, str] = {}
    clean_commits_created = 0
    clean_commits_skipped_ai_only = 0
    clean_commits_skipped_noop = 0

    for source_sha in clean_source_shas:
        parents = git_ops.parents_of(source_sha, cwd)
        if len(parents) > 1 and not fake_merges:
            if not dry_run and clean_commits_created > 0:
                git_ops.move_ref(clean_ref, clean_tip, None, cwd)
            raise UncleanMergeDetected(source_sha, parents, "clean")

        cls = classify.classify_commit(
            source_sha,
            git_ops.subject_for_commit(source_sha, cwd),
            git_ops.changed_paths_for_commit(source_sha, cwd),
            ignore_file=ignore_file,
        )
        kind = kind_for(cls)

        if cls.is_ai_only_commit:
            clean_commits_skipped_ai_only += 1
            continue

        clean_tree = tree_ops.build_filtered_tree(
            git_ops.tree_for_commit(clean_tip, cwd),
            source_sha,
            cwd,
            keep=lambda p: not classify.is_ai_base_path(p, ignore_file=ignore_file),
        )
        if clean_tree == git_ops.tree_for_commit(clean_tip, cwd):
            clean_commits_skipped_noop += 1
            continue
        # end if

        new_clean_tip = make_split_commit(
            clean_tip, clean_tree, source_sha, kind, {}, cwd, include_provenance=False
        )
        clean_tip = new_clean_tip
        source_to_clean_commit[source_sha] = new_clean_tip
        clean_commits_created += 1

    if not dry_run and clean_commits_created > 0:
        git_ops.move_ref(clean_ref, clean_tip, None, cwd)
    if not dry_run and clean_source_shas:
        git_ops.move_ref(forward_cursor_ref(base_branch, "clean"), clean_source_shas[-1], None, cwd)

    # --- history pass ---
    history_last_source = find_forward_cursor(base_branch, "history", history_ref, cwd)
    if history_last_source is None:
        history_last_source = find_reconstruction_correlated_cursor(unclean_ref, history_ref, cwd)
    history_source_shas = commits_to_replay(unclean_ref, history_last_source, history_main_ref, cwd)

    history_commits_created = 0

    for source_sha in history_source_shas:
        parents = git_ops.parents_of(source_sha, cwd)
        if len(parents) > 1 and not fake_merges:
            if not dry_run and history_commits_created > 0:
                git_ops.move_ref(history_ref, history_tip, None, cwd)
            raise UncleanMergeDetected(source_sha, parents, "history")

        cls = classify.classify_commit(
            source_sha,
            git_ops.subject_for_commit(source_sha, cwd),
            git_ops.changed_paths_for_commit(source_sha, cwd),
            ignore_file=ignore_file,
        )
        kind = kind_for(cls)

        history_tree = tree_ops.build_filtered_tree(
            git_ops.tree_for_commit(history_tip, cwd),
            source_sha,
            cwd,
            keep=lambda p: classify.is_ai_base_path(p, ignore_file=ignore_file),
        )

        extra_trailers: dict[str, str] = {}
        counterpart_commit = source_to_clean_commit.get(source_sha)
        if counterpart_commit is not None:
            extra_trailers[CLEAN_COMMIT_TRAILER] = counterpart_commit
            extra_trailers[COUNTERPART_TREE_TRAILER] = git_ops.tree_for_commit(counterpart_commit, cwd)
        if len(parents) > 1:
            extra_trailers[ORIGINAL_MERGE_PARENTS_TRAILER] = " ".join(parents)

        new_history_tip = make_split_commit(history_tip, history_tree, source_sha, kind, extra_trailers, cwd)
        history_tip = new_history_tip
        history_commits_created += 1

    if not dry_run and history_commits_created > 0:
        git_ops.move_ref(history_ref, history_tip, None, cwd)
    if not dry_run and history_source_shas:
        git_ops.move_ref(forward_cursor_ref(base_branch, "history"), history_source_shas[-1], None, cwd)

    return SyncSplitsResult(
        branch=base_branch,
        clean_ref=clean_ref,
        clean_commits_created=clean_commits_created,
        clean_commits_skipped_ai_only=clean_commits_skipped_ai_only,
        clean_commits_skipped_noop=clean_commits_skipped_noop,
        history_ref=history_ref,
        history_commits_created=history_commits_created,
    )


def _conflicted_paths(cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"], cwd=cwd, capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line]


def _current_checkout(cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _cleanup_merge_scratch(cwd: Path, scratch_branch: str, original_checkout: str | None) -> None:
    if original_checkout is not None:
        subprocess.run(["git", "checkout", original_checkout], cwd=cwd, capture_output=True)
    else:
        subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=cwd, capture_output=True)
    subprocess.run(["git", "update-ref", "-d", f"refs/heads/{scratch_branch}"], cwd=cwd, capture_output=True)


def build_filtered_merge_commit(
    onto: str,
    second_parent_sha: str,
    source_sha: str,
    kind: str,
    keep: Callable[[str], bool],
    cwd: Path,
) -> str | None:
    """Attempt a REAL 2-parent merge of `second_parent_sha` onto `onto`,
    filtered so only paths satisfying `keep` survive in the result -- even a
    cleanly-merging path gets stripped if `keep` rejects it (a clean-branch
    attempt must never end up with AI content just because the incoming side
    didn't conflict on it). `KNOWN_NOISY_MERGE_PATHS` conflicts auto-resolve
    in favor of `second_parent_sha`'s content (mirrors
    history_master.py's first-fold auto-resolve). Any OTHER genuine conflict
    aborts the attempt (returns None) so the caller can offer other options
    instead. Whatever was checked out before this call is restored afterward,
    success or failure -- this never leaves the caller's repo detached.
    """
    original_checkout = _current_checkout(cwd)
    scratch_branch = "_base_split_merge_scratch"
    subprocess.run(["git", "checkout", "--detach", onto], cwd=cwd, capture_output=True, check=True)
    subprocess.run(["git", "update-ref", "-d", f"refs/heads/{scratch_branch}"], cwd=cwd, capture_output=True)
    git_ops.create_branch(scratch_branch, onto, cwd)
    git_ops.checkout_branch(scratch_branch, cwd)

    merge_result = git_ops.merge_no_commit(second_parent_sha, cwd)
    if merge_result.returncode != 0:
        conflicted = _conflicted_paths(cwd)
        if not conflicted:
            git_ops.merge_abort(cwd)
            _cleanup_merge_scratch(cwd, scratch_branch, original_checkout)
            return None
        # .gitattributes is the inverse of KNOWN_NOISY_MERGE_PATHS: the
        # incoming side must never win if onto's own history already has
        # non-LFS blobs for an extension it would newly filter (see
        # gitattributes_safety.py) -- resolved separately, before the
        # generic "take theirs" loop below.
        gitattributes_resolved = (
            gitattributes_safety.GITATTRIBUTES_PATH in conflicted
            and gitattributes_safety.restore_original(second_parent_sha, onto, cwd)
        )
        remaining: list[str] = []
        for path in conflicted:
            if path == gitattributes_safety.GITATTRIBUTES_PATH and gitattributes_resolved:
                continue
            if path in KNOWN_NOISY_MERGE_PATHS:
                content = git_ops.show_path_at(second_parent_sha, path, cwd)
                target = cwd / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                subprocess.run(["git", "add", "--", path], cwd=cwd, check=True)
            else:
                remaining.append(path)
        if remaining:
            git_ops.merge_abort(cwd)
            _cleanup_merge_scratch(cwd, scratch_branch, original_checkout)
            return None
    else:
        # Merged cleanly -- but a clean merge is exactly how a risky
        # .gitattributes change slips through unnoticed.
        gitattributes_safety.restore_original(second_parent_sha, onto, cwd)

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    for path in tracked:
        if not keep(path):
            subprocess.run(["git", "rm", "-q", "--cached", "--", path], cwd=cwd, capture_output=True, check=True)
            target = cwd / path
            if target.exists():
                target.unlink()

    tree = subprocess.run(["git", "write-tree"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    author_name, author_email, author_date = _author_info(source_sha, cwd)
    message = trailers.strip_trailers_with_prefix(git_ops.commit_message(source_sha, cwd), "X-Base-")
    new_sha = git_ops.commit_tree(
        tree,
        [onto, second_parent_sha],
        message,
        cwd,
        author_name=author_name,
        author_email=author_email,
        author_date=author_date,
        committer_name=identity.BOT_NAME,
        committer_email=identity.BOT_EMAIL,
        committer_date=_committer_date_now(),
    )
    _cleanup_merge_scratch(cwd, scratch_branch, original_checkout)
    return new_sha


def discover_unclean_branches(cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/ai/UNCLEAN/"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    names: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        base_name = branches.base_name_from_unclean(line)
        if base_name is not None:
            names.append(base_name)
    return names
