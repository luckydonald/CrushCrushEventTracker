## Investigation summary

### 1. What the test verifies (`scripts/°base/tests/test_git_split_e2e_deep_flow.py`)

`_run_deep_flow` (lines 48-88) builds one of 6 repo-preparation variants, then creates `ai/UNCLEAN/feature/test-eins` via `fixtures.checkout_variant_8_unclean_mixed_ai_code_both` (a mix of pure-code, pure-ai, and "both" commits — the return value is `unclean_manifest`), runs the real `get-base.py`/`sync-splits` tool against it, and asserts the resulting `feature/test-eins` (clean) and `ai/history/feature/test-eins` branches.

`known_base_merge_shas` = the set of commit SHAs in the manifest that represent a `base/base` merge done during fixture setup (line 51) — used only to confirm those merges are still ancestors of the resulting branch (line 97-101).

`_assert_clean_branch` (lines 90-129) checks, among other things:
- **7b (line 105-111):** for every commit reachable in `mane..feature/test-eins`, none of its changed paths should classify as `is_ai_base_path` — i.e. base/AI-owned content must never leak onto the clean feature branch.
- **7c/7d (113-125):** code-containing unclean commits map 1:1 onto feature/test-eins's own commits, and for "both" commits only the non-ai half should have landed.
- **line 127-129:** ai-only unclean commits should have **no counterpart at all** on `feature/test-eins`.

### 2. Where `ai/ckpt8_ai_0.md` comes from (`_git_split_e2e_fixtures.py`)

`_random_commits` (lines 183-210):
```python
elif ai:
    sha = make_commit(repo_root, f"ai/{prefix}_{i}.md", f"ai: {prefix} notes {i}")
```
`checkout_variant_8_unclean_mixed_ai_code_both` calls this with `prefix="ckpt8_ai", ai=True` (line 404):
```python
_random_commits(repo_root, manifest, 2, prefix="ckpt8_ai", ai=True)
```
So `ai/ckpt8_ai_0.md` is **deliberately** an ai-only commit (path under `ai/`, commit subject prefixed `ai:`) — it's meant to represent a base-owned, AI-only change that should be entirely excluded from the clean feature branch (per the `ai_only_sources` check on line 127-129).

### 3. `is_ai_base_path` implementation (`scripts/°base/git/°split_lib/classify.py:65-80`)

```python
def is_ai_base_path(path: str, *, ignore_file: Path | None = None) -> bool:
    path_parts = PurePosixPath(path)
    is_ai_path = False

    for current_ignore_file, relative_path in ai_ignore_files(path_parts, ignore_file):
        for rule in ai_ignore_rules(current_ignore_file):
            is_negation = rule.startswith("!")
            pattern = rule[1:] if is_negation else rule
            if path_matches_glob(relative_path, pattern):
                is_ai_path = not is_negation
    return is_ai_path
```
It walks `.ai-ignore` files (gitignore-style) and applies glob rules. This repo's actual `.ai-ignore` (root, and also present on the `base` branch fetched by the fixtures) contains:
```
# AI/base content separated into the history branch.
ai/**
...
```
So any path under `ai/` — including `ai/ckpt8_ai_0.md` — is base-owned by design.

### 4. Cross-check against `test_git_split_classify.py`

`test_git_split_classify.py:20-21` explicitly asserts this exact pattern is `True`:
```python
"ai/something.py": True,
"ai/query.md": True,
```
This is a plain `ai/<name>.<ext>` path (not `ai/°base/...`), same shape as `ai/ckpt8_ai_0.md`, and it's an accepted, intentional "should classify as ai_base" case.

### Conclusion

`classify.is_ai_base_path` is correct and consistent with its own dedicated test suite and with the `.ai-ignore` rule `ai/**`. The e2e test's expectation (no commit on `feature/test-eins` touches an ai-base path) is also the documented contract of `sync_splits.py`, which explicitly:
- skips ai-only commits entirely (`sync_splits.py:291-293`, `cls.is_ai_only_commit` → `continue`), and
- filters ai paths out of mixed "both" commits when building the clean tree (`sync_splits.py:299`, `keep=lambda p: not classify.is_ai_base_path(...)`).

So neither `classify.is_ai_base_path` nor the test's assertion is wrong — they agree with each other and with the fixture's intent (`ai/ckpt8_ai_0.md` is supposed to be filtered out). The failure the user is seeing (this path surviving onto `feature/test-eins`) points to a real behavioral bug in the split/sync pipeline (something causing an ai-only or "both" commit's ai half to leak through), not a classification or test-expectation problem.

One caveat worth flagging: I could not reproduce the exact reported failure locally (variants 1-3 passed for me; variants 4-6 failed instead, with a different assertion at line 117 — a commit-count mismatch, not an ai-path leak). The test's own docstring (`test_git_split_e2e_deep_flow.py:11-13`) notes it fetches `base/base` from "this repo's own real, currently committed `base` branch," so its outcome is sensitive to the current state of that branch — this is a plausible source of the discrepancy between environments/runs, and worth checking (e.g. via `git log base -- .ai-ignore` and recent `°split_lib` changes) before assuming a single universal root cause.