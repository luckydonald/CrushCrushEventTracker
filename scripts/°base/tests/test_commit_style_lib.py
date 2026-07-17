"""Tests for `°commit_style_lib`'s override lookup (`.py` preferred over
`.md`, `str.format()` placeholder substitution, and save-plan/record-memory
now honoring an override file too — see
scripts/°base/ai/hooks/°commit_style_lib/__init__.py).
"""
from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

import importlib

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
MEMORY_HOOK = _routing.MEMORY_HOOK
PLAN_HOOK = _routing.PLAN_HOOK
PROMPT_HOOK = _routing.PROMPT_HOOK
_encode_project_path = _routing._encode_project_path
init_repo = _routing.init_repo
last_subject = _routing.last_subject
run_hook = _routing.run_hook


class CommitStyleLibOverrideTests(unittest.TestCase):
    def test_md_override_substitutes_msg_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "prompt.md"
            template.parent.mkdir(parents=True)
            template.write_text("🤌 {msg}", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "🤌 ai: updated prompt")
        # end with
    # end def

    def test_md_override_with_stray_brace_falls_back_to_raw_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "prompt.md"
            template.parent.mkdir(parents=True)
            template.write_text("literal {unresolved} braces", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "literal {unresolved} braces")
        # end with
    # end def

    def test_py_override_preferred_over_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            templates_dir = repo / "ai" / "commit-templates"
            templates_dir.mkdir(parents=True)
            (templates_dir / "prompt.md").write_text("should not be used", encoding="utf-8")
            (templates_dir / "prompt.py").write_text(
                "def format_message(msg, **extra):\n"
                "    return f'PY: {msg}'\n",
                encoding="utf-8",
            )

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "PY: ai: updated prompt")
        # end with
    # end def

    def test_broken_py_override_falls_back_to_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            templates_dir = repo / "ai" / "commit-templates"
            templates_dir.mkdir(parents=True)
            (templates_dir / "prompt.md").write_text("🤌 {msg}", encoding="utf-8")
            (templates_dir / "prompt.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "🤌 ai: updated prompt")
        # end with
    # end def

    def test_save_plan_honors_override_and_keeps_dynamic_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "plan.md"
            template.parent.mkdir(parents=True)
            template.write_text("🗺️ {msg}", encoding="utf-8")

            run_hook(
                repo,
                PLAN_HOOK,
                {
                    "hook_event_name": "Stop",
                    "session_id": f"test-{uuid.uuid4()}",
                    "last_assistant_message": (
                        "<proposed_plan>\n# Styled Plan\nBody.\n</proposed_plan>"
                    ),
                },
                "codex",
            )

            self.assertEqual(last_subject(repo), "🗺️ ai: save plan 001_styled-plan")
        # end with
    # end def

    def test_record_memory_honors_override_and_keeps_dynamic_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            home = Path(tmp) / "home"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "memory.md"
            template.parent.mkdir(parents=True)
            template.write_text("🧠 {msg}", encoding="utf-8")
            encoded = _encode_project_path(repo.resolve())
            src_dir = home / ".claude" / "projects" / encoded / "memory"
            src_dir.mkdir(parents=True)
            (src_dir / "note.md").write_text("remember this\n", encoding="utf-8")

            run_hook(
                repo,
                MEMORY_HOOK,
                {"hook_event_name": "SessionStart"},
                extra_env={"HOME": str(home)},
            )

            self.assertEqual(last_subject(repo), "🧠 ai: record memory note")
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
