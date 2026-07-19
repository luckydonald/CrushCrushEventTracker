# Capture Manual and Automatic Compact Results

## Summary

Persist every Claude compaction result under `output/compact/NNN.<prompt_id>/result.md`. Record whether it was manual or automatic in `query.md`, while keeping the saved summary verbatim.

## Implementation Changes

- Extend `save-compact-prompt/hook.py`:
  - Preserve existing `PreCompact` custom-instruction handling.
  - Handle `PostCompact` for both `manual` and `auto`, using the documented `compact_summary` field as the authoritative result.
  - Write the exact summary to `output/compact/NNN.<prompt_id>/result.md`; fall back to `NNN/result.md` only when an older payload lacks `prompt_id`.
- Add shared compact-artifact logic that:
  - Allocates the next numeric prefix across existing compact directories.
  - Reuses a matching `NNN.<prompt_id>` directory when another hook is adding a missing artifact for the same compaction.
  - Skips a duplicate event when the same prompt ID and result content were already captured, while allowing distinct summaries from multiple compactions during one prompt.
- Use the existing `record-memory` `SessionStart` path as compatibility fallback:
  - After memory synchronization, when `source == "compact"`, parse the latest matching transcript `compact_boundary` and `isCompactSummary` record.
  - Preserve its `manual`/`auto` trigger and call the shared compact writer.
  - Do nothing when `PostCompact` already captured that result.
- Update the legacy autoload capture to use `NNN.<prompt_id>` when available, allowing `autoloads.md` and `result.md` for the same compaction to share a directory.
- Append a local-relative entry such as:
  - `❯ Conversation compacted <kbd>manual</kbd>:` or
  - `❯ Conversation compacted <kbd>auto</kbd>:`
  - followed by the existing character-count/file-size `Result` link whose path contains the prompt ID.
- Add a `PostCompact` hook matching `manual|auto` to canonical tool settings and regenerate derived hook configurations. The direct field and common `prompt_id` contract come from the repository’s downloaded [hooks reference](/home/user/git/luckydonald/base/ai/references/https/code.claude.com/docs/en/hooks.md:605).

## Interfaces and Compatibility

- New path convention: `ai[/°base]/output/compact/NNN.<prompt_id>/result.md`.
- Existing `output/compacted/NNN.md` files for reusable custom instructions remain unchanged.
- Payloads without `prompt_id`, missing transcripts, malformed JSONL, and empty summaries remain safe no-ops or use numeric-only directory fallback as applicable.
- Ordinary prompt logging and memory synchronization behavior remain unchanged.

## Test Plan

- Cover manual and automatic `PostCompact` payloads, exact result preservation, trigger badges, prompt-ID paths, and base/consumer routing.
- Replay the supplied `SessionStart source=compact` transcript shape for both trigger types.
- Verify `PostCompact` plus `SessionStart` produces one result and one query entry.
- Verify different summaries sharing one prompt ID remain distinct, while repeated identical events deduplicate.
- Cover missing prompt IDs, malformed or lagging transcripts, sequential numbering, and co-location with legacy `autoloads.md`.
- Run the focused hook-routing tests with the repository’s `uv` command and temporary cache, then regenerate settings and run `sync.py --check`.

## Assumptions

- Both manual and automatic compactions receive visible trigger badges; IDs are shown only through the result link path.
- `result.md` contains no heading or metadata so it remains byte-for-byte equal to Claude’s compact summary.
- Existing unrelated untracked files remain untouched.
- The repository origin enables the lplp commit workflow automatically for implementation.
