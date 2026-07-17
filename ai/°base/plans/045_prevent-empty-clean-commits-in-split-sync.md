# Prevent empty clean commits in split sync

## Summary

`get-base.py` chooses the correct auto-mode command. The defect is in `sync-splits`: empty unclean commits with AI-prefixed subjects are not AI-only, so their unchanged clean projection is still committed.

## Implementation changes

- In `sync_splits.sync_branch`, skip a clean projection when its filtered tree equals the current clean tip’s tree.
- Preserve the existing history-side behavior: those source commits remain represented in `ai/history/<branch>` for provenance.
- Add a separate no-op-skip count to `SyncSplitsResult` and CLI output; do not misclassify these commits as AI-only.
- Do not create a clean counterpart-tree trailer for a skipped clean projection.

## Test plan

- Add a focused regression in `test_git_split_sync_splits.py` with two `--allow-empty` unclean commits matching the reported subjects, followed by one real code commit.
- Assert clean contains exactly the real code projection and no empty commits; history retains all three source commits; rerunning creates no new commits.
- Run the focused split-sync module.
- Reproduce the reported case in a fresh `/tmp` clone before the fix: check out `ai/UNCLEAN/XXXXXX-manual-widget-refresh` at `cc6a7ba…`, delete only that branch’s local clean/history refs, retain `ai/history/master`, and run `get-base.py` with no arguments. Confirm the current failure sequence and source trailers.

## Assumptions

- “Expected” means clean should contain only the non-empty code projection (`49967ded…` from `336441f…`).
- Empty history commits are intentionally retained.
