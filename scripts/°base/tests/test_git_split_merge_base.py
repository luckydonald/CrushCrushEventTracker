"""Tests for °split_lib.merge_base (the `split.py merge-base` subcommand):
merging `base/base` into a consuming repo's real branch, auto-resolving
predictable conflicts (README.md/.gitignore/.gitattributes)."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

merge_base = importlib.import_module("°split_lib.merge_base")


class MergeBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)

        self.base_repo = tmp_path / "base"
        self.base_repo.mkdir(parents=True)
        init_repo(self.base_repo, branch="base")
        make_commit(self.base_repo, "README.md", "base readme", content="from base\n")
        make_commit(self.base_repo, "shared.txt", "base shared file", content="base content\n")

        self.consumer_repo = tmp_path / "consumer"
        self.consumer_repo.mkdir(parents=True)
        init_repo(self.consumer_repo, branch="mane")
        make_commit(self.consumer_repo, "own.txt", "consumer's own commit", content="consumer content\n")
        git(["remote", "add", "base", str(self.base_repo)], self.consumer_repo)

    def test_dirty_worktree_refuses(self) -> None:
        (self.consumer_repo / "own.txt").write_text("dirty\n")

        with self.assertRaises(merge_base.MergeBaseError) as ctx:
            merge_base.merge_base_into_current_branch(self.consumer_repo)

        self.assertIn("dirty", str(ctx.exception))

    def test_happy_path_merges_cleanly_and_applies_prefix(self) -> None:
        new_sha = merge_base.merge_base_into_current_branch(
            self.consumer_repo, message_prefix="\U0001F4C4TEMPLATE | "
        )

        self.assertEqual(git(["rev-parse", "HEAD"], self.consumer_repo), new_sha)
        self.assertEqual(
            (self.consumer_repo / "shared.txt").read_text(encoding="utf-8"), "base content\n",
        )
        subject = git(["log", "-1", "--pretty=%s"], self.consumer_repo)
        self.assertTrue(subject.startswith("\U0001F4C4TEMPLATE | "), subject)
        # A genuine merge commit (two parents), not a fast-forward/squash.
        parents = git(["log", "-1", "--pretty=%P"], self.consumer_repo).split()
        self.assertEqual(len(parents), 2)

    def test_readme_conflict_is_auto_resolved_in_favor_of_base(self) -> None:
        (self.consumer_repo / "README.md").write_text("consumer's own readme\n")
        git(["add", "README.md"], self.consumer_repo)
        git(["commit", "-m", "consumer readme edit"], self.consumer_repo)

        merge_base.merge_base_into_current_branch(self.consumer_repo)

        self.assertEqual(
            (self.consumer_repo / "README.md").read_text(encoding="utf-8"), "from base\n",
        )
        self.assertEqual(git(["status", "--porcelain"], self.consumer_repo), "")

    def test_unresolvable_conflict_raises_and_leaves_merge_in_progress(self) -> None:
        make_commit(self.base_repo, "shared.txt", "base changes shared file again", content="base v2\n")
        (self.consumer_repo / "shared.txt").write_text("consumer conflicting edit\n")
        git(["add", "shared.txt"], self.consumer_repo)
        git(["commit", "-m", "consumer edits shared file"], self.consumer_repo)

        with self.assertRaises(merge_base.MergeBaseError) as ctx:
            merge_base.merge_base_into_current_branch(self.consumer_repo)

        self.assertIn("shared.txt", str(ctx.exception))
        # Left mid-merge for manual resolution, like a normal failed `git merge`.
        self.assertTrue((self.consumer_repo / ".git" / "MERGE_HEAD").exists())


if __name__ == "__main__":
    unittest.main()
