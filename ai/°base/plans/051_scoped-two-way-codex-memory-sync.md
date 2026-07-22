# Scoped two-way Codex memory sync

## Summary

Replace `ai/.../memory/codex/` with the same shared project-memory tree Claude uses. Codex’s counterpart will be a visible `$CODEX_HOME/memories/extensions/base_synced/` extension; native global ad-hoc notes are attributed only when a current-repo write event provides a safe scope.

## Synchronization design

- Extract the existing hardlink-first, symlink-fallback behavior into `scripts/°base/ai/hooks/°memory_lib/links.py`; both Claude and Codex memory hooks use it for inode checks, safe replacement, and repo-wins conflict reconciliation.

- Create and own these Codex-side files:
  - `extensions/base_synced/instructions.md`: scope-aware consolidation guidance; read `scope.json` and `MEMORY.md` first, never edit synchronized resources directly.
  - `extensions/base_synced/resources/<encoded-project-root>/scope.json`: current canonical absolute CWD.
  - `.../.codex-sync.json`: synchronized metadata counterpart for the project file below.

- Create `ai/°base/memory/.codex-sync.json` (or `ai/memory/.codex-sync.json`) in the project and commit it like the memory files. It records:
  - native source identity as `<device-id>:extensions/ad_hoc/<name>.md`;
  - target filename, assignment state, and optional content hash;
  - ignored/unassigned sources.
  - Device ID is `CODEX_MEMORY_DEVICE_ID` when set, otherwise the hostname. JSON is sorted and semantically merged by source identity; incompatible mappings for the same source are reported, never overwritten.

- Mirror all shared project memory Markdown files, including `MEMORY.md`, between the project tree and that project’s scoped Codex resource. Existing tracked project content wins on divergence; missing counterparts are restored. The metadata map merges rather than blindly replacing either side.

- Retire the current Codex-only repository subtree. Move its actual note files into the normal shared memory directory, add normal pending-summary entries, and remove its stale extension instruction file/tree.

## Native Codex notes and indexing

- Narrow `record-codex-memory` to write-like `PostToolUse` events plus SessionStart and Stop. Preserve the non-blocking lock and commit only workspace/project changes made by the hook.

- When a native `extensions/ad_hoc/*.md` note first changes during a write-like event:
  - assign it to the current project in `.codex-sync.json`;
  - link it into that project’s `base_synced` resource and shared memory directory;
  - retain the native ad-hoc source;
  - append `- [<title>](<file>.md) — TODO: summarize this file.` to the normal `MEMORY.md`.
    Use the first H1 as title; otherwise derive the filename label, stripping `feedback_`.

- When a previously unassigned native note is noticed only at SessionStart/Stop, print a stdout instruction:
  - if this repo is confirmed as owner, Codex may run `scripts/°base/ai/memory/import-codex.py <note>` automatically;
  - otherwise ask the user which repository owns it and direct them to run that command there;
  - `--ignore <note>` records a device-specific ignore entry so this machine stops prompting.
  - `--as <filename>` resolves a differing-content filename collision without overwriting a note.

- Extend the sanctioned deletion helper to remove the shared project file, scoped Codex resource, mapped native ad-hoc source, metadata entry, and `MEMORY.md` index entry under the existing deletion-marker protection. Never infer deletion from a missing side.

## Verification

- Add focused automated tests using temporary Git repositories and temporary `CODEX_HOME` trees under `/tmp`; tests must never inspect, modify, commit, or link live `$HOME/.codex` data.
- Cover shared-link helper behavior, scoped setup, semantic metadata merge, device IDs, direct-write attribution, H1/fallback index labels, unassigned output, `--ignore`, explicit import, collision handling, safe deletion, and idempotency.
- Verify the narrowed generated Codex matcher, tool-identity rewriting, and `sync.py --check`; run the focused hook/settings tests and full `scripts/°base` suite.

## Assumptions

- The project memory directory remains the durable cross-machine source of truth; `base_synced` is its scoped Codex representation.
- Per-project resources are nested below `resources/<project-key>/`, so Codex’s top-level extension-resource retention pruning does not remove persistent synchronized files.
