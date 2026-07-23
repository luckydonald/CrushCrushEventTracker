# Scope pending-decision markers/sweeps by session, to survive concurrent Claude instances

## Context

The previous plan (already implemented, commits `24bcb1e`..`ef8027f` etc.) added a pending-marker mechanism in `scripts/°base/ai/hooks/_lib.py` (`write_pending_decision`/`delete_pending_decision`/`sweep_pending_decisions`) so a canceled ("chat about this") `AskUserQuestion` still gets recorded to `query.md`. Markers live at `ai[/°base]/output/.pending-decisions/<tool_use_id>.md` and are keyed by `tool_use_id` — globally unique per tool call, so two sessions never collide on *which* marker belongs to which question.

But **`sweep_pending_decisions()` currently sweeps every marker in the directory, regardless of which session created it** (`scripts/°base/ai/hooks/_lib.py`'s `sweep_pending_decisions`, called from `save-decision/hook.py`'s `Stop` branch). When two Claude Code instances share the same working directory (two terminals/panes `cd`'d into the same repo checkout — not worktree-isolated, where each worktree has its own `ai/output` tree and this problem can't occur), this creates exactly the race the user asked about:

- Session A asks a question (`PreToolUse` writes `toolu_A.md`).
- Session B asks a question (`PreToolUse` writes `toolu_B.md`).
- Session B answers first (`PostToolUse` deletes `toolu_B.md`) — fine, keyed correctly, no cross-contamination here.
- Session A's turn ends before A's question is answered (e.g. A is still waiting on the user) and **A's `Stop` hook fires** → today's `sweep_pending_decisions()` lists *the whole directory*, finds B's answer already gone but could just as easily catch **A's own still-outstanding marker is fine (that's correct — A's Stop reconciling A's own leftover is exactly the intended fallback) — the actual bug is the reverse ordering**: if B is still mid-question (hasn't answered yet) when **A's `Stop` fires first**, A's sweep would find and commit B's `toolu_B.md` as "canceled" even though B hasn't decided yet, since the sweep has no concept of "whose marker is this." B then answers normally moments later, and B's own `PostToolUse` still appends the real "answered" block (that logic never checked whether the marker existed) — leaving a spurious, contradictory "canceled" entry in `query.md` right next to the real answer.

So the concurrency bug is specifically: **a session's `Stop` can misclassify another still-live session's in-flight question as canceled.** The fix is to make the sweep session-aware.

## Approach

1. **Scope marker filenames by `session_id`.** `session_id` is a common field on every hook event (`PreToolUse`, `PostToolUse`, `Stop`) per `ai/references/https/code.claude.com/docs/en/hooks.md:605-611` and is already used the same way elsewhere in this codebase (e.g. `scripts/°base/ai/hooks/save-plan/hook.py:440`). Change the marker filename from `<tool_use_id>.md` to `<session_id>__<tool_use_id>.md` (session_id and tool_use_id are both harness-generated opaque tokens — safe to join with `__` directly for these hooks; no extra sanitization is warranted since real payloads never contain such tokens with filesystem-unsafe characters, matching how `slugify`/other hook helpers treat harness-provided IDs elsewhere in this file).
2. **`write_pending_decision(session_id, tool_use_id, rendered_block)`** and **`delete_pending_decision(session_id, tool_use_id)`** in `_lib.py` take the extra parameter and build the scoped filename. `save-decision/hook.py` passes `payload.get("session_id", "")` through at both call sites.
3. **`sweep_pending_decisions(session_id)`** only globs `f"{session_id}__*.md"` — a session's `Stop` reconciles *only its own* leftover markers, never another session's. This alone eliminates the cross-session false-positive.
4. **Orphan cleanup for crashed/killed sessions.** Scoping alone means a marker from a session that dies without ever calling `Stop` (crash, kill, forced-quit) is *never* swept by anyone — a real regression versus today's unscoped-but-buggy sweep, which would eventually (if imperfectly) clean up anyone's leftovers. Fix: `sweep_pending_decisions(session_id)` also does a second pass over *all* markers (any session) whose file `mtime` is older than a staleness threshold (e.g. 30 minutes — comfortably longer than the single request/response round-trip a live in-flight question takes, so a live session's own marker is never touched by another session's stale-sweep) and sweeps those too, regardless of session, labeling them distinctly (e.g. `"Question canceled (chat about this, stale)"` — reuse `_render_block`'s existing `status` parameter with one more variant, or just note staleness in the rendered text) so it's clear in `query.md` that this was an orphan-cleanup, not a same-session cancellation.
5. No change needed to the answered path's correctness: `PostToolUse` already renders from `tool_response` directly (not from the marker), so answering out of order across sessions (`B answers, then A answers`) was never at risk — only the cancellation-sweep needed scoping.

## Files to change

- `scripts/°base/ai/hooks/_lib.py` — thread `session_id` through `write_pending_decision`/`delete_pending_decision`/`sweep_pending_decisions`; add the mtime-based stale-orphan pass to the sweep.
- `scripts/°base/ai/hooks/save-decision/hook.py` — pass `payload.get("session_id", "")` at the `PreToolUse` write, `PostToolUse` delete, and `Stop` sweep call sites.
- `scripts/°base/tests/test_save_decision_pending.py` (already exists from the prior change) — add tests for: two distinct `session_id`s each get their own marker file; session A's `Stop` sweep does not touch session B's still-fresh marker; a marker older than the staleness threshold gets swept by a *different* session's `Stop` and is labeled as stale/orphaned.

## Verification

1. Re-run the targeted test module: `uv run --project scripts/°base python -m unittest scripts.°base.tests.test_save_decision_pending -v`.
2. Full suite: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` (expect the same pre-existing unrelated `test_git_split_recovery` failure, nothing new).
3. `python3 scripts/°base/ai/settings/sync.py --check` (no hook wiring changes in this plan, so this should already be clean — just confirming no drift).
4. Manual repro of the original race, if practical: simulate two sessions by invoking `save-decision/hook.py` directly (as the tests do) with two different `session_id`s — one `PreToolUse` per session, then one session's `Stop` — and confirm only that session's own marker gets swept, the other session's marker survives untouched.
