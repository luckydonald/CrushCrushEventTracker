# Strip Forwarded Codex Plan Prompts Using Saved Plan Match

## Summary
Prevent Codex implementation-start prompts from being appended verbatim to `ai/°base/query.md` when they contain the forwarded-plan boilerplate and repeat the plan that was just saved. Use the latest saved plan file as the primary strip boundary when it looks like a real plan.

## Key Changes
- Add prompt normalization in `scripts/°base/ai/hooks/save-prompt/hook.py` before skip checks, task notification handling, and `append_and_commit`.
- Detect Codex forwarded implementation prompts starting with:
  `A previous agent produced the plan below to accomplish the user's task. Implement the plan in a fresh context. Treat the plan as the source of user intent, re-read files as needed, and carry the work through implementation and verification.`
- Find the latest numbered plan file under the resolved plans directory, using the highest `NNN_*.md` prefix.
- Treat that latest plan file as matchable only when it has plan-like size and structure, defaulting to at least `1024` bytes and at least `8` line breaks.
- If the prompt contains that latest plan text after the boilerplate, strip the boilerplate plus exactly that plan block and preserve only any user-authored text after it.
- If the latest plan file is too small or does not match the prompt text, fall back to stripping from the first markdown heading after the boilerplate through the end only when there is no clear trailing user instruction.
- If stripping leaves no meaningful prompt text, exit without writing `query.md` or creating an `ai: updated prompt` commit.
- Do not change `scripts/°base/ai/hooks/save-plan/hook.py`; its query-log fallback remains responsible for saving the plan artifact.

## Tests
- Add `save-prompt` coverage for a Codex prompt containing only the forwarded boilerplate plus the latest saved plan text; assert no query file is created and HEAD remains unchanged.
- Add coverage for a forwarded prompt followed by a real user instruction after the matched saved plan; assert `query.md` contains only that instruction, prefixed with `›`.
- Add coverage where the newest plan file is tiny and plan-like matching is rejected; assert the hook does not strip based on that tiny file.
- Keep existing `save-plan` forwarded-query fallback coverage unchanged to prove plan files are still captured.
- Run:
  `python3 -m unittest scripts/°base/tests/test_ai_hooks_base_routing.py -v`
  `python3 -m py_compile scripts/°base/ai/hooks/save-prompt/hook.py`

## Assumptions
- “Last plan file” means the highest numbered `NNN_*.md` file in the resolved `ai[/°base]/plans` directory, not filesystem mtime.
- The conservative plan-like threshold is `>= 1024` bytes and `>= 8` newline characters.
- Existing committed duplicated prompt entries are not rewritten.
- Existing dirty files `ai/°base/decisions/001_reverse_scope.json` and `ai/°base/decisions/002_reverse_scope.json` are unrelated and must be left untouched.
