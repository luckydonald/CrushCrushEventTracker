No plan file needed since this is investigation-only; presenting findings directly.

## Findings

**Test expectation (`scripts/°base/tests/test_git_split_recovery.py:41-55`):**
```python
def test_single_branch_includes_all_derived_refs(self):
    refs = recovery.resolve_watched_refs("feature", "master", self.repo)
    self.assertEqual(
        refs,
        [
            "master",
            "ai/history/master",
            "feature",
            "ai/UNCLEAN/feature",
            "ai/history/feature",
            "refs/base-split/history-master-fork-point/feature",
            "refs/base-split/unclean-cursor/clean/feature",
            "refs/base-split/unclean-cursor/history/feature",
        ],
    )
```
This literal list has **no** `forward-cursor` entries.

**Implementation (`scripts/°base/git/°split_lib/recovery.py:26-43`):**
```python
def resolve_watched_refs(branch: str | None, main_branch: str, cwd: Path) -> list[str]:
    branches_to_cover = [branch] if branch is not None else sync_splits.discover_unclean_branches(cwd)
    refs: list[str] = [main_branch, branches.history_name(main_branch)]
    for base_branch in branches_to_cover:
        refs.extend(
            [
                base_branch,
                branches.unclean_name(base_branch),
                branches.history_name(base_branch),
                branches.history_fork_point_ref(base_branch),
                sync_unclean.clean_cursor_ref(base_branch),
                sync_unclean.history_cursor_ref(base_branch),
                sync_splits.forward_cursor_ref(base_branch, "clean"),    # line 40
                sync_splits.forward_cursor_ref(base_branch, "history"),  # line 41
            ]
        )
    ...
```
This *does* append the two `forward-cursor` refs.

**Actual test run (unittest, since pytest isn't installed in this env):**
```
python3 -m unittest tests.test_git_split_recovery.ResolveWatchedRefsTests.test_single_branch_includes_all_derived_refs
```
gives:
```
AssertionError: ... First list contains 2 additional elements.
First extra element 8: 'refs/base-split/forward-cursor/clean/feature'
  ...
   'refs/base-split/unclean-cursor/clean/feature',
-  'refs/base-split/unclean-cursor/history/feature',
+  'refs/base-split/unclean-cursor/history/feature']
-  'refs/base-split/forward-cursor/clean/feature',
-  'refs/base-split/forward-cursor/history/feature']
```
Note: `assertEqual(refs, [...])` — the first arg (`refs`, the *actual* computed list) is the one with the extra `forward-cursor` elements; the second arg (the hard-coded expected list in the test) is the one missing them. **This is the reverse of the failure description given in the task** — in reality the implementation produces more refs than the test expects, not fewer. (Worth flagging to the user/task-issuer in case the report was garbled or comes from a different test-run environment.)

**`forward-cursor` / `forward_cursor` usage across the codebase** (grep counts):
- `scripts/°base/git/°split_lib/sync_splits.py` — 6 occurrences: defines `forward_cursor_ref()` (line 66-69, producing `refs/base-split/forward-cursor/{target}/{base_branch}`), `find_forward_cursor()` (line 73), and live call sites at lines 266, 316, 319, 363 that read/write these refs during the real forward sync-splits replay (tracking the last-processed unclean source per target so replay resumes correctly).
- `scripts/°base/git/°split_lib/recovery.py` — 2 occurrences (lines 40-41, inside `resolve_watched_refs`, the code under test).
- `scripts/°base/git/°split_lib/cli.py` — 3 occurrences (lines 216, 257, 277), all real `git_ops.move_ref(sync_splits_lib.forward_cursor_ref(...))` calls used for backup/rollback restore of forward-cursor refs.
- `scripts/°base/tests/` — **0** occurrences anywhere (no test currently exercises `forward_cursor_ref`/`find_forward_cursor` directly, and the `unclean-cursor` refs in `test_git_split_recovery.py` are the only cursor-family refs any test currently asserts on).

**`unclean-cursor` usage:** defined/used only in `sync_unclean.py` (`clean_cursor_ref`, `history_cursor_ref`, lines 48/52) plus the one reference in `recovery.py` (lines 38-39) and the test's expected list.

**Git history:** commit `d2cb8ad46fc` ("[base] [hoass_plugin-template] git split: ai: Run: Removed base trailers from clean split commits.") is what added the `forward_cursor_ref(...)` calls to `recovery.py`'s `resolve_watched_refs` (diff shows a 2-line addition at exactly those two lines). That same commit touched `sync_splits.py`, `sync_unclean.py`, `cli.py`, `history_master.py`, `trailers.py`, `test_git_split_e2e_deep_flow.py`, and `test_git_split_sync_splits.py` — but **did not touch `test_git_split_recovery.py` at all** (`git show d2cb8ad -- scripts/°base/tests/test_git_split_recovery.py` shows an empty diff). No later commit touched `test_git_split_recovery.py` either (`git log` shows `b070d7b` and `f07d024` as the only later commits touching that file, both unrelated ref-backup-tag-naming changes).

## Conclusion

`forward-cursor` refs are a real, currently-implemented, actively-used concept — not a stale/removed idea and not a half-built planned feature. `forward_cursor_ref()` is defined and consumed by the live forward-replay logic in `sync_splits.py` (used to persist per-branch/per-target "last processed unclean source" cursors across runs) and by crash-recovery restore logic in `cli.py`. Commit `d2cb8ad` deliberately added these two refs to `resolve_watched_refs` so that a full recovery snapshot correctly covers all refs that `sync_splits`/`cli` might mutate during a real run — omitting them from the watched-refs list would be a genuine recovery-log correctness bug (an interrupted forward-cursor move wouldn't be snapshotted/restorable).

The test's hard-coded expected list in `test_git_split_recovery.py` is simply stale: it was written against the pre-`d2cb8ad` version of `resolve_watched_refs` and was never updated when that commit added the two `forward_cursor_ref(...)` lines to the implementation, even though the same commit updated several other test files. The fix is to update the test's expected list (not the implementation) to append `'refs/base-split/forward-cursor/clean/feature'` and `'refs/base-split/forward-cursor/history/feature'` after the `unclean-cursor` entries, matching what the implementation actually (and correctly) produces.