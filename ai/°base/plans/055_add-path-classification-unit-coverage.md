# Add path-classification unit coverage

## Summary

Extend the existing `IsAiBasePathTests` in `scripts/°base/tests/test_git_split_classify.py`; leave production code and unrelated dirty changes untouched.

## Key changes

- Add a table-driven test covering every AI top-level directory, including the currently untested `.agents` path, with both directory-root and nested-file forms.
- Retain/extend coverage for the three remaining classification routes: exact root files, a `°base` segment at any depth, and close-but-invalid names.
- Do not change the `is_ai_base_path(path: str) -> bool` interface or implementation.

## Test plan

- Run `uv run --project scripts/°base python -m unittest scripts.°base.tests.test_git_split_classify -v`.
- Confirm AI/base paths return `True` and ordinary or lookalike paths return `False`.

## Assumptions

- The requested tests target the existing path-classification contract, including `.agents`, which is already part of `AI_TOP_LEVEL_DIRS`.
