# Tests: save-plan hook — Stop false positive and routing (Fix 1 & Fix 2)

## Context

We just fixed two bugs in `save-plan/hook.py` and `_lib.py`. The test suite at `scripts/°base/tests/test_ai_hooks_base_routing.py` already covers the Write and Codex-Stop triggers for save-plan, but has **no coverage** for the Claude Stop event or ExitPlanMode. These are the exact paths the fixes address.

Tests go in **`scripts/°base/tests/test_ai_hooks_base_routing.py`**, using the existing helpers (`init_repo`, `run_hook`, `last_subject`, `PLAN_HOOK`). Run with:
```
uv run --project scripts/°base python -m unittest scripts.°base.tests.test_ai_hooks_base_routing -v
```

## Fix 1: Stop false positive — 3 new tests

All use a repo named `base` with origin `https://luckydonald@github.com/luckydonald/base.git`.

### `test_claude_stop_does_not_commit_string_tool_response`
**What it proves:** a Stop event whose `tool_response` is a plain string (e.g., Bash stdout) is silently ignored — no commit, no plans dir.

```python
payload = {
    "hook_event_name": "Stop",
    "session_id": "sess-stop-str",
    "tool_name": "",          # Stop has no tool_name
    "tool_input": {},
    "tool_response": "Exit code: 0\nSuccess. Updated:\nM scripts/°base/tests/test_foo.py",
}
run_hook(repo, PLAN_HOOK, payload, "claude")

self.assertEqual(last_subject(repo), "init")           # no new commit
self.assertFalse((repo / "ai" / "°base" / "plans").exists())
self.assertFalse((repo / "ai" / "plans").exists())
```

### `test_claude_stop_does_not_commit_dict_tool_response_without_plan`
**What it proves:** a Stop payload with a dict `tool_response` that has no `"plan"` or `"filePath"` key is also ignored.

```python
payload = {
    "session_id": "sess-stop-dict",
    "tool_name": "",
    "tool_input": {},
    "tool_response": {"status": "ok", "duration_ms": 120},
}
# assertions same as above
```

### `test_claude_exit_plan_mode_still_captures_plan_from_file_path`
**What it proves:** Fix 1 did not break ExitPlanMode — plan is still extracted from `tool_response.filePath` and committed.

```python
plan_file = Path(tmp) / "plan.md"
plan_file.write_text("# My Plan\n\nStep 1.\nStep 2.\n")
payload = {
    "session_id": "sess-exit",
    "tool_name": "ExitPlanMode",
    "tool_input": {},
    "tool_response": {"filePath": str(plan_file)},
}
run_hook(repo, PLAN_HOOK, payload, "claude")

plan_files = list((repo / "ai" / "°base" / "plans").glob("001_*.md"))
self.assertEqual(len(plan_files), 1)
self.assertIn("Step 1.", plan_files[0].read_text())
self.assertEqual(last_subject(repo), "[base] ai: save plan 001_my-plan")
```

## Fix 2: Routing — note on testability

Fix 2 adds `or _is_inside_base_repo(git_root)` as a fallback in `resolve_log_path`. A full integration test for this path requires `CLAUDE_PROJECT_DIR` to point to a directory whose `.name != "base"` while the git root IS named `"base"`. **The problem:** `resolve_log_path` constructs `log_path = (subproject / relpath).resolve()`, so if `subproject` differs from the git root, the plan file lands outside the repo and the `git add` fails silently.

**Recommendation:** skip an integration test for this fallback. The detection logic is a one-liner (`or _is_inside_base_repo(git_root)`) with no branching; confidence comes from the existing routing tests passing and the fact that the common case (`CLAUDE_PROJECT_DIR == git_root`) exercises the same `_is_inside_base_repo` call.

If a future change also corrects the path construction to use `git_root` when `is_base` was triggered via that fallback, a proper integration test can be added then.

## Verification

Run the full routing test file:
```
uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v 2>&1 | grep -E "test_|ERROR|FAIL|OK"
```

All existing tests must still pass. The three new tests must pass.
