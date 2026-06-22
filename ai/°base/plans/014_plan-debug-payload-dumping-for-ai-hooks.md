# Plan: Debug payload dumping for AI hooks

## Context

When debugging hook behavior, it's useful to inspect the raw JSON payload each hook receives from Claude Code. This plan adds an opt-in debug mode: if `ai/.debug` (or `ai/°base/.debug` inside the base repo) exists, every hook writes its raw stdin payload as a JSON file to `ai/output/debug/` (or `ai/°base/output/debug/`). The `.debug` flag is absent by default, so this has zero runtime cost in normal operation.

## Changes

### 1. `scripts/°base/ai/hooks/_lib.py` — add `dump_debug_payload()`

Add a new exported function after `read_payload()`:

```python
def dump_debug_payload(payload: dict, hook_name: str) -> None:
    """If ai[/°base]/.debug exists, write payload JSON to ai[/°base]/output/debug/."""
    import datetime
    subproject = _subproject_root()
    git_root_str = _git_text("rev-parse", "--show-toplevel")
    git_root = Path(git_root_str) if git_root_str else subproject
    is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
    ai_prefix = "ai/°base" if is_base else "ai"
    if not (subproject / ai_prefix / ".debug").is_file():
        return
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S_%f")
    debug_dir = subproject / ai_prefix / "output" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{ts}-{hook_name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

Also add `import datetime` at the top-level imports (rather than inside the function, for cleanliness).

### 2. Four hooks — call `dump_debug_payload()` right after `read_payload()`

Each hook already imports from `_lib`. Add `dump_debug_payload` to the import and insert one call:

| File | After which line | Call |
|---|---|---|
| `save-prompt/hook.py` | `payload = read_payload()` | `dump_debug_payload(payload, "save-prompt")` |
| `save-decision/hook.py` | `payload = read_payload()` | `dump_debug_payload(payload, "save-decision")` |
| `save-plan/hook.py` | `payload = read_payload()` | `dump_debug_payload(payload, "save-plan")` |
| `record-memory/hook.py` | `payload = read_payload()` | `dump_debug_payload(payload, "record-memory")` |

`record-memory` already calls `_chdir_to_git_root()` before `read_payload()`, but `dump_debug_payload` uses `_subproject_root()` which prefers `CLAUDE_PROJECT_DIR`, so cwd changes don't matter.

### 3. `scripts/°base/tests/test_ai_hooks_base_routing.py` — add tests

Add three tests to `AiHooksBaseRoutingTests`:

- **`test_debug_payload_written_when_flag_exists`**: consuming repo (non-base origin), create `ai/.debug`, run `save-prompt` hook, assert one file appears in `ai/output/debug/` with valid JSON matching the payload.
- **`test_debug_payload_not_written_without_flag`**: same setup but no `ai/.debug`, assert `ai/output/debug/` does not exist.
- **`test_debug_payload_routes_to_base_prefix`**: base-repo origin, create `ai/°base/.debug`, run `save-prompt` hook, assert file appears in `ai/°base/output/debug/` (and NOT in `ai/output/debug/`).

## Verification

```bash
# Run the full hook test suite
uv run --project scripts/°base python -m unittest scripts.°base.tests.test_ai_hooks_base_routing -v

# Manual smoke-test: touch ai/.debug, run any hook, check ai/output/debug/
touch ai/.debug
echo '{"prompt":"hello"}' | python3 scripts/°base/ai/hooks/save-prompt/hook.py claude
ls ai/output/debug/
```
