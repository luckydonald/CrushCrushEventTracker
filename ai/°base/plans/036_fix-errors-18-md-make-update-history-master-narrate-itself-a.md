# Fix errors/18.md: make update-history-master narrate itself and print clear recovery options

## Context

`ai/°base/errors/18.md` captured a real run of `split.py update-history-master --yes`
against the external `ssp` repo. It hit a cherry-pick conflict on commit
`7afd08be7fc178abd1744706c781b583ce6f69d9`, and the only output was:

1. A giant, unconditional "before" ref table + full `git update-ref` rollback
   block, printed *before anything even started*.
2. A bare Python dict repr for the conflict: `{'status': 'conflict', 'pending': {...}}`
   — no explanation, no next steps.
3. Another giant "before | after" ref table at the end.

Root cause, traced through `scripts/°base/git/°split_lib/`:

- `cli.py:_run_with_recovery` (lines 24-51) unconditionally prints the full
  `recovery.format_recovery_entry(...)` block *before* `run_fn()` even runs,
  and unconditionally prints `format_after_summary(...)` in a `finally` —
  regardless of whether anything went wrong. That's the "spam."
- `history_master.py:_run_steps` (lines 426-437) catches `CherryPickConflict`/
  `MergeConflict` with a bare `except ...:` (no `as exc`), discarding the
  message those exceptions already carry ("Resolve the conflict..., then
  rerun update-history-master with --continue..."). `_do_continue` has the
  same pattern in three more spots (lines 559-560, 565-566, 586-596).
- Nothing in `history_master.py` narrates progress while it runs — it's
  silent until the final dict comes back.
- `cli.py:_update_history_master` (lines 137-154) just does `print(result)`
  on whatever comes back, with no formatting for the conflict case.

No test pins the current dict shape or CLI stdout format (confirmed via
`scripts/°base/tests/test_git_split_history_master.py` and `test_get_base.py`),
so this is safe to restructure. Per this repo's convention, `18.md` itself is
never edited — the fix is to the code; add a fresh `18.expected.md` showing
the corrected output for the same scenario.

**Goal:** restructure the output (both stdout *and* the `.rebase-recovery.tmp`
log file — they should say the same thing) so it reads as a narrated,
sectioned report instead of a data dump: what's about to happen, what's
happening step by step, and — if something goes wrong — exactly two
labeled ways to recover, with copy-pasteable commands.

## Code changes

### 1. `history_master.py` — thread a logger through step execution

Add an optional `log: Callable[[str], None] = lambda _msg: None` parameter to
`update_history_master`, `_run_steps`, and `_do_continue` (default no-op so
existing tests/callers are unaffected).

- `_run_steps` logs one line before each step (`f"[{i}/{total}] {kind} {sha[:8]}: replaying..."`)
  and one line after (`"  -> ok"` or `"  -> CONFLICT"`).
- Bind the caught exceptions (`as exc`) in `_run_steps` (lines 432-435) and
  `_do_continue`'s `except MergeConflict:` (lines 586-596), and put
  `str(exc)` into the returned/persisted dict as `"message"`. The two
  `"detail"` spots at lines 559-560 and 565-566 already have a message string;
  leave them as `"detail"` — the CLI layer will check both keys.

### 2. `recovery.py` — split "log everything" from "print everything"

Keep `format_recovery_entry`/`format_after_summary`/`write_recovery_log`
as-is (still the source of the full ref table + rollback block, still always
written in full to `.rebase-recovery.tmp` for every mutating subcommand — no
regression to crash-safety). Add:

- `format_recovery_header(invocation, before, timestamp) -> str`: just the
  `#### Run ... \`invocation\`` line + timestamp, no table (for a short stdout
  line).
- Nothing else needs to change here — the full block is still built by
  `format_recovery_entry`, just *displayed* differently by the caller (below).

### 3. `cli.py` — set up a real `logging.Logger` (first use of `logging` in this repo's scripts)

This is the one deliberate deviation from the rest of `scripts/°base` (which
is `print()`-only everywhere) — narration + dual console/file output is
exactly what `logging` is for, so it's worth the one new import rather than
hand-rolling a tee function. Everything below stays confined to `cli.py`;
`history_master.py` remains a pure library module and never imports
`logging` itself (see #4 — it just takes a generic callable).

- In `_run_with_recovery` (or a small helper it calls), build a
  `logging.Logger` per invocation:
  ```python
  logger = logging.getLogger(f"split.{invocation_id}")
  logger.setLevel(logging.INFO)
  logger.handlers.clear()
  logger.addHandler(logging.StreamHandler(sys.stdout))          # console
  file_handler = logging.FileHandler(repo_root / recovery.RECOVERY_FILENAME)
  file_handler.setFormatter(logging.Formatter("%(message)s"))   # match existing markdown-ish log format, no level/time prefix noise
  logger.addHandler(file_handler)
  ```
  (Use a `Formatter("%(message)s")` on the console handler too, so output
  reads like today's plain text rather than gaining `INFO:root:` prefixes.)
- Always still write the full `format_recovery_entry(...)` (ref table +
  rollback commands) straight to the file handler via
  `logger.debug(entry)` with the file handler's level lowered to `DEBUG`
  and the console handler kept at `INFO` — this is the cleanest way to get
  "full detail in the file, short line on screen" without writing to the
  file twice. Concretely: `logger.info("snapshotted N refs -> .rebase-recovery.tmp")`
  for the console-visible line, `logger.debug(entry)` for the full block
  (file-handler-only, since its level is `DEBUG` and the console handler's
  level is `INFO`).
- After `run_fn()` returns: `logger.debug(format_after_summary(...))`
  (file-only), and only `logger.warning(...)` the same content to be
  console-visible if the run's exit code was non-zero.
- Close/remove the handlers when the invocation finishes (`finally:
  logger.handlers.clear()`) so repeated CLI invocations in the same process
  (e.g. in tests) don't accumulate duplicate handlers.

### 4. `cli.py:_update_history_master` — sectioned, narrated output

Pass `log=logger.info` (a plain `Callable[[str], None]`) into
`history_master_lib.update_history_master(..., log=log)` — `history_master.py`
keeps its existing signature style and has no idea it's talking to a
`logging.Logger` underneath.

Restructure the result handling:

- `status == "ok"`: one concise `logger.info(...)` line, e.g.
  `"history-master updated: <old-sha> -> <new-sha>"`.
- `status == "conflict"`: print a clearly labeled block via `logger.warning(...)`
  (so it's visually distinct on the console and still lands in the file):
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
        already written to .rebase-recovery.tmp for this run.
  ```
- Other statuses (`aborted`, `dry_run`) keep their current simple prints.

This satisfies "print clearly the two recovery options" and "tell the user
what it's doing, in the log file too" while cutting the unconditional
before/after table spam down to a pointer at the file, surfaced in full only
when it's actually relevant (conflict, or non-zero exit).

## Test coverage

In `scripts/°base/tests/test_git_split_history_master.py`, add one test that
triggers a real cherry-pick conflict and asserts:
- `result["pending"]["message"]` contains the "--continue" recovery text.
- Passing a `log` callback (plain function, no `logging` involved at this
  layer) collects at least one "CONFLICT" narration line.

In a CLI-level test (new or existing `test_get_base.py`-style test), use
`caplog`/a temporary `logging.Handler` to assert: the console-level output
for a conflict includes both recovery options ("--continue" and "--abort"),
and `.rebase-recovery.tmp` contains the full ref table + `git update-ref`
rollback block via the `DEBUG`-level file handler.

## Documentation artifact

Add `ai/°base/errors/18.expected.md` showing the corrected, sectioned output
for this same scenario (short snapshot line, per-step narration, `== CONFLICT ==`
block with the three labeled options), matching this directory's
`N.md`/`N.expected.md` convention.

## Recovering the `ssp` repo right now (manual — you run this there)

The code fix only changes future runs' *output*; the `ssp` repo is mid-conflict
right now under the old behavior. Two options (mirrors the `[1]`/`[2]` design above):

**Option 1 — resolve and continue** (finishes updating `ai/history/master`):
```
cd /home/user/Documents/PycharmProjects/abelmann/hansecom/ssp
git status   # conflict is on branch _base_split_scratch, cherry-pick of 7afd08be7fc1
# resolve the conflicting files, then:
git add <resolved files>
python3 <path-to-base>/scripts/°base/git/split.py --repo-root "$(pwd)" update-history-master --continue
```
Repeat if it hits another conflict.

**Option 2 — abort this run** (cancels the in-progress cherry-pick/merge, keeps
the `master` branch pull that already happened):
```
cd /home/user/Documents/PycharmProjects/abelmann/hansecom/ssp
python3 <path-to-base>/scripts/°base/git/split.py --repo-root "$(pwd)" update-history-master --abort
```

**Option 3 — full manual rollback** (only if you also want to undo the
`master` pull, i.e. restore *every* ref exactly to how it was before this
invocation): run the `git rebase/cherry-pick/merge --abort || true` lines
followed by the `git update-ref` commands from `ai/°base/errors/18.md`
lines 55-106 (same content is already sitting in `.rebase-recovery.tmp` at
the `ssp` repo root). Then `rm -f .git/BASE_SPLIT_HISTORY_MASTER_STATE` and
`git branch -D _base_split_scratch` if it still exists.

I won't run any of this myself — it mutates branch refs in a repo outside
this session's working directory. Run it yourself and check with
`git status`/`git log` afterward.
