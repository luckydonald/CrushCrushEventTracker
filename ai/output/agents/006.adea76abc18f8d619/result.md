## Conclusion: Real bug — silent, deterministic classification failure (not flaky, not a fixture-randomness issue, not `base`-branch-content sensitivity)

**This is 100% deterministic, not intermittent.** I ran each variant 2-3 times in isolation:

```
variant 1: FAIL every time  — AssertionError: True is not false : commit <sha> on feature/test-eins
                               touches an ai/base path: ['ai/ckpt8_ai_0.md']
variant 2: FAIL every time  — same assertion, same failing path
variant 3: FAIL every time  — same assertion, same failing path
variant 4: OK every time
variant 5: OK every time
variant 6: OK every time
```

Command used (per project's `scripts/°base/tests/README.md`):
```
uv run --project scripts/°base python -m unittest scripts.°base.tests.test_git_split_e2e_deep_flow.DeepFlowTests.test_deep_flow_repo_variant_N -v
```

Repeat runs of variant 1 produced different commit SHAs but the exact same assertion failure and exact same path (`ai/ckpt8_ai_0.md`) — so what looked like "flakiness" across a test session is actually a fixed function of *which repo-preparation variant* runs, not randomness.

### Root cause

`classify.ai_ignore_path()` (`scripts/°base/git/°split_lib/classify.py:20-22`):

```python
def ai_ignore_path(repo_root: Path | None = None) -> Path:
    return (repo_root or Path.cwd()) / AI_IGNORE_FILENAME
```

and `ai_ignore_rules()` (`classify.py:25-32`):

```python
def ai_ignore_rules(ignore_file: Path | None = None) -> list[str]:
    path = ignore_file or ai_ignore_path()
    if not path.is_file():
        return []
    ...
```

`sync_branch()` in `scripts/°base/git/°split_lib/sync_splits.py:249` resolves this once per run:
```python
ignore_file = classify.ai_ignore_path(repo_root)
```
and passes it through to `classify.classify_commit(...)` for **every** replayed commit (lines 283-288, 333-338) and to `tree_ops.build_filtered_tree(..., keep=lambda p: not classify.is_ai_base_path(p, ignore_file=ignore_file))` (line 299).

This reads `.ai-ignore` **from the actual filesystem of `repo_root`'s current checkout**, not from the git tree of the source commit being classified, and with **no fallback/default and no error if the file is missing**. If `.ai-ignore` simply doesn't exist on disk at that moment, `ai_ignore_rules()` returns `[]`, so `is_ai_base_path()` (`classify.py:65-80`) never matches anything and always returns `False`, so `classify_commit()` (`classify.py:93-114`) reports `is_ai_only_commit=False` and `is_code_containing_commit=True` for literally every commit regardless of its actual paths. Consequently:
- `sync_splits.py:291` — `if cls.is_ai_only_commit: continue` — **never fires**, so ai-only commits are never skipped.
- `sync_splits.py:299`'s `keep=lambda p: not classify.is_ai_base_path(...)` **keeps every path**, so ai paths from "both"/mixed commits are never stripped.

The filtering silently degrades to a complete no-op — no exception, no warning — whenever the target repo's currently-checked-out tree lacks a `.ai-ignore` file.

### Why it's variant-dependent (and reproduced directly)

I verified by instrumenting the fixture builders directly (`scripts/°base/tests/_git_split_e2e_fixtures.py`):

```
1_random_commits            ai-ignore present on disk: False
2_empty_init_then_random    ai-ignore present on disk: False
3_readme_gitignore_conflict ai-ignore present on disk: False
4_based_on_real_base_tip    ai-ignore present on disk: True
5_empty_and_base_merge      ai-ignore present on disk: True
6_double_base_merge         ai-ignore present on disk: True
```

- Variants 1-3 build `mane` from scratch (`init_repo(..., branch="mane")`) or from the `empty/init` stand-in (`make_empty_init_remote`, `_git_split_e2e_fixtures.py:93-101` — a repo containing only `EMPTY.md`), and **never write a `.ai-ignore` anywhere** in `build_repo_variant_1/2/3_*` (`_git_split_e2e_fixtures.py:218-245`). So the fixture repo's working tree genuinely has no `.ai-ignore` file, ever.
- Variants 4-6 base `mane` on (or merge in) this real repo's actual `base/base` tip via `add_and_fetch_real_base_branch` (`_git_split_e2e_fixtures.py:130-140`), and this repo's real `base` branch *does* carry a top-level `.ai-ignore` with `ai/**` (confirmed via `git show base:.ai-ignore`). That file rides along into `mane`'s checked-out tree, so classification happens to work there by accident of fixture construction — not because `sync_splits.py`/`classify.py` are correct.

By contrast, `scripts/°base/tests/test_git_split_sync_splits.py:33-34` explicitly copies the real repo's `.ai-ignore` content into its own fixture (`(Path(__file__).resolve().parents[3] / ".ai-ignore").read_text(...)`) — which is exactly why that lower-level suite and the dedicated `classify` unit tests pass: they compensate for this gap themselves, masking the missing-default problem everywhere except the e2e deep-flow/smoke-matrix suites that build repos from a truly clean slate.

### Ruled out
- **No `random` module usage anywhere** — `_random_commits` in `_git_split_e2e_fixtures.py:183-210` is a misleading name; it's fully deterministic (`prefix_{i}` filenames/content by loop index), so there's no missing-seed issue.
- **No sets/dicts/threads/multiprocessing causing walk-order nondeterminism** in `sync_splits.py` — commit ordering comes from `git rev-list --first-parent` (`git_ops.rev_list_first_parent_reverse`), and all trailer/cursor bookkeeping uses ordinary dicts keyed by sha, iterated in insertion order only for `.get()` lookups, not iterated for ordering-sensitive logic.
- **No cross-variant shared state** — `setUp()` creates a fresh `tempfile.TemporaryDirectory()` per test (`test_git_split_e2e_deep_flow.py:40-46`), and each variant's failure/pass is 100% reproducible independent of run order or other variants.
- **Live `base`-branch content sensitivity** exists in a secondary, benign way (variants 4-6 do fetch `base/base` from the real repo and could theoretically shift if `base` gets rewritten mid-run), but that is not the deep bug here — in my 2-3x repeated runs, variants 4-6 passed consistently and did not reproduce the "commit-count mismatch at line ~117" the prior investigator saw; that's a distinct, much rarer real-fetch race that I could not reproduce and did not further pursue since the primary, always-reproducible bug fully explains the reported symptom (ai-only commit landing on the clean branch).

### Bottom line
Real bug, not flakiness: **`sync_splits.py:249` (and the `classify.ai_ignore_path`/`ai_ignore_rules` machinery it calls, `classify.py:20-32`) silently no-ops the AI/code split when `.ai-ignore` isn't present in the checked-out working tree**, instead of erroring, warning, or falling back to a built-in default rule set. `scripts/°base/tests/_git_split_e2e_fixtures.py`'s variants 1-3 expose this because they legitimately model a consumer repo that hasn't yet merged `base` (and thus has no `.ai-ignore`), which is exactly the state a first-time `bootstrap-branch`/`sync-splits` invocation could realistically be in.