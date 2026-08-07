"""End-to-end deep flow for split.py/get-base.py: for each of the 6
repo-preparation variants, create `ai/UNCLEAN/feature/test-eins` with a
realistic ai/code/both commit mix, run the tool to generate `feature/test-eins`
+ `ai/history/feature/test-eins` from it, verify their content and trailers
in detail, advance `mane`, rebase, and verify the rebased state.

See test_git_split_e2e_smoke_matrix.py for the shallow-but-wide 54-combo
matrix; this file is the narrow-but-deep complement (one scenario, inspected
thoroughly, per repo variant).

Like the smoke matrix, this normally fetches `base/base` from THIS repo's own
real, currently committed `base` branch -- so it only exercises whatever's
actually been committed there, not local uncommitted changes to °split_lib.
Each variant additionally runs once with `--base-ref HEAD` (this repo's
current checked-out commit, not just what's landed on `base`), so a fix made
here shows up in this suite before it's merged into `base`.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git  # noqa: E402
import _git_split_e2e_fixtures as fixtures  # noqa: E402

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

git_ops = importlib.import_module("°split_lib.git_ops")
branches = importlib.import_module("°split_lib.branches")
classify = importlib.import_module("°split_lib.classify")
trailers = importlib.import_module("°split_lib.trailers")
sync_splits = importlib.import_module("°split_lib.sync_splits")


class DeepFlowTests(unittest.TestCase):
    # get-base.py's own default (REMOTE_BRANCH) is "base" -- "HEAD" instead
    # pins the fetch to this repo's current checked-out commit via
    # get-base.py's `--base-ref` flag, so local fixes are exercised too.
    BASE_REFS = ("base", "HEAD")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.this_repo_root = fixtures.resolve_this_repo_root()
        self.empty_remote = fixtures.make_empty_init_remote(Path(self._tmp.name))

    def _run_for_every_base_ref(self, repo_builder) -> None:
        for base_ref in self.BASE_REFS:
            with self.subTest(base_ref=base_ref):
                with tempfile.TemporaryDirectory() as tmp:
                    self.repo_root = Path(tmp) / "repo"
                    self.repo_root.mkdir()
                    self._run_deep_flow(repo_builder, base_ref)

    def _run_deep_flow(self, repo_builder, base_ref: str) -> None:
        manifest = repo_builder(self.repo_root, self.empty_remote)

        known_base_merge_shas = {r.commit for r in manifest if r.merge and r.merge.branch == "base/base"}
        mane_merge_count_at_fork = int(git(["rev-list", "--merges", "--count", "mane"], self.repo_root))

        # Step 5: ai/UNCLEAN/feature/test-eins with the ai/code/both mix.
        unclean_manifest = fixtures.checkout_variant_8_unclean_mixed_ai_code_both(
            self.repo_root, [], branch_name="ai/UNCLEAN/feature/test-eins"
        )

        # Step 6: run the tool (auto mode -> sync-splits feature/test-eins).
        fixtures.ensure_base_remote(self.repo_root, self.this_repo_root)
        result = fixtures.run_fake_curl(
            self.repo_root, "--base-ref", base_ref, this_repo_root=self.this_repo_root
        )
        self.assertEqual(result.returncode, 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        # Step 7: assert feature/test-eins.
        self._assert_clean_branch(unclean_manifest, known_base_merge_shas, mane_merge_count_at_fork)
        # Step 8: assert ai/history/feature/test-eins.
        self._assert_history_branch(unclean_manifest)

        # Step 9: advance mane.
        git(["checkout", "mane"], self.repo_root)
        old_history_master_tip = git_ops.rev_parse("ai/history/mane", self.repo_root)
        fixtures._random_commits(self.repo_root, [], 2, prefix="mane_advance")

        # Step 10: run the tool to rebase -- both explicit, since auto mode
        # never selects rebase-branches-to-master, and update-history-master
        # must run first (rebase-branches-to-master never touches
        # ai/history/{main} itself).
        result = fixtures.run_fake_curl(
            self.repo_root, "--base-ref", base_ref, "update-history-master", "--yes", this_repo_root=self.this_repo_root
        )
        self.assertEqual(result.returncode, 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        result = fixtures.run_fake_curl(
            self.repo_root,
            "--base-ref",
            base_ref,
            "rebase-branches-to-master",
            "feature/test-eins",
            this_repo_root=self.this_repo_root,
        )
        self.assertEqual(result.returncode, 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        # Step 11: assert rebased state.
        self._assert_rebased_onto_new_mane(old_history_master_tip)

    def _assert_clean_branch(self, unclean_manifest, known_base_merge_shas, mane_merge_count_at_fork) -> None:
        feature_tip = git_ops.rev_parse("feature/test-eins", self.repo_root)
        self.assertIsNotNone(feature_tip)

        # 7a: the merges already present in mane are still there, and no new
        # merge (base-related or otherwise) got introduced -- sync-splits
        # only ever creates single-parent commits.
        for sha in known_base_merge_shas:
            self.assertTrue(
                git_ops.is_ancestor(sha, feature_tip, self.repo_root),
                f"expected pre-existing base merge {sha} to still be an ancestor of feature/test-eins",
            )
        feature_merge_count = int(git(["rev-list", "--merges", "--count", "feature/test-eins"], self.repo_root))
        self.assertEqual(feature_merge_count, mane_merge_count_at_fork)

        # 7b: no commit past mane touches an ai/base path.
        for sha in git_ops.rev_list_reverse("mane..feature/test-eins", self.repo_root):
            paths = git_ops.changed_paths_for_commit(sha, self.repo_root)
            self.assertFalse(
                any(classify.is_ai_base_path(p) for p in paths),
                f"commit {sha} on feature/test-eins touches an ai/base path: {paths}",
            )

        # 7c/7d: code-containing unclean commits (pure-code + "both"), in
        # order, map 1:1 onto feature/test-eins's own new commits.
        clean_shas = git_ops.rev_list_reverse("mane..feature/test-eins", self.repo_root)
        code_containing = [r for r in unclean_manifest if r.code]
        self.assertEqual(len(clean_shas), len(code_containing))
        for clean_sha, record in zip(clean_shas, code_containing):
            if record.ai:
                # a "both" commit: only the non-ai half should have landed.
                clean_paths = set(git_ops.changed_paths_for_commit(clean_sha, self.repo_root))
                original_paths = set(git_ops.changed_paths_for_commit(record.commit, self.repo_root))
                expected = {p for p in original_paths if not classify.is_ai_base_path(p)}
                self.assertEqual(clean_paths, expected)
                self.assertFalse(any(classify.is_ai_base_path(p) for p in clean_paths))

        # ai-only unclean commits have no counterpart at all on feature/test-eins.
        ai_only_sources = {r.commit for r in unclean_manifest if r.ai and not r.code}
        self.assertTrue(ai_only_sources.isdisjoint({r.commit for r in code_containing}))

    def _assert_history_branch(self, unclean_manifest) -> None:
        fork_point = git_ops.rev_parse(branches.history_fork_point_ref("feature/test-eins"), self.repo_root)
        self.assertIsNotNone(fork_point)
        history_shas = git_ops.rev_list_reverse(f"{fork_point}..ai/history/feature/test-eins", self.repo_root)

        self.assertEqual(len(history_shas), len(unclean_manifest))
        for history_sha, record in zip(history_shas, unclean_manifest):
            source = trailers.read_trailer_value(
                git_ops.commit_message(history_sha, self.repo_root), sync_splits.SOURCE_TRAILER, self.repo_root
            )
            self.assertEqual(source, record.commit)

            history_paths = set(git_ops.changed_paths_for_commit(history_sha, self.repo_root))
            original_paths = set(git_ops.changed_paths_for_commit(record.commit, self.repo_root))

            if record.ai and not record.code:
                # ai-only: unchanged.
                self.assertEqual(history_paths, original_paths)
            elif record.ai and record.code:
                # "both": only the ai half survives.
                expected = {p for p in original_paths if classify.is_ai_base_path(p)}
                self.assertEqual(history_paths, expected)
            else:
                # pure-code: an empty commit (no changes at all).
                self.assertEqual(history_paths, set())

    def _assert_rebased_onto_new_mane(self, old_history_master_tip) -> None:
        mane_tip = git_ops.rev_parse("mane", self.repo_root)
        history_master_tip = git_ops.rev_parse("ai/history/mane", self.repo_root)
        feature_tip = git_ops.rev_parse("feature/test-eins", self.repo_root)
        history_feature_tip = git_ops.rev_parse("ai/history/feature/test-eins", self.repo_root)
        unclean_tip = git_ops.rev_parse("ai/UNCLEAN/feature/test-eins", self.repo_root)

        self.assertTrue(git_ops.is_ancestor(mane_tip, feature_tip, self.repo_root))

        # ai/history/mane itself must have advanced (update-history-master
        # replayed mane's 2 new commits onto it) and history/feature/test-eins
        # must now be based on that new tip.
        self.assertNotEqual(history_master_tip, old_history_master_tip)
        self.assertTrue(git_ops.is_ancestor(history_master_tip, history_feature_tip, self.repo_root))

        # unclean rebases onto history's just-rebased tip.
        self.assertTrue(git_ops.is_ancestor(history_feature_tip, unclean_tip, self.repo_root))

    def test_deep_flow_repo_variant_1(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_1_random_commits)

    def test_deep_flow_repo_variant_2(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_2_empty_init_then_random)

    def test_deep_flow_repo_variant_3(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_3_readme_gitignore_conflict_setup)

    def test_deep_flow_repo_variant_4(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_4_based_on_real_base_tip)

    def test_deep_flow_repo_variant_5(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_5_empty_and_base_merge)

    def test_deep_flow_repo_variant_6(self) -> None:
        self._run_for_every_base_ref(fixtures.build_repo_variant_6_double_base_merge)


if __name__ == "__main__":
    unittest.main()
