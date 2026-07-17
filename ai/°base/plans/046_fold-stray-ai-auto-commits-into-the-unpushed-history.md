# Fold stray `ai:` auto-commits into the unpushed history

## Context

`git log @{u}..HEAD` has 11 unpushed commits. Per the `commit-with-lplp-style` skill's cleanup procedure, chained `ai: updated prompt` / `ai: save decision …` / `ai: save plan …` commits should be folded into the code commit they lead up to, except genuine plan revisions which stay separate as `ai: Plan:` / `ai: Plan update:`.

Audited group (oldest → newest):

```
2a82274 ai: updated prompt                                              (query.md only)
4e1ea6c ai: save decision the-two-source-commits-are-already-empty…     (query.md only)
bce480b ai: save plan 045_prevent-empty-clean-commits-in-split-sync     (plan v1 — different scope)
65e2bc3 ai: updated prompt                                              (query.md only)
a83fc24 ai: updated prompt                                              (query.md only)
ebb114f ai: save decision should-trailer-free-clean-commits-include…   (query.md only)
8a48cf9 ai: save decision with-all-clean-master-trailers-forbidden…    (query.md only)
82ae4a7 ai: save decision should-this-rewrite-existing-clean-master…   (query.md only)
45a2751 ai: save plan 045_make-clean-branches-trailer-free…             (plan v2 — supersedes v1, real revision)
1c557b3 git split: ai: Run: Removed base trailers from clean split commits.  (the actual code commit)
7cb8d31 ai: updated prompt                                              (this very "fix the commits" request — new/unrelated topic, stays put)
```

The two plan saves (`bce480b`, `45a2751`) are a genuine content revision (different title, different scope — v1 proposed skipping empty clean commits, v2 fully reworked into stripping all trailers + history-manifest changes) — per the skill rule these earn separate `ai: Plan:` / `ai: Plan update:` commits, not a fold. Everything else in the group is disposable prompt/decision scaffolding for the same investigation and folds into `1c557b3`. `7cb8d31` starts a new task (this cleanup request itself) and has no code commit yet, so it's left alone.

## Plan

Run an interactive rebase (`GIT_SEQUENCE_EDITOR` script writing the todo) against `@{u}`, reordering to:

1. `pick bce480b` → reworded to `[base] git split: ai: Plan: Prevent empty clean commits in split sync.`
2. `pick 45a2751` → reworded to `[base] git split: ai: Plan update: Remove base trailers from clean split commits, preserving split metadata in history.`
3. `pick 1c557b3` (message unchanged) with `fixup`s of `2a82274, 4e1ea6c, 65e2bc3, a83fc24, ebb114f, 8a48cf9, 82ae4a7` folded in
4. `pick 7cb8d31` (unchanged)

Result: unpushed history shrinks from 11 commits to 4 — two plan commits, one implementation commit (now carrying the full folded query.md trail), and the trailing prompt commit for this task.

## Execution steps

1. Write the two reworded messages to temp files (`ai/git/rebase-msg-bce480b.md`, `ai/git/rebase-msg-45a2751.md`).
2. Write a `GIT_SEQUENCE_EDITOR` shell script that emits the reordered todo (pick/fixup list above).
3. Run `GIT_SEQUENCE_EDITOR=/path/to/script git rebase -i @{u}`.
4. `git rebase --exec` renames `bce480b`'s and `45a2751`'s pick commits via `git commit --amend -F <msg-file>` right after each pick.
5. Verify: `git log --oneline @{u}..HEAD` shows exactly 4 commits in the order above; `git show --stat` on the folded `1c557b3` confirms `query.md` + the code files are all present; working tree is clean (no leftover conflicts).
6. Clean up temp message files.

## Verification

- `git log --oneline @{u}..HEAD` → 4 commits, correct messages.
- `git show <new-1c557b3-sha> --stat` → still touches the same `scripts/°base/git/°split_lib/*.py` + tests, plus `ai/°base/query.md`.
- `git diff @{u} HEAD -- ':!ai' ':!scripts'` (or just full `git diff`) before/after rebase on non-`ai:` paths is empty — i.e. no code content was altered, only history shape.
- No `git push` performed (out of scope — history was already unpushed, rebase of local-only commits is safe, but pushing is a separate confirmable step).
