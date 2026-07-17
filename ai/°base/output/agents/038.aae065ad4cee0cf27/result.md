[harness: subagent output matched instruction-shaped pattern(s): settings-json. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

## Report: Hook Infrastructure for `/compact` Handling

### 1. Where hooks are defined

- **Source of truth (tool-neutral):** `/home/user/git/luckydonald/base/ai/tool-settings/settings.json` — a `hooks` object keyed by event name (`PermissionRequest`, `SessionStart`, `PostToolUse`, `Stop`, `UserPromptSubmit`). Edit this file, then run `python3 scripts/°base/ai/settings/sync.py` to regenerate the per-tool files.
- **Generated (do not hand-edit):**
  - `/home/user/git/luckydonald/base/.claude/settings.json` (Claude Code)
  - `/home/user/git/luckydonald/base/.codex/hooks.json` / `.codex/rules/generated.rules` / `.codex/config.toml` (Codex)
  - `.github/hooks/generated.json` (Copilot CLI, per plan `038_native-copilot-cli-hook-support-...`)
- **Hook implementations:** `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/` — one subdir per hook (`save-prompt/hook.py`, `save-plan/hook.py`, `save-decision/hook.py`, `record-memory/hook.py`), plus shared libs: `_lib.py`, `°commit_style_lib/__init__.py`, `°memory_lib/`, `°reffiles_lib/`.
- **No `PreCompact` event is wired anywhere** — I grepped `.claude/settings.json`, `ai/tool-settings/settings.json`, `.codex/*`, `.github/hooks`, and all of `scripts/°base` for "compact"/"PreCompact"; the only event handling `/compact` today is `UserPromptSubmit` (see §4).
- `.claude/settings.json`'s current `hooks` map (relevant excerpt, lines ~1–99): `PermissionRequest`→`permission-check.py`; `SessionStart`→sync.py + checkout.sh + record-memory; `PostToolUse` (matchers `AskUserQuestion|...`→save-decision, `Write|Edit|Bash|...`→record-memory, `Write|Edit|ExitPlanMode|...` and `TodoWrite|...`→save-plan); `Stop`→save-plan; `UserPromptSubmit`→save-prompt. All commands are invoked as `python3 "$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/<name>/hook.py" 'claude'` with `"async": true`.

### 2. The three save/record hooks

**save-prompt** — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-prompt/hook.py`
- Event: `UserPromptSubmit`. `main()` at line 976.
- Reads JSON payload from stdin (`read_payload()`), extracts `prompt`, resolves the log file via `resolve_log_path("ai/query.md", "ai/°base/query.md")` (line 990).
- No NNN numbering for the main log — it's an append-only file. Numbering *is* used for sub-artifacts it spins off:
  - Codex command outputs: `_next_command_number()` (line 289) — scans `commands_dir.iterdir()` for `r"(\d+)\.log"`, `max(...)+1`.
  - Task/agent results: `_next_agent_number()` (line 863) — scans dirs matching `r"^(\d+)\."`, `max(...)+1`.
  - **Compact autoload dirs** (already exists!) — `_handle_compact_prompt()` (line 807) numbers `ai/output/compact/NNN/` the same way (lines 819–830):
    ```python
    compact_dir = log_path.parent / "output" / "compact"
    if not compact_dir.exists():
        num = 1
    else:
        nums = [
            int(m.group(1))
            for d in compact_dir.iterdir()
            if d.is_dir() and (m := re.match(r"^(\d+)$", d.name))
        ]
        num = max(nums, default=0) + 1
    dir_name = f"{num:03d}"
    ```
- Commit: appends a markdown block to `ai/query.md` and auto-commits **only that file** (plus any `extra_paths`) via `append_and_commit()` in `_lib.py` (line 197): `git add -- <relpath> <extra_relpaths>` then `git commit --no-verify --only <relpath> <extra_relpaths> -m <msg>`. Commit message default is `"ai: updated prompt"`, styled via `commit_message("ai/commit-templates/prompt", default_commit_msg)` → `°commit_style_lib.commit_message()` → `base_ai_commit_subject()` which prepends `[base] ` and/or an issue-key prefix when applicable (see §3 commit-format table). The compact-autoloads file itself is committed separately and directly (lines 840–845, not through `append_and_commit`):
  ```python
  subprocess.run(["git", "add", "--", autoloads_rel], capture_output=True)
  subprocess.run(
      ["git", "commit", "--no-verify", "--only", autoloads_rel,
       "-m", base_ai_commit_subject(f"ai: compact {dir_name} autoloads")],
      capture_output=True,
  )
  ```
- `SKIP_PROMPTS` (line 72) includes the bare literal `"/compact"` (line 93) — a plain `/compact` with no autoload lines and no custom argument is silently dropped, never logged.

**save-plan** — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-plan/hook.py`
- Events: `PostToolUse` for `Write|Edit|ExitPlanMode|TodoWrite|TaskCreate|TaskUpdate` matchers, plus `Stop` (used for Codex's proposed-plan extraction).
- NNN numbering: `_next_prefix()` (line 316) — simple increment based on existing files in the plans dir:
  ```python
  def _next_prefix(plans_dir: Path) -> str:
      highest = 0
      for entry in plans_dir.glob("[0-9]*_*.md"):
          m = re.match(r"^(\d+)_", entry.name)
          if m:
              highest = max(highest, int(m.group(1)))
      return f"{highest + 1:03d}"
  ```
  (Note real-world collision already exists: `ai/°base/plans/043_log-direct-codex-shell-executions.md` and `043_fix-orphaned-memory-md-entries-harden-record-memory-sync.md` share `043` — worth being defensive about races/duplicates in your new hook too.)
- Session state (survives across hook invocations within one Claude session) is a temp JSON file: `_STATE_FILE = Path(tempfile.gettempdir()) / "save-plan-state.json"`, keyed by `session_id`, storing `{"prefix", "relpath", "source", "done", "tasks"}`. First `Write`/`ExitPlanMode` allocates NNN and creates `NNN_slug.md`; subsequent writes in the same session reuse the prefix (renaming the file if the slug changed).
- Slug: `slugify()` from `_lib.py` (line 57) — first non-empty line, lowercased, non-alphanumeric runs → `-`, capped at 60 chars.
- Commit: `_commit()` (line 329):
  ```python
  def _commit(paths: list[str], msg: str) -> None:
      for p in paths:
          if Path(p).exists():
              subprocess.run(["git", "add", "--", p], capture_output=True)
      msg = commit_message("ai/commit-templates/plan", msg)
      subprocess.run(["git", "commit", "--no-verify", "--only", *paths, "-m", msg], capture_output=True)
  ```
  Message format: `f"ai: save plan {prefix}_{new_slug}"`, run through the same `commit_message()`/`base_ai_commit_subject()` styling.

**record-memory** — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/record-memory/hook.py`
- Events: `PostToolUse(Write|Edit)`, `PostToolUse(Bash|shell|unified_exec)` (to catch `rm` of memory files), and `SessionStart` (bulk catch-up sync).
- No NNN numbering — filenames are `<slug>.md` hardlinked from `~/.claude/projects/<encoded-path>/memory/<name>.md` into `ai[/°base]/memory/<name>.md` (`_memory_dirs()`, line 60; `_sync_file()`, line 73, hardlink-then-symlink-fallback).
- Commit: `_commit()` (line 245):
  ```python
  def _commit(dst_dir_rel: str, names: list[str]) -> None:
      if not names:
          return
      subprocess.run(["git", "add", "--", dst_dir_rel], capture_output=True)
      if len(names) == 1:
          msg = f"ai: record memory {Path(names[0]).stem}"
      else:
          head = ", ".join(Path(n).stem for n in names[:3])
          extra = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
          msg = f"ai: record memories {head}{extra}"
      msg = commit_message("ai/commit-templates/memory", msg)
      subprocess.run(["git", "commit", "--no-verify", "--only", dst_dir_rel, "-m", msg], capture_output=True)
  ```

**save-decision** (asked about implicitly under "memory records" but is really the AskUserQuestion hook) — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-decision/hook.py`. Event: `PostToolUse(AskUserQuestion|...)`. No file-per-item numbering; appends a rendered Q&A block to the same `ai/query.md` via `append_and_commit()`, commit message `f"ai: save decision {slug}"` (slug from the first question text).

### 3. `ai/°base/{plans,decisions,memory}` conventions

- `ai/°base/plans/` — file-per-plan, `NNN_slug.md`, created/maintained by `save-plan/hook.py` as above. Currently has ~46 entries (`001_...md` .. `046_...md`), with the noted `043` collision.
- `ai/°base/decisions/` — exists on disk (`/home/user/git/luckydonald/base/ai/°base/decisions/001_reverse_scope.json`, `002_reverse_scope.json`, dated 8 Jul) but **is not written to by any current hook** — `save-decision/hook.py` writes into `query.md`, not this directory. This looks like a legacy/experimental format (`NNN_slug.json`) that predates or was superseded by the current query.md-based decision log. Worth confirming with the user before assuming it's the pattern to reuse for the new hook.
- `ai/°base/memory/` — flat `<slug>.md` files plus an index file `MEMORY.md`, maintained by `record-memory/hook.py`. `_check_memory_index_consistency()` (line 217) warns (never auto-fixes) when `MEMORY.md`'s markdown links to `(name.md)` don't match what's on disk.
- Central routing logic for all of the above is `resolve_log_path()` / the `_is_inside_base_repo()` check in `_lib.py` (lines 34–46 of `°commit_style_lib/__init__.py`, reused via `_lib.py`): inside the `base` meta-repo itself, artifacts go to `ai/°base/...`; in a consuming repo, to `ai/...`. There's also an optional `by-issue/<KEY>/` sub-routing driven by an `ai[/°base]/.by-issue` file (`_read_by_issue()`).
- Documented in `/home/user/git/luckydonald/base/ai/°base/AGENTS.md` lines 94–106 (hook/output table) and 112–118 (commit format: `` [base] topic: ai: Run: Short summary. ``). No explicit prose about the NNN scheme beyond what's inferable from the table; no mention of `ai/°base/decisions/` at all in AGENTS.md (further evidence it's stale/unused by current hooks).

### 4. Existing `/compact` handling

All in `save-prompt/hook.py` (`UserPromptSubmit` only — **not** a `PreCompact` hook, which doesn't exist in this repo's config at all):
- `SKIP_PROMPTS` set includes the literal `"/compact"` (line 93) — a bare `/compact` invocation with no post-compaction summary is dropped entirely, never logged, never committed.
- `_handle_compact_prompt()` (line 807) fires only when the *next* `UserPromptSubmit` payload's prompt text starts with `/compact` **and** contains a `⎿` character — i.e., it's reacting to Claude's own rendered "conversation compacted, here's what got reloaded" summary that shows up as the harness-injected prompt after compaction finishes, not to the user's typed `/compact <custom prompt>` command itself. It parses `⎿ Read X (N lines)` / `⎿ Referenced file X` / etc. lines into an `autoloads.md` file under `ai/output/compact/NNN/`, commits that file directly, then appends a summary link line to `query.md` via `append_and_commit()`.
- Tests: `/home/user/git/luckydonald/base/scripts/°base/tests/test_ai_hooks_base_routing.py` lines 1659–1716 (`test_compact_prompt_writes_autoloads_file`, `test_compact_autoloads_skips_compacted_line`, `test_compact_sequential_numbering`) — all drive the hook via a synthetic `{"prompt": "/compact\n  ⎿  Compacted\n..."}` `UserPromptSubmit` payload, confirming there is no separate `PreCompact`-event code path or test anywhere.

**Implication for your new hook:** capturing the *invocation* of `/compact <custom prompt>` (the user's typed argument, before compaction runs) is a different moment than what `_handle_compact_prompt` reacts to (the post-compaction reload summary). Claude Code's harness does have a documented `PreCompact` hook event (fires before compaction starts, with the custom instructions in the payload) that this repo doesn't currently wire up at all — you'd be adding a genuinely new `hooks.PreCompact` entry to `ai/tool-settings/settings.json`, a new hook script (or extend `save-prompt`), and running `sync.py` to propagate it into `.claude/settings.json`. The existing `_handle_compact_prompt`/`output/compact/NNN/` machinery in `save-prompt/hook.py` is the closest existing analog for directory/numbering/commit conventions to mirror, but it currently only sees the *result* of compaction, not the argument that triggered it.