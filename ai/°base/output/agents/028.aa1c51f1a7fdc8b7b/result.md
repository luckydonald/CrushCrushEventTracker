## Summary of Findings

### 1. Every file under `scripts/°base/tests/` (recursively, excluding `__pycache__`/`.pytest_cache`/`.venv`/`.run`)

| File | One-line summary |
|---|---|
| `tests/__init__.py` | Empty, makes `tests/` a package. |
| `tests/README.md` | How to run the suite (`uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`, etc.). |
| `tests/_git_test_helpers.py` | **Shared real-git-repo helpers** (`git`, `make_commit`, `init_repo`) reused across the `git_split` test suite — see Q2/Q3 below. |
| `tests/aaa.py` | **Not a test** — a leftover `pyte` debug scratch script (feeds an ANSI escape blob into `pyte.DebugScreen`); no `TestCase`, not collected by `unittest discover` (no `test_` prefix, no `Test*` classes). |
| `tests/git_remote_fix_tui_test_support.py` | Shared TUI test-harness support module (fake prompt_toolkit runtime, `TuiHarness`, `TuiTestCase`) for the `fix_username.py` interactive remote-picker TUI. |
| `tests/test_ai_hooks_base_routing.py` | Tests that Claude Code hooks route correctly to the shared `°base` hook implementations across project/base symlink setups. |
| `tests/test_ai_settings_sync.py` | Tests `ai/settings/sync.py` / `°settings_lib` (settings/skills/hooks sync logic for Claude/Codex config). |
| `tests/test_download_link.py` | Unit tests for `ai/references/°dllink_lib` (download-link planner/providers/CLI), using `unittest.mock`. |
| `tests/test_download_link_live.py` | Live/network-hitting tests for `download-link.py`, skipped unless `DOWNLOAD_LINK_LIVE=1`. |
| `tests/test_get_base.py` | Tests `git/get-base.py` (ensuring/fetching a `base` remote+worktree, auto-mode branch detection, delegating to `split.py`) — builds real temp git repos + a fake `base` remote. |
| `tests/test_git_remote_fix.py` | Tests `git/remote/fix_username.py`'s non-interactive logic (URL rewriting). |
| `tests/test_git_remote_fix_tui_tdd.py` | TDD-style interaction tests for the `fix_username.py` TUI (focus/keyboard navigation), built on `TuiTestCase`. |
| `tests/test_git_remote_fix_tui_terminal.py` | Terminal-rendering tests for the same TUI (uses `pyte` if available) — also on `TuiTestCase`. |
| `tests/test_git_split_bootstrap.py` | Tests `°split_lib/bootstrap.py` (`bootstrap_branch`) — creating `ai/history/*` + `ai/UNCLEAN/*` from a clean branch. |
| `tests/test_git_split_branches.py` | Tests `°split_lib/branches.py` — branch classification/naming helpers + `detect_main_branch`. |
| `tests/test_git_split_classify.py` | Tests `°split_lib/classify.py` — AI-vs-code path/commit classification. |
| `tests/test_git_split_git_ops.py` | Tests `°split_lib/git_ops.py`'s ref-qualification behavior (`create_branch`/`move_ref` on bare vs. fully-qualified refs). |
| `tests/test_git_split_history_master.py` | Large suite for `°split_lib/history_master.py` (`update_history_master`) — replay, base-fold, conflict/continue/abort, checkout-sync regressions. |
| `tests/test_git_split_push_checks.py` | Tests `°split_lib/push_checks.py` policy matrix + an end-to-end `pre-push` hook simulation via `cli._check_push`. |
| `tests/test_git_split_rebase_to_master.py` | Tests `°split_lib/rebase_to_master.py` (`rebase_branches_to_master`) across clean/unclean/history branch combinations. |
| `tests/test_git_split_recovery.py` | Tests `°split_lib/recovery.py` (ref snapshot/recovery log) + CLI integration for undo-via-recovery-log. |
| `tests/test_git_split_sync_splits.py` | Tests `°split_lib/sync_splits.py` (`sync_branch`) — forward unclean→clean/history split, idempotency, fork points, reconstruction cursor. |
| `tests/test_git_split_sync_unclean.py` | Tests `°split_lib/sync_unclean.py` (`reconstruct_unclean`) — merging clean+history commits back into `ai/UNCLEAN/*`, divergence detection/rewrite. |
| `tests/test_memory_delete.py` | Tests `ai/memory/delete.py` + the `require_memory_delete_marker.py` commit hook. |
| `tests/test_permission_check.py` | Tests `.claude/hooks/permission-check.py`. |
| `tests/test_rebase_strip_claude_authorship.py` | Tests `git/rebase_strip_claude_authorship.py` (rewriting Claude-authored commits during rebase). |
| `tests/test_save_decision.py`, `test_save_decision_15.py`, `test_save_decision_codex.py`, `test_save_decision_copilot.py` | Tests for `ai/hooks/save-decision/hook.py`'s per-CLI (Claude/Codex/Copilot) `AskUserQuestion`/decision-rendering logic, several driven by recorded real payload fixtures. |
| `tests/test_save_plan.py`, `test_save_plan_todo_capture.py` | Tests for `ai/hooks/save-plan/hook.py` (plan snapshot capture from Write/Edit, todo-list capture). |

### 2. Temp-git-repo test infrastructure — `tests/_git_test_helpers.py`

Full contents (`/Users/user/Documents/programming/Python/base/scripts/°base/tests/_git_test_helpers.py`):

```python
ZERO_SHA = "0" * 40

def git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()

def make_commit(cwd: Path, filename: str, message: str, content: str | None = None) -> str:
    path = cwd / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content is not None else message)
    git(["add", filename], cwd)
    git(["commit", "-m", message], cwd)
    return git(["rev-parse", "HEAD"], cwd)

def init_repo(cwd: Path, *, branch: str = "master") -> None:
    git(["init", "-b", branch], cwd)
    git(["config", "user.email", "test@example.com"], cwd)
    git(["config", "user.name", "Test"], cwd)
```
Lines: `git` 11-14, `make_commit` 17-23, `init_repo` 26-29.

This is the one reusable module, imported via `sys.path.insert(0, str(Path(__file__).resolve().parent)); from _git_test_helpers import git, init_repo, make_commit` in essentially every git-split test file (`test_git_split_bootstrap.py:9-10`, `test_git_split_history_master.py:11-12`, `test_git_split_rebase_to_master.py:11-12`, `test_git_split_recovery.py:12-13`, `test_git_split_sync_splits.py:9-10`, `test_git_split_sync_unclean.py:9-10`, `test_get_base.py:13-14`). Two files (`test_git_split_branches.py`, `test_git_split_push_checks.py`) instead re-declare local `git()`/`make_commit()` copies rather than importing the shared helper — that's the one inconsistency worth normalizing.

There are **no** helper functions for "make branch"/"merge"/"assert log" beyond raw `git([...], cwd)` calls — every test file inlines its own `git(["checkout", "-b", ...])`, `git(["merge", ...])`, `git(["log", "--format=%H", ...])` etc. directly using the `git()` wrapper. Reusable higher-level assertions worth knowing about, all defined inline per-file (not shared):
- Ancestry assertion idiom: `git(["merge-base", "--is-ancestor", a, b], repo)` — raises via `check=True` on failure, used as the assertion itself (e.g. `test_git_split_rebase_to_master.py:60,114-116`, `test_git_split_history_master.py:95`).
- Clean/porcelain assertion: `git(["status", "--porcelain"], repo) == ""` (`test_git_split_history_master.py:371,470`).
- Building a shared-history "fake remote" by `git clone` from the repo-under-test (not `git init` — needed so `merge`/base-fold scenarios share ancestry): `test_git_split_history_master.py:106-116` (`base_repo_root`), `:346-350` (`origin_root`), `test_get_base.py:52-61` (`base_repo`).
- Building a genuinely unrelated-history remote via a fresh `init_repo(..., branch="base")`: `test_git_split_history_master.py:176-184` (`test_first_base_fold_allows_unrelated_histories`).

### 3. Shared base `TestCase` class

There is **no shared `GitTestCase`** used across the git-split test files. Instead every file defines its *own* small local base class extending `unittest.TestCase`, each with its own `setUp`/`tearDown` built on top of the shared `_git_test_helpers` functions:
- `BootstrapTestBase` — `tests/test_git_split_bootstrap.py:20-33`
- `RecoveryTestBase` — `tests/test_git_split_recovery.py:24-37`
- `SyncSplitsTestBase` — `tests/test_git_split_sync_splits.py:24-41`
- `SyncUncleanTestBase` — `tests/test_git_split_sync_unclean.py:49-79`
- (inline, no separate base class) `HistoryMasterTests.setUp` — `tests/test_git_split_history_master.py:23-28`, and `CheckoutSyncTests.setUp` — `:339-354`

The one genuine shared base *class* in the whole test tree is `TuiTestCase` (`tests/git_remote_fix_tui_test_support.py:682-709`), used by `test_git_remote_fix_tui_tdd.py` and `test_git_remote_fix_tui_terminal.py` — but it's for TUI rendering, unrelated to git-repo setup:
```python
class TuiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt_toolkit_modules = PromptToolkitTestModules()
        self.prompt_toolkit_modules.install()
        self.addCleanup(self.prompt_toolkit_modules.uninstall)
        self.set_terminal_size(120, 40)

    def build_ui(self, *, username="luckydonald", theme="rounded", remotes=None) -> TuiHarness:
        app = MODULE.run_tui(remotes or make_sample_remotes(), theme=MODULE.THEMES[theme], username=username)
        return TuiHarness(app)

    def set_terminal_size(self, columns, lines) -> None: ...
    def set_terminal_width(self, columns) -> None: ...
    def set_monotonic_time(self, value_ref) -> None: ...
```
(`TuiHarness` itself: `git_remote_fix_tui_test_support.py:528-615`.)

**Implication for planning:** if a new suite needs a reusable `GitTestCase`, one doesn't exist yet — it would need to be introduced (e.g. into `_git_test_helpers.py` or a new module), following the existing per-file `*TestBase(unittest.TestCase)` pattern already established by `BootstrapTestBase`/`RecoveryTestBase`/`SyncSplitsTestBase`/`SyncUncleanTestBase`.

### 4. Framework conventions

- **Plain `unittest`** throughout (`import unittest`, `unittest.TestCase`, `if __name__ == "__main__": unittest.main()` at the bottom of every file). No `pytest` imports anywhere (`grep` for `import pytest`/`from pytest` returned nothing), even though a stray `.pytest_cache/` exists (someone likely ran `pytest` once against the unittest-style suite, which pytest can auto-discover, but the suite is authored for `unittest`).
- `unittest.mock` is used in 5 files: `test_get_base.py`, `test_download_link.py`, `test_rebase_strip_claude_authorship.py`, `test_save_plan.py`, `test_save_plan_todo_capture.py` — typically `mock.patch.object(module, "execvp", side_effect=...)` / `mock.patch.object(module, "find_repo_root", return_value=...)` style (see `test_get_base.py:129-130, 156-157, 231-235`).
- Git commands are run via a tiny local `subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()` wrapper, always named `git(args, cwd)` — either imported from `_git_test_helpers` or hand-duplicated (`test_git_split_branches.py:16-19`, `test_git_split_push_checks.py:23-26`).
- **No deterministic committer/author dates are faked in tests.** `git_ops.commit_tree()` (`git/°split_lib/git_ops.py:185-219`) does accept `author_date`/`committer_date` and sets `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` env vars, and `history_master.py:442` computes `now = f"{int(datetime.now(timezone.utc).timestamp())} +0000"` for its own replay commits — but no test mocks `datetime.now`/`time.monotonic` to pin these; tests never assert on exact commit dates, only on tree/ancestry/trailer content. (`set_monotonic_time` exists only in the unrelated `TuiTestCase` helper, for TUI double-key-press timing — `git_remote_fix_tui_test_support.py:707-709`.)
- Bot identity for tool-authored commits is centralized in `git/°split_lib/identity.py` (`BOT_NAME = "✨❯ Lucky Lucy"`, `BOT_EMAIL`, `BOT_AUTHOR`), but no test currently asserts against it directly.

### 5. Temp-directory handling pattern

Universally `tempfile.TemporaryDirectory()`, with two equally-common cleanup idioms:
- Older/manual style: `self._tmpdir = tempfile.TemporaryDirectory(); self.repo = Path(self._tmpdir.name); ...; def tearDown(self): self._tmpdir.cleanup()` (e.g. `test_git_split_bootstrap.py:22-33`, `test_git_split_git_ops.py:25-31`, `test_git_split_recovery.py:26-33`).
- Newer/preferred style: `self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)` — no explicit `tearDown` needed (e.g. `test_git_split_history_master.py:24-25`, `test_git_split_rebase_to_master.py:22-23`, `test_get_base.py:46-47`). Nested temp dirs (extra remotes/clones) also use `addCleanup` scoped per-test (`test_git_split_history_master.py:106-108,176-178,199-201,346-348`).
- No `pytest` `tmp_path` fixture anywhere (consistent with pure-`unittest` usage).

### 6. `pyproject.toml` / dependencies

`scripts/°base/pyproject.toml` (full):
```toml
[project]
name = "ai-scripts"
version = "0.0.1"
description = "Local environment for scripts/°base/ helpers and tests."
requires-python = ">=3.11"
dependencies = [
    "prompt_toolkit>=3.0.52,<4",
    "pydantic>=2.0,<3",
    "pyte>=0.8.1,<0.9",
]

[tool.uv]
package = false
```
No `pytest`, no `gitpython`, no other git-testing library — git repos are driven purely through the real `git` CLI via `subprocess`. `prompt_toolkit`/`pyte` exist only for the TUI test harness; `pydantic` is used by hook code (e.g. `save-decision`'s `Question` model), not by the git-split tests.

### 7. State of split/history_master/rebase_to_master/sync_unclean/sync_splits/trailers/classify/branches/bootstrap

All of these live under `git/°split_lib/` and (except `trailers.py`) each has a corresponding, apparently mature/non-WIP test file already reviewed above in full:

| Module | LOC | Test file | State |
|---|---|---|---|
| `bootstrap.py` | 70 | `test_git_split_bootstrap.py` (102 lines) | Complete — dry-run, idempotency, error paths covered. |
| `branches.py` | 108 | `test_git_split_branches.py` (110 lines) | Complete — naming/classification/round-trip/main-branch detection covered. |
| `classify.py` | 60 | `test_git_split_classify.py` (100 lines) | Complete — AI-path detection, subject regex, commit classification covered. |
| `git_ops.py` | 324 | `test_git_split_git_ops.py` (59 lines) | Only ref-qualification (`create_branch`/`move_ref`) is directly unit-tested; the rest of `git_ops.py`'s many small wrappers are exercised indirectly through the other suites. |
| `history_master.py` | 863 | `test_git_split_history_master.py` (547 lines) | Very thorough — first-run, idempotency, replay-with-marker-preservation, base-merge recreation/conflict recreation, unrelated-histories first fold, master-never-mutated invariant, force-merge search widening, conflict/continue/abort + stale-state detection, and checked-out-branch/detached-HEAD sync regressions. |
| `rebase_to_master.py` | 152 | `test_git_split_rebase_to_master.py` (126 lines) | Complete — all 2^3 combinations of clean/history/unclean branch presence. |
| `sync_splits.py` | 288 | `test_git_split_sync_splits.py` (380 lines) | Thorough — pure-code/pure-ai/mixed splitting, rename-across-boundary, fresh-branch parenting + fork-point ref, idempotent re-run, all-ai-only branch, dry-run, reconstruction-cursor fallback, bootstrap-then-sync non-duplication, unclean-branch discovery. |
| `sync_unclean.py` | 602 | `test_git_split_sync_unclean.py` (312 lines) | Thorough — merged-pair reconstruction (subject/body precedence), solo cherry-picks (with/without dangling source trailer), divergence detection vs. `allow_diverge_rewrite`, idempotency, duplicate-trailer-collision error. |
| `trailers.py` | 58 | **None dedicated** | No `test_git_split_trailers.py` exists. `read_trailers`/`read_trailer_value`/`write_trailers` are only exercised indirectly as a dependency inside `test_git_split_history_master.py`, `test_git_split_sync_splits.py`, and `test_git_split_sync_unclean.py` — this is the one clear gap if direct unit coverage is wanted. |
| `identity.py` | 10 | **None** | Trivial constants module (`BOT_NAME`/`BOT_EMAIL`/`BOT_AUTHOR`); untested but also nearly untestable content. |
| `tree_ops.py` | 158 | **None dedicated** | Shared tree-splitting/overlay plumbing for `sync_splits`; exercised only transitively via the `sync_splits`/`sync_unclean` test suites, no direct unit tests. |
| `cli.py` | 375 | **None dedicated** | The `git/°split_lib/cli.py` argument-parsing/dispatch layer (`cli.main`, `cli._check_push`) is exercised only end-to-end through `test_git_split_push_checks.py::EndToEndCheckPushTests` (calls `cli._check_push`) and `test_git_split_recovery.py::CliIntegrationTests` (calls `cli.main([...])`) — no dedicated `test_git_split_cli.py`. |
| `push_checks.py` | 77 | `test_git_split_push_checks.py` (184 lines) | Complete — policy matrix, name policy, and full end-to-end `pre-push` hook simulation via temp repo + `cli._check_push`. |
| `recovery.py` | 99 | `test_git_split_recovery.py` (211 lines) | Complete — watched-ref resolution, snapshotting, recovery-entry formatting, log file appending, and full CLI round-trip (snapshot → undo commands actually restore refs). |

None of the above modules are WIP/partial stubs — they're all fully implemented with matching (or, for `trailers.py`/`cli.py`/`tree_ops.py`/`identity.py`/`git_ops.py`, partially-indirect) test coverage. The clearest actionable gaps for a new plan to fill are: a dedicated `test_git_split_trailers.py`, and possibly `test_git_split_cli.py`/expanded `test_git_split_git_ops.py` coverage, plus normalizing the two files that hand-roll their own `git()`/`make_commit()` instead of importing `_git_test_helpers`.
