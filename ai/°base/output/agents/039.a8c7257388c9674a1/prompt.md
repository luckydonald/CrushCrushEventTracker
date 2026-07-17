Repo: /home/user/git/luckydonald/base ("base" — a meta-repo providing shared AI-agent tooling/hooks that other luckydonald/* repos consume).

Goal: design a new hook that captures a `/compact <custom prompt>` command's custom instructions (the argument text a user types after `/compact`) and saves it to a new file, distinct from the EXISTING `_handle_compact_prompt()` machinery in `scripts/°base/ai/hooks/save-prompt/hook.py` (line ~807), which reacts to the *post-compaction reload summary* (a UserPromptSubmit payload starting with `/compact` and containing `⎿`), not to the user's original custom-instructions argument.

Context already gathered (trust this, don't re-derive):
- Hooks are declared tool-neutrally in `ai/tool-settings/settings.json` under a `hooks` object keyed by event name (`PermissionRequest`, `SessionStart`, `PostToolUse`, `Stop`, `UserPromptSubmit`) and propagated to `.claude/settings.json`, `.codex/hooks.json`/`.codex/rules/generated.rules`/`.codex/config.toml`, and `.github/hooks/generated.json` via `python3 scripts/°base/ai/settings/sync.py`.
- Hook implementations live one-per-directory under `scripts/°base/ai/hooks/<name>/hook.py`, e.g. `save-prompt/`, `save-plan/`, `save-decision/`, `record-memory/`. Shared helpers in `scripts/°base/ai/hooks/_lib.py` and `°commit_style_lib/__init__.py` (`resolve_log_path()`, `slugify()`, `commit_message()`/`base_ai_commit_subject()`, `append_and_commit()`).
- `resolve_log_path("ai/query.md", "ai/°base/query.md")` picks the right root: inside the `base` repo itself → `ai/°base/...`; in a consuming repo → `ai/...`.
- NNN-numbering patterns already used elsewhere (copy this style — zero-padded 3 digits, scan dir for existing numbers, max+1):
  ```python
  def _next_prefix(plans_dir: Path) -> str:
      highest = 0
      for entry in plans_dir.glob("[0-9]*_*.md"):
          m = re.match(r"^(\d+)_", entry.name)
          if m:
              highest = max(highest, int(m.group(1)))
      return f"{highest + 1:03d}"
  ```
  and the existing compact-autoloads numbering in `save-prompt/hook.py` line ~819:
  ```python
  compact_dir = log_path.parent / "output" / "compact"
  if not compact_dir.exists():
      num = 1
  else:
      nums = [int(m.group(1)) for d in compact_dir.iterdir() if d.is_dir() and (m := re.match(r"^(\d+)$", d.name))]
      num = max(nums, default=0) + 1
  dir_name = f"{num:03d}"
  ```
- Commit pattern used everywhere: `git add -- <path>` then `git commit --no-verify --only <path> -m <styled message>`, message text run through `commit_message("ai/commit-templates/<kind>", default_msg)` → `base_ai_commit_subject()` (prepends `[base] ` / issue-key prefix).
- The user wants the new artifact at (their literal phrasing, with a typo — "ouput" should read "output"): `ai/°base/output/compacted/NNN.md` inside the base repo (and presumably `ai/output/compacted/NNN.md` in a consuming repo, mirroring `resolve_log_path`), linked from `query.md` as a markdown link with label `` `/compact` possible prompt `` — i.e. `` - [`/compact` possible prompt](./output/compacted/NNN.md) ``. This directory name (`compacted`, flat `NNN.md` files) is intentionally distinct from the existing `output/compact/NNN/` autoloads directory (which holds a different kind of artifact — reload summaries, plural files per numbered dir).
- Trigger event should be Claude Code's `PreCompact` hook (fires before compaction begins; NOT currently wired anywhere in this repo — grepped and confirmed absent from `ai/tool-settings/settings.json`, `.claude/settings.json`, `.codex/*`, `.github/hooks/*`, and all of `scripts/°base`). Per Claude Code's hook docs, the PreCompact payload includes a `trigger` field (`"manual"` vs `"auto"`) and a custom-instructions field carrying the user's `/compact <text>` argument (confirm exact field name from Claude Code's official hooks documentation — don't guess if uncertain, note it as an open question). Only manual invocations with non-empty custom instructions should be recorded — bare `/compact` (no argument) or auto-compaction should NOT create a file.
- Other repos in the `luckydonald/` org (e.g. `hoass_plugin-template`) consume this `base` repo's hook tooling via the sync/get-base mechanism — so this hook must work correctly there too (writing to `ai/output/compacted/NNN.md`, not `ai/°base/...`, when run outside the `base` repo itself).

Your task:
1. Read `scripts/°base/ai/hooks/save-prompt/hook.py` in full (it's large — read enough to see the imports, `main()`, `_handle_compact_prompt()`, and how `append_and_commit()` / `resolve_log_path()` / debug-dump helpers are used) to nail the exact reusable helper signatures.
2. Read `scripts/°base/ai/hooks/_lib.py` and `scripts/°base/ai/hooks/°commit_style_lib/__init__.py` for `resolve_log_path`, `append_and_commit`, `commit_message`, `base_ai_commit_subject`, `slugify`, and whatever debug-dump helper writes those `ai/°base/output/debug/*.json` files (mentioned in prior exploration but not yet located precisely — find it).
3. Read `scripts/°base/ai/settings/sync.py` to determine: is `PreCompact` already a recognized/supported hook-event key in whatever event→tool mapping table it uses? If not, what do I need to add there to support it (for Claude Code at minimum; note if Codex/Copilot CLI don't support a PreCompact-equivalent event at all — that's fine, this can be Claude-Code-only for now)?
4. Confirm (from whatever official Claude Code hook documentation/reference is available to you, e.g. via WebFetch/WebSearch if needed) the exact JSON shape of a `PreCompact` hook's stdin payload — specifically the field name holding the user's custom compact instructions, and the field distinguishing manual vs auto triggers. If you cannot access external docs, say so explicitly rather than guessing, and propose defensively reading multiple plausible field names.
5. Look at one or two existing hook tests (e.g. `scripts/°base/tests/test_ai_hooks_base_routing.py` around the compact-autoload tests, lines ~1659–1716) to understand the test harness pattern (how a synthetic hook payload is constructed and fed in, how `resolve_log_path`/repo-root fixtures work) so the plan can specify how to test the new hook the same way.
6. Design the new hook: file layout (`scripts/°base/ai/hooks/save-compact-prompt/hook.py` or better name if you find one more consistent with existing naming — e.g. compare against `save-prompt`, `save-decision`, `save-plan`, `record-memory` naming conventions and pick the best fit), its `main()` logic (parse payload → bail out if no custom instructions or if it's an auto-trigger → compute NNN via `output/compacted/` dir scan → write `NNN.md` with the raw custom-instructions text → append a link line to `query.md` via `append_and_commit()` → commit the new file separately, mirroring the two-commit pattern in `_handle_compact_prompt()` lines ~840-845), the settings wiring changes needed in `ai/tool-settings/settings.json` (new `PreCompact` hook entry, same invocation style: `python3 "$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/<name>/hook.py" 'claude'`, `"async": true`), any `sync.py` changes needed, and a new/extended test file mirroring the existing compact-autoload tests.

Report back a concrete, ready-to-execute design: exact file paths, function skeletons (not necessarily full code, but real signatures and key logic), the settings.json diff, and the test plan. Flag any open questions (especially the exact PreCompact payload field names) that need user confirmation before implementation. Keep the report tight — this feeds directly into a plan-mode plan file, not a fully-implemented PR.