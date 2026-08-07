# Fix compact-result artifact split / duplicate / uncommitted bug (error 23)

## Context

`ai/°base/errors/23.md` documents a real bug from `luckydonald/tunnel2tunnel`: one `/compact just the failing tests, I want you to fix those` produced **two** disconnected `query.md` blocks (`output/compact/008.<uuid>/result.md` and `.../009.<uuid>/result.md`, same `prompt_id`), plus a third, unrelated block linking the raw instruction text (`output/compacted/001.md`). `008`'s `result.md` was staged but never committed (silently failed `git commit`, likely index-lock contention between two hook processes firing near-simultaneously). `ai/°base/errors/23.expected.md` shows the target: **one** block, the instruction text quoted inline, and **one** directory holding both `analysis.md` (the reliable `PostCompact` payload text) and `result.md` (the transcript-reconstructed text), as two distinctly-named artifacts of the same compaction — not two competing "the same event" candidates.

Root causes (confirmed via code + a real `tunnel2tunnel` transcript):
1. `compact_result.reserve_artifact_directory()` (`compact_result.py:65-98`) only reuses a directory for a `prompt_id` when the new content is byte-identical to what's already there; a mismatch falls through to `next_compact_number()` and allocates a **new** directory/number instead of adding a second, distinctly-named artifact.
2. `save-compact-prompt/hook.py`'s `PreCompact`-manual path writes the typed `/compact <text>` to its own disconnected counter (`output/compacted/NNN.md`) with no link back to the eventual `output/compact/NNN.<uuid>/` directory.
3. No commit call site in this family (`_lib.py:append_and_commit`, and three more ad hoc `subprocess.run(["git","commit",...])` sites in `save-compact-prompt/hook.py`, `save-prompt/hook.py`'s `_handle_compact_prompt`, `record-memory/hook.py`'s `_commit`) checks the `git commit` return code — a lock-contention failure (two hook processes committing near-simultaneously, exactly what `PostCompact` + `SessionStart(source=compact)` do) is silently swallowed, leaving a file staged-but-uncommitted while `query.md` already links it.
4. Every artifact-writing call site always appends a **brand-new** `query.md` block — there is no "find the existing block for this compaction and add a link to it" path anywhere, so `capture_postcompact`, the `SessionStart` fallback, and `_handle_compact_prompt`'s `autoloads.md` each independently create their own block even when they share a `prompt_id`.

Confirmed scope for Claude **and** Codex: `.claude/settings.json` / `.codex/hooks.json` wire `PreCompact`, `PostCompact` (`matcher: "manual|auto"`), and `SessionStart` to the same hook scripts symmetrically for both tools — the fix must not assume Claude-only payload shape. `custom_instructions()` already checks 4 differently-named keys for this reason; keep that. Codex's `SessionStart` payload is unverified against the Claude-JSONL-shaped transcript parser (`compact_summary_from_transcript`) — that parser already fails soft (returns `None`/`False`) on anything that doesn't match, so no change needed there for Codex compatibility, it just naturally contributes nothing on tools where it can't parse a transcript.

"Non-prompt" usage = `trigger == "auto"` compaction (no user-typed instructions) and the legacy `SessionStart(source=compact)` fallback. `PreCompact` already hard-drops non-`manual` triggers before reaching `custom_instructions()` (`save-compact-prompt/hook.py:63-65`) — correct, keep it; `PostCompact` already handles both triggers. The fix must degrade cleanly to "no quoted instructions line" when there's nothing to quote.

## Pre-flight: 4 live repro cases (do this before finalizing design)

Reproduce and document (debug json copied to `ai/°base/output/debug/`, plus any new observations) before touching code — each may reveal payload-shape or ordering quirks the plan above doesn't yet cover:

- [x] Claude `/compact` (no args, i.e. `trigger: manual` with empty `custom_instructions` — this is *also* "non-prompt" usage, not just `trigger: auto`)
- [x] Claude `/compact <args>`
- [ ] Codex `/compact` (no args)
- [ ] Codex `/compact <args>`

For each: capture the `PreCompact`/`PostCompact`/`SessionStart` debug json, note actual field names/values (especially whether Codex populates `prompt_id`, and which `custom_instructions`-family key each tool uses), and check off only once documented here and any plan section above has been amended to match. Do not proceed to implementation until all 4 are checked.

### Findings — Claude `/compact` no args (this repo, prompt_id `cd1cdae4-cc3d-4a14-b66f-f1e3fa628253`)

Debug json (untracked, gitignored, in `ai/°base/output/debug/`, still need force-add+commit at implementation time — not done now, plan-mode is read-only):
- `20260806-153341_090687-save-compact-prompt.json` — `PreCompact`, `trigger: manual`, `custom_instructions: null` (JSON `null`, not `""` or missing key — `custom_instructions()`'s `isinstance(value, str)` guard already handles this correctly, returns `""`, hook early-returns before writing anything). No `output/compacted/NNN.md`, no query.md link — correct, nothing to quote for a bare `/compact`.
- `20260806-153553_367346-save-compact-prompt.json` — `PostCompact`, same `prompt_id`, full `compact_summary` (34138 chars, `<analysis>`/`<summary>` "summary" shape). Written to `output/compact/001.cd1cdae4-.../result.md`, single commit `97aed6a`, single `query.md` block. **Bug did NOT reproduce here** — only one artifact/commit/block total.
- `20260806-153553_335865-record-memory.json` — `SessionStart`, `source: compact`, same `prompt_id`. Ran `capture_session_start` → `compact_summary_from_transcript()`, but produced no second artifact: its reconstructed text must have matched the already-written `result.md` byte-for-byte, so `reserve_artifact_directory`'s content-equality dedup correctly no-opped instead of splitting.

Conclusion: confirms the split bug is *content-source-dependent*, not deterministic on every bare `/compact` — it only manifests when `compact_summary_from_transcript()`'s reconstruction diverges from the `PostCompact` payload text (as it did in the original tunnel2tunnel case, "summary" 24091 chars vs "resume" 15941 chars). No plan-design change needed from this case; it's a clean confirmation of the no-args path's early-return behavior in `custom_instructions()`/`PreCompact`, and doesn't contradict §2's "always reuse directory" fix (which handles both the match and mismatch sub-cases uniformly).

### Findings — Claude `/compact <args>` (this repo, prompt_id `04a0b8f8-01fb-4bec-963a-1cdba9928746`, args: "and this is the example of something with a message now.")

**Bug reproduced cleanly** — no lock contention needed, split happens deterministically whenever `PostCompact` fires twice for one `prompt_id` with differing content:

- `20260807-100323_345880-save-compact-prompt.json` — `PreCompact`, `trigger: manual`, `custom_instructions` populated with the typed text. Wrote `output/compacted/001.md` (raw text, no trailing newline, disconnected counter — not tied to `04a0b8f8` uuid) + `query.md` line `- [`/compact` possible prompt](./output/compacted/001.md)`, two separate commits (`589b610` prompt file, `3069d39` query link) — confirms root cause #2 as designed against.
- `20260807-100458_146134-save-compact-prompt.json` — `PostCompact`, same `prompt_id`, `compact_summary` 25528 chars (this very compaction's `<analysis>`/`<summary>` text). Written to new dir `002.04a0b8f8-.../result.md` (20091 bytes), commit `b837cd5`, own `query.md` block.
- A second `SessionStart`(`source: compact`)-driven capture for the *same* `prompt_id` produced **another new directory** `003.04a0b8f8-.../result.md` (25709 bytes, different content than `002`), commit `75b963a`, its own third `query.md` block. Confirms `reserve_artifact_directory`'s content-equality dedup falling through to `next_compact_number()` exactly as root cause #1 describes — this time both commits succeeded individually (no returncode-swallow needed to produce the bug), so **the split is not solely a lock-contention symptom — it reproduces even when every commit succeeds**, purely from "two different content blobs, same `prompt_id`, dedup requires byte-identity."
- Net result: 3 disconnected `query.md` blocks for one `/compact <args>` invocation (`possible prompt` line + `002` block + `003` block), matching the original tunnel2tunnel shape almost exactly.

Conclusion: no Design change needed — this is the textbook case §2/§3/§4 already target. Confirms priority: §2 (always-reuse-directory) and §4 (upsert single query.md block) are the two fixes that matter most; the lock-contention retry in §1 is a secondary hardening, not the primary trigger.

## Design

### 1. Centralize + harden the commit primitive (`_lib.py`)

Add `_commit_paths(paths: Sequence[Path | str], message: str, *, retries: int = 3) -> bool`:
- `git add -- <paths>`, then `git commit --no-verify --only <paths> -m <message>`.
- Check `returncode`; on failure where stderr indicates `index.lock`/lock contention, sleep briefly (e.g. `0.2s * attempt`) and retry up to `retries` times.
- Return `True`/`False`; never raise.

Rewrite `append_and_commit` to build its content/log-file changes, then call `_commit_paths` for the actual git step, and return the bool. Route the three other ad hoc commit sites (`save-compact-prompt/hook.py`'s manual-instructions-file commit, `save-prompt/hook.py`'s `_handle_compact_prompt` autoloads commit, `record-memory/hook.py`'s `_commit`) through `_commit_paths` too, removing their duplicated `subprocess.run` pairs.

### 2. One directory per `prompt_id`, artifact identity by source, not by content-equality (`compact_result.py`)

- Change `reserve_artifact_directory` (or add a thin wrapper) so a matching `prompt_id` directory is **always** reused — drop the "fall through to a new number when content differs" branch entirely. Only skip the write when the *specific* target filename already holds byte-identical content (pure re-fire idempotency); otherwise overwrite that filename.
- `capture_postcompact` always writes `analysis.md` (the direct `compact_summary` payload text). `capture_session_start` always writes `result.md` (the transcript-reconstructed text). Fixed names by source, not by arrival order.
- This changes the semantics of `test_postcompact_deduplicates_same_result_but_keeps_distinct_same_prompt_results` and `test_postcompact_and_session_start_fallback_store_one_result` — update them to assert "same directory, two named files" (or one file when both sources genuinely produce identical text) instead of "second directory".

### 3. Fold the `/compact` instruction text into the same directory, drop `output/compacted/`

- `save-compact-prompt/hook.py`'s `PreCompact`-manual branch stops writing `output/compacted/NNN.md` / the "possible prompt" query.md line. Instead: add `compact_result.ensure_prompt_directory(log_path, payload) -> Path` (allocates/reuses the `NNN.<uuid>` directory for this `prompt_id`, same numbering as today, no artifact written yet), write the instruction text to `instructions.md` inside it, commit via `_commit_paths`. No `query.md` write at this point.
- Non-`manual` triggers keep the existing early-return (nothing to quote for `auto`).

### 4. Regenerate one deterministic block per compaction directory instead of appending fragments

- Add `render_compact_block(directory: Path, trigger: str) -> str`: reads `instructions.md` (if present) for the quoted line, then emits a link for each of `analysis.md`, `result.md`, `autoloads.md` found in the directory, in that fixed order — this fixes both the "two blocks" bug and the "arrival-order-dependent line ordering" issue (matches `analysis.md` before `result.md` in `23.expected.md`).
- Add `upsert_query_block(log_path, anchor, block_text, *, extra_commit_paths, commit_template_relpath, default_commit_msg) -> bool` in `_lib.py`: anchor is an HTML comment keyed by the directory's relative path (e.g. `<!-- compact:output/compact/008.<uuid> -->`). If found in `query.md`, replace the anchor-through-next-blank-line span in place; else append a new block with the anchor. Commits `query.md` + `extra_commit_paths` in one `_commit_paths` call (atomic — fixes root cause #3's dangling-reference failure mode: file and its link always land in the same commit or neither does).
- `capture_summary` (both sources) and `_handle_compact_prompt` (`autoloads.md`) switch from building ad hoc block strings + calling `append_and_commit` to: write their artifact file, call `render_compact_block` + `upsert_query_block` for that directory.

### 5. Tests (`scripts/°base/tests/test_ai_hooks_base_routing.py`)

- Update the two tests named in §2 for the new "same directory, named artifacts" semantics.
- Update `test_precompact_manual_with_instructions_writes_file` → expects `instructions.md` inside the `NNN.<uuid>` compact directory, no `output/compacted/` path, no immediate `query.md` change.
- New test: `PreCompact` (instructions) → `PostCompact` (same `prompt_id`) produces exactly one `❯ Conversation compacted` block containing the quoted instructions line + the `analysis.md` link.
- New test: a second capture for the same `prompt_id` (session-start fallback, or `autoloads.md` via a `/compact` prompt) appends its link into the *same* block rather than creating a second one.
- New test: simulate one failing `git commit` (lock contention) via monkeypatched `subprocess.run` and assert `_commit_paths` retries and succeeds.
- New test: run at least the `PreCompact`→`PostCompact` happy path with `run_hook(..., "codex")` to close the existing Codex-coverage gap.
- Retire/adjust any test asserting the old `output/compacted/NNN.md` + "possible prompt" line behavior.

## Verification

- Run `uv run --project scripts/°base python -m unittest ai.scripts.tests.test_ai_hooks_base_routing -v` after each change.
- Hand-replay the real scenario: feed the three copied debug payloads (`ai/°base/output/debug/20260805-153419_735201-save-compact-prompt.json`, `...-153559_283740-save-compact-prompt.json`, `...-153559_206417-record-memory.json`) through the updated hooks in a scratch git repo and diff the resulting `query.md` block against `ai/°base/errors/23.expected.md`.
