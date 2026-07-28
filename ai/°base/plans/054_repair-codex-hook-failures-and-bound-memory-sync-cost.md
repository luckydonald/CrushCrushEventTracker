# Repair Codex hook failures and bound memory-sync cost

## Summary

- Confirmed current Stop-hook defect: `record-codex-memory` writes plain-text status/instructions to stdout, but Codex requires JSON (or no stdout) for successful Stop hooks.
- The historical PostToolUse timeout began with the original catch-all `.*` Codex-memory hook, which performed full synchronization and Git commits after every tool call. No retained error log identifies the exact blocked Git operation.
- Preserve the selected contract: full reconciliation at SessionStart/Stop, plus immediate capture after write-like tool events.

## Implementation Changes

- Update `record-codex-memory` so Stop output is always valid Codex hook JSON:
  - Collect unassigned-note and successful-sync messages rather than printing during processing.
  - Emit them as one `systemMessage` JSON response on Stop; retain plain SessionStart output so the next agent receives the import instruction as context.
  - Keep errors on stderr with a nonzero exit.
- Narrow its Codex `PostToolUse` matcher to `Write|Edit|apply_patch`; shell commands are reconciled at the next Stop boundary instead of running a full sync after reads.
- Give the Codex-memory hook an explicit bounded timeout in shared hook settings, then regenerate all native hook config outputs. Leave other tools’ behavior intact.

## Test Plan

- Extend the temporary-repository hook tests to assert that a Stop event with an unassigned note returns parseable JSON containing the instruction, while project and memory state remain unchanged.
- Cover Stop synchronization status with valid JSON/no raw stdout and retain PostToolUse import coverage.
- Assert generated Codex settings use the narrowed write matcher and configured timeout; run the focused hook/settings tests and settings sync check.

## Assumptions

- SessionStart and Stop are the durable catch-up boundaries for filesystem changes made outside write tools.
- A bounded hook failure is preferable to Codex’s implicit 600-second wait; failed syncs remain visible via stderr and retry at the next boundary.
