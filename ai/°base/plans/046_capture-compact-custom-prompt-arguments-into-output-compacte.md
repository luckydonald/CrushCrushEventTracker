# Capture `/compact <custom prompt>` arguments into `output/compacted/NNN.md`

## Context

Right now, when someone runs `/compact <custom prompt>` (e.g. just happened in `hoass_plugin-template`), the custom instructions text is thrown away — the only existing compact-related hook (`_handle_compact_prompt()` in `save-prompt/hook.py`) reacts to the *post-compaction reload summary* (a `UserPromptSubmit` payload starting with `/compact` + `⎿`), not to the argument the user actually typed. A bare `/compact` is even explicitly skipped (`SKIP_PROMPTS`). There is no `PreCompact` hook wired up anywhere in this repo — that's the only event that sees the custom-instructions argument before compaction runs.

Goal: whenever `/compact <text>` is invoked manually (not on auto-compaction, not on a bare `/compact`), save `<text>` to a new numbered file and link it from `query.md`, so these prompts aren't lost — they're often reusable "how to compact this kind of session" recipes.

## Plan

### New hook: `scripts/°base/ai/hooks/save-compact-prompt/hook.py`

Mirrors the existing `save-plan`/`save-decision`/`record-memory` hook shape (one dir, one `hook.py`, shared `_lib.py` helpers).

- Trigger: Claude Code's `PreCompact` event. Payload includes a `trigger` field (`"manual"` vs `"auto"`) and a custom-instructions field. **Open/unverified**: exact field name — web sources agree on `custom_instructions` but I couldn't reach Anthropic's first-party hooks-reference page to confirm. The hook defensively checks `custom_instructions` / `custom_instruction` / `customInstructions` / `instructions` and uses whichever is a non-empty string. `dump_debug_payload()` (existing helper, same as other hooks use) records the raw payload either way, so the very first real invocation will confirm/correct the field name from `ai/°base/output/debug/*.json`.
- Bail out (no file, no commit) when `trigger != "manual"` or the resolved instructions text is empty after `.strip()`.
- On a real manual+non-empty invocation:
  1. `resolve_log_path("ai/query.md", "ai/°base/query.md")` to get the right root (base repo vs. consuming repo).
  2. `compacted_dir = log_path.parent / "output" / "compacted"` — a new, separate directory from the existing `output/compact/NNN/` (autoload summaries; different artifact, keep them apart).
  3. Number via existing simple-increment pattern: scan `compacted_dir` for `NNN.md`, `max+1`, zero-padded 3 digits.
  4. Write the raw instructions text to `NNN.md`.
  5. Commit that file alone: `git add` + `git commit --no-verify --only <path> -m <styled "ai: compact NNN prompt">`.
  6. Append a link line to `query.md` via the existing `append_and_commit()` helper: `` - [`/compact` possible prompt](./output/compacted/NNN.md) `` (own commit, same as the existing autoloads flow's two-commit pattern).

### Settings wiring — `ai/tool-settings/settings.json`

Add a new `"PreCompact"` key to the shared `hooks` object:
```json
"PreCompact": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/save-compact-prompt/hook.py\" 'claude'",
        "async": true
      }
    ]
  }
]
```
No `°settings_lib/hooks.py` code changes needed — event names are opaque dict keys throughout its merge/render pipeline; it'll propagate into `.claude/settings.json` correctly and pass through harmlessly (inert) into `.codex/hooks.json` / `.github/hooks/generated.json`, matching how `record-memory`'s Claude-only `SessionStart` entry is already handled (hardcoded `'claude'` arg, no cross-tool arg-swap needed). Then run `python3 scripts/°base/ai/settings/sync.py` to regenerate the per-tool files.

### Tests — extend `scripts/°base/tests/test_ai_hooks_base_routing.py`

Using the existing `run_hook`/`init_repo` harness (same pattern as the `test_compact_prompt_writes_autoloads_file` tests around line 1659):
- Manual trigger + non-empty instructions → `output/compacted/001.md` has the exact text; `query.md` has the link line.
- Manual trigger + empty/missing instructions → nothing written.
- Auto trigger (even with instructions present, defensively) → nothing written.
- Two manual calls → sequential `001.md`, `002.md`.
- Consuming-repo routing (non-`luckydonald/base` origin) → lands at `ai/output/compacted/001.md`, not `ai/°base/...`.

## Verification

- Run the new/extended pytest module: `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py -k compact_prompt` (or the project's normal test invocation).
- `python3 scripts/°base/ai/settings/sync.py` then diff `.claude/settings.json` to confirm the `PreCompact` entry rendered correctly and nothing else changed.
- Real-world check: trigger an actual manual `/compact <text>` in this session (or `hoass_plugin-template`) after implementing, then inspect the freshly written `ai/°base/output/debug/*save-compact-prompt*.json` dump to confirm the real field name matches `custom_instructions` (or note which fallback key actually fired) — fix the primary key if the assumption was wrong.
- Confirm `output/compacted/NNN.md` and the `query.md` link line both land under `ai/°base/` when run inside this repo, and would land under plain `ai/` in a consuming repo (can spot-check via the routing test above; no need to actually run it in `hoass_plugin-template`).
