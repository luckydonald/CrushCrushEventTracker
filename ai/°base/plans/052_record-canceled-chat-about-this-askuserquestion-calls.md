# Record canceled ("chat about this") AskUserQuestion calls

## Context

`ai/°base/query.md` (or `ai/query.md` in consuming repos) is meant to be the full record of every question asked and every answer given. Today `scripts/°base/ai/hooks/save-decision/hook.py` only runs as a `PostToolUse` hook (matcher `AskUserQuestion|request_user_input|ask_user`), so it only fires when the user actually answers.

When the user instead picks "chat about this" (declines to answer and types a free-form message instead), Claude Code fires **no** `PostToolUse`, `PostToolUseFailure`, or `PermissionDenied` hook — confirmed experimentally in this session (asked a throwaway test question, canceled it, checked both `ai/°base/query.md` and `ai/°base/output/debug/*save-decision*.json`: neither gained an entry). Per `ai/references/https/code.claude.com/docs/en/hooks.md:1752` and `:1858-1860`: `PostToolUseFailure` explicitly excludes permission denials, and `PermissionDenied` only fires for *auto-mode* classifier denials, not manual dialog denials. The only hook that reliably fires for every `AskUserQuestion` call, answered or not, is `PreToolUse` (before the dialog is even shown).

So the question text and options that were asked are otherwise lost forever the moment the user cancels. The fix: capture them at `PreToolUse` time, and reconcile at the next point we know the outcome.

## Approach

Reuse the existing `save-decision/hook.py` script and its parsers (`_parse_claude`/`_parse_codex`/`_parse_copilot`) for all stages — one file, dispatched on `payload["hook_event_name"]`.

1. **`PreToolUse` (new wiring)** — same matcher `AskUserQuestion|request_user_input|ask_user`. On this event, `tool_input` is present but `tool_response` is not, which the existing parsers already handle gracefully (empty answers → every choice unselected — that's exactly the "asked, not yet answered" shape we want to persist). Serialize the parsed `Question` list + `tool` (claude/codex/copilot) + `tool_use_id` to a small JSON marker file under a new pending-state directory, keyed by `tool_use_id`.

2. **`PostToolUse` (existing stage, extended)** — before doing its current work, delete the pending marker matching this `tool_use_id` (it's now resolved with a real answer, nothing to reconcile). Behavior otherwise unchanged.

3. **Sweep (new)** — a function that lists any *remaining* marker files (i.e. ones whose `AskUserQuestion` was never answered because the user canceled), renders each via `_render_block(..., status="canceled")`, appends+commits them to `query.md`, and deletes the markers. Call this sweep at the very start of:
   - `save-prompt/hook.py` (already wired to `UserPromptSubmit`) — since picking "chat about this" always leads into the user typing a new prompt, this is the primary catch point, and ordering naturally puts the "canceled" block before the new prompt's own block.
   - `Stop` (already has hook entries for `save-plan` and `record-codex-memory`) — fallback for the rare case where the session ends right after a cancellation without another user prompt.

   Known limitation: if the session is killed/crashes between cancel and the next `UserPromptSubmit`/`Stop`, the marker is simply never swept (no worse than today, where the event is lost entirely).

### Pending-state directory

New gitignored directory, mirroring the existing `ai[/°base]/output/debug` base/consuming-repo split: `ai/°base/output/.pending-decisions/<tool_use_id>.json` (base repo) / `ai/output/.pending-decisions/<tool_use_id>.json` (consuming repo). Add both patterns to `.gitignore` next to the existing `**/ai/output/debug/` / `**/ai/°base/output/debug/` lines (around line 953-954).

### Rendering

Extend `_render_block(questions, *, tool="claude", status="answered")` in `save-decision/hook.py`:
- `status="answered"` (default): unchanged — `"{glyph} Question answered.\n"`.
- `status="canceled"`: first line becomes `"{glyph} Question canceled (chat about this).\n"`; the rest of the block (summary + details, all choices unchecked since nothing was selected) renders exactly as it does today for an unanswered/timed-out question — no other changes needed since the parsers already produce all-unselected `Choice` objects when there's no `tool_response`.

### Files to change

- `scripts/°base/ai/hooks/save-decision/hook.py` — dispatch on `hook_event_name`; add pending-marker write/delete/sweep functions; extend `_render_block` with `status`.
- `scripts/°base/ai/hooks/_lib.py` — if the marker read/write helpers are generic enough, they can live here instead (matches the file's existing role as shared hook helpers); otherwise keep them local to `save-decision/hook.py` since it's the only consumer besides the sweep call sites.
- `scripts/°base/ai/hooks/save-prompt/hook.py` — call the sweep function at the top of its `main()`, before recording the new prompt.
- `ai/tool-settings/settings.json` — add the new `PreToolUse` entry (matcher `AskUserQuestion|request_user_input|ask_user`, same command as the existing `PostToolUse` entry) so `sync.py` renders it into `.claude/settings.json` / Codex config. Add a `Stop` entry for the sweep call if not folding it into an existing `Stop` hook invocation of the same script.
- `.gitignore` — add the two new pending-decisions ignore patterns.
- `scripts/°base/ai/hooks/tests/` (wherever `save-decision` already has unit tests, e.g. the ones covering `_render_block`/render-format from plans 016-018/033) — add tests for: marker written on `PreToolUse`, marker deleted on matching `PostToolUse`, sweep renders + deletes leftover markers, canceled block format.

## Verification

1. Run the existing hook test suite: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` (confirm no regressions plus new tests pass).
2. `python3 scripts/°base/ai/settings/sync.py --check` to confirm the new `PreToolUse`/`Stop` wiring round-trips cleanly between `ai/tool-settings/settings.json` and `.claude/settings.json`/Codex config.
3. Manual end-to-end check in this same session: ask a throwaway `AskUserQuestion`, cancel it via "chat about this", confirm a pending marker briefly exists under `ai/°base/output/.pending-decisions/`, then send any follow-up prompt and confirm `ai/°base/query.md` gains a "Question canceled" block and the marker file is gone.
4. Ask another throwaway question and actually answer it, to confirm the normal answered-path still renders identically to before (no regression from the new `PreToolUse` marker write/delete).
