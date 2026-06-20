# Strip Forwarded Codex Plan Prompts From Prompt Log

## Summary
Prevent Codex implementation-start prompts from being appended verbatim to `ai/°base/query.md` when they begin with the forwarded-plan boilerplate. Keep the actual plan capture behavior unchanged: `save-plan` should still extract and commit the plan file from the forwarded prompt when needed.

## Key Changes
- Add prompt normalization in `scripts/°base/ai/hooks/save-prompt/hook.py` before skip checks, task notification handling, and `append_and_commit`.
- Detect prompts starting with:
  `A previous agent produced the plan below to accomplish the user's task. Implement the plan in a fresh context. Treat the plan as the source of user intent, re-read files as needed, and carry the work through implementation and verification.`
- Strip that boilerplate plus the embedded forwarded plan content from prompt logging.
- If there is user-authored text after the forwarded plan, preserve and log only that remainder with the normal Codex `›` prefix.
- If stripping leaves no meaningful prompt text, exit without writing `query.md` or creating an `ai: updated prompt` commit.
- Do not change `scripts/°base/ai/hooks/save-plan/hook.py`; its query-log fallback remains responsible for saving the plan artifact.

## Tests
- Add `save-prompt` coverage in `scripts/°base/tests/test_ai_hooks_base_routing.py` for a Codex prompt containing only the forwarded-plan boilerplate and plan markdown; assert no query file is created and HEAD remains unchanged.
- Add coverage for a forwarded-plan prompt followed by a real user instruction; assert `query.md` contains only that instruction, prefixed with `›`.
- Keep existing `save-plan` forwarded-query fallback coverage unchanged to prove plan files are still captured.
- Run:
  `python3 -m unittest scripts/°base/tests/test_ai_hooks_base_routing.py -v`
  `python3 -m py_compile scripts/°base/ai/hooks/save-prompt/hook.py`

## Assumptions
- The strip rule is Codex-only in practice because this boilerplate is a Codex implementation prompt format.
- Existing committed duplicated prompt entries are not rewritten.
- Existing dirty files `ai/°base/decisions/001_reverse_scope.json` and `ai/°base/decisions/002_reverse_scope.json` are unrelated and must be left untouched.
