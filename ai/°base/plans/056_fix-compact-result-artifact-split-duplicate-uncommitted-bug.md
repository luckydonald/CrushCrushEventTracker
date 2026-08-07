# Fix compact-result artifact split / duplicate / uncommitted bug (error 23)

## Context

`ai/°base/errors/23.md` documents a real bug from `luckydonald/tunnel2tunnel`: one `/compact just the failing tests, I want you to fix those` produced **two** disconnected `query.md` blocks (`output/compact/008.<uuid>/result.md` and `.../009.<uuid>/result.md`, same `prompt_id`), plus a third, unrelated block linking the raw instruction text (`output/compacted/001.md`). `008`'s `result.md` was staged but never committed (silently failed `git commit`, likely index-lock contention between two hook processes firing near-simultaneously). `ai/°base/errors/23.expected.md` shows the target: **one** block, the instruction text quoted inline, and **one** directory holding both `analysis.md` (the reliable `PostCompact` payload text) and `result.md` (the transcript-reconstructed text), as two distinctly-named artifacts of the same compaction — not two competing "the same event" candidates.

Root causes (confirmed via code + a real `tunnel2tunnel` transcript):
1. `compact_result.reserve_artifact_directory()` (`compact_result.py:65-98`) only reuses a directory for a `prompt_id` when the new content is byte-identical to what's already there; a mismatch falls through to `next_compact_number()` and allocates a **new** directory/number instead of adding a second, distinctly-named artifact.
2. `save-compact-prompt/hook.py`'s `PreCompact`-manual path writes the typed `/compact <text>` to its own disconnected counter (`output/compacted/NNN.md`) with no link back to the eventual `output/compact/NNN.<uuid>/` directory.
3. No commit call site in this family (`_lib.py:append_and_commit`, and three more ad hoc `subprocess.run(["git","commit",...])` sites in `save-compact-prompt/hook.py`, `save-prompt/hook.py`'s `_handle_compact_prompt`, `record-memory/hook.py`'s `_commit`) checks the `git commit` return code — a lock-contention failure (two hook processes committing near-simultaneously, exactly what `PostCompact` + `SessionStart(source=compact)` do) is silently swallowed, leaving a file staged-but-uncommitted while `query.md` already links it.
4. Every artifact-writing call site always appends a **brand-new** `query.md` block — there is no "find the existing block for this compaction and add a link to it" path anywhere, so `capture_postcompact`, the `SessionStart` fallback, and `_handle_compact_prompt`'s `autoloads.md` each independently create their own block even when they share a `prompt_id`.
5. `compact_summary_from_transcript()` walks backward to an older completed boundary when the newest boundary has no summary yet. The live auto run therefore paired the new auto `prompt_id` with a prior manual summary, creating a mislabeled, stale `result.md` before the real PostCompact payload arrived.
6. Retrying a failed `git commit` alone cannot prevent logical interleaving: another hook may append and stage its query change between the first hook's append and commit, so the first `git commit --only` can commit both links while excluding the second artifact.

Confirmed scope for Claude **and** Codex: `.claude/settings.json` / `.codex/hooks.json` wire `PreCompact`, `PostCompact` (`matcher: "manual|auto"`), and `SessionStart` to the same hook scripts symmetrically for both tools — the fix must not assume Claude-only payload shape. `custom_instructions()` already checks 4 differently-named keys for this reason; keep that. Codex's `SessionStart` payload is unverified against the Claude-JSONL-shaped transcript parser (`compact_summary_from_transcript`) — that parser already fails soft (returns `None`/`False`) on anything that doesn't match, so no change needed there for Codex compatibility, it just naturally contributes nothing on tools where it can't parse a transcript.

"Non-prompt" usage = `trigger == "auto"` compaction (no user-typed instructions) and the legacy `SessionStart(source=compact)` fallback. `PreCompact` already hard-drops non-`manual` triggers before reaching `custom_instructions()` (`save-compact-prompt/hook.py:63-65`) — correct, keep it; `PostCompact` already handles both triggers. The fix must degrade cleanly to "no quoted instructions line" when there's nothing to quote.

## Pre-flight: 6 live repro cases (do this before finalizing design)

Reproduce and document (debug json copied to `ai/°base/output/debug/`, plus any new observations) before touching code — each may reveal payload-shape or ordering quirks the plan above doesn't yet cover:

- [x] Claude `/compact` (no args, i.e. `trigger: manual` with empty `custom_instructions` — this is *also* "non-prompt" usage, not just `trigger: auto`)
- [x] Claude `/compact <args>`
- [x] Codex `/compact` (no args)
- [x] Codex `/compact <args>` (client-side invocation unavailable from this conversation; limitation documented below)
- [x] Claude automatic compact (`trigger: auto`, context window auto-compact firing without explicit `/compact`) — triggered this session by running `/autocompact` (window set to 100k tokens) and continuing to write until Claude auto-compacts; capture `PreCompact`/`PostCompact`/`SessionStart` debug json same as the manual cases.
- [ ] Codex automatic compact (`trigger: auto`) — needs equivalent trigger in a Codex session (context window pressure); capture same debug json set.

For each: capture the `PreCompact`/`PostCompact`/`SessionStart` debug json, note actual field names/values (especially whether Codex populates `prompt_id`, and which `custom_instructions`-family key each tool uses), and check off only once documented here and any plan section above has been amended to match. Do not proceed to implementation until all 6 are checked (cases 1-4 already closed above; case 4 permanently accepted as unavailable — see below).

### Findings — Claude `/compact` no args (this repo, prompt_id `cd1cdae4-cc3d-4a14-b66f-f1e3fa628253`)

Debug json (untracked, gitignored, in `ai/°base/output/debug/`, still need force-add+commit at implementation time — not done now, plan-mode is read-only):
- `20260806-153341_090687-save-compact-prompt.json` — `PreCompact`, `trigger: manual`, `custom_instructions: null` (JSON `null`, not `""` or missing key — `custom_instructions()`'s `isinstance(value, str)` guard already handles this correctly, returns `""`, hook early-returns before writing anything). No `output/compacted/NNN.md`, no query.md link — correct, nothing to quote for a bare `/compact`.
- `20260806-153553_367346-save-compact-prompt.json` — `PostCompact`, same `prompt_id`, full `compact_summary` (34138 chars, `<analysis>`/`<summary>` "summary" shape). Written to `output/compact/001.cd1cdae4-.../result.md`, single commit `97aed6a`, single `query.md` block. **Bug did NOT reproduce here** — only one artifact/commit/block total.
- `20260806-153553_335865-record-memory.json` — `SessionStart`, `source: compact`, same `prompt_id`. Ran `capture_session_start` → `compact_summary_from_transcript()`, but produced no second artifact: its reconstructed text must have matched the already-written `result.md` byte-for-byte, so `reserve_artifact_directory`'s content-equality dedup correctly no-opped instead of splitting.

Conclusion: confirms the split bug is *content-source-dependent*, not deterministic on every bare `/compact` — it only manifests when `compact_summary_from_transcript()`'s reconstruction diverges from the `PostCompact` payload text (as it did in the original tunnel2tunnel case, "summary" 24091 chars vs "resume" 15941 chars). No plan-design change needed from this case; it's a clean confirmation of the no-args path's early-return behavior in `custom_instructions()`/`PreCompact`, and doesn't contradict §2's "always reuse directory" fix (which handles both the match and mismatch sub-cases uniformly).

### Findings — Claude `/compact <args>` (this repo, prompt_id `04a0b8f8-01fb-4bec-963a-1cdba9928746`, args: "and this is the example of something with a message now.")

**Bug reproduced cleanly** — no lock contention needed: the two capture paths split whenever they receive differing text for one `prompt_id`.

- `20260807-100323_345880-save-compact-prompt.json` — `PreCompact`, `trigger: manual`, `custom_instructions` populated with the typed text. Wrote `output/compacted/001.md` (raw text, no trailing newline, disconnected counter — not tied to `04a0b8f8` uuid) + `query.md` line `- [`/compact` possible prompt](./output/compacted/001.md)`, two separate commits (`589b610` prompt file, `3069d39` query link) — confirms root cause #2 as designed against.
- `20260807-100458_094663-record-memory.json` — `SessionStart`, `source: compact`, same `prompt_id`. Its transcript reconstruction is the plain resume-shape `output/compact/002.04a0b8f8-.../result.md` (19978 chars rendered; 20091 bytes), commit `b837cd5`, own `query.md` block.
- `20260807-100458_146134-save-compact-prompt.json` — `PostCompact`, same `prompt_id`, `compact_summary` 25528 chars (this compaction's tagged `<analysis>`/`<summary>` text). It produced **another new directory**, `003.04a0b8f8-.../result.md` (25709 bytes), commit `75b963a`, its own third `query.md` block. This confirms `reserve_artifact_directory`'s content-equality dedup falling through to `next_compact_number()` exactly as root cause #1 describes — both commits succeeded individually (no returncode-swallow needed), so **the split is not solely a lock-contention symptom: two different content blobs with one `prompt_id` are sufficient.**
- Net result: 3 disconnected `query.md` blocks for one `/compact <args>` invocation (`possible prompt` line + `002` block + `003` block), matching the original tunnel2tunnel shape almost exactly.

Conclusion: no Design change needed — this is the textbook case §2/§3/§4 already target. Confirms priority: §2 (always-reuse-directory) and §4 (upsert single query.md block) are the two fixes that matter most; the lock-contention retry in §1 is a secondary hardening, not the primary trigger.

### Findings — Codex `/compact` no args (this repo, session_id `019fdb75-51c0-7ef2-8b85-94b2fdd31a14`)

- `20260807-111231_592676-save-compact-prompt.json` — `PreCompact`, `trigger: manual`, with `session_id`, `turn_id`, and `transcript_path`, but no `prompt_id`, no `custom_instructions`-family key, and no user text. Correctly produces no instructions artifact.
- `20260807-111326_589211-save-compact-prompt.json` — `PostCompact`, same `session_id`/`turn_id` and `trigger`, but no `prompt_id` and no `compact_summary`. `capture_postcompact()` therefore returns `False`; no compact directory, query block, or commit is created.
- `20260807-111351_159322-record-memory.json` — `SessionStart`, `source: compact`, same `session_id` and transcript path, again with no `prompt_id`. The Codex transcript records the compaction as a `compacted` event whose summary is `encrypted_content`, not Claude's plaintext `compact_boundary` plus `isCompactSummary` schema. `compact_summary_from_transcript()` returns `None`, so the fallback also creates no artifact.

Conclusion: a Codex bare compact has no hook-visible plaintext result with the current event/transcript contract. Do **not** add a decoder or rely on the encrypted transcript blob. The implementation must use `session_id` as the stable directory correlation fallback when an artifact is available, but otherwise gracefully make no result/log entry; this is preferable to creating a misleading empty artifact. This changes the prior plan's Codex assumption and requires dedicated no-summary and session-id fallback tests.

### Codex `<args>` pre-flight invocation limitation

The bare no-argument form is a real Codex client compaction (`trigger: manual`),
but a literal `/compact <args>` sent through this conversation is delivered as a
normal `UserPromptSubmit` prompt. There is no enabled workspace tool or skill
that can invoke the client-side compaction command, and Codex's recorded
compaction summary is encrypted. The final live case must therefore be started
through the Codex client's own command/control surface; do not substitute a
synthetic payload for this required pre-flight observation.

**Accepted as final:** case 4 stays unresolved — no client-side surface in
either conversation can trigger it, and confirmed via `20260807-112501_867367-save-prompt.json`
(committed `1398c2a`) that a literal `/compact <args>` typed into Codex chat
just becomes a normal prompt, never a compaction event. Cases 5 and 6
(automatic `trigger: auto` compaction, Claude and Codex respectively) are now
in scope — pursue those before implementation; case 4 remains the only
permanently-unavailable one.

### Findings — Claude automatic compact (`trigger: auto`, this repo, prompt_id `3a286d24-2fee-4c23-8c4b-24cff3c19aeb`)

Triggered via `/autocompact` (window set to 100k) then continuing to write until Claude auto-compacted.

- `20260807-113932_249301-save-compact-prompt.json` — `PreCompact`, `trigger: auto`, `custom_instructions: null` (as expected — `auto` never has typed instructions). Correctly produces no instructions artifact.
- `20260807-114116_439198-save-compact-prompt.json` — `PostCompact`, same `prompt_id`, `compact_summary` 27532 chars. Wrote `output/compact/005.3a286d24-.../result.md`.
- `20260807-114116_416485-record-memory.json` — `SessionStart`, `source: compact`, same `prompt_id`, no `compact_summary` field. It ran before the current auto summary was in the transcript, then walked backward and selected a **prior manual** summary (17,028 chars). That stale content became `004.../result.md` and its query block was mislabeled `<kbd>manual</kbd>`.
- `20260807-114116_439198-save-compact-prompt.json` then supplied the actual auto `compact_summary` (27,532 chars), creating `005.../result.md` and its `<kbd>auto</kbd>` query block.
- `004...` was committed as `0735066`, but its transaction committed `query.md` after the competing writer had appended the `005` link. It therefore committed both links while excluding `005...`; `005/result.md` was left untracked. This proves a full write/commit transaction lock is required in addition to return-code retries.

Conclusion: automatic compaction exposes two additional requirements: do not use an older transcript summary when the newest boundary is incomplete, and serialize the complete artifact/query/commit transaction. The existing one-directory and deterministic-block design still applies, but a retry-only commit primitive is insufficient.

## Design

### 1. Centralize + harden the commit primitive (`_lib.py`)

Add `_commit_paths(paths: Sequence[Path | str], message: str, *, retries: int = 3) -> bool`:
- `git add -- <paths>`, then a normal verified `git commit --only <paths> -m <message>`.
- Check `returncode`; on failure where stderr indicates `index.lock`/lock contention, sleep briefly (e.g. `0.2s * attempt`) and retry up to `retries` times.
- Return `True`/`False`; never raise.

Wrap each compact-artifact operation in a repository-local advisory lock: reserve directory and metadata → write artifact → render/upsert query block → stage → commit. `_commit_paths` executes inside that lock, so retry handles transient git failures but cannot allow two writers to interleave their query edits. Route `append_and_commit` and the three ad hoc commit sites (`save-compact-prompt/hook.py`, `save-prompt/hook.py`, `record-memory/hook.py`) through the centralized primitive, removing duplicated unchecked `subprocess.run` pairs.

### 2. One directory per `prompt_id`, artifact identity by source, not by content-equality (`compact_result.py`)

- Change `reserve_artifact_directory` (or add a thin wrapper) so a matching correlation ID is **always** reused — use valid `prompt_id` when present, otherwise valid `session_id` (Codex's observed fallback). Drop the "fall through to a new number when content differs" branch entirely. Only skip the write when the *specific* target filename already holds byte-identical content (pure re-fire idempotency); otherwise overwrite that filename.
- Every `PreCompact`, including `trigger: auto`, reserves the directory and stores the canonical trigger in compact metadata. Manual instructions additionally write `instructions.md`. No query block is written at this stage. Later writers read the stored trigger; SessionStart must never infer or overwrite it.
- `capture_postcompact` always writes `analysis.md` (the direct `compact_summary` payload text). `capture_session_start` writes `result.md` only when the summary belongs to the newest compact boundary; if that boundary's summary is not yet available, it no-ops rather than selecting an earlier boundary. `result.md` is optional; `analysis.md` remains authoritative.
- This changes the semantics of `test_postcompact_deduplicates_same_result_but_keeps_distinct_same_prompt_results` and `test_postcompact_and_session_start_fallback_store_one_result` — update them to assert "same directory, two named files" (or one file when both sources genuinely produce identical text) instead of "second directory".

### 3. Fold the `/compact` instruction text into the same directory, drop `output/compacted/`

- `save-compact-prompt/hook.py`'s `PreCompact`-manual branch stops writing `output/compacted/NNN.md` / the "possible prompt" query.md line. Instead: add `compact_result.ensure_prompt_directory(log_path, payload) -> Path` (allocates/reuses the `NNN.<uuid>` directory for this `prompt_id`, same numbering as today, no artifact written yet), write the instruction text to `instructions.md` inside it, commit via `_commit_paths`. No `query.md` write at this point.
- Non-`manual` triggers keep the existing early-return (nothing to quote for `auto`).

### 4. Regenerate one deterministic block per compaction directory instead of appending fragments

- Add `render_compact_block(directory: Path, trigger: str) -> str`: reads `instructions.md` (if present) for the quoted line, then emits a link for each of `analysis.md`, `result.md`, `autoloads.md` found in the directory, in that fixed order — this fixes both the "two blocks" bug and the "arrival-order-dependent line ordering" issue (matches `analysis.md` before `result.md` in `23.expected.md`).
- Reword the `<kbd>{trigger}</kbd>` label in `compact_result.py:136` (currently the raw `trigger` value, `"manual"`/`"auto"`): map `manual` → `<kbd>manually</kbd>`, `auto` → `<kbd>automatic</kbd>`. `23.expected.md` already has the desired manual label; align code and tests to it.
- Add `upsert_query_block(log_path, anchor, block_text, *, extra_commit_paths, commit_template_relpath, default_commit_msg) -> bool` in `_lib.py`, with explicit start/end HTML comments keyed by the directory's relative path (for example `<!-- compact:start:output/compact/008.<uuid> -->` / `<!-- compact:end:... -->`). Replace only that bounded region, or append both markers and the new block. Commit `query.md` + every changed artifact/metadata file in one locked `_commit_paths` call.
- `capture_summary` (both sources) and `_handle_compact_prompt` (`autoloads.md`) switch from building ad hoc block strings + calling `append_and_commit` to: write their artifact file, call `render_compact_block` + `upsert_query_block` for that directory.

### 5. Tests (`scripts/°base/tests/test_ai_hooks_base_routing.py`)

- Update the two tests named in §2 for the new "same directory, named artifacts" semantics.
- Update `test_precompact_manual_with_instructions_writes_file` → expects `instructions.md` inside the `NNN.<uuid>` compact directory, no `output/compacted/` path, no immediate `query.md` change.
- New test: `PreCompact` (instructions) → `PostCompact` (same `prompt_id`) produces exactly one `❯ Conversation compacted` block containing the quoted instructions line + the `analysis.md` link.
- New test: a second capture for the same `prompt_id` (session-start fallback, or `autoloads.md` via a `/compact` prompt) appends its link into the *same* block rather than creating a second one.
- New test: simulate one failing `git commit` (lock contention) via monkeypatched `subprocess.run` and assert `_commit_paths` retries and succeeds.
- New auto-race test: a newest auto boundary without its own summary plus an older manual summary must create no stale `result.md` or manual-labeled block; a later PostCompact produces one `automatic` block with `analysis.md`.
- New concurrency test: coordinate SessionStart and PostCompact at the transaction boundary and assert one directory, one bounded query block, and no link to an uncommitted artifact.
- New Codex tests: (a) observed bare `/compact` PreCompact/PostCompact/SessionStart payloads with no plaintext summary produce no artifact or query entry, and (b) a synthetic Codex payload with a usable summary but no `prompt_id` reuses its `session_id` directory. Do not assert that Codex's encrypted transcript can be reconstructed.
- Retire/adjust any test asserting the old `output/compacted/NNN.md` + "possible prompt" line behavior.

## Verification

- Run `uv run --project scripts/°base python -m unittest ai.scripts.tests.test_ai_hooks_base_routing -v` after each change.
- Hand-replay the real scenario: feed the three copied debug payloads (`ai/°base/output/debug/20260805-153419_735201-save-compact-prompt.json`, `...-153559_283740-save-compact-prompt.json`, `...-153559_206417-record-memory.json`) through the updated hooks in a scratch git repo and diff the resulting `query.md` block against `ai/°base/errors/23.expected.md`.
