from __future__ import annotations

import importlib.util
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "°base" / "git" / "rebase_strip_claude_authorship.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("rebase_strip_claude_authorship", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RebaseStripClaudeAuthorshipTests(unittest.TestCase):
    def test_rebase_exec_uses_temporary_script_copy(self):
        module = load_script_module()
        rebase_commands: list[list[str]] = []
        exec_scripts: list[Path] = []

        def fake_run(args, **kwargs):
            args = list(args)
            if args[:2] == ["git", "fetch"]:
                return subprocess.CompletedProcess(args, 0)
            if args[:2] == ["git", "merge-base"]:
                return subprocess.CompletedProcess(args, 0, stdout="abc123\n")
            if args[:2] == ["git", "rebase"]:
                rebase_commands.append(args)
                exec_args = shlex.split(args[4])
                self.assertEqual(exec_args[0], sys.executable)
                self.assertEqual(exec_args[2], "--amend-step")
                exec_script = Path(exec_args[1])
                exec_scripts.append(exec_script)
                self.assertNotEqual(exec_script, SCRIPT)
                self.assertTrue(exec_script.exists())
                return subprocess.CompletedProcess(args, 0)
            raise AssertionError(f"unexpected command: {args}")

        with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
            self.assertEqual(module.main([]), 0)

        self.assertEqual(len(rebase_commands), 1)
        self.assertEqual(rebase_commands[0][:4], ["git", "rebase", "abc123", "--exec"])
        self.assertFalse(exec_scripts[0].exists())

    def test_rebase_failure_prints_recovery_without_traceback(self):
        module = load_script_module()
        exec_scripts: list[Path] = []

        def fake_run(args, **kwargs):
            args = list(args)
            if args[:2] == ["git", "fetch"]:
                return subprocess.CompletedProcess(args, 0)
            if args[:2] == ["git", "merge-base"]:
                return subprocess.CompletedProcess(args, 0, stdout="abc123\n")
            if args[:2] == ["git", "rebase"]:
                exec_scripts.append(Path(shlex.split(args[4])[1]))
                raise subprocess.CalledProcessError(1, args)
            raise AssertionError(f"unexpected command: {args}")

        with (
            mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            mock.patch("sys.stderr") as stderr,
        ):
            self.assertEqual(module.main([]), 1)

        output = "".join(call.args[0] for call in stderr.write.call_args_list if call.args)
        self.assertIn("git rebase --continue", output)
        self.assertIn("git rebase --abort", output)
        self.assertNotIn("Traceback", output)
        self.assertTrue(exec_scripts[0].exists())
        shutil.rmtree(exec_scripts[0].parent)


class AmendStepIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        self.run_git("init", "-b", "master")
        self.run_git("config", "user.name", "Repository User")
        self.run_git("config", "user.email", "repository@example.com")
    # end def

    def tearDown(self):
        self.temp_dir.cleanup()
    # end def

    def run_git(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
    ) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    # end def

    def make_commit(
        self,
        *,
        author_name: str,
        author_email: str,
        committer_name: str,
        committer_email: str,
        message: str,
    ) -> None:
        env = os.environ.copy()
        env.update(
            GIT_AUTHOR_NAME=author_name,
            GIT_AUTHOR_EMAIL=author_email,
            GIT_COMMITTER_NAME=committer_name,
            GIT_COMMITTER_EMAIL=committer_email,
        )
        self.run_git("commit", "--allow-empty", "--file", "-", env=env, input_text=message)
    # end def

    def run_amend_step(self, overrides: dict[str, str] | None = None) -> None:
        env = os.environ.copy()
        env.pop("BASE_SPLIT_NAME", None)
        env.pop("BASE_SPLIT_EMAIL", None)
        if overrides:
            env.update(overrides)
        # end if
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--amend-step"],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
    # end def

    def head_identity(self) -> tuple[str, str, str, str]:
        values = self.run_git("log", "-1", "--format=%an%x1f%ae%x1f%cn%x1f%ce")
        return tuple(values.split("\x1f"))
    # end def

    def test_claude_committer_with_luckydonald_author_uses_default_identity(self):
        self.make_commit(
            author_name="Workstation User",
            author_email="workstation@luckydonald.de",
            committer_name="Claude",
            committer_email="41898282+claude[bot]@users.noreply.github.com",
            message="AI-assisted change\n\nCo-authored-by: Claude <41898282+claude[bot]@users.noreply.github.com>\n",
        )

        self.run_amend_step()

        expected = ("✨❯ Lucky Lucy", "claude._.ai._.code@luckydonald.de")
        self.assertEqual(self.head_identity(), (*expected, *expected))
        self.assertNotIn("Co-authored-by:", self.run_git("log", "-1", "--format=%B"))
    # end def

    def test_codex_committer_with_foreign_author_preserves_human_identity(self):
        self.make_commit(
            author_name="Contributor",
            author_email="contributor@example.com",
            committer_name="Codex",
            committer_email="codex@openai.com",
            message="Contributor change\n",
        )

        self.run_amend_step()

        expected = ("Contributor", "contributor@example.com")
        self.assertEqual(self.head_identity(), (*expected, *expected))
    # end def

    def test_two_ai_identities_fall_back_to_normal_git_config(self):
        self.make_commit(
            author_name="GitHub Copilot",
            author_email="copilot@github.com",
            committer_name="Claude",
            committer_email="claude@anthropic.com",
            message="AI change\n",
        )

        self.run_amend_step()

        expected = ("Repository User", "repository@example.com")
        self.assertEqual(self.head_identity(), (*expected, *expected))
    # end def

    def test_environment_override_wins_over_remaining_identity_and_git_config(self):
        self.run_git("config", "base.split.name", "Configured Bot")
        self.run_git("config", "base.split.email", "configured@example.com")
        self.make_commit(
            author_name="Contributor",
            author_email="contributor@example.com",
            committer_name="Copilot",
            committer_email="copilot@github.com",
            message="AI-assisted change\n",
        )

        self.run_amend_step(
            {
                "BASE_SPLIT_NAME": "Environment Bot",
                "BASE_SPLIT_EMAIL": "environment@example.com",
            }
        )

        expected = ("Environment Bot", "environment@example.com")
        self.assertEqual(self.head_identity(), (*expected, *expected))
    # end def

    def test_trailer_only_cleanup_preserves_non_ai_author_and_committer(self):
        self.make_commit(
            author_name="Author",
            author_email="author@example.com",
            committer_name="Committer",
            committer_email="committer@example.com",
            message="Human change\n\nCo-authored-by: Assistant <assistant@example.com>\n",
        )

        self.run_amend_step()

        self.assertEqual(
            self.head_identity(),
            ("Author", "author@example.com", "Committer", "committer@example.com"),
        )
        self.assertNotIn("Co-authored-by:", self.run_git("log", "-1", "--format=%B"))
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
