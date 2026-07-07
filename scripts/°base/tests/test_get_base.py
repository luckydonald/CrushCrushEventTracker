from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "git" / "get-base.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("get_base", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GetBaseTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script_module()

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        init_repo(self.repo)
        make_commit(self.repo, "README.md", "initial commit")

        # A fake "base" remote, cloned from this repo so history is shared
        # (mirrors the pattern used in test_git_split_history_master.py).
        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        self.base_repo = Path(base_tmp.name)
        git(["clone", str(self.repo), str(self.base_repo)], self.repo)
        git(["config", "user.email", "test@example.com"], self.base_repo)
        git(["config", "user.name", "Test"], self.base_repo)
        make_commit(self.base_repo, "scripts/°base/git/split.py", "pretend tool", content="# stand-in\n")
        git(["branch", "-m", "base"], self.base_repo)

    def _add_real_base_remote(self):
        git(["remote", "add", "base", str(self.base_repo)], self.repo)

    def test_ensure_base_remote_adds_when_missing(self):
        self.module.ensure_base_remote(self.repo, "someuser")
        url = git(["remote", "get-url", "base"], self.repo)
        self.assertEqual(url, self.module.remote_url("someuser"))

    def test_ensure_base_remote_leaves_existing_url_untouched(self):
        self._add_real_base_remote()
        self.module.ensure_base_remote(self.repo, "someuser")
        url = git(["remote", "get-url", "base"], self.repo)
        self.assertEqual(url, str(self.base_repo))

    def test_ensure_worktree_creates_then_refreshes(self):
        self._add_real_base_remote()
        self.module.fetch_base(self.repo)

        path = self.module.ensure_worktree(self.repo)
        self.assertTrue(path.exists())
        first_tip = git(["rev-parse", "HEAD"], path)

        make_commit(self.base_repo, "more.txt", "base advances", content="more\n")
        self.module.fetch_base(self.repo)
        path_again = self.module.ensure_worktree(self.repo)

        self.assertEqual(path, path_again)
        second_tip = git(["rev-parse", "HEAD"], path_again)
        self.assertNotEqual(first_tip, second_tip)

    def test_main_delegates_with_repo_root_and_forwarded_argv(self):
        self._add_real_base_remote()

        captured = {}

        def fake_execvp(executable, args):
            captured["executable"] = executable
            captured["args"] = args

        with mock.patch.object(self.module.os, "execvp", side_effect=fake_execvp), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo):
            self.module.main(["bootstrap-branch", "feature"])

        self.assertEqual(captured["executable"], sys.executable)
        args = captured["args"]
        self.assertEqual(args[0], sys.executable)
        self.assertIn("split.py", args[1])
        self.assertIn("--repo-root", args)
        self.assertEqual(args[args.index("--repo-root") + 1], str(self.repo))
        self.assertEqual(args[-2:], ["bootstrap-branch", "feature"])

        self.assertIsNotNone(git(["remote", "get-url", "base"], self.repo))

    def test_never_touches_current_checkout(self):
        self._add_real_base_remote()
        (self.repo / "untracked.txt").write_text("scratch")
        status_before = git(["status", "--porcelain"], self.repo)
        head_before = git(["rev-parse", "HEAD"], self.repo)

        with mock.patch.object(self.module.os, "execvp"), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo):
            self.module.main(["update-history-master", "--yes"])

        self.assertEqual(git(["status", "--porcelain"], self.repo), status_before)
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), head_before)


if __name__ == "__main__":
    unittest.main()
