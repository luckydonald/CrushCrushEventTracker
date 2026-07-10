# Deep Dive: The `°split_lib` Git Branch-Split Tool

## 0. Where everything lives

```
scripts/°base/git/split.py                        <- thin CLI shim (delegates to °split_lib.cli.main)
scripts/°base/git/get-base.py                      <- standalone "curl bootstrap" launcher (stdlib-only)
scripts/°base/git/°split_lib/
  cli.py             argparse + recovery-wrapped dispatch
  bootstrap.py       Phase-3 "start from a clean-only branch" glue
  branches.py        naming/classification (clean/unclean/history), main-branch detection
  classify.py        AI-vs-code path/commit classification
  git_ops.py         all subprocess/git plumbing (frozen, test-friendly)
  history_master.py  (C) part 1: keep ai/history/{main} in sync with {main} and base/base
  identity.py        shared bot committer identity
  push_checks.py      pure push-policy logic (name+content rules)
  rebase_to_master.py (C) part 2: rebase clean/history/unclean onto current masters
  recovery.py         crash-safe ref snapshot/undo logging (.rebase-recovery.tmp)
  sync_splits.py      (A) forward direction: UNCLEAN -> clean + history
  sync_unclean.py     (B) reverse direction: clean+history -> UNCLEAN reconstruction
  trailers.py         git-trailer read/write via `git interpret-trailers`
  tree_ops.py         scratch-index tree-splitting/merging plumbing
scripts/°base/tests/test_git_split_*.py            <- unit test suite (11 files)
README.md ("Branch splitting (clean/unclean/history)" section, lines 289-307)
ai/°base/todo.md (lines 59-163)                     <- original design spec/prompt
```

---

## 1. Overall purpose

Confirmed exactly as described in the prompt. Per `ai/°base/todo.md:59-163` (the original design spec) and the module docstrings, this tool keeps three parallel variants of a feature branch in sync:

| format | branch name | content policy |
|---|---|---|
| clean | `{branch}` (any name) | never AI/base content — safe to publish (`push_checks.py:33-39`) |
| unclean | `ai/UNCLEAN/{branch}` | free mix of code + AI/base commits — the actual working branch |
| history | `ai/history/{branch}` | AI/base-only leftovers, kept even if the corresponding code is empty (`push_checks.py:40-46`) |

There's also a repo-wide `ai/history/{main}` (e.g. `ai/history/master`/`ai/history/mane`) that accumulates all history-branches' AI content once their clean counterpart merges into `{main}`, plus periodic folds of an upstream `base/base` template repo (`history_master.py`).

- **sync-splits (A, `sync_splits.py`)**: unclean → clean + history (forward replay, filtered trees).
- **sync-splits --direction=to-unclean (B, `sync_unclean.py`)**: clean + history → unclean (reconstruction/merge-back).
- **update-history-master (C1, `history_master.py`)**: keeps `ai/history/{main}` rebased onto `{main}`, replays merged branches' history, and folds `base/base`.
- **rebase-branches-to-master (C2, `rebase_to_master.py`)**: rebases one branch's clean/history/unclean trio onto their respective updated masters.
- **bootstrap-branch (Phase 3, `bootstrap.py`)**: starts the whole workflow for a branch that currently only exists as `{branch}` (clean).
- **check-push (`push_checks.py` + `cli.py:110-142`)**: a pre-receive/pre-push style hook enforcing the naming/content policy.

---

## 2. CLI entry points (`cli.py`)

Entrypoint: `scripts/°base/git/split.py` → `°split_lib.cli.main` (`split.py:10`). Top-level flag: `--repo-root PATH` (defaults to the repo containing cwd, `cli.py:267-274`), letting the tool run against a target repo from elsewhere (used heavily by `get-base.py`'s worktree trick).

Subcommands (`cli.py:276-375`):

1. **`check-push --remote-name NAME --remote-url URL`** (`cli.py:277-281`) — reads `local_ref local_sha remote_ref remote_sha` lines from stdin (git's pre-push hook protocol), classifies each ref, computes new commits vs remote, classifies them, and calls `push_checks.evaluate_ref_update`. Prints violations to stderr and returns 1 if any (`cli.py:110-142`).
2. **`sync-splits [branch] [--direction={to-clean-history,to-unclean}] [--dry-run] [--force] [--allow-diverge-rewrite]`** (`cli.py:283-292`) — `branch` optional; if omitted, iterates `sync_splits_lib.discover_unclean_branches()` (all `ai/UNCLEAN/*`). `to-clean-history` calls `sync_splits.sync_branch`; `to-unclean` calls `sync_unclean.reconstruct_unclean`.
3. **`update-history-master [--force-merge BRANCH ...] [--pull-master] [--pull-base] [--yes] [--continue] [--abort] [--dry-run]`** (`cli.py:294-301`) — drives `history_master.update_history_master`; on conflict prints a formatted `_CONFLICT_NEXT_STEPS` block (`cli.py:182-235`) pointing at `--continue`/`--abort`/manual rollback via `.rebase-recovery.tmp`.
4. **`rebase-branches-to-master [branch] [--yes] [--dry-run]`** (`cli.py:303-308`) — calls `rebase_to_master.rebase_branches_to_master` per target branch (all discovered unclean branches if omitted).
5. **`bootstrap-branch BRANCH [--dry-run]`** (`cli.py:310-315`) — calls `bootstrap.bootstrap_branch`.

Every mutating command (all except `check-push`) is wrapped by `_run_with_recovery` (`cli.py:54-96`), which snapshots every ref the invocation could touch (via `recovery.resolve_watched_refs`) before running, logs an undo table to `.rebase-recovery.tmp`, and logs an after-summary. A dedicated logger (`_build_logger`, `cli.py:25-51`) sends INFO+ to stdout and full DEBUG detail (every git command, ref snapshots) to `.rebase-recovery.tmp`.

### "Fake curl" bootstrap mechanism — `get-base.py`

`scripts/°base/git/get-base.py` (not inside `°split_lib`, deliberately stdlib-only/no imports from `°split_lib` per its docstring lines 1-29) is exactly this. Its docstring states the intended real invocation:

```
curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/git/get-base.py | python3 - bootstrap-branch feature
```

and also documents running it locally once a copy exists on disk:

```
python3 scripts/°base/git/get-base.py update-history-master --yes
```

(`get-base.py:10-16`). README.md documents the same at lines 293-307.

**How it works** (mirrors "as if downloaded via curl" but locally):
1. `find_repo_root()` (`get-base.py:53-57`) — `git rev-parse --show-toplevel` from cwd.
2. `ensure_base_remote(repo_root, username)` (`get-base.py:64-71`) — adds remote literally named `base` pointing at `https://{username}@github.com/{username}/base.git` (env `BASE_GIT_USERNAME`, default `luckydonald`) if missing; never overwrites an existing one.
3. `fetch_base(repo_root)` (`get-base.py:74-76`).
4. `ensure_worktree(repo_root)` (`get-base.py:90-102`) — creates/refreshes a **detached worktree at `.git/base-tools`** checked out at `base/base`'s tip. This is the key trick that lets the code run "as if downloaded" without ever touching the caller's checked-out branch/working tree.
5. If invoked with no args, `auto_argv()` (`get-base.py:131-180`) inspects the *current* branch of the *original* repo (not the worktree) via `°split_lib.branches` (imported dynamically from the worktree's copy, `get-base.py:145-147`) and picks a sensible default: on `{main}` → `update-history-master --yes`; on a clean feature branch → `bootstrap-branch <name>` (auto-running `update-history-master --yes` first if `ai/history/{main}` doesn't exist yet); on UNCLEAN/history branches → `sync-splits <name> --direction=to-clean-history`.
6. `delegate()` (`get-base.py:110-113`) execs `sys.executable <worktree>/scripts/°base/git/split.py --repo-root <repo_root> <argv...>` — i.e. it runs the *real* `split.py` sitting inside the `base/base`-checked-out worktree, but pointed with `--repo-root` at the *original* repo.

**To invoke it against a local checkout instead of GitHub**: since the remote it adds is a real git remote URL, you can point `BASE_GIT_USERNAME`/manually pre-add a `base` remote at a local path (e.g. `git remote add base /path/to/local/base/checkout` before running), or simply run `python3 scripts/°base/git/get-base.py ...` directly from a local clone that already has the `base` remote configured — the script itself doesn't care whether `base`'s URL is local or remote, it just does `git fetch base base` and worktree-checks-out `base/base`.

---

## 3. Branch naming conventions (`branches.py`)

Regexes (`branches.py:15-16`):
```python
UNCLEAN_RE = re.compile(r"^ai/UNCLEAN/(.+)$")
HISTORY_RE = re.compile(r"^ai/history/(.+)$")
```
- `unclean_name(base)` → `f"ai/UNCLEAN/{base}"` (`branches.py:65-66`)
- `history_name(base)` → `f"ai/history/{base}"` (`branches.py:69-70`)
- Anything not matching either is `BranchFormat.CLEAN` with `base_name == name` (`branches.py:43-62`).
- `is_history_master` is `True` iff the history branch's base name equals the detected main branch (`branches.py:59`) — e.g. `ai/history/master`, `ai/history/mane`, `ai/history/main`, whatever main is.
- Fork-point tracking ref: `refs/base-split/history-master-fork-point/{branch}` (`branches.py:18-22`, `FORK_POINT_REF_TEMPLATE`).

**`mane` is not hardcoded** as a magic name anywhere in the split logic itself. It only appears as one of three **fallback candidates** in `detect_main_branch()` (`branches.py:83-108`):
```python
try:
    # refs/remotes/origin/HEAD -> strip "origin/" prefix
except CalledProcessError: pass
for candidate in ("main", "master", "mane"):
    if refs/heads/{candidate} exists: return candidate
return "master"
```
So detection order is: (1) `origin/HEAD` symbolic ref if resolvable, else (2) whichever of `main`/`master`/`mane` exists as a local branch (checked in that order), else (3) hardcoded default `"master"`. Every other module (`sync_splits`, `sync_unclean`, `history_master`, `rebase_to_master`, `bootstrap`) receives `main_branch` as a parameter computed once by `branches.detect_main_branch()` in `cli.py` — there's no special-casing of the literal string `"mane"` beyond this fallback list. `README.md:108` and `todo.md:71` are what motivate `mane` as a common self-adopted main-branch name (a pony-themed rename of `main`), but the code treats it generically as "whatever the current main branch is called."

`empty/init` (from `README.md:5,90-97,167,204,213`) is purely a **remote/ref name convention documented in README.md for initial repo re-rooting** (`git fetch empty init` / `git rebase --root --onto empty/init`) — it is not referenced anywhere in `°split_lib` code; it's a one-time adoption mechanic, not something the split tool detects/handles at runtime.

`base/base` **is** handled at runtime, in `history_master.py` (see §5) — remote name is always literally `base`, fetched ref `refs/remotes/base/base` (`history_master.py:35` `BASE_REMOTE_REF`).

---

## 4. AI-vs-code path classification (`classify.py`)

```python
AI_TOP_LEVEL_DIRS = ("ai", ".claude", ".codex")        # classify.py:10
AI_EXACT_PATHS = (".mcp.json", "AGENTS.md", "CLAUDE.md") # classify.py:11
BASE_SEGMENT_NAME = "°base"                              # classify.py:12
AI_SUBJECT_RE = re.compile(r"^(\[.*\]\s*)?.*\bai:")       # classify.py:19
```

`is_ai_base_path(path)` (`classify.py:22-32`): a path counts as AI/base content if:
- its **first path component** is `ai`, `.claude`, or `.codex` (top-level dirs anywhere the file lives under them), OR
- the path exactly equals `.mcp.json`, `AGENTS.md`, or `CLAUDE.md` (top-level only — exact string match, not basename), OR
- **any path segment** (anywhere in the path, not just top-level) is literally `°base` (e.g. catches `scripts/°base/...`).

`classify_commit(sha, subject, paths)` (`classify.py:45-60`) builds a `CommitClassification` with:
- `is_ai_only_commit` — all changed paths are AI/base (and there's ≥1 path).
- `is_code_containing_commit` — at least one changed path is *not* AI/base.
- `is_ai_tainted_commit` — ai_only OR any path is AI/base OR the subject matches `AI_SUBJECT_RE` (i.e. even an empty-paths commit, or a pure-code-paths commit, is "tainted" if its subject line contains `ai:`, optionally after a `[topic]` prefix — matches this repo's own commit convention like `"[base] topic: ai: Run: ..."` but not `"aisle: fix typo"`).

Used by `sync_splits.kind_for()` (`sync_splits.py:102-107`) to pick `"code"`/`"history"`/`"mixed"`, and by `push_checks.check_content_policy` to enforce clean-format bans on any tainted commit and history-format bans on any code-containing commit.

---

## 5. Merge-commit / `empty/init` / `base/base` handling (`history_master.py`)

`empty/init` is not code-handled (README-only, §3 above). `base/base` handling is entirely in `history_master.py`:

- **Detecting a base-merge**: `is_base_merge(sha, cwd)` (`history_master.py:305-306`) reads the `X-Base-History-Merge-Kind` trailer and checks it equals `"base-merge"`.
- **Never re-merging twice**: on every run, after replaying/rebuilding history-master, `base_sha = git_ops.rev_parse(BASE_REMOTE_REF, cwd)` (i.e. `refs/remotes/base/base`'s current tip) is compared with `git_ops.is_ancestor(base_sha, new_tip, cwd)` (`history_master.py:826-828`, and again in `_do_continue` at `721-724`). If `base_sha` is already an ancestor of the new history-master tip, nothing is folded — this is what makes repeated runs idempotent even without walking the whole log.
- **Finding "the most recent base/base merge already present"**: when history-master already has commits (`old_history_sha` not None) and needs to be rebased onto a moved `{main}`, `_build_plan()` walks history-master's **first-parent chain only** (`_first_parent_chain_reverse`, `history_master.py:122-141` — deliberately first-parent so `base/base`'s second-parent side isn't misclassified as ordinary standalone commits) between `old_master_sha` (merge-base of old history tip and new master tip) and `old_history_sha`. Each first-parent commit found is either enqueued as `{"kind": "commit", "sha": sha}` or, if `is_base_merge(sha)` is true, as `{"kind": "base_merge", "sha": sha}` (`history_master.py:581-585`).
- **Recreating a base-merge instead of re-merging from scratch** — `recreate_base_merge(old_merge_sha, onto, cwd)` (`history_master.py:341-388`): reads the original merge's `X-Base-History-Merge-Sha` trailer (the recorded `base/base` sha that was merged), re-runs `git merge --no-commit --no-ff base_old_sha` onto the (possibly rebased) new tip. If it conflicts, it **auto-resolves each conflicted path by reusing the ORIGINAL merge commit's already-resolved blob for that exact path** (`git_ops.show_path_at(old_merge_sha, path, cwd)`, written into the working tree and `git add`-ed, `history_master.py:368-373`) — never a wholesale tree replace or raw patch-apply. The new commit is tagged `X-Base-History-Merge-Kind: base-merge`, `X-Base-History-Merge-Sha: <original base sha>`, and `X-Base-History-Merge-Replayed-From: <old_merge_sha>` (`history_master.py:379-384`).
- **Folding a genuinely new base/base tip** — `_fold_base(base_sha, onto, cwd)` (`history_master.py:404-433`): unlike recreation, there's no prior resolution to reuse, so real conflicts surface as `MergeConflict` for manual resolution. Detects the very-first-fold case by checking `git_ops.merge_base(onto, base_sha, cwd) is None` (unrelated histories) and only then passes `--allow-unrelated-histories` — this is exactly the scenario documented in `README.md` "Setup: c) Merge base/base" (`history_master.py:404-417`) and exercised by `test_first_base_fold_allows_unrelated_histories` in the test suite (regression for `ai/°base/errors/18.md`).
- **Never touches `{main}`/clean branches** — the fold only ever moves `ai/history/{main}`; `test_master_is_never_mutated_by_a_base_merge` explicitly asserts `master`'s sha is unchanged across both the base-merge setup and a subsequent run.
- **Newly-merged clean branches**: `find_newly_merged_clean_branches(old_master_sha, new_master_sha, cwd)` (`history_master.py:459-475`) scans new master commits for the `X-Base-Split-Clean-Branch` trailer (written, presumably by a merge/squash bot when landing a clean branch — see `_add_clean_branch_trailer` test helper). For each newly detected branch, if it has its own `ai/history/{branch}`, the unique commits since its `history_fork_point_ref` (or a merge-base fallback) get queued as ordinary `"commit"` steps, followed by an empty `"marker"` step tagged `X-Base-Split-Merge-Marker-For: <clean_merge_sha>` (`_create_merge_marker`, `history_master.py:436-456`) so `has_merge_marker()` can detect "already replayed" on future runs and avoid duplicating it (also recoverable via `--force-merge` widening the detection window past the normal incremental range, `history_master.py:591-599`).
- **Conflict/resume workflow**: ordinary commit replay uses `git_ops.cherry_pick`/`cherry_pick_continue`/`cherry_pick_abort` (never `git rebase --exec`, explicitly avoided per the module docstring citing `ai/°base/errors/16.txt`/`17.txt`). On any unresolved conflict (`CherryPickConflict`/`MergeConflict`), state is persisted to `.git/BASE_SPLIT_HISTORY_MASTER_STATE` (JSON: remaining steps, current tip, pending op, original checkout) so `--continue`/`--abort` can resume later, even detecting a case where someone bypassed the tool with a raw `git cherry-pick --abort` (`_pending_git_op_missing`, `history_master.py:635-642`, regression for `ai/°base/errors/18.md`).

---

## 6. `trailers.py` and the trailer schema

`trailers.py` is a thin, generic wrapper around `git interpret-trailers`:
- `read_trailers(message, cwd)` (`trailers.py:10-29`) — `git interpret-trailers --parse` on stdin, parses `key: value` lines into `dict[str, list[str]]`.
- `read_trailer_value(message, key, cwd)` (`trailers.py:32-35`) — first value or `None`.
- `write_trailers(message, trailers, cwd)` (`trailers.py:38-58`) — `git interpret-trailers --trailer "k: v" ...` against a temp file (cleaned up in `finally`).

Trailers actually used across the codebase:

| trailer | written by | meaning |
|---|---|---|
| `X-Base-Split-Source` | `sync_splits.make_split_commit` (`sync_splits.py:19,139`) | the original `ai/UNCLEAN/*` commit sha a clean/history commit was derived from |
| `X-Base-Split-Kind` | same | `"code"` / `"history"` / `"mixed"` (`sync_splits.kind_for`) |
| `X-Base-Split-Counterpart-Tree` | `sync_splits.sync_branch` (`sync_splits.py:21,250-253`) | for a mixed commit, the sibling clean tree, recorded on the history commit |
| `X-Base-Unclean-Reconstructed-From` (`RECON_TRAILER`) | `sync_unclean.build_merged_commit` (`sync_unclean.py:41,407`) | the bucket key (usually `X-Base-Split-Source` value) a reconstructed `ai/UNCLEAN/*` commit was built for — this is the tool's own bookkeeping trailer, not part of the original plan, added so idempotent re-runs/divergence-detection don't need a side database |
| `X-Base-History-Merge-Kind` | `history_master._complete_base_fold` / `recreate_base_merge` (`history_master.py:26,379,395`) | `"base-merge"` marker |
| `X-Base-History-Merge-Sha` | same (`history_master.py:27`) | the `base/base` sha that was merged |
| `X-Base-History-Merge-Replayed-From` | `recreate_base_merge` (`history_master.py:28,381`) | the prior base-merge commit this one recreates |
| `X-Base-Split-Clean-Branch` | (external — presumably a merge/squash bot) | on a master commit: names the clean branch just merged |
| `X-Base-Split-Merge-Marker-For` | `history_master._create_merge_marker` (`history_master.py:30,444`) | empty marker commit referencing the clean merge sha it marks the end of |

**How trailers on `ai/history/*` verify against the original commit on `ai/UNCLEAN/*`**: `sync_splits.make_split_commit` (`sync_splits.py:128-154`) stamps *both* the clean and the history commit it creates with `X-Base-Split-Source: <source_sha>` where `source_sha` is literally the sha being replayed off `ai/UNCLEAN/{branch}`. A test would therefore:
1. Create/collect a commit on `ai/UNCLEAN/{branch}`, capture its sha (`source_sha`).
2. Run `sync_splits.sync_branch(branch, ...)` (or the CLI `sync-splits ... --direction=to-clean-history`).
3. Resolve the new tip of `ai/history/{branch}` and read its trailers via `trailers.read_trailers(git_ops.commit_message(tip, cwd), cwd)`.
4. Assert `trailers[sync_splits.SOURCE_TRAILER] == [source_sha]` and that `source_sha` is still resolvable via `git_ops.rev_exists(source_sha, cwd)` on the unclean branch.

This exact pattern is already implemented in `test_git_split_sync_splits.py:44-74` (`test_pure_code_commit_lands_on_clean_only`, asserting `clean_trailers[sync_splits.SOURCE_TRAILER] == [code_sha]` and `history_trailers[...]` likewise) and reversed in `test_git_split_sync_unclean.py:82-124` (`test_code_and_history_pair_merge`, asserting the reconstructed unclean commit's `RECON_TRAILER` equals the shared source sha, and that both `clean_sha`/`history_sha` remain resolvable).

---

## 7. Rebase onto updated `{main}` / special `mane` case (`rebase_to_master.py`, `sync_unclean.py`, `history_master.py`)

`rebase_to_master.py` (module docstring lines 1-9) implements **(C) part 2**, deliberately *not* auto-synthesizing missing branches — it skips-and-reports rather than side-effect-calling sync-splits. Per `rebase_branches_to_master(base_branch, ...)` (`rebase_to_master.py:43-136`):
- **clean** rebases onto `{main}` directly (`git rebase {main}` with `{base_branch}` checked out).
- **history** rebases onto `ai/history/{main}` (i.e. `branches.history_name(main_branch)` — for `main_branch == "mane"` this is literally `ai/history/mane`).
- **unclean** rebases onto **history's just-rebased tip** — a real dependency, not an independently-computed target: if history is missing or its rebase failed, unclean's rebase is skipped too (`rebase_to_master.py:122-133`), with explicit status strings like `"skipped: history missing (unclean rebases onto history's rebased tip)"`.
- Raises `ValueError` if none of the three variants exist at all (likely a typo) (`rebase_to_master.py:68-72`).
- On any single-branch rebase failure, aborts with `git rebase --abort` and reports (never partial-state) (`_rebase_onto`, `rebase_to_master.py:23-40`).
- Restores whatever branch/HEAD was checked out before the run, always (`_restore_ref`, `rebase_to_master.py:151-152`, called even on dry-run).

**The `mane`-named branch special case**: there is no branch named literally `ai/UNCLEAN/mane` in the sense of a feature — rather, when `base_branch == main_branch` (e.g. the repo's main branch is called `mane` and its history variant is being handled), `branches.classify_branch("ai/history/mane", main_branch="mane")` sets `is_history_master=True` (`branches.py:59`) and the *whole update-history-master machinery* (`history_master.py`) — not `rebase_to_master.py` — is what handles it: `update_history_master` rebases `ai/history/{main}` onto `{main}` itself (`_build_plan`, computing `old_master_sha = merge_base(old_history_sha, master_tip)` and replaying only what's new, `history_master.py:562-628`), whereas `rebase_to_master.py` handles ordinary **feature** branches' history/unclean pairs (based on `ai/history/{main}`, not `{main}` itself). `get-base.py:auto_argv()` (`get-base.py:150-161`) explicitly special-cases this: if the current branch equals `main_branch`, OR `classification.is_history_master` is true, it runs `update-history-master --yes` rather than `bootstrap-branch`/`sync-splits`.

`sync_unclean.reconstruct_unclean` doesn't rebase per se, but it starts a brand-new `ai/UNCLEAN/{branch}` at `{main}`'s tip if none exists (`sync_unclean.py:562-568`) — note this is `main_branch`, not `ai/history/{main}` (a deviation worth flagging vs. `todo.md:124,138`'s spec of starting from `history/master`; `bootstrap.py` compensates for this in the Phase-3 case by pre-seeding `ai/history/{branch}` at `ai/history/{main}`'s tip before delegating, `bootstrap.py:48-56`).

---

## 8. README.md / .gitignore conflict auto-resolution

**Not found.** I grepped the entire `°split_lib` package for `README`/`gitignore` special-casing and found only one incidental reference: `history_master.py:410-411`, a comment pointing at `README.md` "Setup: c) Merge base/base" as documentation for why `--allow-unrelated-histories` is conditionally needed — it is not file-content-specific conflict logic.

The only conflict auto-resolution logic that exists anywhere in the tool is `recreate_base_merge()`'s per-path blob-reuse mechanism (§5 above), which is **generic to any conflicted path** in a *recreated* `base/base` merge — it reuses whatever blob the *original* merge resolved to for that exact path, with no special-casing of `README.md` or `.gitignore` specifically. Fresh (non-recreation) merges/conflicts (ordinary cherry-pick conflicts, first-time `base_fold` conflicts) are always surfaced for **manual** resolution (`MergeConflict`/`CherryPickConflict`, `history_master.py:71-84`, `52-67`) — there is no automatic "prefer ours/theirs on README.md/.gitignore" policy anywhere in this codebase. If such a workflow exists, it isn't part of `°split_lib`; I found no merge driver in `.gitattributes` (only Git-LFS `merge=lfs` entries) and no such logic in `scripts/°base/git/hooks/` or `checkout.sh`.

---

## 9. Existing tests (`scripts/°base/tests/`)

Run via (from `tests/README.md:7-13`):
```bash
uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v
```

Shared helper: `_git_test_helpers.py` (14 lines) —
```python
def git(args, cwd) -> str            # subprocess.run(["git", *args], ..., check=True).stdout.strip()
def make_commit(cwd, filename, message, content=None) -> sha   # writes file, git add, git commit -m, returns HEAD sha
def init_repo(cwd, *, branch="master")  # git init -b <branch>; sets a fixed test user.email/user.name
```
Every `test_git_split_*.py` follows the same pattern: `sys.path.insert` to reach `_git_test_helpers` and the `°split_lib` package directly (bypassing normal package install), `tempfile.TemporaryDirectory()` per test as an isolated real git repo (no mocking — all through real `git` subprocess calls), `init_repo` + `make_commit` to seed history, then call the module function under test directly (not via the CLI, except `test_git_split_recovery.py`'s `CliIntegrationTests` which does invoke `cli.main(...)`).

Full file list and focus:
- **`test_git_split_branches.py`** (110 lines) — `ClassifyBranchTests` (clean/unclean/history classification, refs/heads stripping, malformed-prefix fallback, `is_history_master` flag correctness), `NameHelperTests` (name round-trips), `DetectMainBranchTests` (fallback candidate list behavior, including a `test_falls_back_to_existing_main_branch` and `test_falls_back_to_master_when_nothing_found`).
- **`test_git_split_classify.py`** (100 lines) — `IsAiBasePathTests` (ai/.claude/.codex dirs, exact paths, `°base` segment anywhere, non-matching similar names like `aisle:`), `AiSubjectRegexTests`, `ClassifyCommitTests` (ai-only/pure-code/mixed/tainted-by-subject-only combinations).
- **`test_git_split_git_ops.py`** (59 lines) — plumbing sanity (rev_parse, tree/commit helpers).
- **`test_git_split_push_checks.py`** (184 lines) — pure-logic tests of `evaluate_ref_update`/name+content policy matrix (no git repo needed for most, since `push_checks.py` is dependency-free).
- **`test_git_split_recovery.py`** (211 lines) — `ResolveWatchedRefsTests`, `SnapshotTests`, `FormatTests`, `WriteRecoveryLogTests`, and `CliIntegrationTests` which actually invokes `cli.main([...])` end-to-end and asserts `.rebase-recovery.tmp` content plus that logged undo commands actually restore refs; also covers the update-history-master conflict path printing recovery options only to console (not swallowed) and dry-run skipping recovery logging.
- **`test_git_split_sync_splits.py`** (forward direction A) — `SyncSplitsTestBase` seeds `ai/history/master` branch and an `ai/UNCLEAN/{branch}` branch via `make_unclean()`; `BasicClassificationSplitTests` covers pure-code → clean-only, pure-ai → history-only, mixed → both, and asserts exact `X-Base-Split-Source`/`X-Base-Split-Kind`/`X-Base-Split-Counterpart-Tree` trailer values on both output commits.
- **`test_git_split_sync_unclean.py`** (reverse direction B, 313 lines) — `SyncUncleanTestBase` (seeds `ai/history/master`, `feature`, `ai/history/feature`), helper `commit_with_trailer()` hand-crafts trailer-carrying commits without going through `sync_splits`. `MergedPairTests` (clean+history pair merge, subject/body preference rules), `SoloCherryPickTests` (code-only, history-only, dangling-trailer fallback-to-unmatched), `DivergenceTests` (detect-but-don't-rewrite by default vs. `allow_diverge_rewrite=True` actually rewriting history in place while leaving the other side's content untouched), `IdempotencyTests` (rerun creates 0 new commits, cursors unchanged), `BucketingTests` (duplicate-source-key collision raises `ValueError`).
- **`test_git_split_history_master.py`** (548 lines, largest, `HistoryMasterTests` + `CheckoutSyncTests`) — first-run creation, idempotent no-op rerun, replay preserving a prior merge marker, **base-merge recreation after master advances** (constructs a fake `base` remote by cloning the repo, manually builds a base-merge commit with the right trailers, advances master with a conflicting add on the same path, and asserts the *recreated* merge keeps the *original* merge's resolved content — exactly the mechanism in §5), **`test_first_base_fold_allows_unrelated_histories`** (fresh unrelated `base` remote, asserts `merge_base(...) is None` before the run and that the fold succeeds via `--allow-unrelated-histories`, regression for `ai/°base/errors/18.md`), `test_master_is_never_mutated_by_a_base_merge`, `force_merge` widened-search-window recovery test, conflict-message content assertions (`--continue`/`--abort` mentioned), stale-state-after-manual-abort detection, and a whole `CheckoutSyncTests` class covering working-tree/index staying in sync when the currently-checked-out branch is `{main}`/`ai/history/{main}`/an unrelated third branch/detached HEAD, across success, conflict, continue, and abort paths — culminating in `test_full_yes_run_pulls_master_replays_and_folds_base_in_order`, an end-to-end scenario with real `origin` and `base` remotes verifying pull → replay pre-existing history → replay newly-merged branch's history + marker → base-fold, strictly in that order (asserted via the base-merge trailer being on the literal last commit).
- **`test_git_split_rebase_to_master.py`** — `RebaseBranchesToMasterTests`: only-unclean-exists (skips clean/history, reports "history missing"), only-clean-exists (rebases successfully, asserts ancestor relation via `merge-base --is-ancestor`), and (by file length) further cases for the full three-way dependency chain.
- **`test_git_split_bootstrap.py`** — `BootstrapTestBase` (creates a `feature` clean branch off `master`), `NoHistoryMasterTests` (errors clearly, mentions `update-history-master`, doesn't create partial branches), `NoCleanBranchTests` (errors when the named clean branch itself is missing), `BootstrapFromCleanOnlyTests` (creates `ai/history/feature` + fork-point ref, delegates to `reconstruct_unclean`).

I did not find any test file specifically named for README.md/.gitignore conflict handling, consistent with §8's finding that no such logic exists in this tool.

---

## 10. Prose documentation

The authoritative prose docs are:

1. **`/Users/user/Documents/programming/Python/base/README.md`**, section **"Branch splitting (clean/unclean/history)"** (lines 289-307) — the user-facing summary: what clean/unclean/history mean, why the tooling itself "never exists on a clean checkout" (since it's itself AI/base content) and therefore ships as the standalone `get-base.py` launcher, the curl one-liner, the auto-mode branch-based dispatch table, and the explicit `bootstrap-branch feature` example.
   - The same README also documents `empty/init` (lines 5, 90-100, 167, 204, 213), `base/base` adoption via checkout/rebase/merge (lines 41-224), and the `mane` branch-naming convention/rename recipe (lines 104-157) — but these sections are about *adopting* `base` into a consuming repo, independent of the split tool.
2. **`/Users/user/Documents/programming/Python/base/ai/°base/todo.md`** (lines 59-163) — the original design prompt/spec that `°split_lib` was built from: the clean/unclean/history table, the `update-history-master` procedure (including the exact "manually rebase, then re-merge+reapply the old conflict resolution" idea that became `recreate_base_merge`), `sync-splits` generation rules for clean/history/unclean, `rebase-branches-to-master`'s three-way dependency rules, and the push name/content policy — each module's docstring cross-references this file directly (e.g. `branches.py:3-5`, `sync_splits.py:1-7`, `history_master.py:11-13`, `push_checks.py:3-4`).
3. Design plans under **`ai/°base/plans/`**: `026_...phase-1-classification-push-prot.md`, `027_...phase-2-sync-splits-unclean-reconstruction.md`, `028_...phase-3-bootstrap...`, `029_get-base-py-follow-up...`, `030_fix-forward-sync-splits-duplicates...`, `031_verify-fix-update-history-master...`, `035_add-progress-output-to-get-base-py.md`, `040_fix-get-base-py-auto-mode-fails-on-a-fresh-repo...` — these are the incremental implementation plans (not read in full here, but their filenames map directly onto the phases/modules described above and are worth reading if you need the detailed rationale behind a specific design decision).
4. **`ai/°base/errors/18.md`** and **`ai/°base/errors/16.txt`/`17.txt`** (referenced but not opened) — documented real-world failure cases that directly shaped `history_master.py`'s design (avoiding `git rebase --exec`, detecting a stale/orphaned state file after a manual `git ... --abort`).