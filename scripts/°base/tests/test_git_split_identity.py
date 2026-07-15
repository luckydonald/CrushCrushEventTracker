from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo  # noqa: E402

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

identity = importlib.import_module("°split_lib.identity")


class IdentityResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        init_repo(self.repo)
    # end def

    def tearDown(self):
        self.temp_dir.cleanup()
    # end def

    def test_environment_identity_has_highest_precedence(self):
        git(["config", "base.split.name", "Configured Bot"], self.repo)
        git(["config", "base.split.email", "configured@example.com"], self.repo)

        result = identity.resolve_identity(
            self.repo,
            remaining=identity.CommitIdentity("Remaining Human", "remaining@example.com"),
            environ={
                "BASE_SPLIT_NAME": "Environment Bot",
                "BASE_SPLIT_EMAIL": "environment@example.com",
            },
        )

        self.assertEqual(result, identity.CommitIdentity("Environment Bot", "environment@example.com"))
    # end def

    def test_special_git_config_precedes_commit_and_normal_git_identity(self):
        git(["config", "base.split.name", "Configured Bot"], self.repo)
        git(["config", "base.split.email", "configured@example.com"], self.repo)

        result = identity.resolve_identity(
            self.repo,
            remaining=identity.CommitIdentity("Remaining Human", "remaining@example.com"),
            environ={},
        )

        self.assertEqual(result, identity.CommitIdentity("Configured Bot", "configured@example.com"))
    # end def

    def test_luckydonald_remaining_email_maps_to_lucky_lucy_default(self):
        result = identity.resolve_identity(
            self.repo,
            remaining=identity.CommitIdentity("Machine Identity", "machine@luckydonald.de"),
            environ={},
        )

        self.assertEqual(result, identity.DEFAULT_IDENTITY)
    # end def

    def test_foreign_remaining_email_is_preserved(self):
        result = identity.resolve_identity(
            self.repo,
            remaining=identity.CommitIdentity("Contributor", "contributor@example.com"),
            environ={},
        )

        self.assertEqual(result, identity.CommitIdentity("Contributor", "contributor@example.com"))
    # end def

    def test_luckydonald_normal_git_email_wins_domain_check_over_foreign_remaining(self):
        git(["config", "user.name", "Workstation User"], self.repo)
        git(["config", "user.email", "workstation@luckydonald.de"], self.repo)

        result = identity.resolve_identity(
            self.repo,
            remaining=identity.CommitIdentity("Contributor", "contributor@example.com"),
            environ={},
        )

        self.assertEqual(result, identity.DEFAULT_IDENTITY)
    # end def

    def test_normal_git_identity_is_the_last_fallback(self):
        git(["config", "user.name", "Repository User"], self.repo)
        git(["config", "user.email", "repository@example.com"], self.repo)

        result = identity.resolve_identity(self.repo, environ={})

        self.assertEqual(result, identity.CommitIdentity("Repository User", "repository@example.com"))
    # end def

    def test_remaining_identity_ignores_ai_side(self):
        author = identity.CommitIdentity("Contributor", "contributor@example.com")
        committer = identity.CommitIdentity("GitHub Copilot", "copilot@github.com")

        self.assertEqual(identity.remaining_identity(author, committer), author)
        self.assertTrue(identity.is_ai_identity(committer))
        self.assertTrue(identity.is_ai_identity(identity.CommitIdentity("Claude", "bot@example.com")))
        self.assertTrue(identity.is_ai_identity(identity.CommitIdentity("OpenAI", "codex@openai.com")))
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
