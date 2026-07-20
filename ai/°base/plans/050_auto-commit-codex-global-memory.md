# Auto-commit Codex global memory

## Summary

Add a dedicated Codex-memory commit hook. It will reconcile and commit the standalone `$CODEX_HOME/memories` Git repository on `SessionStart`, every `PostToolUse`, and `Stop`, so edits made through `Write`, `Edit`, `Bash`, `unified_exec`, `apply_patch`, or other tools are eventually captured.

## Implementation changes

- Add `scripts/°base/ai/hooks/record-codex-memory/hook.py`.
  - Resolve `$CODEX_HOME` with `~/.codex` fallback, then `$CODEX_HOME/memories`.
  - No-op when the directory is absent or not a Git worktree.
  - Serialize invocations with a repository lock to prevent PostToolUse/Stop races.
  - Stage all changes in that dedicated memory repository, including additions, modifications, and deletions.
  - Commit only when changes exist, using a deterministic `ai: record codex memory` message with changed paths in the body.
  - Use `--no-verify`; report actionable Git stderr rather than swallowing failures.
  - Keep the current memory repository’s existing unrelated state intact; only the repository’s own memory files are in scope.

- Wire the hook into `ai/tool-settings/settings.json` for:
  - `SessionStart`
  - `PostToolUse` with a catch-all matcher
  - `Stop`
  Pass the tool identity as an argument so the generated Claude/Copilot configurations no-op while Codex runs the hook. Extend settings normalization/rendering so this new hook’s argument is rewritten consistently for each tool and remains deduplicated during sync.

- Update generated/native hook files through the existing settings-sync workflow and document the new Codex-memory behavior in the hook table/docs.

- After implementation, invoke the new hook once to commit the currently untracked memory note in `/home/user/.codex/memories`.

## Tests

- Unit tests for:
  - `$CODEX_HOME` resolution and missing/non-Git directory no-op.
  - New, modified, and deleted memory files.
  - No-op when clean.
  - Git failure propagation with stderr.
  - Lock-safe repeated invocations producing one commit.
- Settings-sync tests verifying the hook appears on all three events, uses a catch-all PostToolUse matcher, and receives `codex` only in Codex output.
- End-to-end test invoking the hook for SessionStart, PostToolUse, and Stop against a temporary memory repository; assert one commit contains the expected file changes.
- Run the existing hook/settings test suites and `sync.py --check`.

## Assumptions

- The dedicated `$CODEX_HOME/memories` repository is the authoritative Codex-memory store.
- Committing all changes in that repository is safe because it contains memory data rather than project source.
- SessionStart, PostToolUse, and Stop coverage is intentional redundancy; locking and clean-state checks make repeated invocations harmless.
