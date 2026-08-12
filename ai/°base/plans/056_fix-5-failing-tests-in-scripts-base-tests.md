# Fix 5 failing tests in scripts/°base/tests

## Context

Full suite run (626 tests) has 5 failures across 3 unrelated root causes. Each was root-caused by a dedicated investigation (code + git history), not just guessed from the assertion text. Two are one-line test/impl fixes; the third is a real, deterministic production bug in the ai/base commit-classification pipeline that the deep-flow e2e tests correctly caught.

## 1. `test_yarn_4_hook.Yarn4HookTests.test_no_node_files_is_silent` — fix implementation

`scripts/°base/git/hooks/commit/require_yarn_4.py`'s `policy_enabled()` (~line 88-105) prints two unconditional `debug: ...` lines to stderr (added in commit `4ca382e`, "made the yarn@4 check more verbose"), before the no-node-files short-circuit at line ~273-277. This breaks the hook's silent-no-op contract for repos with zero Node/JS files.

**Fix:** remove the two `print(f"debug: ...", file=sys.stderr)` calls at lines 93 and 95 (or move the diagnostic behind an explicit opt-in env var if the debugging value is worth keeping — default: just delete them, they're leftover troubleshooting output with no flag and no other test expects them).

## 2. `test_git_split_recovery.ResolveWatchedRefsTests.test_single_branch_includes_all_derived_refs` — fix test

`resolve_watched_refs()` (`scripts/°base/git/°split_lib/recovery.py:26-43`) correctly includes `sync_splits.forward_cursor_ref(base_branch, "clean")` and `..."history")` — added deliberately in commit `d2cb8ad` alongside the real forward-cursor replay/rollback logic in `sync_splits.py` and `cli.py`. That commit updated other test files but missed `test_git_split_recovery.py`, leaving its hardcoded expected list stale (missing the two `forward-cursor` refs the implementation has produced ever since).

**Fix:** update the expected list in `test_git_split_recovery.py` (~line 41-55) to append, after `'refs/base-split/unclean-cursor/history/feature'`:
```python
"refs/base-split/forward-cursor/clean/feature",
"refs/base-split/forward-cursor/history/feature",
```

## 3. `test_git_split_e2e_deep_flow.DeepFlowTests.test_deep_flow_repo_variant_{1,2,3}` — fix implementation (real bug) + fixtures

### Root cause

`classify.ai_ignore_path()`/`ai_ignore_rules()` (`scripts/°base/git/°split_lib/classify.py:20-32`) read `.ai-ignore` only from `repo_root/.ai-ignore` on disk, returning `[]` silently if the file doesn't exist — no error, no fallback. `sync_splits.sync_branch()` (`sync_splits.py:249`) resolves this once per run and uses it for every commit's classification (`is_ai_only_commit` skip at line 291, path filtering at line 299).

When the file is genuinely missing (variants 1-3 build a fresh `mane` trunk from scratch, with no `.ai-ignore` ever written — confirmed deterministic via repeated isolated runs, not flaky), `is_ai_base_path()` never matches anything, so ai-only commits are never skipped and ai paths are never stripped from mixed commits — they leak onto the clean branch. Variants 4-6 accidentally pass today only because they merge in this repo's real `base/base` tip, which happens to carry a `.ai-ignore`.

### Fix — fallback chain, not a hard requirement

Per user decision: don't just fail immediately when `.ai-ignore` is missing from the working tree. Try local sources first, warn on every fallback tier used, and only error if nothing works. In priority order:

1. `repo_root/.ai-ignore` on disk (current behavior, silent — this is the expected normal case).
2. `.ai-ignore` at `refs/remotes/base/base` (an already-fetched remote-tracking ref for a remote named `base`), via `git show`. Warn.
3. `.ai-ignore` at a local branch literally named `base` (relevant when working inside this repo itself), via `git show`. Warn.
4. Ensure a `base` remote exists pointing at `https://{username}@github.com/{username}/base.git` (default username `luckydonald`, mirroring `get-base.py`'s `REMOTE_NAME`/`remote_url()`, `get-base.py:49-85`), fetch it, then re-check `refs/remotes/base/base`. Warn loudly (this one hits the network).
5. Nothing found anywhere → raise a clear `MissingAiIgnoreError` explaining ai/base split cannot proceed safely without it.

### Implementation

- Add `git_ops.show_path_at_or_none(ref, path, cwd) -> bytes | None` in `scripts/°base/git/°split_lib/git_ops.py`: thin non-raising wrapper around the existing `show_path_at()` (`git_ops.py:376-384`), catching the "missing ref/path" `CalledProcessError` and returning `None`.
- Add to `classify.py`:
  - `class MissingAiIgnoreError(RuntimeError)`.
  - `resolve_ignore_file(repo_root: Path) -> Path`: implements the 5-tier chain above. Tiers 2-4 materialize their fetched content into a `tempfile.NamedTemporaryFile` and return that path (keeps `ai_ignore_rules()`'s existing `Path.is_file()`/`read_text()` contract unchanged — no signature changes needed downstream in `ai_ignore_files`, `is_ai_base_path`, `classify_commit`). Print one `warning: ...` line to stderr per fallback tier actually used, naming which source it fell back to.
  - Wrap with `functools.lru_cache` (keyed by `str(repo_root)`) so a single CLI invocation doesn't repeat git-show/network calls across its multiple call sites.
- Only the **root** `.ai-ignore` gets this treatment — nested per-directory `.ai-ignore` overrides (`ai_ignore_files()`'s walk up subdirectories) stay disk-only/optional, unchanged, since those are legitimately allowed to not exist.
- Swap the 4 call sites from `classify.ai_ignore_path(repo_root)` to `classify.resolve_ignore_file(repo_root)`: `sync_splits.py:249`, `cli.py:152`, `cli.py:174`, `cli.py:179`.

### Fixture fix (keep tests hermetic, no live network)

`_git_split_e2e_fixtures.py` already has exactly the machinery needed for tier 2, used today only by variants 4-6: `ensure_base_remote()` (adds remote `base` pointed at the real on-disk dev repo path, not a URL) + `git fetch base base` (`add_and_fetch_real_base_branch`, `_git_split_e2e_fixtures.py:117-140`), which lands content at `refs/remotes/base/base` — exactly tier 2's target ref.

Update `build_repo_variant_1_random_commits`, `build_repo_variant_2_empty_init_then_random`, and `build_repo_variant_3_readme_gitignore_conflict_setup` (`_git_split_e2e_fixtures.py:218-245`) to also call `ensure_base_remote` + `git fetch base base` (reusing the existing helper rather than merging `base/base` into `mane` — these variants should keep testing a repo whose `mane` trunk has no `.ai-ignore` of its own, only reachable via the fallback ref). This makes the fallback chain resolve at tier 2 in tests, matching realistic post-bootstrap state without any network call.

## Verification

```bash
uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v
```
Expect 0 failures, same skip count (2) as before. Also spot-check the fixed deep-flow variants individually and confirm the `MissingAiIgnoreError` path by temporarily pointing `resolve_ignore_file` at a repo with no `.ai-ignore`, no `base` remote, and no local `base` branch (or trust unit coverage if time-constrained — at minimum add/extend a `classify.py` unit test for the fallback chain and the error case).
