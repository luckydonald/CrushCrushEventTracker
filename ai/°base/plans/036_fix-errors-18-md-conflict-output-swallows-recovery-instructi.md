# Fix errors/18.md: conflict output swallows recovery instructions

## Context

`ai/°base/errors/18.md` captured a real run of `split.py update-history-master --yes`
against the external `ssp` repo. It hit a cherry-pick conflict on commit
`7afd08be7fc178abd1744706c781b583ce6f69d9` and the tool's only output for that
was the raw Python dict repr:

```
{'status': 'conflict', 'pending': {'kind': 'cherry-pick', 'step': {'kind': 'commit', 'sha': '7afd08be7fc178abd1744706c781b583ce6f69d9'}}}
```

That's why the user couldn't tell how to proceed. Root cause, traced through
`scripts/°base/git/°split_lib/history_master.py` and `cli.py`:

- `CherryPickConflict`/`MergeConflict` (history_master.py:41-72) already build a
  full human-readable message ("Resolve the conflict in the working tree...,
  then rerun update-history-master with --continue...").
- But `_run_steps()` (history_master.py:426-437) catches them with a bare
  `except CherryPickConflict:` / `except MergeConflict:` (no `as exc`),
  discarding that message and returning only `{"kind": ..., "step": step}`.
- `_do_continue()` has the same pattern in two more spots (lines 559-560,
  565-566, 586-596).
- `cli.py:_update_history_master` (lines 137-154) just does `print(result)` on
  whatever comes back — no special-casing for `status == "conflict"` at all.

No test in the repo pins the current dict shape or CLI print format (confirmed
via `scripts/°base/tests/test_git_split_history_master.py` and
`test_get_base.py`), so this is safe to change without touching other tests.

Following this repo's convention, `18.md` itself stays as-is (error transcripts
are never edited/deleted) — the fix is to the code, and we add a fresh
`18.expected.md` to document the corrected behavior for this scenario.

## Code changes

**`scripts/°base/git/°split_lib/history_master.py`**

1. `_run_steps` (lines 426-437): bind the exceptions and thread the message
   through:
   ```python
   except CherryPickConflict as exc:
       return tip, remaining, {"kind": "cherry-pick", "step": step, "message": str(exc)}
   except MergeConflict as exc:
       return tip, remaining, {"kind": "merge", "step": step, "message": str(exc)}
   ```
2. `_do_continue` (lines 586-596): same fix for the `except MergeConflict:` around
   `_fold_base` during `--continue` — bind `as exc` and add `"message": str(exc)`
   to both the persisted state's `pending` and the returned dict.
3. Lines 559-560 and 565-566 already build ad-hoc `"detail"` strings for
   continue-time conflicts (git reported conflict, not one of our exception
   classes) — leave those as `"detail"`, just make sure the CLI (below) knows to
   check both `"message"` and `"detail"`.

**`scripts/°base/git/°split_lib/cli.py`**

`_update_history_master` (lines 137-154): replace the bare `print(result)` with
a status-aware branch:

```python
print(result)
if result.get("status") == "conflict":
    pending = result.get("pending", {})
    text = result.get("message") or pending.get("message") or pending.get("detail")
    if text:
        print()
        print(text)
    print()
    print(
        f"Rerun to resume: scripts/°base/git/split.py --repo-root {repo_root} "
        "update-history-master --continue"
    )
    print(f"Or cancel:       scripts/°base/git/split.py --repo-root {repo_root} update-history-master --abort")
return 0 if result.get("status") != "conflict" else 1
```

(Keep the raw dict print for anyone scripting against stdout, but add the
human-readable instructions immediately after it.)

## Test coverage

In `scripts/°base/tests/test_git_split_history_master.py`, add one test that
sets up a real cherry-pick conflict (same style as existing fixture setup in
that file) and asserts `result["pending"]["message"]` contains the
"--continue" recovery text — locking in that the message now survives.

## Documentation artifact

Add `ai/°base/errors/18.expected.md` showing the corrected tool output for
this same scenario (dict line followed by the human-readable message and the
`--continue`/`--abort` command hints), matching the `N.md`/`N.expected.md`
convention used elsewhere in that directory.

## Recovering the old branches in the `ssp` repo (manual — for you to run there)

The base repo's fix only affects *future* runs; the `ssp` repo is currently
mid-conflict right now. Two options, both documented in `errors/18.md` itself:

**Option A — resume and finish the split (recommended if you still want
`ai/history/master` updated):**
1. `cd /home/user/Documents/PycharmProjects/abelmann/hansecom/ssp`
2. `git status` — you're currently on the scratch branch `_base_split_scratch`
   mid cherry-pick of `7afd08be7fc178abd1744706c781b583ce6f69d9`. Resolve the
   conflicting files, then `git add <resolved files>`.
3. Re-run the tool so it can pick up its own state file
   (`.git/BASE_SPLIT_HISTORY_MASTER_STATE`) and finish the remaining steps —
   do **not** run `git cherry-pick --continue` directly:
   ```
   python3 <path-to-base>/scripts/°base/git/split.py --repo-root /home/user/Documents/PycharmProjects/abelmann/hansecom/ssp update-history-master --continue
   ```
4. If it hits another conflict, repeat step 2-3.

**Option B — abandon this run and restore every branch to how it was before
(full rollback):**
1. `cd /home/user/Documents/PycharmProjects/abelmann/hansecom/ssp`
2. Run the shell block from `ai/°base/errors/18.md` lines 55-106 (the
   `git rebase/cherry-pick/merge --abort || true` lines followed by the
   `git update-ref` commands) — this restores `master`,
   `ai/history/master`, every `feature/...` branch, and all `ai/UNCLEAN/...`
   variants to their exact pre-run SHAs, and deletes the `refs/base-split/...`
   scratch refs that didn't exist before.
   - Equivalently, the tool already wrote this same block to
     `.rebase-recovery.tmp` in the `ssp` repo root — you can just run that
     file's contents instead of retyping from `18.md`.
3. Clean up leftover tool state: `rm -f .git/BASE_SPLIT_HISTORY_MASTER_STATE`
   and delete the scratch branch: `git branch -D _base_split_scratch` (if it
   still exists).
4. This is a real rollback of branch refs in a repo outside this session's
   working directory — I won't run it for you; execute it yourself and verify
   with `git status`/`git log` afterward.

Only `master` had actually moved (`a493b18...` → `f6bec55...`) before the
conflict was hit; everything else in that run was untouched, per the
before/after tables in `errors/18.md`.
