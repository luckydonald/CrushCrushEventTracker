# Fix orphaned MEMORY.md entries left by commit 121ab69

## Context

Commit `121ab69` ("ai: record memory MEMORY") removed two lines from
`ai/°base/memory/MEMORY.md` — the entries for `feedback_commit_prefix_ssp_tag.md`
and `feedback_lib_naming_convention.md` — but left both underlying memory files
untouched on disk and in git.

Investigation findings:

- The commit was produced by the `record-memory` hook's `SessionStart` catch-up
  path (`scripts/°base/ai/hooks/record-memory/hook.py::_sync_all`), which mirrors
  whatever content is currently in the Claude-side source `MEMORY.md`
  (`~/.claude/projects/.../memory/MEMORY.md`) into the repo copy and commits only
  what changed. It has no logic that inspects *content* changes inside `MEMORY.md`
  to cross-delete files it stops referencing — deletion propagation only happens
  via an observed `rm <path>.md` in a `Bash` PostToolUse event, or via the
  sanctioned `scripts/°base/ai/memory/delete.py` helper. Neither fired here.
- The debug logs can't show the actual edit: `ai/°base/output/debug/` has no
  entries for 2026-07-09, and there's no Claude Code session transcript between
  2026-07-07 00:18 and 2026-07-10 12:47 — the exact window the edit must have
  happened in. The one debug entry at the commit's timestamp is a bare
  `SessionStart` payload with no command/tool info.
- No deletion was ever attempted through the sanctioned path: `git log
  --diff-filter=D` shows zero delete commits for either file, and
  `require_memory_delete_marker.py` (a commit-msg pre-commit hook) would have
  hard-blocked any staged deletion under `ai/°base/memory/` without a
  `Deleted Memory: <file>` marker line — no such commit exists. Both files remain
  byte-identical and fully intact in both the repo mirror and the Claude-side
  source directory.
- Conclusion: this was a plain content edit to `MEMORY.md`'s index (most likely
  manual, or a "forget" step that only trims the index) — not a deletion attempt,
  successful or otherwise. Both memories still read as valid/current content, so
  this looks like accidental index drift rather than intended removal.

## Fix

Restore the two removed lines in `ai/°base/memory/MEMORY.md` (no changes to the
memory files themselves, which are already intact):

```
- [commit prefix: [base] [ssp]](feedback_commit_prefix_ssp_tag.md) — use `[base] [ssp] ` prefix, not bare `[base] `, for the git branch-split feature work.
- [lib naming convention](feedback_lib_naming_convention.md) — new shared logic goes in a `°name_lib` package, not `_lib.py`; public functions there have no leading underscore.
```

Re-insert them after the existing `lplp` line, matching their original order and
wording from commit `a9ec8a9`.

## Verification

- `git diff ai/°base/memory/MEMORY.md` shows exactly the two lines restored, no
  other changes.
- `git status` confirms no changes to the two `feedback_*.md` files (they were
  never touched).
