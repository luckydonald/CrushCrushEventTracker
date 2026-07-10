You are designing an implementation plan for a large addition to the repo at /Users/user/Documents/programming/Python/base. Do NOT write any code — only research (read files) and produce a detailed plan as your final answer. This is going into a plan file that a human will review before implementation begins.

## Background you need

This repo ("base") is a reusable git base that other repos adopt via checkout/rebase/merge. It ships a tool `scripts/°base/git/split.py` (thin shim -> `°split_lib.cli.main`) that keeps three branch variants in sync for any feature branch:
- clean: `{branch}` — no AI/base content, safe to publish
- unclean: `ai/UNCLEAN/{branch}` — free mix of code + AI/base commits (the real working branch)
- history: `ai/history/{branch}` — AI/base-only leftovers

Plus a repo-wide `ai/history/{main}` ("history-master") that replays merged branches' AI history and periodically folds an upstream `base/base` remote (a separate template repo — this same repo, fetched as a remote named literally `base`, branch `base`).

Modules under `scripts/°base/git/°split_lib/`: `cli.py` (argparse dispatch for `check-push`, `sync-splits`, `update-history-master`, `rebase-branches-to-master`, `bootstrap-branch`), `branches.py` (branch naming/classification, `detect_main_branch()` which falls back through `main`/`master`/`mane` local branches), `classify.py` (AI-vs-code path classification: top-level dirs `ai`, `.claude`, `.codex`; exact paths `.mcp.json`, `AGENTS.md`, `CLAUDE.md`; any path segment `°base`), `git_ops.py` (subprocess plumbing), `history_master.py` (keeps `ai/history/{main}` in sync + folds `base/base`), `rebase_to_master.py`, `sync_splits.py` (forward: unclean -> clean+history), `sync_unclean.py` (reverse: clean+history -> unclean), `trailers.py` (`git interpret-trailers` wrapper), `bootstrap.py`, `recovery.py`, `push_checks.py`.

Trailers used: `X-Base-Split-Source` (original UNCLEAN commit sha), `X-Base-Split-Kind` (code/history/mixed), `X-Base-Split-Counterpart-Tree`, `X-Base-Unclean-Reconstructed-From`, `X-Base-History-Merge-Kind` (="base-merge"), `X-Base-History-Merge-Sha`, `X-Base-History-Merge-Replayed-From`, `X-Base-Split-Clean-Branch`, `X-Base-Split-Merge-Marker-For`.

Standalone bootstrap launcher `scripts/°base/git/get-base.py` (stdlib-only, meant to be run via `curl -fSL <github-raw-url> | python3 - [subcommand ...]`): adds a `base` remote (never overwrites an existing one — `ensure_base_remote()` checks first), fetches `base base`, creates a detached worktree at `<repo_root>/.git/base-tools` checked out at `base/base`'s tip (`ensure_worktree()`), then `delegate()` execs `<worktree>/scripts/°base/git/split.py --repo-root <repo_root> <argv>` (replacing the process via `os.execvp`). With no argv, `auto_argv()` inspects the current branch and picks: on main branch -> `update-history-master --yes`; on a clean feature branch -> `bootstrap-branch <name>` (running `update-history-master --yes` first if `ai/history/{main}` doesn't exist); on UNCLEAN/history branch -> `sync-splits <name> --direction=to-clean-history`.

Existing test conventions (scripts/°base/tests/): plain `unittest`, real temp git repos via `tempfile.TemporaryDirectory()` + `subprocess` git calls (NO gitpython/pytest), a shared helper module `tests/_git_test_helpers.py` with `git(args, cwd) -> str`, `make_commit(cwd, filename, message, content=None) -> sha`, `init_repo(cwd, *, branch="master")`. Each `test_git_split_*.py` defines its own small `*TestBase(unittest.TestCase)` with setUp/tearDown (no shared GitTestCase exists yet). Tests run via `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`.

`git_ops.py` key functions you can rely on: `rev_parse(ref,cwd)->sha|None`, `rev_list_reverse(range_expr,cwd)`, `is_ancestor(a,b,cwd)->bool`, `merge_base(a,b,cwd)->sha|None`, `commit_message(sha,cwd)->str` (%B format), `subject_for_commit`, `changed_paths_for_commit(sha,cwd)->list[str]`, `show_path_at(sha,path,cwd)->bytes`, `create_branch(ref,at_sha,cwd)`, `move_ref(ref,new_sha,old_sha,cwd)`, `checkout_branch(ref,cwd)`, `merge_no_commit`, `merge_abort`, `cherry_pick`/`cherry_pick_continue`/`cherry_pick_abort`, `tree_for_commit`, `commit_tree(...)`.

`history_master.py`'s `_fold_base(base_sha, onto, cwd)` (lines ~404-433) currently: checks if unrelated histories (passes `--allow-unrelated-histories` if so), runs `git merge --no-commit --no-ff base_sha`, and on ANY conflict raises `MergeConflict` for manual resolution — UNLIKE `recreate_base_merge()` (lines ~341-388, used when RE-folding an already-resolved base-merge after a rebase) which auto-resolves every conflicted path by reusing the original merge commit's already-resolved blob for that exact path (`git_ops.show_path_at(old_merge_sha, path, cwd)`).

## The decision already made (do not re-litigate)

We are adding a NEW feature to `_fold_base()`: when a first-time (non-recreation) base/base fold conflicts specifically on the paths `README.md` and/or `.gitignore` (top-level, exact match), auto-resolve those two paths by taking `base_sha`'s version (`git_ops.show_path_at(base_sha, path, cwd)`), `git add` them, and only raise `MergeConflict` if OTHER paths remain conflicted after that (leaving the two auto-resolved paths already staged so the user only deals with genuine conflicts). This mirrors `recreate_base_merge`'s per-path blob-reuse mechanism but sources content from `base_sha` (the incoming tip) instead of a prior resolved merge. Rationale: `ai/history/{main}` is a bookkeeping/AI-content branch (never the real `{main}` branch — that invariant is already tested elsewhere), so on first fold it's fine and expected for base's own README.md/.gitignore to win over whatever the consuming repo already had there.

## The test to write (this is the big part)

The user wants a comprehensive end-to-end test suite for `split.py`/`get-base.py`, structured as:

**Repo-preparation variants** (each is a separate temp repo, main branch renamed to `mane`):
1. A few random commits.
2. Starting from `empty/init`'s initial commit (a local stand-in remote for `https://github.com/EmptyAAS/empty.git` — must be hermetic/offline, so build a tiny local one-commit repo to serve as the `empty` remote rather than hitting GitHub), then random commits.
3. A few commits, then commit a `README.md` and `.gitignore` (short content) — specifically to set up a first-fold conflict scenario for the new auto-resolve feature.
4. Starting from a branch based on the current tip of THIS repo's own `base` branch (add a `base` remote pointing at this actual repo's absolute path on disk — resolved via `git -C <this-test-file's-repo> rev-parse --show-toplevel` — and `git fetch base base`; never hit GitHub), then a few random commits.
5. Random commits + `empty/init` merge (`--allow-unrelated-histories`) + `base/base` merge (`--no-ff`) + random commits — mirrors README.md's documented "Setup: c) Merge base/base" recipe.
6. Like #5, but merge `base/base` a SECOND time into `mane` (`--no-ff`), then a few more commits including some touching `ai/**` paths (using the same commit-mix pattern as branch-checkout variant 2.8 below).

Each repo variant's commits must be tracked in a structured manifest list build up as commits are made:
```python
{
    "commit": "<hash>",
    "merge": None | {"branch": "empty/init"|"base/base", "commit_theirs": "<hash>", "commit_ours": "<hash>", "is_allowed_merge": bool},
    "code": bool,   # touches non-AI paths
    "ai": bool,     # touches ai/** or similar (per classify.is_ai_base_path)
    "msg": "...",   # subject+body up to trailers
    "trailer": "...",  # raw trailer block
}
```
`is_allowed_merge=True` means the merge was done as test-fixture preparation (plain git merge commands), not by running split.py itself.

**Branch-checkout variants** (applied on top of a prepared repo, i.e. checked out from `mane`):
1. Stay on `mane`.
2. `mane` + a couple more commits.
3. New branch `feature/foobar` + a couple random commits.
4. New branch `test_idk_lol` + a couple random commits.
5. New branch `ai/UNCLEAN/feature/batz` + a couple code-only commits.
6. Same branch name + a couple ai-folder-only commits.
7. Same branch name + a couple commits that each touch BOTH code and ai paths in the same commit ("both" commits).
8. Same branch name + a mix: a couple ai-only, a couple code-only, a couple "both" commits, in that ai/code/both order.
9. New branch `ai/history/mane` + 2 ai-only commits, then the same pattern as variant 2.8 (this is the special case where the *history-master* branch itself gets extra local commits before the tool is run — relevant to steps 9-11 below).

**Applying the tool** ("fake curl", confirmed approach): from the temp repo, run `cat <this-repo>/scripts/°base/git/get-base.py | python3 -  [args]` (feed via stdin exactly like the documented curl one-liner — no real network, no real curl/HTTP server) — with the temp repo's `base` remote PRE-ADDED to point at this actual repo's path (`ensure_base_remote()` never overwrites an existing remote, so pre-adding one pointed locally is how GitHub is avoided). Confirmed scope decision: run the full 6×9 = 54 (repo-variant × branch-variant) combinations as a lightweight smoke matrix (assert: the tool runs without unhandled crashes, any merges/folds it performs internally complete without leaving an unresolved conflict / without needing --continue, i.e. "merges cleanly"). Separately, run a deeper flow (steps 5-11 below) once for EACH of the 6 repo variants (not combined with the 9 branch variants).

**Deep flow** (run once per repo variant, on top of that prepared `mane`):
5. Create branch `ai/UNCLEAN/feature/test-eins`, with commits following the SAME pattern as branch-checkout variant 2.8 (ai-only commits, then code-only commits, then "both" commits mixing code+ai in a single commit) — record each commit in the manifest.
6. Run the tool (fake curl) to generate `feature/test-eins` from it (this is `sync-splits feature/test-eins --direction=to-clean-history`, likely via auto mode since the branch is `ai/UNCLEAN/feature/test-eins`).
7. Assert `feature/test-eins` exists and:
   a. Contains no `base/base` merge beyond what was already in `mane` before this branch was created: repo variants 1-3 should have NONE; variant 4/5 should have exactly the ONE merge already in `mane`; variant 6 should have exactly the TWO merges already in `mane` (never a NEW merge introduced by the split tool itself).
   b. Contains no commit touching `ai/**` or equivalent AI paths.
   c. Contains only the code and "both" commits from step 5's `ai/UNCLEAN/feature/test-eins`.
   d. For "both" commits, the corresponding commit on `feature/test-eins` contains ONLY the code half of the diff (no AI paths).
8. Assert `ai/history/feature/test-eins` exists and:
   a. Contains ALL commits from step 5's `ai/UNCLEAN/feature/test-eins`, in the same order, with the same commit metadata (author/committer/date/message) EXCEPT trailers — verify via the `X-Base-Split-Source` trailer on each history commit pointing back to the correct original `ai/UNCLEAN/feature/test-eins` commit sha, and that no extra commits were introduced in between.
   b. None of these commits contain "code" changes: ai-only commits map unchanged (still ai-only), "both" commits map to ai-only (code half stripped), pure-code commits map to EMPTY commits (no changes at all, just the marker/trailer).
9. Commit 2 more commits to `mane`.
10. Run the tool to rebase the branches (`rebase-branches-to-master` — likely via fake-curl auto mode again, or explicit subcommand — check `cli.py`'s exact argv shape and decide which is appropriate given the branch checked out).
11. Assert `ai/UNCLEAN/feature/test-eins` and `ai/history/feature/test-eins` are now based on (rebased onto) the new `mane` tip — EXCEPT for repo variant/branch-checkout-2.9's scenario, where instead `ai/history/mane` itself should be rebased onto the new `mane`, and `ai/UNCLEAN/feature/test-eins`/`ai/history/feature/test-eins` should be based on THAT updated `ai/history/mane` (per `rebase_to_master.py`'s documented dependency chain: unclean depends on history's rebased tip, and history-master is handled by `update_history_master`, not `rebase_to_master`).

## Your task

Read whatever additional source you need (in particular: `cli.py` for exact subcommand argv shapes and the `--repo-root` flag; `branches.py` for `classify_branch`/`history_fork_point_ref`/`detect_main_branch`; `sync_splits.py` and `bootstrap.py` for exact function signatures if the plan should call them directly instead of only through the CLI; `trailers.py` for `read_trailers`/`read_trailer_value`/`write_trailers` exact signatures; `rebase_to_master.py` for `rebase_branches_to_master`'s exact behavior/return value; the existing `tests/test_git_split_history_master.py`, `tests/test_git_split_sync_splits.py`, `tests/test_git_split_bootstrap.py`, `tests/test_git_split_rebase_to_master.py` in full for patterns to reuse, especially how they build a fake `base` remote and assert trailers/ancestry).

Then produce a concrete, file-by-file implementation plan covering:

1. The exact code change to `history_master.py` (new constant name, exact diff-level description of the `_fold_base` change, and where a new test method should go in `tests/test_git_split_history_master.py` mirroring `test_first_base_fold_allows_unrelated_histories`).

2. A new shared fixture module (propose exact path, e.g. `tests/_git_split_e2e_fixtures.py`) exposing: functions to build each of the 6 repo variants, functions to apply each of the 9 branch-checkout variants, a function to build the "empty" local stand-in remote, a function to resolve THIS repo's real path + fetch its `base` branch, a `run_fake_curl(repo_root, *args) -> subprocess.CompletedProcess` helper, a commit-manifest recorder function matching the dict schema above (using `git_ops.changed_paths_for_commit` + `classify.classify_commit` + `trailers.read_trailers` to split message/trailers), and any dataclass/TypedDict you think clarifies the manifest entries. Give exact function signatures.

3. The new test file(s) (propose exact paths/names) implementing the 54-combo smoke matrix (using `subTest`) and the 6 deep-flow tests, with concrete descriptions of each assertion block (referencing the specific git_ops/branches/trailers functions to use) — detailed enough that whoever implements this doesn't have to re-derive the git plumbing.

4. Call out any real risks/edge cases you find while reading the code that the plan should explicitly address (e.g., whether `sync-splits`'s auto-discovery would also try to process `ai/UNCLEAN/feature/batz` from branch-checkout variants 2.5-2.8 when the fake-curl call targets a different branch; whether get-base.py's `os.execvp` process-replacement works cleanly when invoked via `subprocess.run(["python3","-"], input=...)`; whether cloning/fetching THIS live repo's `base` branch mid-development is a stability concern and how to mitigate it, e.g. by fetching a pinned known-good commit instead of always "most recent tip" if that matters for determinism).

Be concrete and reference file:line where possible. Do not write or edit any code. Your final answer should be the full plan text, organized under clear headings, ready to be adapted into a plan file.