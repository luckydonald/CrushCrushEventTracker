# Capture Claude `/compact` Results

## Summary

Extend the existing compact hook to persist Claude’s generated manual-compaction summary as `output/compact/NNN/result.md` and link it from `query.md`, while retaining current custom-instruction and legacy autoload behavior.

## Implementation Changes

- Dispatch `save-compact-prompt/hook.py` by event:
  - Keep current `PreCompact` handling for non-empty manual custom instructions.
  - Handle `PostCompact` as the primary path, reading `compact_summary` directly.
  - Handle `SessionStart` with `source: "compact"` as a compatibility fallback for the captured Claude version. Parse the transcript’s latest manual `compact_boundary` and its child `isCompactSummary: true` user record.
  - Ignore automatic compactions, malformed payloads, missing transcripts, and empty summaries.
- Store the summary verbatim in the next numeric `output/compact/NNN/result.md`, sharing numbering with existing autoload directories.
- Append:
  `❯ Conversation compacted:` followed by a `Result` link with character count and file size. Commit `result.md` and `query.md` together through the existing scoped artifact-commit helper.
- Prevent duplicate capture when both lifecycle events fire by comparing the candidate with the latest numbered `result.md` before allocating another directory.
- Add Claude-only `PostCompact` and `SessionStart`-`compact` hook entries to canonical tool settings, then regenerate `.claude`, `.codex`, and Copilot hook files through the settings sync. Current Claude documentation exposes `compact_summary` directly on `PostCompact`; the transcript fallback supports the supplied older event capture. [Claude hooks reference](https://code.claude.com/docs/en/hooks)

## Interfaces

- New persisted artifact: `ai[/°base]/output/compact/NNN/result.md`.
- New prompt-log entry: blockquoted `Result` link under `Conversation compacted`.
- No changes to ordinary Claude/Codex prompt normalization, memory synchronization, or the legacy `autoloads.md` format.

## Test Plan

- Verify manual `PostCompact` stores the exact summary and creates the correctly routed query link.
- Replay a minimal transcript matching the supplied debug capture; verify the newest manual boundary’s matching compact summary is selected.
- Verify direct `PostCompact` followed by the `SessionStart` fallback creates only one result.
- Cover auto compaction, empty/malformed payloads, missing transcripts, multiple historical boundaries, sequential numbering, existing autoload-only directories, and base-versus-consuming-repository routing.
- Run the focused hook-routing unittest module with `UV_CACHE_DIR=/tmp/uv-cache`, then run settings synchronization and `sync.py --check`.

## Assumptions

- Only explicit `/compact` results are stored; automatic compaction remains out of scope.
- The summary is preserved verbatim, including Claude’s continuation wrapper.
- Existing unrelated untracked files remain untouched.
- The repository’s `luckydonald/base` origin enables the lplp commit workflow automatically for implementation.
