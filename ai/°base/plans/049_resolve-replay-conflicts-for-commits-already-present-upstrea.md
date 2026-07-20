# Resolve replay conflicts for commits already present upstream

## Summary

Make history replay recognize commits that are already ancestors of the target tip. For conflicts caused by replaying such a commit, preserve the target-side versions of conflicting files, retain any genuinely missing files from the replay, and continue automatically.

Real conflicts from commits not already present will remain resumable and will still require explicit `--continue` or `--abort`.

## Implementation changes

- Add an ancestry-aware conflict resolver in `history_master.py`:
  - After a cherry-pick conflict, check whether the replayed commit is already an ancestor of the `onto` tip.
  - For conflicted paths in that case, select the target-side (`ours`) version and stage it.
  - Continue the cherry-pick so non-conflicting additions from the commit are retained.
  - If no staged changes remain, skip the now-empty cherry-pick cleanly.
  - Keep the existing conflict state/recovery behavior for commits that are not already ancestors.

- Keep the recovery contract explicit:
  - Never discard a genuine unresolved conflict automatically.
  - Preserve the scratch branch and state file for `--continue`.
  - Keep `--abort` as the documented safe exit path.
  - Continue reporting the commit, paths, and copy-pastable recovery commands without exposing the redacted path in plan or user-facing summaries.

## Tests

- Add a regression where an older commit is already reachable from the replay target but its file was later edited; verify replay completes without conflict and preserves the target’s later content.
- Add a regression where the ancestor commit contains an additional file absent from the target; verify that file is retained while the already-present conflicting file stays unchanged.
- Preserve coverage that a genuinely unrelated conflicting commit still returns a resumable conflict.
- Run the focused history-master/recovery tests, then the full base test suite.

## Assumptions

- The target-side version is authoritative when a replayed commit is already an ancestor of the target tip.
- Missing, non-conflicting files from that commit should still be replayed.
- Genuine conflicts remain manual rather than being guessed or silently discarded.
