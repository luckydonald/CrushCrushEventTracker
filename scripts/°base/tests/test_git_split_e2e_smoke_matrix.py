"""End-to-end smoke matrix for split.py/get-base.py: every repo-preparation
variant (1.1-1.6 from the e2e test plan) combined with every branch-checkout
variant (2.1-2.9), run through the real "fake curl" get-base.py auto-mode
entry point, asserting the tool runs to completion without crashing and
without leaving an unresolved merge/cherry-pick/rebase behind.

This is deliberately shallow-but-wide -- it does not inspect commit content
in detail (see test_git_split_e2e_deep_flow.py for that). Branch-checkout
variants 5-8 all leave `ai/UNCLEAN/feature/batz` checked out; auto mode
always passes an explicit branch name to sync-splits (get-base.py's
auto_argv never uses the bare all-branches discovery form), so this matrix
does not exercise multi-branch discovery -- that's out of scope here.

Repo-variant 3 (README.md/.gitignore already committed on `mane` before
base/base is ever folded) combined with staying on `mane` (branch-checkout
1/2) is the smoke-level regression test for the history_master.py first-fold
auto-resolve fix: if that fix is missing or broken, this is where the matrix
first fails with a nonzero returncode (a real, unresolved MergeConflict).

Note: this suite fetches `base/base` from THIS repo's own real, currently
committed `base` branch (never GitHub) -- so it only ever exercises
whatever's actually been committed there, not any local uncommitted changes
to °split_lib itself. That's intentional (it tests the tool as a published
consuming repo would experience it), but it does mean local, not-yet-
committed fixes to °split_lib won't show up here until they land on `base`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git  # noqa: E402
import _git_split_e2e_fixtures as fixtures  # noqa: E402


class SmokeMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.this_repo_root = fixtures.resolve_this_repo_root()
        cls.empty_remote = fixtures.make_empty_init_remote(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _ensure_base_remote(self, repo_root: Path) -> None:
        existing = subprocess.run(
            ["git", "remote", "get-url", "base"], cwd=repo_root, capture_output=True
        )
        if existing.returncode != 0:
            git(["remote", "add", "base", str(self.this_repo_root)], repo_root)

    def test_all_repo_and_branch_variant_combinations_run_cleanly(self) -> None:
        for repo_name, repo_builder in fixtures.REPO_VARIANTS:
            for branch_name, branch_applier in fixtures.BRANCH_VARIANTS:
                with self.subTest(repo=repo_name, branch=branch_name):
                    with tempfile.TemporaryDirectory() as tmp:
                        repo_root = Path(tmp)
                        manifest = repo_builder(repo_root, self.empty_remote)
                        branch_applier(repo_root, manifest)

                        self._ensure_base_remote(repo_root)

                        result = fixtures.run_fake_curl(repo_root, this_repo_root=self.this_repo_root)

                        self.assertEqual(
                            result.returncode,
                            0,
                            f"get-base.py failed for repo={repo_name} branch={branch_name}:\n"
                            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
                        )
                        fixtures.assert_no_unresolved_merge_state(repo_root)


if __name__ == "__main__":
    unittest.main()
