"""Tests for °split_lib.gitattributes_safety -- protecting `.gitattributes`
from silently adopting a merge's incoming LFS filter rules for extensions
that already have non-LFS blobs committed in the target's own history.
"""

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

gitattributes_safety = importlib.import_module("°split_lib.gitattributes_safety")


class GitAttributesSafetyTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        init_repo(self.repo, branch="mane")


class ParseLfsPatternsTests(unittest.TestCase):
    def test_extracts_lfs_filtered_patterns(self):
        text = (
            "*  text=auto eol=lf\n"
            "*.png  filter=lfs diff=lfs merge=lfs -text\n"
            "*.jpg filter=lfs diff=lfs merge=lfs -text\n"
            "*.md text\n"
        )
        patterns = gitattributes_safety._parse_lfs_patterns(text)
        self.assertEqual(patterns, {"*.png", "*.jpg"})

    def test_empty_text_yields_no_patterns(self):
        self.assertEqual(gitattributes_safety._parse_lfs_patterns(""), set())


class ShouldProtectTests(GitAttributesSafetyTestBase):
    def _make_base_repo(self, gitattributes_content: str) -> str:
        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        base_repo = Path(base_tmp.name)
        init_repo(base_repo, branch="base")
        make_commit(base_repo, ".gitattributes", "base gitattributes", content=gitattributes_content)
        git(["remote", "add", "base", str(base_repo)], self.repo)
        git(["fetch", "base"], self.repo)
        return git(["rev-parse", "refs/remotes/base/base"], self.repo)

    def test_true_when_matching_binary_already_in_history(self):
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_sha = self._make_base_repo("*.png filter=lfs diff=lfs merge=lfs -text\n")

        self.assertTrue(gitattributes_safety.should_protect(base_sha, mane_tip, self.repo))

    def test_true_even_if_the_matching_file_was_later_deleted(self):
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        git(["rm", "logo.png"], self.repo)
        git(["commit", "-m", "remove logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_sha = self._make_base_repo("*.png filter=lfs diff=lfs merge=lfs -text\n")

        self.assertTrue(gitattributes_safety.should_protect(base_sha, mane_tip, self.repo))

    def test_false_when_no_matching_files_exist(self):
        make_commit(self.repo, "src/app.py", "add app code")
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_sha = self._make_base_repo("*.png filter=lfs diff=lfs merge=lfs -text\n")

        self.assertFalse(gitattributes_safety.should_protect(base_sha, mane_tip, self.repo))

    def test_false_when_onto_already_lfs_tracks_the_same_pattern(self):
        make_commit(self.repo, ".gitattributes", "own gitattributes", content="*.png filter=lfs diff=lfs merge=lfs -text\n")
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        # base introduces an unrelated NEW pattern (*.jpg) -- not risky for
        # the pre-existing *.png files, since *.png itself isn't "new".
        base_sha = self._make_base_repo(
            "*.png filter=lfs diff=lfs merge=lfs -text\n*.jpg filter=lfs diff=lfs merge=lfs -text\n"
        )

        self.assertFalse(gitattributes_safety.should_protect(base_sha, mane_tip, self.repo))

    def test_false_when_base_has_no_gitattributes_at_all(self):
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        base_repo = Path(base_tmp.name)
        init_repo(base_repo, branch="base")
        make_commit(base_repo, "README.md", "base readme")
        git(["remote", "add", "base", str(base_repo)], self.repo)
        git(["fetch", "base"], self.repo)
        base_sha = git(["rev-parse", "refs/remotes/base/base"], self.repo)

        self.assertFalse(gitattributes_safety.should_protect(base_sha, mane_tip, self.repo))


class RestoreOriginalTests(GitAttributesSafetyTestBase):
    def test_removes_gitattributes_when_onto_never_had_one(self):
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        base_repo = Path(base_tmp.name)
        init_repo(base_repo, branch="base")
        make_commit(base_repo, ".gitattributes", "base gitattributes", content="*.png filter=lfs diff=lfs merge=lfs -text\n")
        git(["remote", "add", "base", str(base_repo)], self.repo)
        git(["fetch", "base"], self.repo)
        base_sha = git(["rev-parse", "refs/remotes/base/base"], self.repo)

        # Simulate having just merged base's .gitattributes into the working
        # tree/index (as a real merge step would leave it).
        (self.repo / ".gitattributes").write_text("*.png filter=lfs diff=lfs merge=lfs -text\n")
        git(["add", ".gitattributes"], self.repo)

        applied = gitattributes_safety.restore_original(base_sha, mane_tip, self.repo)
        self.assertTrue(applied)
        self.assertFalse((self.repo / ".gitattributes").exists())
        staged = git(["diff", "--cached", "--name-only"], self.repo)
        self.assertNotIn(".gitattributes", staged.splitlines())

    def test_restores_ontos_own_content_when_it_had_one(self):
        make_commit(self.repo, ".gitattributes", "own gitattributes", content="*.md text\n")
        (self.repo / "logo.png").write_bytes(b"fake png bytes")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        base_repo = Path(base_tmp.name)
        init_repo(base_repo, branch="base")
        make_commit(base_repo, ".gitattributes", "base gitattributes", content="*.png filter=lfs diff=lfs merge=lfs -text\n")
        git(["remote", "add", "base", str(base_repo)], self.repo)
        git(["fetch", "base"], self.repo)
        base_sha = git(["rev-parse", "refs/remotes/base/base"], self.repo)

        (self.repo / ".gitattributes").write_text("*.png filter=lfs diff=lfs merge=lfs -text\n")
        git(["add", ".gitattributes"], self.repo)

        applied = gitattributes_safety.restore_original(base_sha, mane_tip, self.repo)
        self.assertTrue(applied)
        self.assertEqual((self.repo / ".gitattributes").read_text(), "*.md text\n")

    def test_no_op_when_not_risky(self):
        make_commit(self.repo, "src/app.py", "add app code")
        mane_tip = git(["rev-parse", "HEAD"], self.repo)

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        base_repo = Path(base_tmp.name)
        init_repo(base_repo, branch="base")
        make_commit(base_repo, ".gitattributes", "base gitattributes", content="*.png filter=lfs diff=lfs merge=lfs -text\n")
        git(["remote", "add", "base", str(base_repo)], self.repo)
        git(["fetch", "base"], self.repo)
        base_sha = git(["rev-parse", "refs/remotes/base/base"], self.repo)

        applied = gitattributes_safety.restore_original(base_sha, mane_tip, self.repo)
        self.assertFalse(applied)


if __name__ == "__main__":
    unittest.main()
