# Fix orphaned MEMORY.md entries + harden record-memory sync

## Context

Commit `121ab69` ("ai: record memory MEMORY") removed two lines from
`ai/°base/memory/MEMORY.md` — the entries for `feedback_commit_prefix_ssp_tag.md`
and `feedback_lib_naming_convention.md` — but left both underlying memory files
untouched on disk and in git, orphaning them from the index.

Investigation (see conversation) found:
- The commit came from `record-memory` hook's `SessionStart` catch-up path
  (`scripts/°base/ai/hooks/record-memory/hook.py::_sync_all`), which blindly
  mirrors whatever's in the Claude-side source `MEMORY.md`
  (`~/.claude/projects/.../memory/MEMORY.md`) into the repo whenever the two
  copies' inodes differ — regardless of *which side* actually changed.
- The debug/session logs have a full gap over the window the edit must have
  happened in (no `ai/°base/output/debug/` entries on 2026-07-09, no session
  transcript between 2026-07-07 00:18 and 2026-07-10 12:47), so the edit's
  origin is unrecoverable.
- No deletion was ever attempted through the sanctioned path: no
  `Deleted Memory:` marker commit exists for either file (required by
  `require_memory_delete_marker.py` for any real deletion), and both files
  remain byte-identical/intact in both the repo and the Claude-side source.
- Root design gap: for a file that exists on *both* sides with diverging
  content, the hook currently always trusts the Claude-side source — which has
  no audit trail — over the git-tracked repo copy. Legitimate edits already
  reach the repo immediately via the `PostToolUse(Edit|Write)` fast path, so
  any mismatch `_sync_all` finds at `SessionStart` is more likely untracked
  drift than an intentional edit; the repo should win reconciliation in that
  case.

## Changes

**1. Restore the two lines** in `ai/°base/memory/MEMORY.md` (repo copy), right
after the existing `lplp` line, matching wording/order from commit `a9ec8a9`:
```
- [commit prefix: [base] [ssp]](feedback_commit_prefix_ssp_tag.md) — use `[base] [ssp] ` prefix, not bare `[base] `, for the git branch-split feature work.
- [lib naming convention](feedback_lib_naming_convention.md) — new shared logic goes in a `°name_lib` package, not `_lib.py`; public functions there have no leading underscore.
```
No changes needed to the `feedback_*.md` files themselves — never touched.

**2. Flip reconciliation direction in `_sync_all`** (`scripts/°base/ai/hooks/record-memory/hook.py`):
distinguish "dst missing" (new memory, src still wins — existing behavior) from
"dst exists but content differs" (repo wins — new behavior: push dst's content
back into src via `_sync_file(dst, src)`, and do **not** add the name to
`changed`/commit anything, since the repo side didn't change). Concretely,
in the `src_dir` loop: only fall through to `_sync_file(src, dst)` when `dst`
doesn't exist yet; when `dst` exists and `not _same_inode(dst, src)`, call
`_sync_file(dst, src)` instead.

**3. Add an index-consistency check**, run once at the end of `main()` whenever
`dst_dir / "MEMORY.md"` exists: parse `[title](filename.md)` links out of
`MEMORY.md`'s text (regex over `\(([^()\s]+\.md)\)`), diff that name set against
the actual `*.md` files in `dst_dir` (excluding `MEMORY.md` itself), and print a
`record-memory:` warning to stderr for each mismatch — a file present but not
indexed ("orphaned"), or a line referencing a file that doesn't exist
("dangling"). Warnings only, never auto-fixes or deletes — mirrors the existing
`_uninstall_legacy_all` warning style.

## Tests (`scripts/°base/tests/test_ai_hooks_base_routing.py`)

Add, alongside the existing memory tests (~line 926):
- Content-mismatch reconciliation: seed a repo-tracked + external-source pair
  with `_seed_memory_pair`, then diverge the source file's content, run
  `SessionStart`, and assert the source file gets overwritten to match the
  repo's content and no new commit is made (repo wins, no-op commit-wise).
- Orphan warning: seed a repo memory file not referenced by `MEMORY.md`, run
  `SessionStart`, assert a warning mentioning the filename appears on stderr.
- Dangling-reference warning: seed `MEMORY.md` with a link to a nonexistent
  file, run `SessionStart`, assert a warning appears on stderr.

## Verification

- `python3 -m py_compile scripts/°base/ai/hooks/record-memory/hook.py`
- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`
  (full suite, to catch regressions in the other memory-sync tests)
- `git diff ai/°base/memory/MEMORY.md` shows only the two restored lines.
