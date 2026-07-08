# Fix errors/18.md: complete the stuck ssp split, then harden the tool from what that reveals

## Context

`ai/°base/errors/18.md` captured a run of `split.py update-history-master --yes`
against the external `ssp` repo (`/home/user/Documents/PycharmProjects/abelmann/hansecom/ssp`)
that hit a cherry-pick conflict on commit `7afd08be7fc178abd1744706c781b583ce6f69d9`
and printed nothing but a bare `{'status': 'conflict', 'pending': {...}}` dict —
no explanation, no next steps, sandwiched between two giant unconditional ref
tables. The user wants both: (1) the `ssp` repo actually unstuck and the split
finished, and (2) the tool improved based on what doing that reveals.

Live investigation of `ssp` (read-only so far) turned up more than the
original transcript showed:

- **The persisted state is stale.** `.git/BASE_SPLIT_HISTORY_MASTER_STATE`
  still records `pending: {cherry-pick, 7afd08be...}`, but `git status` shows
  no unmerged paths and there's no `.git/CHERRY_PICK_HEAD` — the real
  cherry-pick was already aborted outside the tool at some point, and the
  state file was never told. Currently on branch `_base_split_scratch` at tip
  `8ca28982` (clean, matches the state file's `"tip"` field), state's
  `"remaining"` list still starts at `7afd08be`.
- `--abort` is safe to run despite this: `git_ops.cherry_pick_abort`/
  `merge_abort` (`git_ops.py:246-247`, `260-261`) call `subprocess.run(...)`
  with no `check=True` and discard the result — a failed "nothing to abort"
  is silently swallowed. `_do_abort` (`history_master.py:529-541`) then
  cleans up the scratch branch and clears the state file unconditionally.
- Root cause of the original unhelpful output, traced through
  `scripts/°base/git/°split_lib/`:
  - `cli.py:_run_with_recovery` (lines 24-51) unconditionally prints the full
    `recovery.format_recovery_entry(...)` block *before* anything runs, and
    unconditionally prints `format_after_summary(...)` in a `finally` —
    regardless of outcome. That's the "spam."
  - `history_master.py:_run_steps` (426-437) catches `CherryPickConflict`/
    `MergeConflict` with a bare `except ...:` (no `as exc`), discarding the
    human-readable message those exceptions already carry. `_do_continue` has
    the same pattern at lines 559-560, 565-566, 586-596.
  - Nothing narrates progress while steps run — silence until the final dict.
  - `cli.py:_update_history_master` (137-154) just does `print(result)` with
    no special-casing for `status == "conflict"`.
  - Nothing cross-checks the persisted state file against real git state
    (`CHERRY_PICK_HEAD`/`MERGE_HEAD`) before trusting it on `--continue`.

No test pins the current dict shape or CLI stdout format (confirmed via
`scripts/°base/tests/test_git_split_history_master.py` and `test_get_base.py`),
so all of this is safe to change. Per this repo's convention, `18.md` itself
is never edited — add a fresh `18.expected.md` once the fix is in.

## Part A — actually finish the ssp split

Executed directly in `/home/user/Documents/PycharmProjects/abelmann/hansecom/ssp`
(outside this session's own repo — every mutating step gets called out and
checked before moving on):

1. `python3 <base>/scripts/°base/git/split.py --repo-root <ssp> update-history-master --abort`
   — clears the stale state file and the `_base_split_scratch` branch safely
   (confirmed safe above).
2. Re-run `update-history-master --yes`. Since state was cleared, this
   replays the full history again from `ai/history/master`'s last real tip
   (`c8d15c81...`) — expect it to reach the same conflict at `7afd08be`
   (nothing about that commit's content has changed), likely automatically
   sailing through everything before it.
3. At the conflict: inspect the conflicting files under
   `.claude/VGN-789/cr-001_timeline.*` and
   `api/application/applications/166/index.json` — read both sides (the
   incoming commit's intent vs. what's already on the replayed line),
   resolve mechanically in a way that preserves both sides' intent (standard
   cherry-pick conflict resolution: adopt the incoming commit's changes,
   adapted to whatever already changed underneath it), `git add`, then
   `update-history-master --continue`.
4. Repeat step 3 for any further conflicts. If a conflict resolution isn't
   mechanical — i.e. it requires a business-logic judgment call about the
   SSP application rather than "reconcile two diffs" — stop and ask rather
   than guess.
5. Once `update_history_master` returns `status: ok`, verify: `ai/history/master`
   moved to a real new tip, `master` reflects the pull that already happened,
   and no other branch/ref regressed versus the `errors/18.md` "before" table
   (`git log --oneline -5` on the relevant branches, spot-check via
   `git diff` that nothing unexpected changed).
6. Leave the pile of pre-existing untracked debris in the worktree
   (`branches.*.txt`, `gitblah-0jep`, `notes/`, `openapi/`, etc.) untouched —
   unrelated to this task, not something to clean up here.

## Part B — harden `split.py` based on what Part A exposes

### 1. Validate persisted state against real git state before trusting it

In `update_history_master` / `_do_continue` (`history_master.py`), before
acting on a `pending: cherry-pick` state, check whether
`(repo_root / ".git" / "CHERRY_PICK_HEAD")` (or the merge equivalent)
actually exists. If the state file claims a pending conflict but git shows
none, don't blindly call `cherry_pick_continue` (which would just fail
confusingly) — surface it explicitly: clear the orphaned state and tell the
user to just re-run normally, or auto-recover by treating it as already
resolved. (Exact behavior TBD from what Part A's investigation confirms about
how such staleness happens — likely: someone ran a raw `git cherry-pick --abort`
by hand instead of going through `--abort`.)

### 2. Thread the swallowed exception messages through

- `_run_steps` (426-437): bind `as exc` for both `CherryPickConflict` and
  `MergeConflict`, add `"message": str(exc)` to the returned conflict dict.
- `_do_continue`'s `except MergeConflict:` (586-596): same fix.
- The two ad-hoc `"detail"` conflict dicts at lines 559-560, 565-566 already
  carry a message string under `"detail"` — leave as-is, CLI checks both keys.

### 3. `cli.py` — real narration via `logging` (first use of `logging` in this repo's scripts)

Deliberate deviation from the rest of `scripts/°base` (which is `print()`-only)
because narration + simultaneous console/file output is exactly what
`logging` is for. Stays confined to `cli.py`; `history_master.py` remains a
pure library module taking a plain `log: Callable[[str], None]` callback, no
`logging` import there.

- Build a per-invocation `logging.Logger`: `StreamHandler(sys.stdout)` at
  `INFO` for the console, `FileHandler(repo_root / recovery.RECOVERY_FILENAME)`
  at `DEBUG` for the full detail. Both use `Formatter("%(message)s")` (no
  level/time prefixes — keep it reading like plain text).
- `_run_with_recovery`: `logger.debug(format_recovery_entry(...))` (file-only,
  full ref table + rollback commands) instead of unconditional `print`;
  `logger.info(...)` a one-line pointer to the file for the console. Same
  treatment for `format_after_summary` — file always, console only when the
  run's exit code is non-zero.
- Clear handlers in a `finally` so repeated invocations in-process (tests)
  don't accumulate them.
- `_update_history_master`: pass `log=logger.info` into
  `update_history_master(...)`. On `status == "conflict"`,
  `logger.warning(...)` a clearly labeled block:
  ```
  == CONFLICT ==
  <pending message/detail text>

  Choose one:

    [1] Resolve and continue
        - Resolve the conflict in the working tree (branch `_base_split_scratch`)
        - git add <resolved files>
        - scripts/°base/git/split.py --repo-root <repo_root> update-history-master --continue

    [2] Abort this run (keeps any already-pulled `master`)
        - scripts/°base/git/split.py --repo-root <repo_root> update-history-master --abort

    [3] Full manual rollback (only if [2] isn't enough, e.g. to also undo
        the `master` pull) -- see the ref table and `git update-ref` commands
        in .rebase-recovery.tmp for this run.
  ```
  `status == "ok"`: one concise `logger.info(...)` line. Other statuses keep
  their current simple output.

## Test coverage

- `test_git_split_history_master.py`: a test that triggers a real cherry-pick
  conflict and asserts `result["pending"]["message"]` contains the
  "--continue" recovery text; a test for the stale-state detection from B.1
  (manually delete `CHERRY_PICK_HEAD` under a fake pending state, confirm the
  tool doesn't try a doomed `cherry_pick_continue`).
- A CLI-level test asserting: console output for a conflict mentions both
  `--continue` and `--abort`; `.rebase-recovery.tmp` contains the full ref
  table.

## Documentation artifact

Add `ai/°base/errors/18.expected.md` showing the corrected, narrated output
for this same scenario, matching the `N.md`/`N.expected.md` convention.

## Verification

- Re-run the full `scripts/°base` test suite after the code changes.
- Confirm in `ssp` that `update-history-master` (fresh, no prior state) now
  produces readable console output end-to-end, and that a deliberately
  induced conflict there shows the `[1]`/`[2]`/`[3]` block instead of a raw
  dict.
