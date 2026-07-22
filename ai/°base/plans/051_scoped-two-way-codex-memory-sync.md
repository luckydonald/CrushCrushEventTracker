# Scoped two-way Codex memory sync

## Summary

Replace the separate `ai/.../memory/codex/` mirror with the existing shared project memory tree: `ai/°base/memory/` in base and `ai/memory/` elsewhere. Codex-specific source state will live visibly in `$CODEX_HOME/memories/extensions/base_synced/`, using Codex’s native extension structure and per-project scope.

## Implementation changes

- Refactor `record-codex-memory` to synchronize the shared project memory tree with `extensions/base_synced/resources/<encoded-project-root>/`.
  - Create `scope.json` with the canonical absolute project CWD and an `instructions.md` that requires scope-aware, read-only consolidation of these resources.
  - Use Claude’s per-file hardlink-first, symlink-fallback strategy. Existing repo content wins when linked sides diverge; missing counterparts are restored rather than inferred as deletions.
  - Keep `source-map.json` in `base_synced` to record native `extensions/ad_hoc/*.md` ownership and ignored files.

- On write-like Codex tool events, detect newly changed native ad-hoc notes and attribute them to the current repository:
  - Register the note in `source-map.json`, create its scoped resource and shared repo-memory counterpart, and retain the native ad-hoc source.
  - Add a normal `MEMORY.md` entry: use the note’s first H1 as label; otherwise derive one from its filename, stripping `feedback_`; append `— TODO: summarize this file.`
  - Reject filename collisions with different content instead of overwriting either memory.

- At SessionStart and Stop, reconcile already scoped resources and commit pending Codex-workspace changes. If an unassigned ad-hoc note appears outside a direct write event, print a clear instruction to either:
  - run `scripts/°base/ai/memory/import-codex.py <note>` from the correct repository, or
  - run the same command with `--ignore` to persistently suppress future prompts for that note.

- Add `import-codex.py` for explicit attribution and ignore management. Extend the existing memory-delete path so a sanctioned deletion removes the shared repo file, its `base_synced` counterpart, mapped native source, and index entry while retaining the existing deletion-marker protection.

- Narrow Codex’s `record-codex-memory` `PostToolUse` matcher to write-like tools (`Write|Edit|Bash|shell|unified_exec|apply_patch`), while retaining SessionStart and Stop recovery. Regenerate settings through `ai/tool-settings/`.

- Migrate the current two files from `ai/°base/memory/codex/extensions/ad_hoc/` into the normal shared memory directory, add pending-summary index entries, then remove the obsolete Codex-only tree.

## Test plan

- Cover scoped resource creation, generated `scope.json`, hardlink/symlink fallback, repo-wins reconciliation, and idempotency.
- Cover automatic ad-hoc attribution, H1/fallback index labels, pending-summary text, collision rejection, explicit import, and persistent ignore behavior.
- Cover boundary-time unassigned-note output, scoped deletion propagation, and protection against deletion inferred from a missing side.
- Verify Codex hook rendering uses the narrowed matcher and correct tool identity; run the focused hook/settings tests, full `scripts/°base` suite, and `sync.py --check`.

## Assumptions

- Project keys use the existing Claude-style encoding of the canonical project root; `scope.json` remains the authoritative human-readable scope.
- `base_synced/resources/<project-key>/` is nested, so Codex’s top-level extension-resource retention pruning does not remove persistent project memory files.
- Codex’s consolidation reads `base_synced` resources and updates its global routing memory, but does not edit these synchronized resources directly; the hook is their sole synchronizer.
