## Design: PreCompact hook to capture `/compact <custom prompt>` instructions

### Why a new hook, not `_handle_compact_prompt`

`_handle_compact_prompt()` in `save-prompt/hook.py` (line ~807) fires on `UserPromptSubmit` for the **post-compaction reload** payload (starts with `/compact`, contains `⎿`) — that's the harness re-injecting a summary of what got reloaded, not the user's typed argument. The user's actual `/compact <text>` argument is only visible in the `PreCompact` hook payload's `custom_instructions` field, fired *before* compaction runs, which is a completely separate event never currently wired in this repo.

### Confirmed payload shape (web-corroborated, not 100% from official rendered docs — flag as open question)

Via WebFetch of `code.claude.com/docs/en/hooks` + `hooks-guide`, and a community hooks-schema gist, cross-corroborated:

```json
{
  "session_id": "...",
  "transcript_path": "...",
  "cwd": "...",
  "hook_event_name": "PreCompact",
  "trigger": "manual" | "auto",
  "custom_instructions": "string, empty when auto"
}
```

I could not load Anthropic's actual `hooks-reference` page (404'd) — the exact field names are corroborated by two independent secondary sources agreeing on `trigger` and `custom_instructions`, but not first-party-confirmed. **Open question for user confirmation before implementation**, and the hook should defensively also check `payload.get("custom_instruction")` / `payload.get("customInstructions")` / `payload.get("instructions")` as fallbacks, logging nothing if all are empty.

### Bail-out logic

Only write a file when:
- `trigger == "manual"`, AND
- `custom_instructions` (after `.strip()`) is non-empty.

Bare `/compact` (no arg) → Claude sets `custom_instructions` to `""` → hook exits 0, no file, no commit. Auto-compaction → `trigger == "auto"` → exits 0 regardless of instructions content.

### File layout

New hook directory, mirroring `save-decision`, `save-plan`, `record-memory` naming (`save-<noun>`):

- `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-compact-prompt/hook.py`

### `main()` skeleton

```python
#!/usr/bin/env python3
"""PreCompact hook: save the user's manual `/compact <custom prompt>` argument.

Usage: hook.py [ai_tool_name]   (default: unknown; only 'claude' matters today)
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import (
    append_and_commit, base_ai_commit_subject, dump_debug_payload,
    is_cross_tool_duplicate, read_payload, resolve_log_path,
)

_INSTRUCTION_KEYS = ("custom_instructions", "custom_instruction", "customInstructions", "instructions")

def _custom_instructions(payload: dict) -> str:
    for key in _INSTRUCTION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def _next_compacted_number(compacted_dir: Path) -> int:
    if not compacted_dir.exists():
        return 1
    nums = [int(m.group(1)) for f in compacted_dir.glob("*.md") if (m := re.fullmatch(r"(\d+)\.md", f.name))]
    return max(nums, default=0) + 1

def main() -> int:
    ai_tool = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    payload = read_payload()
    if is_cross_tool_duplicate(ai_tool):
        return 0
    dump_debug_payload(payload, "save-compact-prompt")

    if payload.get("trigger") != "manual":
        return 0
    text = _custom_instructions(payload)
    if not text:
        return 0

    log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")  # cds to git root, creates parents
    compacted_dir = log_path.parent / "output" / "compacted"
    num = _next_compacted_number(compacted_dir)
    dir_name = f"{num:03d}"
    compacted_dir.mkdir(parents=True, exist_ok=True)
    compacted_file = compacted_dir / f"{dir_name}.md"
    compacted_file.write_text(text, encoding="utf-8")

    cwd = Path.cwd()
    rel = str(compacted_file.relative_to(cwd))
    subprocess.run(["git", "add", "--", rel], capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "--only", rel,
         "-m", base_ai_commit_subject(f"ai: compact {dir_name} prompt")],
        capture_output=True,
    )

    link_line = f"- [`/compact` possible prompt](./output/compacted/{dir_name}.md)\n"
    append_and_commit(
        log_path,
        link_line,
        commit_template_relpath="ai/commit-templates/prompt",
        default_commit_msg=f"ai: link compact {dir_name} prompt",
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Notes on the skeleton vs. `_handle_compact_prompt`'s two-commit pattern (lines 838–859): mirrors it exactly — first commit the new artifact file alone (`git add` + `git commit --only`), then `append_and_commit()` for the `query.md` link line as its own commit (which itself does add+commit+restore-staged). Two separate commits, same as the existing autoloads flow.

Since `PreCompact` is a bare event with no per-prompt "current position" in `query.md` the way `UserPromptSubmit` prompts are ordered, appending a link line to `query.md` is a reasonable location per the user's spec, but flag as a design choice: it will land at whatever point `query.md` currently ends — i.e., *before* the actual `/compact` UserPromptSubmit-reload entry that `_handle_compact_prompt` will append moments later (PreCompact fires first, chronologically). That ordering (`possible prompt` link, then later the `Conversation compacted` autoloads entry) is correct and desirable.

### Settings wiring — `ai/tool-settings/settings.json`

Add a new top-level `"PreCompact"` key to the shared `hooks` object (`°settings_lib/hooks.py`'s merge/render pipeline is fully event-name-agnostic — confirmed by reading `_merge`/`_render_hooks`/`render_claude`/`render_codex_hooks`/`render_copilot_hooks`, none of which hardcode an event whitelist), e.g. inserted after `"PermissionRequest"` or before `"SessionStart"`:

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
],
```

- No `matcher` needed (there's nothing to matcher on at this event granularity; the manual/auto distinction is read from the payload inside the hook, same as Claude's own docs suggest via `trigger` field — a `matcher` on `trigger` could theoretically restrict at the settings level too, but doing it in Python keeps behavior identical across tools/future changes and matches this repo's existing pattern of payload-based branching inside hooks rather than matcher-based filtering).
- `async: true` matches the `UserPromptSubmit`/`PostToolUse` fire-and-forget convention already used everywhere else.
- Codex and Copilot CLI renderers (`render_codex_hooks`, `render_copilot_hooks`) will pass this key through harmlessly into `.codex/hooks.json` / `.github/hooks/generated.json` even though neither tool currently fires a `PreCompact`-equivalent event — inert dead config, no special-casing required. Confirm with user whether they'd rather suppress it for non-Claude renderers (would require a small `_render_hooks` filter by event name and tool) — recommend **not** doing this preemptively since it adds tool-specific event whitelisting that doesn't exist anywhere else in `hooks.py` today.
- `°settings_lib/hooks.py` itself: **no code changes needed** — event names are opaque dict keys throughout; `_replace_tool_arg`/`_neutralize_command` only special-case by hook *script path* substring (`save-prompt/hook.py`, `save-decision/hook.py`, `save-plan/hook.py`), and `save-compact-prompt/hook.py` doesn't need the `'claude'`↔`'codex'`↔`'copilot'` arg-swap logic those get (it's Claude-only, always invoked with `'claude'` hardcoded, same as `record-memory/hook.py`'s SessionStart entry which also skips that machinery).
- `sync.py` itself: **no changes** — it's a 12-line dispatcher into `°settings_lib.cli.main`; nothing there is event-aware.

### Directory/README note

`ai/tool-settings/README.md` should probably get a one-line mention of the new `PreCompact` hook if it documents the existing hook list — worth checking before implementation but not load-bearing for the plan.

### Test plan — extend `scripts/°base/tests/test_ai_hooks_base_routing.py`

Add a new hook constant near line 20:
```python
COMPACT_PROMPT_HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-compact-prompt" / "hook.py"
```

New test cases, following the `run_hook(repo, HOOK, payload, "claude")` / `init_repo` pattern used at lines 1659–1716:

1. **`test_precompact_manual_with_instructions_writes_file`**: payload `{"trigger": "manual", "custom_instructions": "focus on the auth refactor"}` → assert `ai/°base/output/compacted/001.md` exists with that exact text, and `ai/°base/query.md` contains `` - [`/compact` possible prompt](./output/compacted/001.md) ``.
2. **`test_precompact_manual_no_instructions_writes_nothing`**: payload `{"trigger": "manual", "custom_instructions": ""}` (or key absent) → assert `output/compacted/` doesn't exist, `query.md` unchanged (or absent if never created).
3. **`test_precompact_auto_trigger_writes_nothing`**: payload `{"trigger": "auto", "custom_instructions": "some text"}` (defensive: even if Claude ever populated it) → assert nothing written.
4. **`test_precompact_sequential_numbering`**: two manual calls → `001.md`, `002.md`.
5. **Repo-routing test** (mirrors the base-vs-consuming-repo tests elsewhere in the file, e.g. around line 1640s `ai/output/debug` vs `ai/°base/output/debug`): run against a repo whose origin isn't `luckydonald/base` → assert file lands at `ai/output/compacted/001.md` (not `ai/°base/...`).

All via the existing `run_hook`/`init_repo`/`last_subject` helpers already defined at the top of the test file — no new harness code needed.

### Open questions requiring user confirmation before implementation

1. **Exact PreCompact payload field names** (`trigger`, `custom_instructions`) — corroborated by two secondary sources (a hooks-guide summary and a community-maintained hooks-schema gist) via WebFetch/WebSearch, but the canonical `hooks-reference` page 404'd, so this is not a first-party confirmation. Recommend keeping the defensive multi-key fallback in `_custom_instructions()` regardless.
2. Whether to suppress the inert `PreCompact` key from Codex/Copilot's generated config files (recommend: don't, for consistency with existing "no event whitelisting" design).
3. Exact commit-message wording/template category (reused `ai/commit-templates/prompt` for the link-line commit above) — fine to bikeshed at implementation time.
4. Whether `ai/tool-settings/README.md` needs a matching doc update (not inspected in this pass).

### Critical Files for Implementation
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-prompt/hook.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/_lib.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/°commit_style_lib/__init__.py
- /home/user/git/luckydonald/base/ai/tool-settings/settings.json
- /home/user/git/luckydonald/base/scripts/°base/tests/test_ai_hooks_base_routing.py
- /home/user/git/luckydonald/base/scripts/°base/ai/settings/°settings_lib/hooks.py (context only — no changes needed, but critical to review before touching settings.json)