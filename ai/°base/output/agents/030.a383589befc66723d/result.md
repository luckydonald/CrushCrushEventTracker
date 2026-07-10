# Implementation Plan: `_fold_base` README/.gitignore auto-resolve + end-to-end split/get-base test suite

## Overview

Two independent pieces of work:

1. A small, surgical change to `history_master.py`'s `_fold_base()` (scripts/°base/git/°split_lib/history_master.py:404-433) so a first-time `base/base` fold that conflicts *only* on `README.md`/`.gitignore` auto-resolves those two paths in favor of `base_sha`'s content, leaving genuine conflicts (if any) for the human.
2. A large new end-to-end test suite exercising `split.py`/`get-base.py` across 6 repo-preparation variants × 9 branch-checkout variants (54-combo smoke matrix) plus a 6-times-repeated deep flow (sync-splits → assert → advance mane → rebase → assert), built on a new shared fixture module.

---

## 1. `history_master.py` change

### New constant

Add near the other trailer/module constants (history_master.py:26-35):

```python
# Paths auto-resolved (in favor of base_sha's content) when a first-time
# base/base fold conflicts on them -- see _fold_base(). Top-level, exact
# match only (a nested doc/README.md is untouched).
FIRST_FOLD_AUTO_RESOLVE_PATHS = ("README.md", ".gitignore")
```

### New helper (placed right before `_fold_base`, after `recreate_base_merge`, ~history_master.py:388)

```python
def _auto_resolve_first_fold_conflicts(base_sha: str, conflicted: list[str], cwd: Path) -> set[str]:
    """Auto-resolve base_sha's own README.md/.gitignore in a first-time (non-
    recreation) base/base fold, mirroring recreate_base_merge's per-path
    blob-reuse mechanism -- but sourcing content from base_sha (the incoming
    tip) rather than a prior resolved merge, since a first-time fold has no
    prior resolution to reuse. Returns the subset of `conflicted` actually
    resolved (and staged via `git add`); leaves everything else untouched so
    genuine conflicts still surface normally.
    """
    resolved: set[str] = set()
    for path in conflicted:
        if path not in FIRST_FOLD_AUTO_RESOLVE_PATHS:
            continue
        content = git_ops.show_path_at(base_sha, path, cwd)
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        _git(["add", "--", path], cwd, check=True)
        resolved.add(path)
    return resolved
```

### Exact diff-level change to `_fold_base` (history_master.py:424-432)

Replace:
```python
    result = _git(merge_args, cwd)
    if result.returncode != 0:
        conflicted = _conflicted_paths(cwd)
        if not conflicted:
            logger.debug("$ git merge --abort")
            git_ops.merge_abort(cwd)
            _cleanup_scratch(cwd)
            raise HistoryMasterError(f"merge of {base_sha} onto {onto} failed: {result.stderr}")
        raise MergeConflict(base_sha, onto, result.stderr)
    return _complete_base_fold(base_sha, cwd)
```

with:
```python
    result = _git(merge_args, cwd)
    if result.returncode != 0:
        conflicted = _conflicted_paths(cwd)
        if not conflicted:
            logger.debug("$ git merge --abort")
            git_ops.merge_abort(cwd)
            _cleanup_scratch(cwd)
            raise HistoryMasterError(f"merge of {base_sha} onto {onto} failed: {result.stderr}")
        auto_resolved = _auto_resolve_first_fold_conflicts(base_sha, conflicted, cwd)
        remaining = [path for path in conflicted if path not in auto_resolved]
        if remaining:
            raise MergeConflict(base_sha, onto, result.stderr)
    return _complete_base_fold(base_sha, cwd)
```

Key correctness points to preserve:
- Do **not** abort the merge when only README.md/.gitignore conflicted and both got auto-resolved — fall straight through to `_complete_base_fold` (same as the clean-merge path), exactly like `recreate_base_merge` does.
- When *some* other path also conflicts, keep the merge in progress with README.md/.gitignore already `git add`-ed (do not abort) and raise `MergeConflict` as before — the existing `--continue` machinery (`_do_continue`, history_master.py:702-711, which calls `_conflicted_paths(cwd)` and only proceeds when empty) already handles "some paths pre-resolved, finish resolving the rest, then continue" correctly with no changes needed there.
- No gating on "is this literally the very first fold ever" is required: `_fold_base` (as opposed to `recreate_base_merge`) is *already* exactly the non-recreation code path per its own docstring (history_master.py:404-417), so every call into it is a "first-time fold of this particular base_sha" by construction.

### Where the new test goes

In `scripts/°base/tests/test_git_split_history_master.py`, inside `HistoryMasterTests`, immediately after `test_first_base_fold_allows_unrelated_histories` (currently lines 169-192). Mirror its setup style (fresh `base` repo via `init_repo(..., branch="base")`, not a clone, so it's a genuinely unrelated history) but seed conflicting README.md/.gitignore content on both sides:

```python
def test_first_base_fold_auto_resolves_readme_and_gitignore(self) -> None:
    # Give master its own README.md/.gitignore before base is ever folded.
    make_commit(self.repo_root, "README.md", "consumer readme", content="consumer readme\n")
    make_commit(self.repo_root, ".gitignore", "consumer gitignore", content="*.consumer\n")

    base_repo_tmp = tempfile.TemporaryDirectory()
    self.addCleanup(base_repo_tmp.cleanup)
    base_repo_root = Path(base_repo_tmp.name)
    init_repo(base_repo_root, branch="base")
    make_commit(base_repo_root, "README.md", "base readme", content="base readme\n")
    make_commit(base_repo_root, ".gitignore", "base gitignore", content="*.base\n")
    base_sha = git(["rev-parse", "HEAD"], base_repo_root)

    git(["remote", "add", "base", str(base_repo_root)], self.repo_root)
    git(["fetch", "base"], self.repo_root)

    result = history_master.update_history_master(repo_root=self.repo_root, main_branch="master")

    self.assertEqual(result["status"], "ok")
    self.assertEqual(result["base_merge"], result["history_master"])
    readme = git_ops.show_path_at(result["history_master"], "README.md", self.repo_root).decode()
    gitignore = git_ops.show_path_at(result["history_master"], ".gitignore", self.repo_root).decode()
    self.assertEqual(readme, "base readme\n")
    self.assertEqual(gitignore, "*.base\n")
```

Add a second companion test asserting the "genuine conflict alongside" behavior isn't silently swallowed — e.g. `test_first_base_fold_still_conflicts_on_other_paths_while_auto_resolving_readme`: same setup plus both sides also add a genuinely conflicting `shared.txt`; assert `result["status"] == "conflict"`, then (before resolving) assert `git(["diff", "--name-only", "--diff-filter=U"], self.repo_root)` no longer lists `README.md`/`.gitignore` (already staged) but still lists `shared.txt`, then resolve `shared.txt` manually + `--continue` and assert final content of README.md is still base's.

---

## 2. New shared fixture module: `scripts/°base/tests/_git_split_e2e_fixtures.py`

This sits alongside `_git_test_helpers.py` and is imported by the new e2e test file(s) the same way (`sys.path.insert(0, str(Path(__file__).resolve().parent))`, then `from _git_split_e2e_fixtures import ...`). It should itself `import` `_git_test_helpers` (`git`, `init_repo`, `make_commit`) rather than duplicating it, and resolve `°split_lib` the same way the other test files do (`LIB_ROOT = Path(__file__).resolve().parents[1] / "git"`, `sys.path.insert(0, str(LIB_ROOT))`, then `importlib.import_module("°split_lib.git_ops")` etc.) — this matters because the module name starts with `°`, which is not a valid plain `import` target.

### Manifest schema (dataclass, not TypedDict — needed because `merge` sub-dict has its own required/optional shape and a plain dataclass reads better with `dataclasses.asdict()` for eventual `assertEqual` against plain dicts if desired)

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class MergeInfo:
    branch: str                 # "empty/init" | "base/base"
    commit_theirs: str
    commit_ours: str
    is_allowed_merge: bool

@dataclass
class CommitRecord:
    commit: str
    merge: MergeInfo | None
    code: bool
    ai: bool
    msg: str          # subject + body, up to (not including) trailers
    trailer: str      # raw trailer block (may be "")

Manifest = list[CommitRecord]
```

Rationale for a `list[CommitRecord]` rather than a dict keyed by sha: the spec explicitly requires order-sensitive assertions ("in the same order... no extra commits introduced in between"), so a plain ordered list matching `git rev-list --reverse` order is the natural structure; a helper `by_sha(manifest) -> dict[str, CommitRecord]` can be added for O(1) lookup where needed.

### Recorder function (exact signature)

```python
def record_commit(sha: str, *, merge: MergeInfo | None, cwd: Path) -> CommitRecord:
    """Build a CommitRecord for `sha` by combining git_ops.changed_paths_for_commit
    + classify.classify_commit (for code/ai flags) + trailers.read_trailers
    (to split the trailer block back out of the full message)."""
    full_message = git_ops.commit_message(sha, cwd)
    parsed_trailers = trailers.read_trailers(full_message, cwd)
    # git interpret-trailers --parse (trailers.read_trailers, trailers.py:10-29)
    # only tells us WHICH trailers exist, not where the trailer block starts in
    # the original message -- so re-derive the split via subject.py's own
    # convention: the trailer block is the trailing run of "Key: value" lines
    # after the last blank line (same heuristic sync_unclean._strip_trailers
    # already uses at sync_unclean.py:332-338 -- reuse that regex/logic here
    # rather than reinventing it).
    msg_body, _, trailer_block = full_message.rpartition("\n\n")
    # (fallback to whole message / "" if there's no blank-line-separated
    # trailer block at all, e.g. a message with no trailers)
    subject = git_ops.subject_for_commit(sha, cwd)
    paths = git_ops.changed_paths_for_commit(sha, cwd)
    cls = classify.classify_commit(sha, subject, paths)
    return CommitRecord(
        commit=sha,
        merge=merge,
        code=cls.is_code_containing_commit,
        ai=cls.is_ai_only_commit or any(classify.is_ai_base_path(p) for p in paths),
        msg=msg_body,
        trailer=trailer_block if _looks_like_trailer_block(trailer_block) else "",
    )
```

Note: rather than reinventing trailer-block detection, reuse the existing regex idea from `sync_unclean._strip_trailers` (sync_unclean.py:332-338, `_TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s")`), applied to the *last* whitespace-separated chunk of the message via `splitlines()` walking backward from the end (exactly the `_strip_trailers` algorithm) rather than a naive `rpartition("\n\n")` (which breaks if the body itself contains blank lines before the trailer block, e.g. the "both"/mixed commits which get real bodies). **Implementer should literally import and reuse `sync_unclean._strip_trailers`-style logic** (or promote it to a shared helper) rather than duplicating a regex by hand in the fixtures module — flag this as a possible small refactor (extract `_TRAILER_LINE_RE`/the trailer-stripping logic into `trailers.py` itself, e.g. `trailers.split_trailer_block(message) -> tuple[str, str]`) since both `sync_unclean.py` and the new fixtures module need the exact same "where does the trailer block start" logic. This refactor is optional but recommended — call it out to the human reviewer rather than silently doing it.

### Empty/init stand-in remote

```python
def make_empty_init_remote(tmp_root: Path) -> Path:
    """Build a tiny local one-commit repo to serve as a hermetic stand-in for
    the real `https://github.com/EmptyAAS/empty.git` remote's `init` branch
    (see README.md "All code for c) as a single copy pastable one"). Returns
    the repo path; caller adds it as a remote (`git remote add empty <path>`)
    and fetches `init` off it -- but since this is a *fresh* init (not a
    clone), the target repo and this remote will NOT share history, so any
    merge of it needs --allow-unrelated-histories, matching the real
    empty/init's actual relationship to a fresh consuming repo.
    """
    repo = tmp_root / "empty-init-remote"
    repo.mkdir()
    init_repo(repo, branch="init")
    make_commit(repo, "EMPTY.md", "empty/init stand-in initial commit")
    return repo
```

### This-repo's real `base` branch

```python
def resolve_this_repo_root() -> Path:
    """`git -C <this test file's repo> rev-parse --show-toplevel` -- the
    actual on-disk repo containing this test file (NOT a temp fixture),
    used only as a local, offline source for `base`'s real content."""
    return Path(
        subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )

def add_and_fetch_real_base_branch(repo_root: Path, *, pin_sha: str | None = None) -> str:
    """Add a `base` remote pointing at THIS repo's own absolute path and
    fetch its `base` branch -- never hits GitHub. If `pin_sha` is given,
    hard-resets a throwaway local tag/ref check to that exact commit after
    fetching (see risk section: pinning for determinism) instead of trusting
    whatever the live repo's `base` branch currently points at. Returns the
    fetched sha (`refs/remotes/base/base`) actually to be used.
    """
    this_repo = resolve_this_repo_root()
    git(["remote", "add", "base", str(this_repo)], repo_root)
    git(["fetch", "base", "base"], repo_root)
    fetched = git(["rev-parse", "refs/remotes/base/base"], repo_root)
    if pin_sha is None:
        return fetched
    if not subprocess.run(
        ["git", "cat-file", "-e", f"{pin_sha}^{{commit}}"], cwd=repo_root, capture_output=True
    ).returncode == 0:
        raise RuntimeError(f"pinned base sha {pin_sha!r} not reachable from this repo's base branch")
    return pin_sha
```

### `run_fake_curl`

```python
def run_fake_curl(repo_root: Path, *args: str, this_repo_root: Path | None = None) -> subprocess.CompletedProcess:
    """Feed get-base.py via stdin exactly like the documented curl one-liner
    (`curl -fSL <raw-url> | python3 - [subcommand ...]`), from `repo_root`.
    Caller must have already pre-added a `base` remote on `repo_root` pointed
    at a local path (ensure_base_remote() never overwrites an existing
    remote -- get-base.py.ensure_base_remote(), get-base.py:64-71) so no real
    network call ever happens; get-base.py's own `main()` unconditionally
    calls fetch_base() (get-base.py:200) regardless of explicit argv, so the
    pre-added remote must resolve locally even for explicit-subcommand calls.
    """
    this_repo_root = this_repo_root or resolve_this_repo_root()
    script_path = this_repo_root / "scripts" / "°base" / "git" / "get-base.py"
    script_text = script_path.read_text()
    return subprocess.run(
        [sys.executable, "-"],
        cwd=repo_root,
        input=script_text,
        capture_output=True,
        text=True,
    ) if not args else subprocess.run(
        [sys.executable, "-", *args],
        cwd=repo_root,
        input=script_text,
        capture_output=True,
        text=True,
    )
```

(Both branches can obviously collapse into one `subprocess.run([sys.executable, "-", *args], ...)` — kept split above only to make explicit that the empty-argv/auto-mode case and the explicit-subcommand case are both exercised by the same helper.)

### Repo-variant builders (exact signatures)

All take a fresh `Path` (already a `tempfile.TemporaryDirectory()`), init with `branch="mane"`, and return `(repo_root, manifest)`:

```python
def build_repo_variant_1_random_commits(repo_root: Path) -> Manifest: ...
def build_repo_variant_2_empty_init_then_random(repo_root: Path, empty_remote: Path) -> Manifest: ...
def build_repo_variant_3_readme_gitignore_conflict_setup(repo_root: Path) -> Manifest: ...
def build_repo_variant_4_based_on_real_base_tip(repo_root: Path, *, pin_sha: str | None = None) -> Manifest: ...
def build_repo_variant_5_empty_and_base_merge(repo_root: Path, empty_remote: Path, *, pin_sha: str | None = None) -> Manifest: ...
def build_repo_variant_6_double_base_merge(repo_root: Path, empty_remote: Path, *, pin_sha: str | None = None) -> Manifest: ...
```

Each internally calls `init_repo(repo_root, branch="mane")`, then a shared `_random_commits(repo_root, manifest, n, *, code=True, ai=False) -> None` helper that appends `n` commits of the requested code/ai/both flavor (touching e.g. `src/f{i}.py` for code, `ai/notes{i}.md` for ai, both paths in one commit for "both") and appends a `CommitRecord` via `record_commit(sha, merge=None, cwd=repo_root)` each time, so manifest construction is uniform across variants and matches the exact "ai/code/both order" pattern needed for branch-checkout variant 2.8/2.9 and deep-flow step 5.

Variant 5 (README.md's "Setup: c) Merge base/base" recipe) does, in order, mirroring README.md lines 208-214:
```python
git(["remote", "add", "empty", str(empty_remote)], repo_root)
git(["fetch", "empty", "init"], repo_root)
merge_before = git(["rev-parse", "HEAD"], repo_root)
git(["merge", "--allow-unrelated-histories", "--no-verify", "empty/init"], repo_root)
empty_merge_sha = git(["rev-parse", "HEAD"], repo_root)
manifest.append(record_commit(empty_merge_sha, merge=MergeInfo("empty/init", theirs, merge_before, True), cwd=repo_root))
this_repo_sha = add_and_fetch_real_base_branch(repo_root, pin_sha=pin_sha)
base_merge_before = git(["rev-parse", "HEAD"], repo_root)
git(["merge", "--no-ff", "--no-verify", "base/base"], repo_root)  # or the pinned sha, see below
base_merge_sha = git(["rev-parse", "HEAD"], repo_root)
manifest.append(record_commit(base_merge_sha, merge=MergeInfo("base/base", this_repo_sha, base_merge_before, True), cwd=repo_root))
```
Variant 6 repeats the `base/base` merge step a second time (`git merge --no-ff base/base` again — a no-op-content but still a real second merge commit, per spec item 6, since `base/base`'s tip hasn't moved between the two merges within one test unless `pin_sha` differs) plus additional mixed ai/code/"both" commits afterward.

### Branch-checkout appliers (exact signatures)

Each takes the already-built `(repo_root, manifest)` (checked out on `mane`) and returns the manifest extended with whatever new commits were added on the resulting branch; the branch itself is left checked out when the function returns:

```python
def checkout_variant_1_stay_on_mane(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_2_mane_plus_commits(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_3_feature_foobar(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_4_test_idk_lol(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_5_unclean_code_only(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_6_unclean_ai_only(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_7_unclean_both(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_8_unclean_mixed_ai_code_both(repo_root: Path, manifest: Manifest) -> Manifest: ...
def checkout_variant_9_history_master_plus_unclean_mixed(repo_root: Path, manifest: Manifest) -> Manifest: ...
```

Variants 5-8 all target the *same* branch name `ai/UNCLEAN/feature/batz` (per spec) — implemented as one shared `_checkout_unclean_batz(repo_root) -> None` (create once, checked out) called by each, followed by variant-specific commit sequences reusing the same `_random_commits`-style helper with `code=`/`ai=`/`both=` flags. Variant 9 additionally does `git checkout -b ai/history/mane` + 2 ai-only commits *before* the 2.8-style mixed sequence — this is the scenario flagged in the risk section below (extra local commits landing directly on the history-master branch itself, ahead of any `update-history-master` run).

A registry list for the smoke matrix:

```python
REPO_VARIANTS: list[tuple[str, Callable[..., Manifest]]] = [...]
BRANCH_VARIANTS: list[tuple[str, Callable[[Path, Manifest], Manifest]]] = [...]
```

so the test file can do `for repo_name, repo_fn in REPO_VARIANTS: for branch_name, branch_fn in BRANCH_VARIANTS: with self.subTest(repo=repo_name, branch=branch_name): ...` without hand-maintaining 54 literal test methods.

### `assert_merges_cleanly` helper

```python
def assert_no_unresolved_merge_state(repo_root: Path) -> None:
    """Assert neither MERGE_HEAD, CHERRY_PICK_HEAD, nor a rebase-in-progress
    directory exists, and `git status --porcelain` shows no unmerged (U)
    entries -- i.e. the tool left nothing needing --continue/--abort."""
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply"):
        assert not (repo_root / ".git" / marker).exists(), f"{marker} left behind"
    status = git(["status", "--porcelain"], repo_root)
    assert "\nU" not in ("\n" + status) and not status.startswith("U"), f"unresolved paths: {status}"
```

---

## 3. New test file(s)

Propose two files (keeps the 54-combo smoke matrix, which is deliberately shallow/wide, separate from the deep flow, which is deliberately narrow/deep — matches the repo's existing one-concern-per-file convention):

- `scripts/°base/tests/test_git_split_e2e_smoke_matrix.py`
- `scripts/°base/tests/test_git_split_e2e_deep_flow.py`

Both import `_git_split_e2e_fixtures` the same way other test files import `_git_test_helpers` (sys.path insert + plain module import), and both import `°split_lib.git_ops`/`branches`/`classify`/`trailers` via the existing `LIB_ROOT` sys.path-insert pattern used throughout the existing test files (e.g. test_git_split_history_master.py:14-19).

### `test_git_split_e2e_smoke_matrix.py`

One `unittest.TestCase` (`SmokeMatrixTests`), `setUpClass` builds the hermetic `empty/init` stand-in remote once (`_git_split_e2e_fixtures.make_empty_init_remote`) into a class-level temp dir (shared read-only across all 54 subtests — never mutated, so sharing is safe), and resolves `this_repo_root`/optionally a pinned `base` sha once.

One test method, `test_all_repo_and_branch_variant_combinations_run_cleanly`, structured as:

```python
def test_all_repo_and_branch_variant_combinations_run_cleanly(self):
    for repo_name, repo_fn in fixtures.REPO_VARIANTS:
        for branch_name, branch_fn in fixtures.BRANCH_VARIANTS:
            with self.subTest(repo=repo_name, branch=branch_name):
                with tempfile.TemporaryDirectory() as tmp:
                    repo_root = Path(tmp)
                    manifest = repo_fn(repo_root, ...)   # variant-specific extra args as needed
                    manifest = branch_fn(repo_root, manifest)

                    git(["remote", "add", "base", str(self.this_repo_root)], repo_root)

                    result = fixtures.run_fake_curl(repo_root, this_repo_root=self.this_repo_root)

                    self.assertEqual(
                        result.returncode, 0,
                        f"get-base.py crashed for {repo_name}/{branch_name}:\n{result.stdout}\n{result.stderr}",
                    )
                    fixtures.assert_no_unresolved_merge_state(repo_root)
```

Notes for the implementer, called out explicitly in-file as comments:
- Auto mode is used (empty `args` to `run_fake_curl`) since the smoke matrix's whole point is "what does the tool decide to do given only the checked-out branch", matching get-base.py's real no-argument entrypoint.
- Since `ensure_base_remote` never overwrites an existing remote (get-base.py:64-71) and `add_and_fetch_real_base_branch`/manual `git remote add base ...` may already have run during repo-variant construction (variants 4/5/6), the smoke test must NOT re-add a `base` remote if the repo-variant builder already added one at a *different* path (this repo's own toplevel) — check `git remote get-url base` first and only add if absent, so all 6×9 combos consistently end up with `base` pointed at `this_repo_root`.
- `result.returncode == 0` alone is not sufficient for repo variants where the branch is `main`/`mane` (auto mode runs `update-history-master --yes`) hitting a genuine, expected content conflict (e.g. repo variant 3, which deliberately seeds a README.md/.gitignore conflict scenario) — the new auto-resolve feature from part 1 should make this a non-issue, but if the human wants "smoke matrix must always exit 0" to be a real invariant, this doubles as an implicit regression test for the `_fold_base` fix from part 1. Document this cross-reference in the test's docstring.
- Branch-checkout variants 5-8 all leave `ai/UNCLEAN/feature/batz` checked out; auto mode on that branch runs `sync-splits feature/batz --direction=to-clean-history --branch feature/batz` implicitly (single-branch, not the no-branch-arg "process all ai/UNCLEAN/*" form) — see risk section below for why this matters and needs an explicit assertion that *other* unclean branches were not touched.

### `test_git_split_e2e_deep_flow.py`

One `unittest.TestCase` subclass per repo variant is cleanest given `subTest` doesn't isolate temp-dir setup well across 6 heavyweight repo builds; propose parametrizing via a class-level loop generating 6 test methods (`test_deep_flow_repo_variant_1` .. `_6`) rather than a single `subTest` loop, since each deep flow does real assertions that should independently report which variant failed without needing `--failfast` off.

```python
class DeepFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_root = Path(self._tmp.name)
        self.this_repo_root = fixtures.resolve_this_repo_root()
        self.empty_remote = fixtures.make_empty_init_remote(Path(self._tmp.name).parent / "empty-remote-shared")
        # (or build fresh per-test; either is fine given TemporaryDirectory cleanup)

    def _run_deep_flow(self, repo_fn) -> None:
        manifest = repo_fn(self.repo_root, ...)
        expected_pre_existing_base_merges = [m for m in manifest if m.merge and m.merge.branch == "base/base"]

        # Step 5: ai/UNCLEAN/feature/test-eins, ai/code/both pattern.
        unclean_manifest = fixtures.checkout_variant_8_unclean_mixed_ai_code_both(
            self.repo_root, [], branch_name="ai/UNCLEAN/feature/test-eins",
        )

        # Step 6: run the tool.
        git(["remote", "add", "base", str(self.this_repo_root)], self.repo_root)
        result = fixtures.run_fake_curl(self.repo_root, this_repo_root=self.this_repo_root)
        self.assertEqual(result.returncode, 0, result.stderr)

        # Step 7: assert feature/test-eins.
        self._assert_clean_branch(unclean_manifest, expected_pre_existing_base_merges)
        # Step 8: assert ai/history/feature/test-eins.
        self._assert_history_branch(unclean_manifest)

        # Step 9: advance mane.
        git(["checkout", "mane"], self.repo_root)
        make_commit(self.repo_root, "mane_advance_1.txt", "mane advances 1")
        make_commit(self.repo_root, "mane_advance_2.txt", "mane advances 2")

        # Step 10: run the tool to rebase -- see risk section: auto mode
        # NEVER selects rebase-branches-to-master, so this must be explicit,
        # and update-history-master must run FIRST to actually move
        # ai/history/mane forward (rebase-branches-to-master never touches
        # ai/history/mane itself -- see rebase_to_master.py's module
        # docstring, rebase_to_master.py:1-9).
        result = fixtures.run_fake_curl(
            self.repo_root, "update-history-master", "--yes", this_repo_root=self.this_repo_root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = fixtures.run_fake_curl(
            self.repo_root, "rebase-branches-to-master", "feature/test-eins",
            this_repo_root=self.this_repo_root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        # Step 11: assert rebased state.
        self._assert_rebased_onto_new_mane()

    def test_deep_flow_repo_variant_1(self):
        self._run_deep_flow(fixtures.build_repo_variant_1_random_commits)

    # ... _2 .. _6 analogously, each passing whatever extra args
    # (empty_remote, pin_sha) that variant's builder needs.
```

Assertion-block detail (implemented as private helper methods so each is independently readable and independently a place a future bug gets caught):

**`_assert_clean_branch(unclean_manifest, expected_pre_existing_base_merges)`** (step 7):
- 7a — walk `git_ops.rev_list_reverse("feature/test-eins", cwd)`, and for each sha check `history_master.is_base_merge(sha, cwd)` (history_master.py:305-306, reads `X-Base-History-Merge-Kind` trailer) — actually **use** `trailers.read_trailer_value(git_ops.commit_message(sha, cwd), "X-Base-History-Merge-Kind", cwd) == "base-merge"` directly instead of importing `history_master` into a sync-splits-focused test (avoid cross-module coupling); count matches must equal `len(expected_pre_existing_base_merges)` exactly (0 for variants 1-3, 1 for 4/5, 2 for 6), and none of them should have a `X-Base-Split-Source` trailer pointing at a sha that's *new* since `mane` was forked for `feature/test-eins` (i.e. no NEW base-merge got introduced by sync-splits itself — sync-splits only ever creates plain `make_split_commit` commits per source, tagged with `X-Base-Split-Source`/`X-Base-Split-Kind`, never a merge — this is really just a sanity check that the commit *count* of ancestors tagged base-merge hasn't grown beyond what `mane` already had before `feature/test-eins` branched off).
- 7b — for every sha in `feature/test-eins`'s history past the fork point from `mane`, assert `set(git_ops.changed_paths_for_commit(sha, cwd))` contains no path where `classify.is_ai_base_path(path)` is true.
- 7c/7d — reconstruct, in order, the subsequence of `unclean_manifest` where `record.code` is true (pure-code and "both" commits, in original order) and zip it 1:1 against `feature/test-eins`'s commits past the fork point (via `git_ops.rev_list_reverse(f"{fork_point}..feature/test-eins", cwd)`, where `fork_point = git_ops.merge_base("ai/UNCLEAN/feature/test-eins", "feature/test-eins", cwd)` or, more directly, `git_ops.rev_parse("mane", cwd)` since clean branches fork straight off `main_branch` per `sync_splits.ensure_branch_started` (sync_splits.py:82-99)). For each pair, assert:
  - `trailers.read_trailer_value(git_ops.commit_message(clean_sha, cwd), "X-Base-Split-Source", cwd) == unclean_manifest_entry.commit` (sync_splits.SOURCE_TRAILER, sync_splits.py:19/139).
  - For "both" commits specifically: `set(git_ops.changed_paths_for_commit(clean_sha, cwd))` equals exactly the code-half of the original commit's changed paths (i.e. `{p for p in git_ops.changed_paths_for_commit(unclean_manifest_entry.commit, cwd) if not classify.is_ai_base_path(p)}`), and no ai path leaked through.
  - Pure ai-only commits from `unclean_manifest` must have **no** counterpart on `feature/test-eins` at all (sync_splits.py:208-210, `clean_commits_skipped_ai_only`).

**`_assert_history_branch(unclean_manifest)`** (step 8):
- 8a — `history_shas = git_ops.rev_list_reverse(f"{history_fork}..ai/history/feature/test-eins", cwd)` where `history_fork = git_ops.rev_parse(branches.history_fork_point_ref("feature/test-eins"), cwd)` (the exact ref sync_splits.py:187-188 records) must have the **same length** as `unclean_manifest`, in the same order; zip and assert for each pair `trailers.read_trailer_value(git_ops.commit_message(history_sha, cwd), sync_splits.SOURCE_TRAILER, cwd) == unclean_manifest_entry.commit` (the `X-Base-Split-Source` trailer, per the task's exact wording). Also assert author/committer name+email+date are preserved verbatim via `git_ops.commit_message`... actually author info needs `git log --format=%an/%ae/%ad` (there's no `git_ops` wrapper for this beyond the private `_author_info` in sync_splits.py:110-121/sync_unclean.py:54-65 — reuse `sync_splits._author_info(sha, cwd)` directly, or add a tiny local helper in the fixtures module rather than reaching into a "private" underscore function from a test — **recommend adding a small public `git_ops.author_info(sha, cwd) -> tuple[str,str,str]`** as a minimal, clearly-scoped addition to shared plumbing, called out to the human as an optional refactor, OR just duplicate the 5-line `subprocess.run(["git","log","-1","--format=%an%x1f%ae%x1f%ad", ...])` helper locally in the fixtures module — the latter keeps `git_ops.py` "frozen" per its own module docstring (git_ops.py:1-4) and is the safer default choice).
- 8b — for ai-only original commits: assert the mapped history commit's changed-paths set is unchanged (still exactly the ai-only paths). For "both" commits: assert the mapped history commit's changed-paths set equals exactly the ai-half of the original (`{p for p in ... if classify.is_ai_base_path(p)}`). For pure-code original commits: assert the mapped history commit is a genuinely empty commit — `git_ops.changed_paths_for_commit(history_sha, cwd) == []` (sync_splits.py's history pass still creates a commit for every source commit regardless of kind, per sync_splits.py:235-257, no equivalent of `clean_commits_skipped_ai_only` on the history side) — this is an important, easy-to-get-wrong assertion and should be called out with an inline comment referencing sync_splits.py:227-260.

**`_assert_rebased_onto_new_mane()`** (step 11):
- Assert `git_ops.is_ancestor(git_ops.rev_parse("mane", cwd), git_ops.rev_parse("feature/test-eins", cwd), cwd)` is True (clean rebases straight onto `main_branch`, rebase_to_master.py:102-107).
- Assert `git_ops.is_ancestor(git_ops.rev_parse("ai/history/mane", cwd), git_ops.rev_parse("ai/history/feature/test-eins", cwd), cwd)` is True, and separately assert `ai/history/mane` itself actually advanced (its tip today is NOT the same sha as before step 9 — since `update-history-master --yes` was run explicitly in step 10, this is the real "history-master gets replayed to reflect mane's 2 new commits" check, rebase_to_master.py:1-9's documented dependency).
- Assert `git_ops.is_ancestor(git_ops.rev_parse("ai/history/feature/test-eins", cwd), git_ops.rev_parse("ai/UNCLEAN/feature/test-eins", cwd), cwd)` is True (unclean rebases onto history's *just-rebased* tip, rebase_to_master.py:122-133).
- **Flag to the human** (see risk item 4 below): the spec's "EXCEPT for repo variant/branch-checkout-2.9's scenario" clause doesn't cleanly map onto the deep flow as described (branch-checkout variants are a smoke-matrix-only concept; the deep flow builds its own dedicated `ai/UNCLEAN/feature/test-eins` branch per step 5, it doesn't run on top of branch-checkout variant 2.9). Recommend implementing the deep flow uniformly across all 6 repo variants using the two-call sequence above (explicit `update-history-master --yes` then explicit `rebase-branches-to-master feature/test-eins`), and get explicit sign-off from the requester on whether a *separate*, additional deep-flow-like test is wanted specifically for the branch-checkout-2.9 scenario (extra local commits landing directly on `ai/history/mane` before any tool run) rather than silently reinterpreting the ambiguous instruction.

---

## 4. Risks / edge cases to call out explicitly in the plan file

1. **`sync-splits` auto-discovery scope.** `get-base.py`'s `auto_argv` (get-base.py:176-180) always calls `sync-splits <classification.base_name> --direction=to-clean-history` with an **explicit branch name** (never the bare `discover_unclean_branches` all-branches form, sync_splits.py:272-288/cli.py:145-147). So in the smoke matrix, branch-checkout variants 5-8 (all on `ai/UNCLEAN/feature/batz`) will only ever sync `feature/batz`, never any other stray `ai/UNCLEAN/*` branch that might exist in that repo variant. This means the smoke matrix is *not* actually exercising the "no-branch-arg, process-all" code path at all — worth either (a) explicitly noting this gap and accepting it (the deep flow doesn't need it either, since it always names `feature/test-eins` explicitly too), or (b) adding one dedicated extra test (outside the 54-combo matrix) that leaves two different `ai/UNCLEAN/*` branches present and asserts an explicit `sync-splits` call (no branch arg) via `run_fake_curl(repo_root, "sync-splits", "--direction=to-clean-history")` processes both. Recommend (b) as a small addition, flagged to the human as optional scope.

2. **`os.execvp` process replacement under `subprocess.run`.** `get-base.py`'s `delegate()` (get-base.py:110-113) calls `os.execvp(sys.executable, command)` unconditionally whenever explicit or auto-derived `argv` is non-empty (`main()`, get-base.py:203-209) — this *replaces* the `python3 -` process spawned by `subprocess.run([sys.executable, "-"], input=script_text, ...)` with a fresh `python3 <worktree>/scripts/°base/git/split.py --repo-root <repo> <argv>` invocation. This is exactly what real `curl | python3 -` does too (a piped stdin script becomes a real, if anonymous, running process, and `execvp` on it works fine — stdin itself is irrelevant post-exec since delegate() doesn't read stdin again). **This should work transparently** through `subprocess.run` with no special handling needed, *but*: (a) the existing `test_get_base.py` already relies on **mocking** `os.execvp` in-process (test_get_base.py:124-139, 156-161, 286-296, etc.) rather than letting a real exec happen — the new e2e tests, by contrast, must let the real exec happen (since the whole point is to run the real `split.py`), so `run_fake_curl` must NOT mock `execvp`, it must let the subprocess actually replace itself and run to completion, then inspect `CompletedProcess.returncode`/`stdout`/`stderr`. (b) Confirm empirically once implementation starts that `subprocess.run([sys.executable, "-", *args], input=script_text, capture_output=True, text=True)` really does capture the *exec'd* process's stdout/stderr correctly (it should, since `execvp` replaces the process image but keeps the same PID/fds, and `subprocess.run` waits on that PID) — recommend a very small, cheap standalone spike/smoke test first (e.g. just `update-history-master --yes` on repo variant 1) before building out the full 54-combo matrix on top of this assumption, in case something about buffering/text-mode/`sys.executable` resolution inside the piped `python3 -` process behaves unexpectedly.

3. **This-repo's real `base` branch: determinism/stability.** Repo variants 4/5/6 and the deep flow all fetch **this actual, currently-evolving repo's** `base` branch (via `git -C <this-file's-repo> rev-parse --show-toplevel` then `git remote add base <that-path>` + `git fetch base base`). Two concrete risks:
   - **Content drift over time**: as this repo's real `base` branch gains commits (including, ironically, commits from *this very test suite's own development*), tests asserting exact merge counts / exact file contents (e.g. auto-resolve test's expectation that base's README.md wins) could still pass structurally but the *actual* diff/conflict shape at merge time may change (e.g. if this repo's own README.md happens to already match a consuming repo's, no conflict occurs at all, silently making a "conflict auto-resolve" test into a no-op non-test). **Mitigation**: don't fetch `base`'s branch *tip* for the auto-resolve test (part 1) — that test builds its own tiny hermetic `base` remote (as already shown in `test_first_base_fold_allows_unrelated_histories`, history_master.py's existing pattern), so it's unaffected. But for e2e repo-variants 4/5/6, which are explicitly *specified* to use this real repo's real `base` branch: recommend **pinning to a known-good, explicitly recorded commit sha** (a `pin_sha` parameter is already threaded through the proposed fixture signatures above) rather than always "whatever HEAD currently is" — i.e. hardcode a specific sha of this repo's `base` branch (recorded once, e.g. as a module-level constant `KNOWN_GOOD_BASE_SHA = "..."` in `_git_split_e2e_fixtures.py`, with a comment explaining it must be updated deliberately if ever bumped) as the default `pin_sha`, with an explicit opt-out (env var or constant `None`) to test against the live tip when someone wants to verify compatibility with an updated base. This directly addresses the "stability concern" the task calls out.
   - **Worktree/exec side effects on THIS repo**: `get-base.py`'s `ensure_worktree()` (get-base.py:90-102) creates a real `git worktree add` **inside the temp repo's own `.git/base-tools`**, not inside this real repo — so there's no risk of the test suite accidentally creating stray worktrees against the actual development repo. Confirm this explicitly in a comment/assertion (`self.assertFalse((self.this_repo_root / ".git" / "base-tools").exists())` as a sanity check somewhere) since it's an easy thing to get subtly wrong if `find_repo_root()` (get-base.py:53-57, based on `cwd`) ever resolved to the wrong directory.
   - Additionally: fetching `base` from a local path is genuinely instant/offline (git recognizes a local filesystem remote and does a fast local object copy), so there's no actual network flakiness risk here — only the content-drift risk above.

4. **The step-11 "EXCEPT branch-checkout-2.9" clause is ambiguous as applied to the deep flow.** As discussed in section 3 above, branch-checkout variants are (per the spec) a smoke-matrix-only concept layered onto a *prepared repo*, while the deep flow builds its own bespoke `ai/UNCLEAN/feature/test-eins` branch directly off `mane` (step 5) — it never goes through `checkout_variant_9_history_master_plus_unclean_mixed`. Two readings are possible: (a) it's just imprecise phrasing for the general, always-true dependency chain (unclean depends on history's rebased tip; history-master is handled by `update_history_master`, not `rebase_to_master` — rebase_to_master.py:1-9) which the plan above already implements uniformly via the explicit two-call sequence, or (b) the deep flow is meant to *additionally* run once more with `ai/history/mane` itself carrying extra un-replayed local commits (i.e., literally reusing branch-checkout variant 9's setup as a 7th "repo+branch" combination fed into the deep flow, not just the smoke matrix). **Recommend flagging this explicitly to the requester before implementation** rather than guessing; the plan file should record both readings and note that (a) is what's currently planned, with (b) as an easy follow-up (`checkout_variant_9` fixture would need to run right before step 5, and `_assert_rebased_onto_new_mane` would need a variant asserting `ai/history/mane`'s pre-existing extra local commits survived the `update-history-master --yes` replay, i.e. a small additional case, not a divergent implementation).

5. **`.rebase-recovery.tmp` side files.** Every real (non-dry-run) invocation of `split.py` through `_run_with_recovery` (cli.py:54-97) writes `.rebase-recovery.tmp` into the target repo root and appends a `BASE_SPLIT_HISTORY_MASTER_STATE` file into `.git/` on conflict (history_master.py:281-297). These are harmless for ephemeral `tempfile.TemporaryDirectory()`-based repos but the smoke matrix (54 iterations) will create/tear-down 54 of these — no action needed beyond noting it, since `TemporaryDirectory` cleanup handles it; just don't accidentally assert `git status --porcelain` is fully empty anywhere (it won't be, due to the untracked `.rebase-recovery.tmp` file at repo root) — `assert_no_unresolved_merge_state` above deliberately checks only for `U` (unmerged) entries, not a fully clean tree, for exactly this reason.

6. **Repo-variant 6's second `base/base` merge being a true no-op.** If `pin_sha` resolves to the *same* commit both times (which it will, since nothing advances `base/base` in between in variant 6's own construction), the second `git merge --no-ff base/base` produces an empty-diff merge commit (still a real commit with two parents, just no tree changes) — confirm `_fold_base`/`update_history_master` never special-cases "already an ancestor" in a way that would make the *second* manually-constructed test-fixture merge fail or get silently deduped by git itself (`git merge --no-ff` of an already-merged ref is normally a hard error "Already up to date" with no commit created **unless** `--no-ff` forces one — actually `git merge --no-ff` on an already-fully-merged branch prints "Already up to date." and does NOT create a merge commit even with `--no-ff`, in modern git). **This is a real correctness risk for repo-variant 6 as literally specified** — since `base/base`'s tip won't have moved between the two merges, the second `git merge --no-ff base/base` will likely be a no-op with no new commit at all, not "exactly two merges in mane" as variant 6 requires. **Mitigation to flag explicitly**: either (a) make an intervening commit *on the `empty_remote`/fake-base-remote-of-record* between the two merges so `base/base`'s tip genuinely advances (not possible if variant 6 is required to use this repo's real, immutable-during-the-test `base` branch) — but since real repo branches don't advance mid-test, the more practical fix is (b) fetch **two different pinned commits** of this repo's `base` branch history (an older sha, then a newer sha) as `pin_sha_1`/`pin_sha_2` for variant 6's two merges, which also incidentally makes the "two distinct base merges" assertion in the deep flow (variant 6: exactly TWO merges) meaningfully different rather than a content-identical no-op. Recommend adding a second constant `KNOWN_GOOD_BASE_SHA_EARLIER` (an ancestor of `KNOWN_GOOD_BASE_SHA`) for this purpose, and calling this out to the human up front since it changes variant 6's exact construction from what's literally written in the spec.

---

### Critical Files for Implementation

- /Users/user/Documents/programming/Python/base/scripts/°base/git/°split_lib/history_master.py
- /Users/user/Documents/programming/Python/base/scripts/°base/tests/test_git_split_history_master.py
- /Users/user/Documents/programming/Python/base/scripts/°base/tests/_git_test_helpers.py (new `_git_split_e2e_fixtures.py` sits beside this)
- /Users/user/Documents/programming/Python/base/scripts/°base/git/get-base.py
- /Users/user/Documents/programming/Python/base/scripts/°base/git/°split_lib/cli.py
- /Users/user/Documents/programming/Python/base/scripts/°base/git/°split_lib/rebase_to_master.py
- /Users/user/Documents/programming/Python/base/scripts/°base/git/°split_lib/sync_splits.py