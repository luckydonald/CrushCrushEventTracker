# Repair Codex hook failures and bound memory-sync cost

## Summary

- Confirmed current Stop-hook defect: `record-codex-memory` writes plain text to stdout, but Codex requires JSON (or no stdout) for successful Stop hooks.
- The historical PostToolUse timeout began with the original catch-all `.*` Codex-memory hook, which performed full synchronization and Git commits after every tool call. No retained error log identifies the exact blocked Git operation.
- Preserve SessionStart/Stop reconciliation plus immediate capture after write-like tool events.

## Implementation Changes

- Make `record-codex-memory` format output by invoking tool:
  - For Codex Stop, collect unassigned-note and successful-sync messages and emit one valid JSON `systemMessage`.
  - For Claude Stop and SessionStart, retain existing plain-text messages.
  - Keep errors on stderr with a nonzero exit.
- Narrow its Codex `PostToolUse` matcher to `Write|Edit|apply_patch`; shell changes reconcile at the next Stop boundary.
- Set an explicit bounded timeout for the Codex-memory hook in shared settings and regenerate native hook configurations.

## Test Plan

- Assert Codex Stop with an unassigned note returns parseable JSON with the instruction.
- Assert Claude Stop retains the existing plain-text instruction.
- Cover Stop status output, narrowed Codex matcher, timeout rendering, and settings synchronization.

## Assumptions

- SessionStart and Stop remain the catch-up boundaries for filesystem changes outside write tools.
- A bounded failure is preferable to the implicit 600-second wait; retries occur at the next boundary.
