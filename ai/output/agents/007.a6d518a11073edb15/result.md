## Findings

### 1. `git_ops.py` — full function list (file: `scripts/°base/git/°split_lib/git_ops.py`)

- `repo_root(cwd=None)` — L15
- `rev_exists(sha, cwd)` — L26
- `commits_new_to_remote(local_sha, remote_sha, remote_name, cwd)` — L35
- `changed_paths_for_commit(sha, cwd)` — L56
- `subject_for_commit(sha, cwd)` — L67
- `commit_message(sha, cwd)` — L78
- `rev_parse(ref, cwd)` — L90 (returns `None` on failure, doesn't raise)
- `rev_list_reverse(range_expr, cwd)` — L102
- `rev_list_first_parent_reverse(range_expr, cwd)` — L114
- `parents_of(sha, cwd)` — L136
- `is_ancestor(ancestor_sha, descendant_sha, cwd)` — L149
- `merge_base(sha_a, sha_b, cwd)` — L158
- `_full_ref(ref)` — L170 (normalizes short branch names to `refs/heads/...`)
- `create_branch(ref, at_sha, cwd)` — L180
- `create_refs(refs, cwd)` — L184
- `move_ref(ref, new_sha, old_sha, cwd)` — L206
- `tree_for_commit(sha, cwd)` — L214
- `ls_tree_entry(tree_or_commit, path, cwd)` — L225
- `commit_tree(...)` — L242
- `cherry_pick` / `cherry_pick_continue` / `cherry_pick_abort` — L282/294/306
- `merge_no_commit` / `merge_abort` — L310/320
- `checkout_branch(ref, cwd)` — L324
- index-manipulation helpers (`read_tree_into_index`, `update_index_add`, `update_index_remove`, `write_tree_from_index`) — L334–373
- **`show_path_at(sha, path, cwd) -> bytes`** — L376-384: `git show f"{sha}:{path}"`. **This is exactly the "read a file at a ref without checkout" helper you need** — already generic over any tree-ish/commit-ish (works with `base/base`, `refs/heads/base`, `refs/get-base/target`, etc.).

**No remote/fetch functions exist in `git_ops.py`** — no `fetch`, no `remote_add`, no `remote_get_url`, nothing "base"-specific. `commits_new_to_remote` takes a `remote_name` string but never resolves/creates it. Fetch/remote logic lives only in `get-base.py` (see below) and in test fixtures.

### 2. `classify.py` (file: `scripts/°base/git/°split_lib/classify.py`)

- `AI_IGNORE_FILENAME = ".ai-ignore"` — L10
- `ai_ignore_path(repo_root=None) -> Path` — L20-22: pure path join, on-disk only, no git awareness.
- `ai_ignore_rules(ignore_file=None) -> list[str]` — L25-32: `if not path.is_file(): return []` — this is the silent-empty-ruleset bug you're fixing.
- `ai_ignore_files(...)` — L35-48: builds the per-directory chain of `.ai-ignore` paths (root + each ancestor dir of the target path). All still `Path.is_file()` based.
- `is_ai_base_path` / `classify_commit` — consume the above.

Callers passing `ignore_file=classify.ai_ignore_path(repo_root)`: `cli.py:152`, `cli.py:174`, `cli.py:179`, `sync_splits.py:249`. All pass a `Path`, all currently assume on-disk file semantics — so a fallback that returns *content* (bytes) rather than a `Path` will need either a temp-file bridge or a signature change propagated to these 4 call sites too.

### 3. `get-base.py` bootstrap / remote pattern (file: `scripts/°base/git/get-base.py`) — **this is the canonical pattern to mirror**

Constants (L49-56):
```python
REMOTE_NAME = "base"
REMOTE_BRANCH = "base"
DEFAULT_USERNAME = "luckydonald"
WORKTREE_RELATIVE_PATH = Path(".git") / "luckydonald" / "base#get-base.py"
LOCAL_TARGET_REF = "refs/get-base/target"
```
- `remote_url(username) -> str` — L84-85: `f"https://{username}@github.com/{username}/base.git"` — this is the canonical GitHub URL builder (parameterized by username, default `luckydonald`, env override `BASE_GIT_USERNAME`).
- `ensure_base_remote(repo_root, username)` — L88-95: `git remote get-url base` (no-op if present, **never overwrites**), else `git remote add base <url>`.
- `fetch_base(repo_root, ref=REMOTE_BRANCH)` — L98-100: `git fetch base +{ref}:refs/get-base/target` (force-updating refspec into a fixed local ref, not a normal remote-tracking ref).
- `ensure_worktree` / `worktree_path` / `_is_valid_worktree` / `remove_stale_worktree` — L103-147: worktree machinery, not needed for your fix (you just need `git show`, not a checkout).
- `--base-ref` / `BASE_GIT_REF` (from commit `d89a425`, L23-36, L256-276, L282): lets you pin fetch to something other than the `base` branch — same idea as your step 4 fallback ref, but here it's operator-supplied rather than auto-detected.

Important nuance: `get-base.py` does **not** use plain `git fetch base base` into `refs/remotes/base/base` — it fetches into the fixed ref `refs/get-base/target` via `+{ref}:refs/get-base/target`. So "a remote-tracking ref for a remote pointing at this repo (e.g. `base/base`)" (your step 2) is **not** what `get-base.py` itself produces; it's what a plain unforced `git fetch base` (without refspec) or an initial clone/remote-add+fetch would produce, and it's what the **test fixtures** use (see below).

`get-base.py` is deliberately stdlib-only and does not import `°split_lib` (see module docstring L1-36) — so if you want classify.py's fallback to reuse `get-base.py`'s remote-url/fetch logic, you'll need to either duplicate the small constants or have `get-base.py` import from `°split_lib` in the other direction (not currently the case; `°split_lib.git_ops`/`branches` are imported *from* `get-base.py` only inside `auto_argv`, after the worktree exists — L196-198).

`bootstrap.py` (`°split_lib/bootstrap.py`) is a different "bootstrap" — it's `bootstrap_branch()`, for reconstructing a clean branch's `ai/history/*`/`ai/UNCLEAN/*` split state; it has nothing to do with fetching the `base` remote/repo itself. Not relevant to your fallback chain.

### 4. Test fixtures: `add_and_fetch_real_base_branch` (file: `scripts/°base/tests/_git_split_e2e_fixtures.py`)

- `resolve_this_repo_root()` — L104-114: resolves the actual on-disk dev repo root via `git -C <this file's dir> rev-parse --show-toplevel` (never GitHub).
- `ensure_base_remote(repo_root, this_repo_root=None)` — L117-127 (fixture's own version, **distinct from** `get-base.py`'s function of the same name): adds remote `base` pointed at `this_repo_root` (a local path, not a URL) if not already present.
- `add_and_fetch_real_base_branch(repo_root, *, this_repo_root=None) -> str` — L130-140:
  ```python
  ensure_base_remote(repo_root, this_repo_root)
  git(["fetch", "base", "base"], repo_root)
  return git(["rev-parse", "refs/remotes/base/base"], repo_root)
  ```
  This is a plain `git fetch base base` (no custom refspec) into the repo, which git resolves to the ordinary remote-tracking ref `refs/remotes/base/base` — matching your step-2 fallback target exactly. This is the mechanism your variants 1-3 fixtures should adopt for exercising the remote-tracking-ref path without live network: point remote `base` at the local on-disk dev repo path and `git fetch base base`, then `git show refs/remotes/base/base:.ai-ignore`.
- `resolve_base_sha_two_commits_earlier` — L143-147, and `run_fake_curl` — L150-169 (feeds `get-base.py`'s source over stdin to simulate the curl one-liner hermetically) are the sibling patterns already used to avoid live network in tests — reuse `run_fake_curl`-style stdin-piping or the local-remote-path trick for your step-4 fixture (fetching `base` "over the network") too, rather than inventing a new mechanism.

### 5. Canonical constants — is there already one shared definition?

**No single shared module-level constant exists yet.** The remote name `"base"` and the GitHub URL pattern are currently duplicated/hard-coded in at least four independent places, with no imports between them:

- `get-base.py`: `REMOTE_NAME = "base"`, `remote_url(username) = f"https://{username}@github.com/{username}/base.git"` (L49, L84-85)
- `°split_lib/merge_base.py`: hard-coded literal `"base/base"` refspec/rev (L81, L87) — no constant at all, just inline strings
- `°split_lib/git/remote/fix_username.py`: `"base": "https://luckydonald@github.com/luckydonald/base.git"` — a different hardcoded mapping (L20)
- `°split_lib/ai/hooks/°commit_style_lib/__init__.py`: regex `r"(^|[:/])luckydonald/base(\.git)?/?$"` matched against `origin`'s URL to detect "is this the base repo" (L36-45) — yet another independent encoding of the same fact
- Test fixtures (`_git_split_e2e_fixtures.py`) reimplement `ensure_base_remote` themselves, using a local path instead of a URL.

So: **you will need to pick one of these as your source of truth or introduce a genuinely new small constant/module** (e.g. in `°split_lib/git_ops.py` or a new tiny `°split_lib/base_remote.py`) rather than reuse an existing canonical one — there isn't one. Given `get-base.py` is deliberately stdlib-only/standalone (can't depend on `°split_lib`), and `°split_lib` code (classify.py, merge_base.py) can't easily import from `get-base.py` (it's a script, not really a library, though it is importable via `importlib` like `bootstrap.py`/`get-base.py`'s own `delegate()` does), the cleanest new-helper approach is:
- Add a small `°split_lib/git_ops.py` (or new module) constant `BASE_REMOTE_NAME = "base"` + a `blob_at_ref(ref, path, cwd) -> bytes | None` wrapper around the existing `show_path_at` (non-raising, returns `None` on missing-path/ref instead of raising `CalledProcessError`, since `show_path_at` uses `check=True` — L376-384 will need a non-throwing variant or a try/except wrapper for your "try in order, fall through" logic).
- For remote-URL construction, either import `get-base.py`'s `remote_url()` dynamically (as `bootstrap.py`/`auto_argv` already do via `importlib.util.spec_from_file_location`/`importlib.import_module` — see `get-base.py` L160-162 and L196-198 for the established pattern of cross-loading between the standalone script and `°split_lib`) or duplicate the tiny one-liner with a comment cross-referencing `get-base.py`.

### Summary of the reusable pattern to mirror

1. **Remote existence check**: `git remote get-url base` (returncode 0 → exists) — pattern in `get-base.py:ensure_base_remote` (L88-95) and fixtures' own `ensure_base_remote` (L117-127). Never overwrite an existing remote.
2. **Remote-tracking ref reads**: plain `git fetch base base` → read `refs/remotes/base/base` — pattern in fixtures' `add_and_fetch_real_base_branch` (L130-140). This matches your step 2 (fallback to an already-fetched remote-tracking ref) — just do `git show refs/remotes/<remote>/base:.ai-ignore` (or whatever local remote name points at `luckydonald/base`) without even fetching, for the "already present locally" case.
3. **Local branch literally named `base`**: no existing helper; trivially `git_ops.rev_parse("base", cwd)` (existing, L90-99) to check existence, then `show_path_at("base", ".ai-ignore", cwd)`.
4. **Fetch-if-missing with GitHub URL**: `get-base.py`'s `remote_url(username)` (L84-85) + `ensure_base_remote`/`fetch_base` (L88-100) is the exact fetch-with-known-URL pattern; default username `luckydonald`, env override `BASE_GIT_USERNAME`, giving `https://luckydonald@github.com/luckydonald/base.git`.
5. **Reading file content at a ref without checkout**: `git_ops.show_path_at(sha, path, cwd) -> bytes` (L376-384) already does `git show <ref>:<path>` — this is the one existing helper directly reusable as-is (note: raises via `check=True` on failure; you'll want a non-raising wrapper or try/except for the fallback chain, and it returns `bytes` not `list[str]`/`Path`, so `ai_ignore_rules`'s signature/call sites (`cli.py:152/174/179`, `sync_splits.py:249`) will need adjusting to accept raw content or you bridge via a `NamedTemporaryFile`).

No existing helper does steps 2-4's git-remote/fetch orchestration inside `°split_lib`; that logic today lives solely in the standalone `get-base.py` script and is partially duplicated in test fixtures for hermetic local testing.